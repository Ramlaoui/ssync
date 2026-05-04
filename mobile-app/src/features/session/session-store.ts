import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

import { normalizeBaseUrl } from '@/src/lib/network';

const SESSION_KEY = 'ssync.session';
const API_KEY_KEY = 'ssync.api_key';

type ConnectionSource = 'idle' | 'polling' | 'websocket';

type SessionInput = {
  baseUrl: string;
  apiKey: string;
};

type SessionState = {
  hydrated: boolean;
  isSaving: boolean;
  baseUrl: string;
  apiKey: string;
  lastError: string | null;
  connectionSource: ConnectionSource;
  websocketHealthy: boolean;
  lastSyncAt: string | null;
  initialize: () => Promise<void>;
  saveSession: (input: SessionInput) => Promise<void>;
  clearSession: () => Promise<void>;
  markRestSuccess: () => void;
  markRestFailure: (message: string) => void;
  markWebsocketHealthy: () => void;
  markPollingFallback: (message?: string) => void;
  clearError: () => void;
};

export const useSessionStore = create<SessionState>((set) => ({
  hydrated: false,
  isSaving: false,
  baseUrl: '',
  apiKey: '',
  lastError: null,
  connectionSource: 'idle',
  websocketHealthy: false,
  lastSyncAt: null,
  initialize: async () => {
    const [rawSession, apiKey] = await Promise.all([
      AsyncStorage.getItem(SESSION_KEY),
      SecureStore.getItemAsync(API_KEY_KEY),
    ]);

    const session = rawSession ? (JSON.parse(rawSession) as { baseUrl?: string }) : {};

    set({
      hydrated: true,
      baseUrl: session.baseUrl ? normalizeBaseUrl(session.baseUrl) : '',
      apiKey: apiKey ?? '',
    });
  },
  saveSession: async ({ baseUrl, apiKey }) => {
    const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
    set({ isSaving: true, lastError: null });
    await AsyncStorage.setItem(SESSION_KEY, JSON.stringify({ baseUrl: normalizedBaseUrl }));
    if (apiKey.trim()) {
      await SecureStore.setItemAsync(API_KEY_KEY, apiKey.trim());
    } else {
      await SecureStore.deleteItemAsync(API_KEY_KEY);
    }
    set({
      isSaving: false,
      baseUrl: normalizedBaseUrl,
      apiKey: apiKey.trim(),
      lastError: null,
    });
  },
  clearSession: async () => {
    await Promise.all([
      AsyncStorage.removeItem(SESSION_KEY),
      SecureStore.deleteItemAsync(API_KEY_KEY),
    ]);
    set({
      baseUrl: '',
      apiKey: '',
      lastError: null,
      connectionSource: 'idle',
      websocketHealthy: false,
      lastSyncAt: null,
    });
  },
  markRestSuccess: () =>
    set((state) => ({
      lastError: null,
      lastSyncAt: new Date().toISOString(),
      connectionSource: state.websocketHealthy ? 'websocket' : 'polling',
    })),
  markRestFailure: (message) =>
    set({
      lastError: message,
      connectionSource: 'polling',
      websocketHealthy: false,
    }),
  markWebsocketHealthy: () =>
    set({
      websocketHealthy: true,
      connectionSource: 'websocket',
      lastError: null,
      lastSyncAt: new Date().toISOString(),
    }),
  markPollingFallback: (message) =>
    set((state) => ({
      websocketHealthy: false,
      connectionSource: state.baseUrl ? 'polling' : 'idle',
      lastError: message ?? state.lastError,
    })),
  clearError: () => set({ lastError: null }),
}));
