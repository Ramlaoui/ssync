export function normalizeBaseUrl(value: string) {
  return value.trim().replace(/\/+$/, '');
}

export function buildAbsoluteUrl(baseUrl: string, path: string) {
  const normalized = normalizeBaseUrl(baseUrl);
  return `${normalized}${path.startsWith('/') ? path : `/${path}`}`;
}

export function toWebSocketUrl(baseUrl: string, path: string) {
  const absoluteUrl = buildAbsoluteUrl(baseUrl, path);
  return absoluteUrl.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
}
