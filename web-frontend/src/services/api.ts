/**
 * API service with authentication support
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { writable, get } from 'svelte/store';
import { safeGetItem, safeSetItem } from '../lib/safeStorage';

export const apiConfig = writable({
  baseURL: import.meta.env.VITE_API_URL || '',
  apiKey: safeGetItem('ssync_api_key') || import.meta.env.VITE_API_KEY || '',
  authenticated: false,
  authError: null as string | null
});

let apiInstance: AxiosInstance;

function createApiInstance() {
  const config = get(apiConfig);
  
  // ⚡ PERFORMANCE: Reduced timeout for faster failure detection
  apiInstance = axios.create({
    baseURL: config.baseURL,
    timeout: 15000, // Reduced from 30s to 15s for faster UI responsiveness
    headers: config.apiKey ? {
      'X-API-Key': config.apiKey
    } : {}
  });
  
  apiInstance.interceptors.response.use(
    response => response,
    (error: AxiosError) => {
      if (error.response?.status === 401) {
        apiConfig.update(c => ({
          ...c,
          authenticated: false,
          authError: 'Authentication failed. Please check your API key.'
        }));
      }
      return Promise.reject(error);
    }
  );
  
  return apiInstance;
}

apiInstance = createApiInstance();

apiConfig.subscribe(config => {
  if (config.apiKey) {
    safeSetItem('ssync_api_key', config.apiKey);
    apiInstance = createApiInstance();
  }
});

/**
 * Test API connection and authentication
 */
export async function testConnection(): Promise<boolean> {
  try {
    const response = await apiInstance.get('/api/hosts');
    apiConfig.update(c => ({
      ...c,
      authenticated: true,
      authError: null
    }));
    return true;
  } catch (error) {
    const axiosError = error as AxiosError;
    if (axiosError.response?.status === 401) {
      apiConfig.update(c => ({
        ...c,
        authenticated: false,
        authError: 'Invalid API key'
      }));
    } else {
      apiConfig.update(c => ({
        ...c,
        authenticated: false,
        authError: 'Cannot connect to API server'
      }));
    }
    return false;
  }
}

/**
 * Set API key
 */
export function setApiKey(key: string) {
  apiConfig.update(c => ({
    ...c,
    apiKey: key,
    authError: null
  }));
}

/**
 * Clear API key
 */
export function clearApiKey() {
  localStorage.removeItem('ssync_api_key');
  apiConfig.update(c => ({
    ...c,
    apiKey: '',
    authenticated: false,
    authError: null
  }));
}

// Export the axios instance for use in components
export { apiInstance as api };

// Re-export common types
export type { AxiosResponse, AxiosError } from 'axios';