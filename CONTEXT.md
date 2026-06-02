# ssync

ssync is a local workflow surface for monitoring and operating SLURM work across configured HPC clusters. The language below keeps the user-facing concepts precise across the CLI, web UI, mobile app, VS Code extension, and Raycast extension.

## Language

**Host**:
A configured HPC cluster endpoint that can report and operate on SLURM jobs. Jobs are grouped by host when showing cross-cluster status.
_Avoid_: Backend, cluster when referring to the configured endpoint

**ssync API Server**:
The local service that exposes ssync status, job detail, output, launch, watcher, and configuration endpoints to clients.
_Avoid_: Backend

**ssync API URL**:
The URL where a client reaches the ssync API server.
_Avoid_: Server URL

**ssync API Key**:
The credential used by a client when the ssync API server requires authentication.
_Avoid_: Token, password

**ssync Connection**:
A client configuration consisting of an ssync API URL and an optional ssync API key that has passed a connection test.
_Avoid_: Configuration when specifically referring to the tested client connection

**Job**:
A SLURM workload tracked by ssync on a host. A job may be active, waiting, completed, failed, cancelled, timed out, or unknown.
_Avoid_: Task, run when referring to the scheduler object

**Running Job**:
A job that is currently executing on allocated resources.
_Avoid_: Active job when specifically meaning running only

**Pending Job**:
A job that is waiting for scheduling or resources before execution.
_Avoid_: Queued task

**Historical Job**:
A job that is no longer running or pending, such as completed, failed, cancelled, timed out, or unknown work.
_Avoid_: The rest, old job

**Historical Job Window**:
The time range used when loading historical jobs for a client view.
_Avoid_: Completed jobs window

**Job Detail**:
The focused view of one job, including its scheduler metadata, resource allocation, timing, paths, outputs, script, manifest, and related watcher information when available.
_Avoid_: Job page when speaking across multiple clients

**Job Output**:
The stdout and stderr content associated with a job.
_Avoid_: Logs when specifically referring to scheduler output files

**Local Job Output Copy**:
A desktop-local copy of Job Output used when a client opens the output in an external application.
_Avoid_: Remote output file

**Job Script**:
The submitted batch script associated with a job.
_Avoid_: Launch script

**Manual Relaunch**:
A user-initiated launch of a new job based on a previous job's script or stored launch request.
_Avoid_: Resubmit when the user is manually starting a new job

**Watcher**:
A persistent rule attached to a job or workflow that observes job output or state and can perform follow-up behavior.
_Avoid_: Monitor, daemon when referring to the rule itself

**Watcher Event**:
A recorded occurrence from watcher evaluation or action execution.
_Avoid_: Notification event, log line

**Watcher Resubmission**:
A watcher-initiated launch of a new job from cached job script or manifest context.
_Avoid_: Manual relaunch

## Example Dialogue

Dev: Should the Raycast extension show every job in one flat list?

Domain expert: No. Group jobs by host, show running jobs first, then pending jobs, then historical jobs.

Dev: When a user opens a job, should watcher information live somewhere else?

Domain expert: No. Job detail should include related watchers and watcher events so the user can understand what follow-up behavior is attached to that job.

Dev: Should a user action and a watcher action both be called resubmit?

Domain expert: No. A user starts a manual relaunch; a watcher performs watcher resubmission.
