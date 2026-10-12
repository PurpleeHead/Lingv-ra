const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const initData = (window as Window & { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp?.initData || ''
  const headers = new Headers(init?.headers)
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (initData) headers.set('X-Telegram-Init-Data', initData)
  const response = await fetch(`${API}${path}`, { ...init, headers })
  if (!response.ok) {
    let message = `API error ${response.status}`
    try {
      const body = await response.json() as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
    } catch { /* Preserve the HTTP status when an error response has no JSON body. */ }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
