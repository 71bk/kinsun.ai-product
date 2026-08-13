function normalizeOrigin(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.username || url.password || (url.protocol !== 'http:' && url.protocol !== 'https:')) {
      return null;
    }
    return url.origin;
  } catch {
    return null;
  }
}

/**
 * Cookie-authenticated state changes must originate from this frontend.
 * Production fails closed until FRONTEND_ORIGIN is explicitly configured.
 */
export function isTrustedRequestOrigin(request: Request): boolean {
  const suppliedOrigin = request.headers.get('origin');
  if (!suppliedOrigin) return false;

  const configuredOrigin = process.env.FRONTEND_ORIGIN;
  if (process.env.NODE_ENV === 'production' && !configuredOrigin) return false;

  const expectedOrigin = normalizeOrigin(configuredOrigin ?? new URL(request.url).origin);
  return expectedOrigin !== null && normalizeOrigin(suppliedOrigin) === expectedOrigin;
}
