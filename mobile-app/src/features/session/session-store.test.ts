import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import { useSessionStore } from '@/src/features/session/session-store';

const resetStore = () => {
  useSessionStore.setState({
    hydrated: false,
    isSaving: false,
    baseUrl: '',
    apiKey: '',
    lastError: null,
    connectionSource: 'idle',
    websocketHealthy: false,
    lastSyncAt: null,
  });
};

describe('session store', () => {
  beforeEach(() => {
    resetStore();
    jest.clearAllMocks();
  });

  it('hydrates persisted base url and api key', async () => {
    (AsyncStorage.getItem as jest.Mock).mockResolvedValueOnce(
      JSON.stringify({ baseUrl: 'https://localhost:8042/' }),
    );
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('top-secret');

    await useSessionStore.getState().initialize();

    expect(useSessionStore.getState().hydrated).toBe(true);
    expect(useSessionStore.getState().baseUrl).toBe('https://localhost:8042');
    expect(useSessionStore.getState().apiKey).toBe('top-secret');
  });

  it('persists updates and normalizes the base url', async () => {
    await useSessionStore.getState().saveSession({
      baseUrl: 'https://remote.example.com///',
      apiKey: 'abc123',
    });

    expect(AsyncStorage.setItem).toHaveBeenCalledWith(
      'ssync.session',
      JSON.stringify({ baseUrl: 'https://remote.example.com' }),
    );
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('ssync.api_key', 'abc123');
    expect(useSessionStore.getState().baseUrl).toBe('https://remote.example.com');
  });
});
