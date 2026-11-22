# Operator dashboard implementation

## Purpose and scope

Improve the existing React/TypeScript operator interface for Gold and Bitcoin.
Keep the FastAPI contracts, authentication, strategies, provider calls and default-off
external flags unchanged. This is a read-only presentation change.

## Implementation plan

1. Replace the monolithic overview with responsive navigation for overview, liquidity
   sweeps, AI reviews, research and system health.
2. Read existing health, engines, candidates and immutable snapshot endpoints. Scope
   research detail and paper transitions to the selected experiment.
3. Visualize recorded entry/invalidation/target levels with their observation time.
   There is no live ticker/candle API: never draw invented price history or label a
   recorded candidate entry as a current quote.
4. Expose actual trigger/evidence, independent provider attempts/rationales, explicit
   lifecycle, source timestamps and UTC budget records. Keep historical confirmation
   distinct from current lifecycle and expiry.
5. Validate responsive layouts, keyboard access, request failures, empty data,
   asset/snapshot races and historical-confirmation presentation with isolated,
   explicitly hypothetical browser fixtures. Run frontend typecheck/build and the
   existing required project gates.

## Data and interaction boundaries

- Navigation, asset/horizon selection, search, refresh and research paging are real.
- Requests are GET only. There are no execution controls, secret inputs, provider
  toggles or actions that open protected holdout data.
- An unavailable read is not zero. Retained data after a failed refresh is marked
  stale; health reachability does not establish market-data freshness.
- Snapshot numbers belong to the selected immutable snapshot. In-flight requests
  are cancelled when selection changes and payload identity is checked.
- Technical swing/session levels are not CoinGlass liquidation clusters. A sweep
  view filters recorded candidate trigger text; the API does not expose a complete
  breach/reclaim event stream or exact swept-boundary fields.
- Preview/test fixtures are never bundled into the production app or written to
  production/research databases. The standalone preview and any screenshots made
  from the fixtures explicitly say hypothetical.

## Verification

The change is based on main commit `399c70bbdd012e539a06d3e423fd30d8de498ab7`.

| Check | Result |
| --- | --- |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed |
| `python -m pytest -q` | 272 passed; two third-party deprecation warnings |
| `npm run typecheck` | Passed |
| `npm test` | 32 passed; no new dependencies |
| `npm run build` | Passed; 37 modules transformed |
| `python -m compileall -q src` | Passed |
| Ruff checks on `frontend/tests` | Passed; explicitly checked because the root Ruff configuration excludes the frontend |
| `git diff --check` | Passed |
| Browser smoke / desktop and mobile visual inspection | Blocked by the execution environment; not claimed as passed |

The Node presentation tests run the actual formatting/identity helpers. They cover
valid Gold and Bitcoin assessment packets; all nine missing/mismatching identities;
terminal lifecycle and exact expiry boundaries; missing/invalid prices and timestamps;
actual zero and valid decimal strings; IST/UTC conversion; and sweep filtering.
They caught a whitespace-only numeric input being interpreted as zero, which was fixed.

The isolated Playwright runner additionally covers asset/snapshot races, missing
snapshots, historical confirmation versus terminal lifecycle, empty/error/authentication
responses, GET-only calls and document overflow at 1440px and 390px. **Those browser
assertions have not executed successfully in this environment.** Local Chromium
aborted because its singleton socket was denied. Automatic approval review rejected
the attempted escalation because sandbox approval and permission requests are disabled.
The provided cloud browser could not reach the loopback preview server; observation
of its internal error page was also blocked. No browser security settings were weakened.
No screenshots or visual-signoff claims are included.

Frontend checks reused the existing repository dependency installation. An offline
`npm ci` attempt failed because a cached package was missing; no dependency or lockfile
changes were made. CI uses `npm ci` and now runs the Node presentation tests on Windows.
Local passing gates do not establish that the new GitHub Actions run has passed.

The destination Windows Server, live accounts, market-feed correctness and real
notification delivery remain unverified. No backend/provider configuration or
`.env.example` change is needed for this presentation-only work.

## Offline preview

`docs/ui-preview/preview.html` is a self-contained copy of the built UI with a
test-only GET-response adapter and visible hypothetical-data labels. Download it
and open it directly in a browser. It is for interface review; it does not connect
to FastAPI, Delta, CoinGlass, GPT or Claude. Browser Content Security Policy blocks
network connections. It is separate from `frontend/dist` and production serving.

The exported artifact was checked statically for remote resource attributes and CSS
URLs. Both inline JavaScript blocks passed `node --check`. A Node VM check verified
the 14 embedded GET routes, rejection of unknown/non-GET/external requests, blocked
alternate transports, safe embedded JSON and the declared frozen preview clock.
These checks establish packaging and adapter behavior, not rendered layout or
browser interaction. The preview clock is fixed at `2026-11-22T12:00:00Z` and clearly
labelled; it must never be read as the current market time.

Generate it from the repository root **after** building the current frontend:

```powershell
python frontend/tests/export_preview.py
```

The same fixtures can be served on loopback for a manual test session:

```powershell
python frontend/tests/ui_fixtures.py --port 8000
```

Use a test session with no real backend on port 8000. Start Vite in a second terminal.
The fixture server is explicitly invoked; the production application never falls
back to it. The README contains the optional browser-runner commands.
