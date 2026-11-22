"""Export the existing Vite build as a self-contained, hypothetical UI review artifact.

From the repository root, after `cd frontend && npm run build`:
    python frontend/tests/export_preview.py

Default output: docs/ui-preview/preview.html. Open that file directly in a browser.
Only local build assets and explicit ui_fixtures payloads are embedded. The preview clock is
frozen and declared; no live API, provider, account, authentication, or trading behavior is tested.
This exporter does not perform browser verification or generate screenshots.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ui_fixtures import WARNING, build_fixtures

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLOCK = datetime(2026, 11, 22, 12, tzinfo=UTC)
API_PATHS = (
    "/api/health",
    "/api/engines",
    "/api/candidates",
    "/api/budget",
    "/api/queue",
    "/api/research/summary",
    "/api/research/experiments",
    "/api/research/paper/transitions",
)
CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; font-src data:; connect-src 'none'; worker-src 'none'; "
    "object-src 'none'; frame-src 'none'; media-src 'none'; manifest-src 'none'; "
    "base-uri 'none'; form-action 'none'"
)

BOOTSTRAP = r"""
(() => {
  'use strict';
  const payload = JSON.parse(document.getElementById('offline-preview-data').textContent);
  const clock = payload.clock;
  const NativeDate = window.Date;
  const PreviewDate = new Proxy(NativeDate, {
    construct(target, args, newTarget) {
      return Reflect.construct(target, args.length ? args : [clock], newTarget);
    },
    apply() { return new NativeDate(clock).toString(); },
    get(target, name, receiver) {
      return name === 'now' ? () => clock : Reflect.get(target, name, receiver);
    },
  });
  Object.defineProperty(window, 'Date', { value: PreviewDate, writable: false });
  const denied = () => {
    throw new TypeError('Network requests are disabled in this offline preview.');
  };
  Object.defineProperty(window, 'fetch', {
    configurable: false, writable: false,
    value: async (input, init = {}) => {
      const signal = init.signal || (input instanceof Request ? input.signal : undefined);
      if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError');
      const method = String(init.method || (input instanceof Request ? input.method : 'GET'))
        .toUpperCase();
      const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (method !== 'GET' || typeof raw !== 'string' || !raw.startsWith('/api/')) return denied();
      const url = new URL(raw, 'https://offline-preview.invalid');
      if (url.origin !== 'https://offline-preview.invalid' ||
          !Object.hasOwn(payload.routes, url.pathname)) return denied();
      return new Response(JSON.stringify(payload.routes[url.pathname]), {
        status: 200, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
      });
    },
  });
  const transports = ['XMLHttpRequest', 'WebSocket', 'EventSource', 'Worker',
    'SharedWorker', 'RTCPeerConnection'];
  for (const name of transports) {
    Object.defineProperty(window, name, { value: denied, writable: false, configurable: false });
  }
  Object.defineProperty(navigator, 'sendBeacon', { value: () => false, writable: false });
  Object.defineProperty(window, 'open', { value: () => null, writable: false });
  document.addEventListener('submit', event => event.preventDefault(), true);
  const disableLinks = () => {
    document.querySelectorAll('a[href]').forEach(anchor => {
      if (anchor.getAttribute('href').startsWith('#')) return;
      anchor.removeAttribute('href');
      anchor.removeAttribute('target');
      anchor.setAttribute('aria-disabled', 'true');
      anchor.title = 'External links are disabled in the offline preview.';
    });
  };
  for (const name of ['click', 'auxclick']) document.addEventListener(name, event => {
    const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null;
    if (anchor && !anchor.getAttribute('href').startsWith('#')) event.preventDefault();
  }, true);
  const prepare = () => {
    disableLinks();
    new MutationObserver(disableLinks).observe(document.body, {
      subtree: true, childList: true, attributes: true, attributeFilter: ['href'],
    });
    const banner = document.getElementById('offline-preview-notice');
    const sizeBanner = () => document.documentElement.style.setProperty(
      '--preview-notice-height', banner.getBoundingClientRect().height + 'px');
    sizeBanner();
    new ResizeObserver(sizeBanner).observe(banner);
  };
  document.addEventListener('DOMContentLoaded', prepare, { once: true });
})();
"""

PREVIEW_CSS = """
:root { --preview-notice-height: 100px; }
body { padding-top: var(--preview-notice-height); }
#offline-preview-notice {
  position: fixed; inset: 0 0 auto; z-index: 2147483647; padding: 12px 20px;
  color: #4b3b17; background: #fff4d4; border-bottom: 1px solid #e4ca83;
  font: 13px/1.45 system-ui, sans-serif; box-sizing: border-box;
}
#offline-preview-notice strong { display: block; font-size: 12px; letter-spacing: .08em; }
#offline-preview-notice small { display: block; margin-top: 3px; font-size: 11px; }
#root .sidebar {
  top: var(--preview-notice-height); height: calc(100dvh - var(--preview-notice-height));
}
#root .topbar { top: var(--preview-notice-height); }
"""


def safe_json(value: object) -> str:
    """JSON inside a script element cannot contain an HTML closing tag or line separator."""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def escape_end_tag(value: str, tag: str) -> str:
    return re.sub("</" + tag, lambda match: match[0].replace("/", "\\/"), value, flags=re.I)


class Tag(HTMLParser):
    def __init__(self, value: str) -> None:
        super().__init__(convert_charrefs=True)
        self.attrs: dict[str, str | None] = {}
        self.feed(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.attrs = dict(attrs)


class Inliner:
    """Consume a fully bundled Vite build; fail rather than silently leave remote assets."""

    def __init__(self, dist: Path) -> None:
        self.dist = dist.resolve()
        self.assets: dict[str, str] = {}

    def read(self, reference: str, parent: Path | None = None) -> tuple[Path, bytes]:
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.netloc:
            raise ValueError(f"External build asset is not supported: {reference}")
        path = unquote(parsed.path)
        source = (
            (self.dist / path.lstrip("/")) if path.startswith("/") else (parent or self.dist) / path
        ).resolve()
        if not source.is_relative_to(self.dist) or not source.is_file():
            raise ValueError(f"Missing or non-build asset: {reference}")
        data = source.read_bytes()
        self.assets[source.relative_to(self.dist).as_posix()] = hashlib.sha256(data).hexdigest()
        return source, data

    def data_uri(self, reference: str, parent: Path | None = None) -> str:
        source, data = self.read(reference, parent)
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        return f"data:{mime};base64," + base64.b64encode(data).decode()

    def stylesheet(self, reference: str) -> str:
        source, data = self.read(reference)
        css = data.decode()
        if re.search(r"@import\b", css, re.I):
            raise ValueError("Bundle CSS @import dependencies before exporting the offline preview")

        def replace_url(match: re.Match[str]) -> str:
            value = match[1].strip().strip("\"'")
            if value.startswith(("data:", "#")):
                return match[0]
            return 'url("' + self.data_uri(value, source.parent) + '")'

        css = re.sub(r"url\(([^)]*)\)", replace_url, css, flags=re.I)
        return "<style>" + escape_end_tag(css, "style") + "</style>"

    def script(self, match: re.Match[str]) -> str:
        opening = match[0].split(">", 1)[0] + ">"
        attrs = Tag(opening).attrs
        reference = attrs.get("src")
        if not reference:
            raise ValueError("Expected an external bundled entry script in dist/index.html")
        source, data = self.read(reference)
        code = data.decode()
        if re.search(r"\bimport\s*(?:\(|[\"'{*])", code):
            raise ValueError(
                "JavaScript imports remain; use a single bundled entry for this preview"
            )
        code = re.sub(
            r"""(["'])(/assets/[^"']+)\1""",
            lambda asset: json.dumps(self.data_uri(asset[2], source.parent)),
            code,
        )
        kind = ' type="module"' if attrs.get("type") == "module" else ""
        return f"<script{kind}>" + escape_end_tag(code, "script") + "</script>"

    def link(self, match: re.Match[str]) -> str:
        attrs = Tag(match[0]).attrs
        if attrs.get("rel") == "stylesheet" and attrs.get("href"):
            return self.stylesheet(str(attrs["href"]))
        if attrs.get("rel") == "icon" and attrs.get("href"):
            reference = str(attrs["href"])
            uri = reference if reference.startswith("data:") else self.data_uri(reference)
            return '<link rel="icon" href="' + html.escape(uri, quote=True) + '">'
        raise ValueError("Unsupported build link; bundle it before export: " + match[0])


def export_preview(dist: Path, destination: Path, clock: datetime) -> dict[str, object]:
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("Preview clock must include a timezone")
    clock = clock.astimezone(UTC)
    inliner = Inliner(dist)
    _, index = inliner.read("index.html")
    document = index.decode()
    if not re.search(r"<head\b", document, re.I) or not re.search(r"<body\b", document, re.I):
        raise ValueError("Expected a complete HTML document in dist/index.html")
    blocks: dict[str, str] = {}

    def remember(value: str) -> str:
        marker = f"<!-- OFFLINE_PREVIEW_ASSET_{len(blocks)} -->"
        blocks[marker] = value
        return marker

    document, script_count = re.subn(
        r"<script\b[^>]*>.*?</script\s*>",
        lambda match: remember(inliner.script(match)),
        document,
        flags=re.I | re.S,
    )
    if not script_count:
        raise ValueError(
            "dist/index.html contains no bundled application script; run npm run build"
        )
    document = re.sub(
        r"<link\b[^>]*>", lambda match: remember(inliner.link(match)), document, flags=re.I
    )
    if re.search(r"<(?:img|source|iframe)\b", document, re.I):
        raise ValueError("Additional HTML media require explicit inlining before preview export")
    fixtures = build_fixtures(clock)
    paths = [*API_PATHS, *("/api/snapshots/" + key for key in sorted(fixtures.snapshots))]
    routes = {path: fixtures.payload(path) for path in paths}
    data = {"clock": int(clock.timestamp() * 1000), "routes": routes}
    controls = (
        '<meta charset="UTF-8">\n'
        '<meta http-equiv="Content-Security-Policy" content="'
        + html.escape(CSP, quote=True)
        + '">\n'
        '<link rel="icon" href="data:,">\n'
        '<script id="offline-preview-data" type="application/json">'
        + safe_json(data)
        + "</script>\n"
        "<script>" + escape_end_tag(BOOTSTRAP, "script") + "</script>\n"
    )
    document = re.sub(
        r"<head\b[^>]*>", lambda match: match[0] + "\n" + controls, document, count=1, flags=re.I
    )
    document = re.sub(
        r"</head\s*>", "<style>" + PREVIEW_CSS + "</style>\n</head>", document, count=1, flags=re.I
    )
    banner = (
        '<aside id="offline-preview-notice" role="note">'
        "<strong>OFFLINE UI PREVIEW · HYPOTHETICAL</strong><span>"
        + html.escape(WARNING)
        + "</span>"
        "<small>Frozen preview clock: " + html.escape(clock.isoformat()) + ". "
        "Embedded fixtures only. Network and external links disabled. "
        "No browser verification, live integration or strategy-performance claim.</small></aside>"
    )
    document = re.sub(
        r"<body\b[^>]*>", lambda match: match[0] + banner, document, count=1, flags=re.I
    )
    document = re.sub(
        r"<title>.*?</title>",
        "<title>Hypothetical offline UI preview · Gold &amp; Bitcoin</title>",
        document,
        count=1,
        flags=re.I | re.S,
    )
    manifest = {"fixture_clock_utc": clock.isoformat(), "build_asset_sha256": inliner.assets}
    document += "\n<!-- Preview source identity: " + safe_json(manifest) + " -->\n"
    for marker, block in blocks.items():
        document = document.replace(marker, block)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return {
        "output": str(destination),
        "bytes": destination.stat().st_size,
        "fixture_routes": len(routes),
        **manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "frontend" / "dist")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs" / "ui-preview" / "preview.html"
    )
    parser.add_argument("--fixture-time", default=DEFAULT_CLOCK.isoformat())
    args = parser.parse_args()
    try:
        result = export_preview(
            args.dist, args.output, datetime.fromisoformat(args.fixture_time.replace("Z", "+00:00"))
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
