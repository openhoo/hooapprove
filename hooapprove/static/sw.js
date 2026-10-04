self.addEventListener('push', event => {
  const message = event.data?.json() || {};
  event.waitUntil(self.registration.showNotification(message.title || 'HooApprove', {
    body: message.body || 'Eine Aktion wartet auf deine Entscheidung.',
    icon: '/static/icon.svg', tag: 'hooapprove-pending',
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.matchAll({type: 'window'}).then(windows => {
    const existing = windows.find(window => new URL(window.url).origin === self.location.origin);
    return existing ? existing.focus() : clients.openWindow('/');
  }));
});
// No caching of authenticated responses or approval state.
