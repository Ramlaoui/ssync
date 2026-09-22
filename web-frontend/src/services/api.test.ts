import { expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { addHandler, setupMSW } from '../test/utils/mockApi';
import { api, apiConfig, clearApiKey, setApiKey } from './api';

setupMSW();

it('replaces the credentials used by subsequent requests when a key is removed', async () => {
  const received: Array<string | null> = [];
  const retainedClient = api;
  addHandler(http.get('*/api/hosts', ({ request }) => {
    received.push(request.headers.get('X-API-Key'));
    return HttpResponse.json([]);
  }));
  addHandler(http.delete('*/api/auth/session', () => HttpResponse.json({ success: true })));
  apiConfig.update(config => ({ ...config, baseURL: 'http://localhost' }));
  setApiKey('test-only-key');
  await retainedClient.get('/api/hosts');
  clearApiKey();
  await retainedClient.get('/api/hosts');
  expect(received).toEqual(['test-only-key', null]);
});
