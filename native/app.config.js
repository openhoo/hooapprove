// HTTP is enabled only for an explicit loopback demo build; production remains HTTPS-only.
module.exports = ({ config }) => {
  const target = process.env.EXPO_PUBLIC_HOOAPPROVE_URL || 'https://approve.openhoo.dev';
  const url = new URL(target);
  const loopback = url.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(url.hostname);
  if ((url.protocol !== 'https:' && !loopback) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('HooApprove requires HTTPS or a loopback demo');
  return {
    ...config,
    plugins: [...config.plugins.filter(p => (typeof p === 'string' ? p : p[0]) !== 'expo-build-properties'), ['expo-build-properties', { android: { usesCleartextTraffic: loopback } }]],
  };
};
