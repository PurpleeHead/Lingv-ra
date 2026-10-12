const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const initData = (window as Window & { Telegram?: { WebApp?: { initData?: string } } }).Telegram?.WebApp?.initData || ''
  const headers = new Headers(init?.headers)
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (initData) headers.set('X-Telegram-Init-Data', initData)

  const url = `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
  let response: Response
  try {
    response = await fetch(url, { ...init, headers })
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error('Network error: cannot reach the Lingvéra API. Check that the backend is running and the Vite API proxy is configured correctly.')
    }
    throw error
  }

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
