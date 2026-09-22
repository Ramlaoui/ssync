export type JobState =
  "PD" | "R" | "CD" | "F" | "CA" | "TO" | "UNKNOWN" | string;

export interface ConnectionSettings {
  id: string;
  name: string;
  apiUrl: string;
  apiKey?: string;
  allowSelfSigned?: boolean;
  defaultHost?: string;
  historyWindow: string;
  jobLimit: number;
  updatedAt: number;
}

export interface JobInfo {
  job_id: string;
  name: string;
  state: JobState;
  hostname: string;
  user?: string | null;
  partition?: string | null;
  nodes?: string | null;
  cpus?: string | null;
  memory?: string | null;
  time_limit?: string | null;
  runtime?: string | null;
  reason?: string | null;
  work_dir?: string | null;
  stdout_file?: string | null;
  stderr_file?: string | null;
  submit_time?: string | null;
  submit_line?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  node_list?: string | null;
  node_hostnames?: string[] | null;
  batch_host?: string | null;
  exit_code?: string | null;
  account?: string | null;
  qos?: string | null;
  priority?: string | null;
  array_job_id?: string | null;
  array_task_id?: string | null;
  alloc_tres?: string | null;
  req_tres?: string | null;
  gres?: string | null;
  tres_per_node?: string | null;
  cpu_time?: string | null;
  total_cpu?: string | null;
  user_cpu?: string | null;
  system_cpu?: string | null;
  ave_cpu?: string | null;
  ave_cpu_freq?: string | null;
  req_cpu_freq_min?: string | null;
  req_cpu_freq_max?: string | null;
  max_rss?: string | null;
  ave_rss?: string | null;
  max_vmsize?: string | null;
  ave_vmsize?: string | null;
  max_disk_read?: string | null;
  max_disk_write?: string | null;
  ave_disk_read?: string | null;
  ave_disk_write?: string | null;
  consumed_energy?: string | null;
  cached?: boolean;
  stale?: boolean;
  refresh_queued?: boolean;
}

export interface JobStatusResponse {
  hostname: string;
  jobs: JobInfo[];
  total_jobs: number;
  query_time: string;
  cached?: boolean;
  group_array_jobs?: boolean;
}

export interface JobCache {
  loadedAt: number;
  responses: JobStatusResponse[];
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

export interface WatcherAction {
  type: string;
  params?: Record<string, unknown>;
  config?: Record<string, unknown>;
  condition?: string;
}

export interface WatcherUpdate {
  name?: string;
  pattern?: string;
  interval_seconds?: number;
  capture_groups?: string[];
  condition?: string | null;
  actions?: WatcherAction[];
  timer_mode_enabled?: boolean;
  timer_interval_seconds?: number;
  trigger_on_job_end?: boolean;
  trigger_job_states?: string[];
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
  failure_count?: number;
  max_failures?: number | null;
  last_check?: string | null;
  last_position?: number | null;
  created_at?: string | null;
  timer_mode_enabled?: boolean;
  timer_interval_seconds?: number;
  timer_mode_active?: boolean;
  trigger_on_job_end?: boolean;
  trigger_job_states?: string[];
  variables?: Record<string, string>;
  remaining_resubmits?: number;
  is_array_template?: boolean;
  array_spec?: string | null;
  parent_watcher_id?: number | null;
  discovered_task_count?: number;
  expected_task_count?: number | null;
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
  action_result?: string | null;
  success: boolean;
}

export interface WatchersResponse {
  job_id?: string;
  watchers: Watcher[];
  count?: number;
}

export interface WatcherEventsResponse {
  events: WatcherEvent[];
  count: number;
}

export interface TriggerWatcherResponse {
  success: boolean;
  message?: string;
  matches?: boolean;
  match_count?: number;
  timer_mode?: boolean;
}

export interface JobsLaunchContext {
  connectionId?: string;
  host?: string;
  job?: JobInfo;
  view?: "detail" | "output" | "script" | "watchers";
}

export type ConnectionInput = Omit<ConnectionSettings, "id" | "updatedAt"> & {
  id?: string;
};
export type JobView =
  "all" | "running" | "pending" | "attention" | "historical" | "pinned";
export interface WorkspaceSettings {
  host: string;
  view: JobView;
  showDetail: boolean;
  pinnedJobs: string[];
}
export interface SlurmDefaults {
  partition?: string | null;
  account?: string | null;
  constraint?: string | null;
  cpus?: number | null;
  mem?: number | null;
  time?: string | null;
  nodes?: number | null;
  ntasks_per_node?: number | null;
  gpus_per_node?: number | null;
  gres?: string | null;
  qos?: string | null;
}
export interface HostInfo {
  hostname: string;
  work_dir: string;
  scratch_dir: string;
  slurm_defaults?: SlurmDefaults | null;
}
export interface HostSettings {
  hostname: string;
  slurm_defaults: SlurmDefaults;
  revision: string;
}
export interface PartitionStatus {
  hostname: string;
  cached: boolean;
  stale: boolean;
  updated_at?: string | null;
  error?: string | null;
  partitions: Array<{
    partition: string;
    availability?: string | null;
    nodes_total: number;
    cpus_alloc: number;
    cpus_idle: number;
    cpus_total: number;
    gpus_total?: number | null;
    gpus_used?: number | null;
    gpus_idle?: number | null;
  }>;
}
export interface LaunchRequest {
  script_content: string;
  source_dir?: string;
  host: string;
  job_name?: string;
  partition?: string;
  account?: string;
  cpus?: number;
  mem?: number;
  time?: number;
  nodes?: number;
  gpus_per_node?: number;
  exclude: string[];
  include: string[];
  no_gitignore: boolean;
}
export interface LaunchResponse {
  success: boolean;
  job_id?: string | null;
  launch_id?: string | null;
  hostname: string;
  message: string;
}
export interface LaunchStatus {
  launch_id: string;
  hostname: string;
  stage: string;
  terminal: boolean;
  success?: boolean | null;
  job_id?: string | null;
  message?: string | null;
  events: Array<{
    sequence: number;
    timestamp: string;
    stage?: string;
    message?: string;
  }>;
}
