import { z } from 'zod';

const nullableString = z.string().nullable().optional();

export const slurmDefaultsSchema = z.object({
  partition: z.string().optional().nullable(),
  account: z.string().optional().nullable(),
  constraint: z.string().optional().nullable(),
  cpus: z.number().optional().nullable(),
  mem: z.number().optional().nullable(),
  time: z.string().optional().nullable(),
  nodes: z.number().optional().nullable(),
  ntasks_per_node: z.number().optional().nullable(),
  gpus_per_node: z.number().optional().nullable(),
  gres: z.string().optional().nullable(),
  job_name_prefix: z.string().optional().nullable(),
  output_pattern: z.string().optional().nullable(),
  error_pattern: z.string().optional().nullable(),
  python_env: z.string().optional().nullable(),
  qos: z.string().optional().nullable(),
  priority: z.number().optional().nullable(),
});

export const hostInfoSchema = z.object({
  hostname: z.string(),
  work_dir: z.string(),
  scratch_dir: z.string(),
  slurm_defaults: slurmDefaultsSchema.optional().nullable(),
});

export const jobInfoSchema = z.object({
  job_id: z.string(),
  name: z.string(),
  state: z.string(),
  hostname: z.string(),
  user: nullableString,
  partition: nullableString,
  nodes: nullableString,
  cpus: nullableString,
  memory: nullableString,
  time_limit: nullableString,
  runtime: nullableString,
  reason: nullableString,
  work_dir: nullableString,
  stdout_file: nullableString,
  stderr_file: nullableString,
  submit_time: nullableString,
  submit_line: nullableString,
  start_time: nullableString,
  end_time: nullableString,
  node_list: nullableString,
  array_job_id: nullableString,
  array_task_id: nullableString,
  alloc_tres: nullableString,
  req_tres: nullableString,
  cpu_time: nullableString,
  total_cpu: nullableString,
  user_cpu: nullableString,
  system_cpu: nullableString,
  ave_cpu: nullableString,
  ave_cpu_freq: nullableString,
  max_rss: nullableString,
  ave_rss: nullableString,
  max_vmsize: nullableString,
  ave_vmsize: nullableString,
  max_disk_read: nullableString,
  max_disk_write: nullableString,
  ave_disk_read: nullableString,
  ave_disk_write: nullableString,
  consumed_energy: nullableString,
});

export const fileMetadataSchema = z.object({
  path: z.string(),
  exists: z.boolean(),
  size_bytes: z.number().nullable().optional(),
  last_modified: z.string().nullable().optional(),
  access_path: z.string().nullable().optional(),
});

export const jobOutputSchema = z.object({
  job_id: z.string(),
  hostname: z.string(),
  stdout: nullableString,
  stderr: nullableString,
  stdout_metadata: fileMetadataSchema.nullable().optional(),
  stderr_metadata: fileMetadataSchema.nullable().optional(),
});

export const jobScriptSchema = z.object({
  job_id: z.string(),
  hostname: z.string(),
  script_content: z.string(),
  content_length: z.number().optional().nullable(),
  local_source_dir: nullableString,
});

export const arrayJobGroupSchema = z.object({
  array_job_id: z.string(),
  job_name: z.string(),
  hostname: z.string(),
  user: nullableString,
  total_tasks: z.number(),
  tasks: z.array(jobInfoSchema),
  pending_count: z.number(),
  running_count: z.number(),
  completed_count: z.number(),
  failed_count: z.number(),
  cancelled_count: z.number(),
});

export const jobStatusResponseSchema = z.object({
  hostname: z.string(),
  jobs: z.array(jobInfoSchema),
  total_jobs: z.number(),
  query_time: z.string(),
  cached: z.boolean().optional().default(false),
  group_array_jobs: z.boolean().optional().default(false),
  array_groups: z.array(arrayJobGroupSchema).optional().nullable(),
});

export const watcherActionSchema = z.object({
  type: z.string(),
  params: z.record(z.string(), z.unknown()).optional().nullable(),
  config: z.record(z.string(), z.unknown()).optional().nullable(),
  condition: z.string().optional().nullable(),
});

export const watcherSchema = z.object({
  id: z.number(),
  job_id: z.string(),
  hostname: z.string(),
  name: z.string(),
  job_name: nullableString,
  pattern: z.string(),
  interval_seconds: z.number(),
  captures: z.array(z.string()).default([]),
  condition: nullableString,
  actions: z.array(watcherActionSchema).default([]),
  state: z.string(),
  trigger_count: z.number().default(0),
  last_check: nullableString,
  last_position: z.number().optional().nullable(),
  created_at: z.string(),
  timer_mode_enabled: z.boolean().optional().nullable(),
  timer_interval_seconds: z.number().optional().nullable(),
  timer_mode_active: z.boolean().optional().nullable(),
  variables: z.record(z.string(), z.unknown()).optional().nullable(),
  is_array_template: z.boolean().optional().nullable(),
  array_spec: nullableString,
  parent_watcher_id: z.number().optional().nullable(),
  discovered_task_count: z.number().optional().nullable(),
  expected_task_count: z.number().optional().nullable(),
});

