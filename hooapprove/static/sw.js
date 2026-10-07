self.addEventListener('push', event => {
  // Older installations may still have this worker. Lock-screen text is always generic,
  // regardless of the push payload; private action details belong in the native inbox.
  event.waitUntil(self.registration.showNotification('HooApprove', {
    body: 'Eine Aktion wartet auf deine Entscheidung.',
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
