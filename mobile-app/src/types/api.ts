export type JobState = "PD" | "R" | "CD" | "F" | "CA" | "TO" | "UNKNOWN" | string;

export type ThemePreference = "light" | "dark" | "system";

export interface SlurmDefaults {
  partition?: string;
  account?: string;
  constraint?: string;
  cpus?: number;
  time?: string;
  mem?: number;
  nodes?: number;
  gpus_per_node?: number;
  ntasks_per_node?: number;
  gres?: string;
  job_name_prefix?: string;
  output_pattern?: string;
  error_pattern?: string;
  python_env?: string;
}

export interface HostInfo {
  hostname: string;
  work_dir: string;
  scratch_dir: string;
  slurm_defaults?: SlurmDefaults;
}

export interface JobInfo {
  job_id: string;
  name: string;
  state: JobState;
  hostname: string;
  user: string | null;
  partition: string | null;
  nodes: string | null;
  cpus: string | null;
  memory: string | null;
  time_limit: string | null;
  runtime: string | null;
  reason: string | null;
  work_dir: string | null;
  stdout_file: string | null;
  stderr_file: string | null;
  submit_time: string | null;
  submit_line: string | null;
  start_time: string | null;
  end_time: string | null;
  node_list: string | null;
  node_hostnames?: string[] | null;
  batch_host?: string | null;
  exit_code?: string | null;
  account?: string | null;
  qos?: string | null;
  priority?: string | null;
  array_job_id?: string | null;
  array_task_id?: string | null;
  alloc_tres: string | null;
  req_tres: string | null;
  gres?: string | null;
  tres_per_node?: string | null;
  cpu_time: string | null;
  total_cpu: string | null;
  user_cpu: string | null;
  system_cpu: string | null;
  ave_cpu: string | null;
  ave_cpu_freq: string | null;
  req_cpu_freq_min: string | null;
  req_cpu_freq_max: string | null;
  max_rss: string | null;
  ave_rss: string | null;
  max_vmsize: string | null;
  ave_vmsize: string | null;
  max_disk_read: string | null;
  max_disk_write: string | null;
  ave_disk_read: string | null;
  ave_disk_write: string | null;
  consumed_energy: string | null;
  cached?: boolean;
  stale?: boolean;
  refresh_queued?: boolean;
}

export interface ArrayJobGroup {
  array_job_id: string;
  job_name: string;
  hostname: string;
  user?: string | null;
  total_tasks: number;
  tasks: JobInfo[];
  pending_count: number;
  running_count: number;
  completed_count: number;
  failed_count: number;
  cancelled_count: number;
}

export interface JobStatusResponse {
  hostname: string;
  jobs: JobInfo[];
  total_jobs: number;
  query_time: string;
  cached?: boolean;
  group_array_jobs?: boolean;
  array_groups?: ArrayJobGroup[];
}

export interface PartitionGpuType {
  total: number;
  used: number;
}

export interface PartitionResources {
  partition: string;
  availability: string | null;
  states: string[];
  nodes_total: number;
  cpus_alloc: number;
  cpus_idle: number;
  cpus_other: number;
  cpus_total: number;
  gpus_total: number | null;
  gpus_used: number | null;
  gpus_idle: number | null;
  gpu_types?: Record<string, PartitionGpuType>;
}

export interface PartitionStatusResponse {
  hostname: string;
  partitions: PartitionResources[];
  query_time: string;
  cached?: boolean;
  stale?: boolean;
  cache_age_seconds?: number;
  updated_at?: string;
  error?: string | null;
}

export interface FileMetadata {
  path: string;
  exists: boolean;
  size_bytes: number | null;
  last_modified: string | null;
  access_path: string | null;
}

export interface JobOutputResponse {
  job_id: string;
  hostname: string;
  output_type: "stdout" | "stderr" | "both";
  stdout: string | null;
  stderr: string | null;
  stdout_metadata: FileMetadata | null;
  stderr_metadata: FileMetadata | null;
  content_truncated?: boolean;
  content_limit_bytes?: number | null;
  cached?: boolean;
  stale?: boolean;
  refresh_queued?: boolean;
}

export interface JobScriptResponse {
  job_id: string;
  hostname: string;
  script_content: string;
  content_length: number;
  local_source_dir?: string | null;
}

export interface LaunchJobRequest {
  script_content: string;
  source_dir: string;
  host: string;
  job_name?: string;
  cpus?: number;
  mem?: number;
  time?: number;
  partition?: string;
  ntasks_per_node?: number;
  n_tasks_per_node?: number;
  nodes?: number;
  gpus_per_node?: number;
  gres?: string;
  output?: string;
  error?: string;
  constraint?: string;
  account?: string;
  python_env?: string;
  exclude: string[];
  include: string[];
  no_gitignore: boolean;
  force_sync?: boolean;
  abort_on_setup_failure?: boolean;
}

export interface LaunchJobResponse {
  success: boolean;
  job_id?: string;
  launch_id?: string;
  message: string;
  hostname: string;
  directory_warning?: string;
  requires_confirmation?: boolean;
}

export interface LaunchEvent {
  type: "launch_stage" | "launch_log" | "launch_result";
  launch_id: string;
  hostname: string;
  sequence: number;
  timestamp: string;
  stage?: string;
  source?: string;
  stream?: string;
  level?: string;
  message?: string;
  job_id?: string;
  success?: boolean;
}

export interface LaunchStatusResponse {
  launch_id: string;
  hostname: string;
  stage: string;
  terminal: boolean;
  success?: boolean;
  job_id?: string;
  message?: string;
  events: LaunchEvent[];
}

export interface WatcherAction {
  type: string;
  params?: Record<string, unknown>;
  config?: Record<string, unknown>;
  condition?: string;
}

export interface Watcher {
  id: number;
  job_id: string;
  hostname: string;
  name: string;
  job_name?: string | null;
  pattern: string;
  interval_seconds: number;
  captures: string[];
  condition?: string;
  actions: WatcherAction[];
  state: string;
  trigger_count: number;
  last_check?: string;
  last_position?: number;
  created_at: string;
  timer_mode_enabled?: boolean;
  timer_interval_seconds?: number;
  timer_mode_active?: boolean;
  trigger_on_job_end?: boolean;
  trigger_job_states?: string[];
  variables?: Record<string, string>;
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
  captured_vars: Record<string, unknown>;
  action_type: string;
  action_result?: string;
  success: boolean;
}

export interface WatchersResponse {
  job_id?: string;
  watchers: Watcher[];
  count: number;
}

export interface WatcherEventsResponse {
  events: WatcherEvent[];
  count: number;
}

export interface NotificationPreferences {
  enabled: boolean;
  allowed_states: string[] | null;
  muted_job_ids: string[];
  muted_hosts: string[];
  muted_job_name_patterns: string[];
  allowed_users: string[];
}

export interface NotificationStatus {
  providers: {
    enabled: boolean;
    apns: boolean;
    expo: boolean;
    webpush: boolean;
  };
  device_registration: {
    platforms: string[];
    token_types: string[];
    payload_formats: string[];
  };
  event_contract: {
    type: string;
    fields: string[];
  };
}

export interface LocalEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface LocalListResponse {
  path: string;
  entries: LocalEntry[];
}
