/**
 * Types for the watcher system
 */

export enum WatcherState {
  PENDING = 'pending',
  ACTIVE = 'active',
  PAUSED = 'paused',
  STATIC = 'static',  // Static watcher for completed jobs (manual trigger only)
  COMPLETED = 'completed',
  FAILED = 'failed'
}

export interface WatcherAction {
  type: string;
  params?: Record<string, any>;
  config?: Record<string, any>;  // Some APIs use config instead of params
  condition?: string;  // Optional condition for the action
}

export interface Watcher {
  id: number;
  job_id: string;
  hostname: string;
  name: string;
  pattern: string;
  interval_seconds: number;
  captures: string[];
  condition?: string;
  actions: WatcherAction[];
  state: string;  // Changed from WatcherState enum to string
  trigger_count: number;
  last_check?: string;
  last_position?: number;
  created_at: string;
  // Timer mode fields
  timer_mode_enabled?: boolean;
  timer_interval_seconds?: number;
  timer_mode_active?: boolean;
  // Captured variables
  variables?: Record<string, string>;
  // Array template fields
  is_array_template?: boolean;
  array_spec?: string;
  parent_watcher_id?: number;
  discovered_task_count?: number;
  expected_task_count?: number;
}

export interface WatcherEvent {
  id: number;
  watcher_id: number;
  watcher_name: string;
  job_id: string;
  hostname: string;
  timestamp: string;
  matched_text: string;
  captured_vars: Record<string, any>;
  action_type: string;
  action_result?: string;
  success: boolean;
}

export interface WatcherStats {
  total_watchers: number;
  watchers_by_state: Record<WatcherState, number>;
  total_events: number;
  events_by_action: Record<string, {
    total: number;
    success: number;
    failed: number;
  }>;
  events_last_hour: number;
  top_watchers: Array<{
    watcher_id: number;
    job_id: string;
    name: string;
    event_count: number;
  }>;
}

export interface WatchersResponse {
  job_id: string;
  watchers: Watcher[];
  count: number;
}

export interface WatcherEventsResponse {
  events: WatcherEvent[];
  count: number;
}

export interface WatcherMetric {
  name: string;
  value: string | number;
  timestamp: string;
}

export interface WatcherVariable {
  watcher_id: number;
  variable_name: string;
  variable_value: string;
  captured_at: string;
}