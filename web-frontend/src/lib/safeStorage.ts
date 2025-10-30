/**
 * Safe localStorage wrapper for iOS and private browsing mode compatibility
 *
 * iOS WebKit and private browsing mode can throw exceptions when accessing localStorage.
 * This utility provides safe fallback behavior.
 */

const inMemoryStorage: { [key: string]: string } = {};
let storageAvailable: boolean | null = null;

/**
 * Check if localStorage is available
 */
function isLocalStorageAvailable(): boolean {
  if (storageAvailable !== null) {
    return storageAvailable;
  }

  try {
    const testKey = '__storage_test__';
    localStorage.setItem(testKey, 'test');
    localStorage.removeItem(testKey);
    storageAvailable = true;
    return true;
  } catch (error) {
    console.warn('localStorage is not available (possibly in private browsing mode). Using in-memory storage fallback.');
    storageAvailable = false;
    return false;
  }
}

/**
 * Safely get an item from localStorage with fallback to in-memory storage
 */
export function safeGetItem(key: string): string | null {
  try {
    if (isLocalStorageAvailable()) {
      return localStorage.getItem(key);
    } else {
      return inMemoryStorage[key] || null;
    }
  } catch (error) {
    console.warn(`Failed to get item "${key}" from storage:`, error);
    return inMemoryStorage[key] || null;
  }
}

/**
 * Safely set an item in localStorage with fallback to in-memory storage
 */
export function safeSetItem(key: string, value: string): void {
  try {
    if (isLocalStorageAvailable()) {
      localStorage.setItem(key, value);
    }
    // Always also store in memory as backup
    inMemoryStorage[key] = value;
  } catch (error) {
    console.warn(`Failed to set item "${key}" in storage:`, error);
    // Fallback to in-memory storage
    inMemoryStorage[key] = value;
  }
}

/**
 * Safely remove an item from localStorage with fallback to in-memory storage
 */
export function safeRemoveItem(key: string): void {
  try {
    if (isLocalStorageAvailable()) {
      localStorage.removeItem(key);
    }
    delete inMemoryStorage[key];
  } catch (error) {
    console.warn(`Failed to remove item "${key}" from storage:`, error);
    delete inMemoryStorage[key];
  }
}

/**
 * Safely clear all storage
 */
export function safeClearAll(): void {
  try {
    if (isLocalStorageAvailable()) {
      localStorage.clear();
    }
    Object.keys(inMemoryStorage).forEach(key => delete inMemoryStorage[key]);
  } catch (error) {
    console.warn('Failed to clear storage:', error);
    Object.keys(inMemoryStorage).forEach(key => delete inMemoryStorage[key]);
  }
}
