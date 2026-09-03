const LOCAL_CORE_API_URL = 'http://127.0.0.1:8000';

interface CoreApiBaseUrlOptions {
  allowLocalDefault?: boolean;
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase();
  if (normalized === 'localhost' || normalized === '[::1]' || normalized === '::1') {
    return true;
  }
  const octets = normalized.split('.');
  return (
    octets.length === 4 &&
    octets.every((octet) => /^\d{1,3}$/.test(octet) && Number(octet) <= 255) &&
    Number(octets[0]) === 127
  );
}

/** Resolve the server-only Core endpoint and reject insecure Production transport. */
export function resolveCoreApiBaseUrl({
  allowLocalDefault = false,
}: CoreApiBaseUrlOptions = {}): URL | null {
  const raw = process.env.CORE_API_INTERNAL_URL ?? (allowLocalDefault ? LOCAL_CORE_API_URL : null);
  if (!raw) return null;

  try {
    const url = new URL(raw);
    if (
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      (url.protocol !== 'http:' && url.protocol !== 'https:') ||
      (process.env.NODE_ENV === 'production' &&
        url.protocol === 'http:' &&
        !isLoopbackHostname(url.hostname))
    ) {
      return null;
    }
    url.pathname = `${url.pathname.replace(/\/+$/, '')}/`;
    return url;
  } catch {
    return null;
  }
}
