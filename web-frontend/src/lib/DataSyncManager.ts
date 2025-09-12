/**
 * Consolidated Data Sync Manager
 * 
 * Single source of truth for all data fetching, polling, and WebSocket coordination.
 * Eliminates redundant API calls and provides intelligent refresh strategies.
 */

import type { JobInfo, HostInfo, JobStatusResponse } from '../types/api';
import { jobsStore } from '../stores/jobs';
import { 
  allJobsWebSocketStore, 
  connectAllJobsWebSocket, 
  disconnectAllJobsWebSocket 
} from '../stores/jobWebSocket';
import { get } from 'svelte/store';

interface SyncManagerState {
  isWebSocketReliable: boolean;
  lastWebSocketActivity: number;
  connectionAttempts: number;
  isTabActive: boolean;
  lastUserActivity: number;
  isPaused: boolean;
}

interface RefreshStrategy {
  immediate: boolean;
  respectCache: boolean;
  source: 'user' | 'interval' | 'websocket' | 'focus';
}

export class DataSyncManager {
  private static instance: DataSyncManager;
  private state: SyncManagerState;
  private pollingInterval: ReturnType<typeof setInterval> | null = null;
  private webSocketHealthCheck: ReturnType<typeof setInterval> | null = null;
  private visibilityChangeHandler: () => void;
  private userActivityHandler: () => void;
  private unsubscribeWebSocket: (() => void) | null = null;
  
  // Configuration
  private readonly config = {
    // WebSocket reliability thresholds
    webSocketTimeoutMs: 45000, // 45 seconds without activity = unreliable
    maxConnectionAttempts: 3,
    
    // Polling fallback intervals (reduced frequency for better performance)
    activePollInterval: 90000,    // 90 seconds when tab is active (increased from 60s)
    backgroundPollInterval: 600000, // 10 minutes when tab is background (increased from 5m)
    
    // Cache durations
    jobCacheDuration: 120000,     // 2 minutes for individual jobs
    hostCacheDuration: 60000,     // 1 minute for host data
    
    // User activity detection
    userActivityTimeout: 300000,  // 5 minutes of inactivity = background mode
  };

  private constructor() {
    this.state = {
      isWebSocketReliable: false,
      lastWebSocketActivity: 0,
      connectionAttempts: 0,
      isTabActive: true,
      lastUserActivity: Date.now(),
      isPaused: false,
    };

    this.visibilityChangeHandler = this.handleVisibilityChange.bind(this);
    this.userActivityHandler = this.handleUserActivity.bind(this);
    
    this.setupEventListeners();
    this.initializeWebSocket();
    this.startHealthMonitoring();
  }

  public static getInstance(): DataSyncManager {
    if (!DataSyncManager.instance) {
      DataSyncManager.instance = new DataSyncManager();
    }
    return DataSyncManager.instance;
  }

  private setupEventListeners(): void {
    // Tab visibility detection
    document.addEventListener('visibilitychange', this.visibilityChangeHandler);
    
    // User activity detection
    const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
    activityEvents.forEach(event => {
      document.addEventListener(event, this.userActivityHandler, { passive: true });
    });
  }

  private handleVisibilityChange(): void {
    this.state.isTabActive = !document.hidden;
    
    if (this.state.isTabActive) {
      // Tab became active - refresh data immediately
      this.refreshData({ 
        immediate: true, 
        respectCache: false, 
        source: 'focus' 
      });
      this.resumePolling();
    } else {
      // Tab became inactive - reduce polling frequency
      this.adjustPollingForBackground();
    }
  }

  private handleUserActivity(): void {
    this.state.lastUserActivity = Date.now();
  }

  private initializeWebSocket(): void {
    // Connect to WebSocket
    connectAllJobsWebSocket();
    
    // Monitor WebSocket state
    this.unsubscribeWebSocket = allJobsWebSocketStore.subscribe(wsState => {
      const wasConnected = this.state.isWebSocketReliable;
      
      if (wsState.connected) {
        this.state.lastWebSocketActivity = Date.now();
        this.state.isWebSocketReliable = true;
        this.state.connectionAttempts = 0;
        
        // If WebSocket just became connected after being disconnected
        if (!wasConnected) {
          console.log('WebSocket reconnected - refreshing job data');
          // Stop polling since WebSocket is back
          this.stopPolling();
          // Immediately refresh data to sync state
          this.refreshData({ 
            immediate: true, 
            respectCache: false, 
            source: 'websocket' 
          });
        }
      } else {
        // Only increment attempts if we were previously connected
        if (wasConnected) {
          this.state.connectionAttempts++;
        }
        this.state.isWebSocketReliable = false;
        
        // If WebSocket became disconnected, start polling fallback immediately
        if (wasConnected || this.state.connectionAttempts === 0) {
          console.log('WebSocket disconnected - starting polling fallback');
          this.startPollingFallback();
          // Also do an immediate refresh to catch any missed updates
          this.refreshData({ 
            immediate: true, 
            respectCache: false, 
            source: 'websocket' 
          });
        }
      }
    });
  }

