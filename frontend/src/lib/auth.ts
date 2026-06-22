// Token storage. Per the security model, the access token lives in memory ONLY —
// never localStorage. The refresh token is an HttpOnly cookie managed by the server.

let accessToken: string | null = null;
let tokenExpiry = 0;

export function setAccessToken(token: string, expiresInSeconds: number): void {
  accessToken = token;
  tokenExpiry = Date.now() + expiresInSeconds * 1000;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken(): void {
  accessToken = null;
  tokenExpiry = 0;
}

/** True if the token is missing or within 30s of expiry. */
export function isTokenExpiring(): boolean {
  if (!accessToken) return true;
  return Date.now() > tokenExpiry - 30_000;
}
