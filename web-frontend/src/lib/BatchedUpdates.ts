/**
 * Batched Updates Manager
 * 
 * Prevents excessive re-renders by batching multiple state updates
 * and applying them in a single operation.
 */

import type { JobInfo } from '../types/api';

interface QueuedUpdate {
  type: 'job_update' | 'job_state_change' | 'host_jobs_update';
  jobId?: string;
  hostname?: string;
  data: any;
  timestamp: number;
}

interface BatchConfig {
  maxBatchSize: number;
  maxBatchDelay: number;
  deduplicate: boolean;
}

export class BatchedUpdatesManager {
  private updateQueue: QueuedUpdate[] = [];
  private batchTimer: ReturnType<typeof setTimeout> | null = null;
  private isProcessing = false;
  private callbacks: Map<string, (updates: QueuedUpdate[]) => void> = new Map();
  
  private readonly config: BatchConfig = {
    maxBatchSize: 50,      // Process after 50 updates
    maxBatchDelay: 100,    // Process after 100ms
    deduplicate: true      // Remove duplicate updates for same job
  };

  constructor(customConfig?: Partial<BatchConfig>) {
    if (customConfig) {
      Object.assign(this.config, customConfig);
    }
  }

  /**
   * Register a callback for processing batched updates
   */
  public registerCallback(key: string, callback: (updates: QueuedUpdate[]) => void): void {
    this.callbacks.set(key, callback);
  }

  /**
   * Unregister a callback
   */
  public unregisterCallback(key: string): void {
    this.callbacks.delete(key);
  }

  /**
   * Queue a job update for batched processing
   */
  public queueJobUpdate(
    jobId: string, 
    hostname: string, 
    jobData: JobInfo, 
    type: 'job_update' | 'job_state_change' = 'job_update'
  ): void {
    const update: QueuedUpdate = {
      type,
      jobId,
      hostname,
      data: jobData,
      timestamp: Date.now()
    };

    this.queueUpdate(update);
  }

  /**
   * Queue a host jobs update for batched processing
   */
  public queueHostUpdate(hostname: string, jobs: JobInfo[]): void {
    const update: QueuedUpdate = {
      type: 'host_jobs_update',
      hostname,
      data: jobs,
      timestamp: Date.now()
    };

    this.queueUpdate(update);
  }

  /**
   * Internal method to queue any update
   */
  private queueUpdate(update: QueuedUpdate): void {
    // Add to queue
    this.updateQueue.push(update);

    // Remove duplicates if enabled
    if (this.config.deduplicate) {
      this.deduplicateUpdates();
    }

    // Process immediately if batch size is reached
    if (this.updateQueue.length >= this.config.maxBatchSize) {
      this.processBatch();
      return;
    }

    // Schedule processing if not already scheduled
    if (!this.batchTimer) {
      this.batchTimer = setTimeout(() => {
        this.processBatch();
      }, this.config.maxBatchDelay);
    }
  }

  /**
   * Remove duplicate updates for the same job/host
   */
  private deduplicateUpdates(): void {
    const seen = new Map<string, number>();
    const deduplicated: QueuedUpdate[] = [];

    // Process in reverse order to keep the latest update for each job
    for (let i = this.updateQueue.length - 1; i >= 0; i--) {
      const update = this.updateQueue[i];
      const key = this.getUpdateKey(update);
      
      if (!seen.has(key)) {
        seen.set(key, i);
        deduplicated.unshift(update); // Add to beginning to maintain chronological order
      }
    }

    this.updateQueue = deduplicated;
  }

  /**
   * Generate a unique key for deduplication
   */
  private getUpdateKey(update: QueuedUpdate): string {
    switch (update.type) {
      case 'job_update':
      case 'job_state_change':
        return `${update.type}:${update.hostname}:${update.jobId}`;
      case 'host_jobs_update':
        return `${update.type}:${update.hostname}`;
      default:
        return `${update.type}:${update.timestamp}`;
    }
  }

  /**
   * Process the current batch of updates
   */
  private processBatch(): void {
    if (this.isProcessing || this.updateQueue.length === 0) {
      return;
    }

    this.isProcessing = true;

    // Clear the timer
    if (this.batchTimer) {
      clearTimeout(this.batchTimer);
      this.batchTimer = null;
    }

    // Get current batch and clear queue
    const batch = [...this.updateQueue];
    this.updateQueue = [];

    // Group updates by type for efficient processing
    const groupedUpdates = this.groupUpdatesByType(batch);

    // Process each group
    for (const [type, updates] of groupedUpdates) {
      this.processUpdateGroup(type, updates);
    }

    // Notify all callbacks
    this.callbacks.forEach(callback => {
      try {
        callback(batch);
      } catch (error) {
        console.error('Error in batched update callback:', error);
      }
    });

    this.isProcessing = false;

    // If more updates were queued while processing, schedule another batch
    if (this.updateQueue.length > 0) {
      this.batchTimer = setTimeout(() => {
        this.processBatch();
      }, this.config.maxBatchDelay);
    }
  }

  /**
   * Group updates by type for efficient processing
   */
  private groupUpdatesByType(batch: QueuedUpdate[]): Map<string, QueuedUpdate[]> {
    const groups = new Map<string, QueuedUpdate[]>();

    for (const update of batch) {
      const key = update.type;
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(update);
    }

    return groups;
  }

  /**
   * Process a group of updates of the same type
   */
  private processUpdateGroup(type: string, updates: QueuedUpdate[]): void {
    console.log(`Processing batch: ${updates.length} ${type} updates`);

    // Additional processing logic can be added here
    // For example, sorting by priority, filtering, etc.
  }

  /**
   * Force immediate processing of all queued updates
   */
  public flush(): void {
    if (this.updateQueue.length > 0) {
      this.processBatch();
    }
  }

  /**
   * Get current queue status
   */
  public getStatus() {
    return {
      queueSize: this.updateQueue.length,
      isProcessing: this.isProcessing,
      hasTimer: this.batchTimer !== null,
      callbackCount: this.callbacks.size
    };
  }

  /**
   * Clear all queued updates and reset state
   */
  public clear(): void {
    this.updateQueue = [];
    if (this.batchTimer) {
      clearTimeout(this.batchTimer);
      this.batchTimer = null;
    }
    this.isProcessing = false;
  }

  /**
   * Destroy the manager and clean up resources
   */
  public destroy(): void {
    this.clear();
    this.callbacks.clear();
  }
}

// Export singleton instance
export const batchedUpdates = new BatchedUpdatesManager();