  private startHealthMonitoring(): void {
    this.webSocketHealthCheck = setInterval(() => {
      const now = Date.now();
      
      // Check WebSocket health
      if (this.state.isWebSocketReliable) {
        const timeSinceActivity = now - this.state.lastWebSocketActivity;
        if (timeSinceActivity > this.config.webSocketTimeoutMs) {
          console.warn('WebSocket appears stale, marking as unreliable');
          this.state.isWebSocketReliable = false;
          this.startPollingFallback();
        }
      }
      
      // Check if we should pause due to inactivity
      const timeSinceUserActivity = now - this.state.lastUserActivity;
      const shouldPause = !this.state.isTabActive && 
                         timeSinceUserActivity > this.config.userActivityTimeout;
      
      if (shouldPause && !this.state.isPaused) {
        this.pauseSync();
      } else if (!shouldPause && this.state.isPaused) {
        this.resumeSync();
      }
      
    }, 30000); // Check every 30 seconds
  }

  private shouldPoll(): boolean {
    // Don't poll if WebSocket is reliable and connected
    if (this.state.isWebSocketReliable) return false;
    
    // Don't poll if sync is paused
    if (this.state.isPaused) return false;
    
    // Don't poll if too many failed connection attempts
    if (this.state.connectionAttempts >= this.config.maxConnectionAttempts) {
      return this.state.isTabActive; // Only poll if tab is active
    }
    
    return true;
  }

  private getPollingInterval(): number {
    if (!this.state.isTabActive) {
      return this.config.backgroundPollInterval;
    }
    
    // Use shorter intervals if WebSocket is unreliable but we're trying to reconnect
    if (this.state.connectionAttempts > 0 && this.state.connectionAttempts < this.config.maxConnectionAttempts) {
      return this.config.activePollInterval / 2; // More aggressive when recovering
    }
    
    return this.config.activePollInterval;
  }

  private startPollingFallback(): void {
    if (!this.shouldPoll()) return;
    
    this.stopPolling(); // Clear any existing interval
    
    const interval = this.getPollingInterval();
    console.log(`Starting polling fallback with ${interval/1000}s interval`);
    
    this.pollingInterval = setInterval(() => {
      if (this.shouldPoll()) {
        this.refreshData({ 
          immediate: false, 
          respectCache: true, 
          source: 'interval' 
        });
      } else {
        this.stopPolling();
      }
    }, interval);
  }

  private stopPolling(): void {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
      console.log('Stopped polling - WebSocket is handling updates');
    }
  }

  private adjustPollingForBackground(): void {
    if (this.pollingInterval) {
      this.stopPolling();
      this.startPollingFallback();
    }
  }

  private resumePolling(): void {
    if (!this.state.isWebSocketReliable && this.shouldPoll()) {
      this.startPollingFallback();
    }
  }

  private pauseSync(): void {
    this.state.isPaused = true;
    this.stopPolling();
    console.log('Data sync paused due to inactivity');
  }

  private resumeSync(): void {
    this.state.isPaused = false;
    if (!this.state.isWebSocketReliable) {
      this.startPollingFallback();
    }
    console.log('Data sync resumed');
  }

  public async refreshData(strategy: RefreshStrategy): Promise<void> {
    if (this.state.isPaused && strategy.source !== 'user' && strategy.source !== 'focus') {
      return;
    }

    try {
      // Always refresh available hosts first (they change less frequently)
      await jobsStore.fetchAvailableHosts();
      
      // Then refresh job data with appropriate caching strategy
      const forceRefresh = !strategy.respectCache || strategy.immediate;
      await jobsStore.fetchAllJobsProgressive(forceRefresh);
      
      console.log(`Data refreshed (source: ${strategy.source}, forced: ${forceRefresh})`);
    } catch (error) {
      console.error('Failed to refresh data:', error);
      
      // If refresh fails and WebSocket was reliable, it might not be anymore
      if (this.state.isWebSocketReliable && strategy.source === 'interval') {
        this.state.isWebSocketReliable = false;
        this.startPollingFallback();
      }
    }
  }

  public requestImmediateRefresh(): Promise<void> {
    return this.refreshData({ 
      immediate: true, 
      respectCache: false, 
      source: 'user' 
    });
  }

  public getStatus() {
    return {
      webSocketConnected: get(allJobsWebSocketStore).connected,
      webSocketReliable: this.state.isWebSocketReliable,
      isPolling: this.pollingInterval !== null,
      isTabActive: this.state.isTabActive,
      isPaused: this.state.isPaused,
      connectionAttempts: this.state.connectionAttempts,
      lastActivity: this.state.lastWebSocketActivity,
    };
  }

  public destroy(): void {
    // Clean up intervals
    this.stopPolling();
    if (this.webSocketHealthCheck) {
      clearInterval(this.webSocketHealthCheck);
    }
    
    // Clean up event listeners
    document.removeEventListener('visibilitychange', this.visibilityChangeHandler);
    const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
    activityEvents.forEach(event => {
      document.removeEventListener(event, this.userActivityHandler);
    });
    
    // Clean up WebSocket subscription
    if (this.unsubscribeWebSocket) {
      this.unsubscribeWebSocket();
    }
    
    // Disconnect WebSocket
    disconnectAllJobsWebSocket();
  }
}

// Export singleton instance
export const dataSyncManager = DataSyncManager.getInstance();