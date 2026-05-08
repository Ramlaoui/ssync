self.addEventListener('push', event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : '' };
  }

  const title = data.title || 'ssync';
  const tag = data.notification_id || (data.job_id ? `job-${data.hostname || 'host'}-${data.job_id}-${data.state || 'state'}` : undefined);
  const options = {
    body: data.body || 'New notification',
    data,
    icon: '/favicon.ico',
    badge: '/favicon.ico',
    tag,
    renotify: Boolean(tag),
    requireInteraction: data.state === 'F' || data.state === 'TO'
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const data = event.notification.data || {};
  const urlToOpen = data.job_id && data.hostname
    ? `/#/jobs/${encodeURIComponent(data.job_id)}/${encodeURIComponent(data.hostname)}`
    : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if ('focus' in client) {
          const clientUrl = new URL(client.url);
          if (clientUrl.pathname + clientUrl.hash === urlToOpen || urlToOpen !== '/') {
            return client.focus().then(focusedClient => {
              if ('navigate' in focusedClient) {
                return focusedClient.navigate(urlToOpen);
              }
              return focusedClient;
            });
          }
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
      return undefined;
    })
  );
});
