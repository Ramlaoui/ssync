/**
 * API service with authentication support
 */

import axios, { type AxiosInstance, type AxiosError } from 'axios';
import { writable, get } from 'svelte/store';

// Store for API configuration
export const apiConfig = writable({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  apiKey: localStorage.getItem('ssync_api_key') || import.meta.env.VITE_API_KEY || '',
  authenticated: false,
  authError: null as string | null
});

// Create axios instance with authentication
let apiInstance: AxiosInstance;

function createApiInstance() {
  const config = get(apiConfig);
  
  apiInstance = axios.create({
    baseURL: config.baseURL,
    timeout: 30000,
    headers: config.apiKey ? {
      'X-API-Key': config.apiKey
    } : {}
  });
  
  // Add response interceptor for auth errors
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

// Initialize API instance
apiInstance = createApiInstance();

// Subscribe to config changes
apiConfig.subscribe(config => {
  if (config.apiKey) {
    localStorage.setItem('ssync_api_key', config.apiKey);
    apiInstance = createApiInstance();
  }
});

/**
 * Test API connection and authentication
 */
export async function testConnection(): Promise<boolean> {
  try {
    // Test authentication directly using the API instance
    const response = await apiInstance.get('/hosts');
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