export const watchersResponseSchema = z.object({
  job_id: z.string().optional().nullable(),
  watchers: z.array(watcherSchema),
  count: z.number().optional().nullable(),
});

export const watcherEventSchema = z.object({
  id: z.number(),
  watcher_id: z.number(),
  watcher_name: z.string(),
  job_id: z.string(),
  hostname: z.string(),
  timestamp: z.string(),
  matched_text: z.string().optional().nullable(),
  captured_vars: z.record(z.string(), z.unknown()).default({}),
  action_type: z.string(),
  action_result: z.string().optional().nullable(),
  success: z.boolean(),
});

export const watcherEventsResponseSchema = z.object({
  events: z.array(watcherEventSchema),
  count: z.number().optional().nullable(),
});

export const watcherStatsSchema = z.object({
  total_watchers: z.number(),
  watchers_by_state: z.record(z.string(), z.number()),
  total_events: z.number(),
  events_by_action: z.record(
    z.string(),
    z.object({
      total: z.number(),
      success: z.number(),
      failed: z.number(),
    }),
  ),
  events_last_hour: z.number(),
  top_watchers: z.array(
    z.object({
      watcher_id: z.number(),
      job_id: z.string(),
      name: z.string(),
      event_count: z.number(),
    }),
  ),
});

export const watcherMessageResponseSchema = z.object({
  message: z.string().optional().nullable(),
});

export const watcherTriggerResponseSchema = z.object({
  success: z.boolean().optional().nullable(),
  message: z.string().optional().nullable(),
  matches: z.boolean().optional().nullable(),
  match_count: z.number().optional().nullable(),
  timer_mode: z.boolean().optional().nullable(),
});

export const launchJobResponseSchema = z.object({
  success: z.boolean(),
  job_id: z.string().optional().nullable(),
  launch_id: z.string().optional().nullable(),
  message: z.string(),
  hostname: z.string(),
  directory_warning: z.string().optional().nullable(),
  directory_stats: z
    .object({
      file_count: z.number().optional().nullable(),
      size_mb: z.number().optional().nullable(),
      dangerous_path: z.boolean().optional().nullable(),
      gitignore_applied: z.boolean().optional().nullable(),
    })
    .optional()
    .nullable(),
  requires_confirmation: z.boolean().optional().default(false),
});

export const launchEventSchema = z.object({
  type: z.string(),
  launch_id: z.string(),
  hostname: z.string(),
  sequence: z.number(),
  timestamp: z.string(),
  stage: z.string().optional().nullable(),
  source: z.string().optional().nullable(),
  stream: z.string().optional().nullable(),
  level: z.string().optional().nullable(),
  message: z.string().optional().nullable(),
  job_id: z.string().optional().nullable(),
  success: z.boolean().optional().nullable(),
});

export const launchStatusSchema = z.object({
  launch_id: z.string(),
  hostname: z.string(),
  stage: z.string(),
  terminal: z.boolean(),
  success: z.boolean().optional().nullable(),
  job_id: z.string().optional().nullable(),
  message: z.string().optional().nullable(),
  events: z.array(launchEventSchema).default([]),
});

export const notificationPreferencesSchema = z.object({
  enabled: z.boolean(),
  allowed_states: z.array(z.string()).optional().nullable(),
  muted_job_ids: z.array(z.string()).default([]),
  muted_hosts: z.array(z.string()).default([]),
  muted_job_name_patterns: z.array(z.string()).default([]),
  allowed_users: z.array(z.string()).default([]),
});

export const notificationDeviceResponseSchema = z.object({
  success: z.boolean(),
  token: z.string().optional().nullable(),
  deleted: z.boolean().optional().nullable(),
  sent: z.number().optional().nullable(),
});

export const healthSchema = z.object({
  status: z.string().optional().nullable(),
  message: z.string().optional().nullable(),
});

export type HostInfo = z.infer<typeof hostInfoSchema>;
export type JobInfo = z.infer<typeof jobInfoSchema>;
export type JobStatusResponse = z.infer<typeof jobStatusResponseSchema>;
export type JobOutput = z.infer<typeof jobOutputSchema>;
export type JobScript = z.infer<typeof jobScriptSchema>;
export type Watcher = z.infer<typeof watcherSchema>;
export type WatcherEvent = z.infer<typeof watcherEventSchema>;
export type WatcherStats = z.infer<typeof watcherStatsSchema>;
export type LaunchStatus = z.infer<typeof launchStatusSchema>;
export type NotificationPreferences = z.infer<typeof notificationPreferencesSchema>;
