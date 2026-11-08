async function call<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    // a hung report send falls back to the offline queue instead of spinning forever
    signal: path === '/api/report' ? AbortSignal.timeout(8000) : undefined,
  })
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`)
  return r.json()
}
export const api = {
  get: <T = any>(p: string) => call<T>('GET', p),
  post: <T = any>(p: string, b?: unknown) => call<T>('POST', p, b ?? {}),
}
