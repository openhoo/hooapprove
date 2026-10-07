export function serverOrigin(value: string): string {
  const url = new URL(value);
  const loopback = url.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !loopback) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('HooApprove requires an HTTPS origin or a loopback demo origin, without credentials, path, query or fragment');
  }
  return url.origin;
}
