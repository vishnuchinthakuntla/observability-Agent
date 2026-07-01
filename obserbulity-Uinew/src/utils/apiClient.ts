/**
 * Cookie-based auth token management and authenticated fetch wrapper.
 *
 * – setAuthToken / getAuthToken / removeAuthToken manage a cookie named "authToken".
 * – apiFetch wraps the native fetch() and automatically injects the
 *   Authorization header with the token from the cookie on every request.
 */

const COOKIE_NAME = 'authToken'

/**
 * Store the JWT in a cookie.
 * Uses SameSite=Strict and Secure (in production) for safety.
 * Default expiry: 7 days.
 */
export function setAuthToken(token: string, maxAgeDays = 7): void {
  const maxAge = maxAgeDays * 24 * 60 * 60 // seconds
  const secure = window.location.protocol === 'https:' ? '; Secure' : ''
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(token)}; path=/; max-age=${maxAge}; SameSite=Strict${secure}`
}

/**
 * Read the JWT from the cookie. Returns empty string if not found.
 */
export function getAuthToken(): string {
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${COOKIE_NAME}=`))
  return match ? decodeURIComponent(match.split('=')[1]) : ''
}

/**
 * Remove the auth cookie by setting max-age=0.
 */
export function removeAuthToken(): void {
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0; SameSite=Strict`
}

/**
 * A thin wrapper around the native `fetch` that automatically attaches the
 * `Authorization: Bearer <token>` header when a token cookie exists.
 *
 * Usage is identical to `fetch()` — just import `apiFetch` instead.
 */
export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const token = getAuthToken()

  const headers = new Headers(init?.headers)

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  return fetch(input, { ...init, headers })
}
