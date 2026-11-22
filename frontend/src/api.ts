/** Same-origin, read-only requests. Browser-managed authentication stays outside React. */
export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController()
  const cancel = () => controller.abort()
  if (signal?.aborted) controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  const timeout = window.setTimeout(() => controller.abort(), 12_000)
  try {
    const response = await fetch(path, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Operator sign-in required. Authenticate with the server, then refresh.')
      }
      let detail = ''
      try {
        const body: unknown = await response.json()
        if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
          detail = body.detail
        }
      } catch { /* A proxy error may not contain JSON. Preserve its HTTP status. */ }
      throw new Error(detail || 'Server unavailable (HTTP ' + response.status + '). Retry when the service is ready.')
    }
    try {
      return await response.json() as T
    } catch {
      throw new Error('The server returned an unreadable response. No data has been inferred.')
    }
  } catch (error) {
    if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError')
    if (controller.signal.aborted) throw new Error('The server did not respond within 12 seconds. Please retry.')
    if (error instanceof TypeError) throw new Error('Cannot reach the server. Check the connection and retry.')
    throw error
  } finally {
    window.clearTimeout(timeout)
    signal?.removeEventListener('abort', cancel)
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unable to load this record.'
}
