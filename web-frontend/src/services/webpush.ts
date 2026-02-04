import { api } from './api';

function urlBase64ToUint8Array(base64String: string) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i += 1) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export async function isWebPushSupported(): Promise<boolean> {
  return (
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

export async function getWebPushSubscription(): Promise<PushSubscription | null> {
  if (!(await isWebPushSupported())) return null;
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
}

export async function enableWebPush(): Promise<void> {
  if (!(await isWebPushSupported())) {
    throw new Error('Web Push is not supported in this browser');
  }

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    throw new Error('Notification permission denied');
  }

  const vapidResponse = await api.get('/api/notifications/webpush/vapid');
  const publicKey = vapidResponse.data?.public_key;
  if (!publicKey) {
    throw new Error('Web Push not configured on server');
  }

  const registration = await navigator.serviceWorker.register('/sw.js');
  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ||
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey)
    }));

  await api.post('/api/notifications/webpush/subscribe', {
    endpoint: subscription.endpoint,
    keys: subscription.toJSON().keys || {},
    user_agent: navigator.userAgent
  });
}

export async function disableWebPush(): Promise<void> {
  if (!(await isWebPushSupported())) return;
  const subscription = await getWebPushSubscription();
  if (!subscription) return;

  await api.post('/api/notifications/webpush/unsubscribe', {
    endpoint: subscription.endpoint
  });
  await subscription.unsubscribe();
}
