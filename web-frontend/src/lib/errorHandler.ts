/**
 * Centralized error handling strategy with retry logic and user-friendly messages
 */

export interface RetryConfig {
  attempts: number;
  backoff: 'linear' | 'exponential';
  baseDelay?: number;
  maxDelay?: number;
}

export interface ErrorHandlerConfig {
  retryStrategies: Record<string, RetryConfig>;
  fallbacks: Record<string, () => string>;
  userMessages: Record<string, string>;
}

export class ErrorHandler {
  private config: ErrorHandlerConfig;
  private retryAttempts: Map<string, number> = new Map();

  constructor(config: ErrorHandlerConfig) {
    this.config = config;
  }

  /**
   * Handle error with automatic retry and user-friendly messaging
   */
  async handleError<T>(
    operation: string,
    fn: () => Promise<T>,
    context?: Record<string, any>
  ): Promise<T> {
    const strategyKey = this.getStrategyKey(operation);
    const strategy = this.config.retryStrategies[strategyKey];
    
    if (!strategy) {
      // No retry strategy, just try once
      try {
        return await fn();
      } catch (error) {
        throw this.enhanceError(error, operation, context);
      }
    }

    const attempts = this.retryAttempts.get(operation) || 0;
    
    try {
      const result = await fn();
      // Success - reset retry counter
      this.retryAttempts.delete(operation);
      return result;
    } catch (error) {
      if (attempts >= strategy.attempts) {
        // Max attempts reached
        this.retryAttempts.delete(operation);
        throw this.enhanceError(error, operation, context);
      }

      // Schedule retry
      this.retryAttempts.set(operation, attempts + 1);
      const delay = this.calculateDelay(strategy, attempts);
      
      await this.sleep(delay);
      return this.handleError(operation, fn, context);
    }
  }

  /**
   * Get user-friendly error message
   */
  getUserMessage(error: any, operation: string): string {
    // Check for specific user messages
    if (this.config.userMessages[operation]) {
      return this.config.userMessages[operation];
    }

    // Extract meaningful message from error
    if (error?.response?.status) {
      return this.getHttpErrorMessage(error.response.status, operation);
    }

    if (error?.message) {
      return this.sanitizeErrorMessage(error.message);
    }

    return `Failed to ${operation}. Please try again.`;
  }

  /**
   * Get fallback data if available
   */
  getFallback(operation: string): string | null {
    const fallback = this.config.fallbacks[operation];
    return fallback ? fallback() : null;
  }

  /**
   * Check if error is retryable
   */
  isRetryableError(error: any): boolean {
    // Network errors are generally retryable
    if (error?.code === 'NETWORK_ERROR') return true;
    
    // HTTP status codes that are retryable
    const retryableStatuses = [408, 429, 500, 502, 503, 504];
    if (error?.response?.status && retryableStatuses.includes(error.response.status)) {
      return true;
    }

    return false;
  }

  private getStrategyKey(operation: string): string {
    // Map operations to strategy keys
    if (operation.includes('network') || operation.includes('fetch')) return 'network';
    if (operation.includes('timeout')) return 'timeout';
    return 'default';
  }

  private calculateDelay(strategy: RetryConfig, attempt: number): number {
    const baseDelay = strategy.baseDelay || 1000;
    const maxDelay = strategy.maxDelay || 30000;
    
    let delay: number;
    
    if (strategy.backoff === 'exponential') {
      delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
    } else {
      delay = Math.min(baseDelay * (attempt + 1), maxDelay);
    }
    
    // Add jitter to prevent thundering herd
    return delay + Math.random() * 0.1 * delay;
  }

  private enhanceError(error: any, operation: string, context?: Record<string, any>): Error {
    const enhanced = new Error(this.getUserMessage(error, operation));
    enhanced.name = 'EnhancedError';
    
    // Preserve original error for debugging
    (enhanced as any).originalError = error;
    (enhanced as any).operation = operation;
    (enhanced as any).context = context;
    
    return enhanced;
  }

  private getHttpErrorMessage(status: number, operation: string): string {
    switch (status) {
      case 401:
        return 'Authentication required. Please check your API key.';
      case 403:
        return 'Access denied. You may not have permission for this operation.';
      case 404:
        return `Resource not found. The ${operation.split(' ')[0]} may have been deleted.`;
      case 408:
      case 504:
        return 'Request timeout. The server is taking too long to respond.';
      case 429:
        return 'Too many requests. Please wait a moment before trying again.';
      case 500:
        return 'Server error. Please try again in a few moments.';
      case 502:
      case 503:
        return 'Service temporarily unavailable. Please try again later.';
      default:
        return `Network error (${status}). Please check your connection and try again.`;
    }
  }

  private sanitizeErrorMessage(message: string): string {
    // Remove technical details that users don't need to see
    return message
      .replace(/^Error:\s*/i, '')
      .replace(/\s*at\s+.*$/g, '')
      .replace(/\s*\(.*\)$/g, '')
      .trim();
  }

  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

// Default configuration
export const defaultErrorHandler = new ErrorHandler({
  retryStrategies: {
    network: { attempts: 3, backoff: 'exponential', baseDelay: 1000, maxDelay: 10000 },
    timeout: { attempts: 2, backoff: 'linear', baseDelay: 2000, maxDelay: 6000 },
    default: { attempts: 1, backoff: 'linear' }
  },
  fallbacks: {
    'load output': () => 'Output temporarily unavailable',
    'load script': () => 'Script content cannot be loaded',
    'load job': () => 'Job information unavailable'
  },
  userMessages: {
    'load output': 'Unable to load job output. This may be due to the job still running or output files being unavailable.',
    'load script': 'Unable to load job script. The script file may not be accessible.',
    'load job': 'Unable to load job details. The job may have been deleted or is not accessible.',
    'cancel job': 'Unable to cancel job. The job may have already completed or been cancelled.',
    'download output': 'Unable to download output. Please try again or contact support.',
    'download script': 'Unable to download script. Please try again or contact support.'
  }
});

/**
 * Helper function for common async operations with error handling
 */
export async function withErrorHandling<T>(
  operation: string,
  fn: () => Promise<T>,
  context?: Record<string, any>
): Promise<T> {
  return defaultErrorHandler.handleError(operation, fn, context);
}