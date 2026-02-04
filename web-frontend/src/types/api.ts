// API Type definitions for ssync

export type JobState = 'PD' | 'R' | 'CD' | 'F' | 'CA' | 'TO' | 'UNKNOWN';

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

  // Additional job metadata
  exit_code?: string | null;
  account?: string | null;
  qos?: string | null;
  priority?: string | null;
  array_job_id?: string | null;
  array_task_id?: string | null;

  // Resource allocation
  alloc_tres: string | null;
  req_tres: string | null;

  // CPU metrics
  cpu_time: string | null;
  total_cpu: string | null;
  user_cpu: string | null;
  system_cpu: string | null;
  ave_cpu: string | null;
  ave_cpu_freq: string | null;
  req_cpu_freq_min: string | null;
  req_cpu_freq_max: string | null;

  // Memory metrics
  max_rss: string | null;
  ave_rss: string | null;
  max_vmsize: string | null;
  ave_vmsize: string | null;

  // Disk I/O metrics
  max_disk_read: string | null;
  max_disk_write: string | null;
  ave_disk_read: string | null;
  ave_disk_write: string | null;

  // Energy metrics
  consumed_energy: string | null;
}

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

export interface ArrayJobGroup {
  array_job_id: string;
  job_name: string;
  hostname: string;
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
  cached?: boolean;  // Indicates if data was served from cache
  group_array_jobs?: boolean;  // Whether array jobs are grouped
  array_groups?: ArrayJobGroup[];  // Array job groups if grouping is enabled
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
  stdout: string | null;
  stderr: string | null;
  stdout_metadata: FileMetadata | null;
  stderr_metadata: FileMetadata | null;
}

export interface JobScriptResponse {
  job_id: string;
  hostname: string;
  script_content: string;
  content_length: number;
}

export interface ApiError {
  detail: string;
}

// Filter types
export interface JobFilters {
  host: string;
  user: string;
  since: string;
  limit: number;
  state: string;
  activeOnly: boolean;
  completedOnly: boolean;
}

// Event types for Svelte components
export interface JobSelectEvent {
  detail: JobInfo;
}

export interface FilterChangeEvent {
  detail: Partial<JobFilters>;
}

// Utility types
export type LoadingState = {
  [key: string]: boolean;
};

export type ApiRequestState = 'idle' | 'loading' | 'error' | 'success';

export interface LaunchJobRequest {
  script_content: string;
  source_dir: string;
  host: string;

  // Slurm parameters
  job_name?: string;
  cpus?: number;
  mem?: number;
  time?: number;
  partition?: string;
  ntasks_per_node?: number;
  // Some backend code expects the alternate name `n_tasks_per_node`
  // include it for compatibility with older/newer API variants.
  n_tasks_per_node?: number;
  nodes?: number;
  gpus_per_node?: number;
  gres?: string;
  output?: string;
  error?: string;
  constraint?: string;
  account?: string;
  python_env?: string;

  // Sync parameters
  exclude: string[];
  include: string[];
  no_gitignore: boolean;
  force_sync?: boolean;
}

export interface LaunchJobResponse {
  success: boolean;
  job_id?: string;
  message: string;
  hostname: string;

  // Directory validation information
  directory_warning?: string;
  directory_stats?: {
    file_count: number;
    size_mb: number;
    dangerous_path: boolean;
    gitignore_applied?: boolean;
  };
  requires_confirmation?: boolean;
}

// Type aliases for component usage
export type OutputData = JobOutputResponse;
export type ScriptData = JobScriptResponse;

// API client types
export interface APIClient {
  getHosts(): Promise<HostInfo[]>;
  getJobs(filters: Partial<JobFilters>): Promise<JobStatusResponse[]>;
  getJobDetails(jobId: string, hostname: string): Promise<JobInfo>;
  getJobOutput(jobId: string, hostname: string, lines?: number, metadataOnly?: boolean): Promise<JobOutputResponse>;
  getJobScript(jobId: string, hostname: string): Promise<JobScriptResponse>;
  cancelJob(jobId: string, hostname: string): Promise<{ message: string }>;
  launchJob(request: LaunchJobRequest): Promise<LaunchJobResponse>;
}
