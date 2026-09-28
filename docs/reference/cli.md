---
description: Every ssync command and option.
---

# CLI reference

Run `ssync COMMAND --help` for the same information in your terminal. Most commands accept `--host` to target one cluster; when omitted, ssync queries every host or finds the host that owns the job.

## Jobs

### `ssync status`

List jobs across hosts.

| Option | Description |
| --- | --- |
| `--host TEXT` | Only this host. |
| `--user TEXT` | Jobs for another user. |
| `--since TEXT` | Include finished jobs since a time: `1h`, `1d`, `1w`, or `2026-08-20`. |
| `--state TEXT` | Filter by state: `PD`, `R`, `CD`, `F`, `CA`, `TO`. |
| `--active-only` | Only running and pending jobs. |
| `--completed-only` | Only finished jobs. |
| `--job-id TEXT` | Specific job IDs, comma-separated. |
| `--limit INTEGER` | Maximum number of jobs. |
| `--format [table\|json\|verbose]` | Output format, default `table`. |

### `ssync cancel JOB_ID`

Cancel a job. `--host` if the ID exists on several hosts.

### `ssync partitions`

Show partition capacity (allocated and idle CPUs and GPUs) across hosts. `--host`, `--json`, and `--force-refresh` to bypass the cache.

## Launching

### `ssync launch SCRIPT_PATH SOURCE_DIR`

Sync `SOURCE_DIR` to the host and submit `SCRIPT_PATH`. See [Launching jobs](../guides/launching-jobs.md).

| Option | Description |
| --- | --- |
| `--host TEXT` | Target host. **Required.** |
| `--job-name TEXT` | Slurm job name. |
| `--partition TEXT` | Partition. |
| `--account TEXT` | Account to charge. |
| `--qos TEXT` | Quality of service. |
| `--cpus INTEGER` | CPUs per task. |
| `--mem INTEGER` | Memory in GB. |
| `--time INTEGER` | Time limit in minutes. |
| `--nodes INTEGER` | Number of nodes. |
| `--ntasks-per-node INTEGER` | Tasks per node. |
| `--gpus-per-node INTEGER` | GPUs per node. |
| `--gres TEXT` | Generic resources, for example `gpu:2`. |
| `--constraint TEXT` | Node constraint, for example `a100`. |
| `--dependency TEXT` | Slurm dependency, for example `afterok:12345`. |
| `--output TEXT` / `--error TEXT` | stdout / stderr file paths. |
| `--python-env TEXT` | Extra setup command run on the login node before submission. |
| `--exclude TEXT` | Additional patterns to skip when syncing (repeatable). |
| `--include TEXT` | Patterns to sync even if ignored (repeatable). |
| `--no-gitignore` | Do not use `.gitignore` files. |
| `--no-abort-on-setup-failure` | Submit even if login-node setup fails. |

### `ssync launch-recipe RECIPE_PATH`

Render a repo-local recipe (by path or bare name) and submit it. Accepts the same resource and sync options as `launch`, plus:

| Option | Description |
| --- | --- |
| `--dry-run` | Print the rendered script without submitting. |
| `--json` | With `--dry-run`, print the resolved manifest as JSON. |
| `--workflow TEXT` | Override the workflow profile. |
| `--host-partition TEXT` | Override the host/partition profile. |
| `--env TEXT` | Override the environment profile. |
| `--var KEY=VALUE` | Override a recipe variable. |
| `--set sbatch.FIELD=VALUE` | Override a scheduler field. |
| `--add-watcher TEXT` / `--remove-watcher TEXT` | Add or remove a watcher policy. |

See [Launch recipes](../guides/recipes.md).

### `ssync manifest JOB_ID`

Show the stored launch manifest for a recipe-submitted job. `--json` for raw output.

### `ssync rerender JOB_ID`

Show the script a recipe-submitted job ran. Uses the frozen script by default; `--from-current-repo` re-resolves the recipe from your current files.

### `ssync sync SOURCE_DIR`

Sync a directory to every host (or `--host`) without submitting. Supports `--exclude`, `--include`, `--no-gitignore`, and `--max-depth` for how deep to look for `.gitignore` files (default 3).

## Output

### `ssync output JOB_ID`

Print a job's output file.

| Option | Description |
| --- | --- |
| `--stderr` | Print stderr instead of stdout. |
| `--both` | Print both streams. |
| `--lines N` | Only the last N lines. |
| `--max-bytes N` | Trailing bytes to fetch when `--lines` is not set (1,024–4,194,304). |
| `--all` | The full file. |
| `--force-refresh` | Re-read from the cluster instead of the cache. |

### `ssync copy-output JOB_ID DESTINATION`

Copy output files into a local directory. `--output-type [stdout|stderr|both]`, `--compressed` to keep `.gz` files, `--overwrite` to replace existing files.

## Watchers

### `ssync watchers`

| Subcommand | Description |
| --- | --- |
| `list` | List watchers. |
| `events` | Show watcher events. |
| `stats` | Watcher statistics. |
| `monitor` | Real-time monitoring dashboard in the terminal. |
| `attach` | Attach watchers to an existing job. |
| `pause` / `resume` | Pause or resume a watcher. |
| `trigger` | Run a watcher's actions now. |
| `cleanup` | Remove watchers for finished or missing jobs. |

See the [Watchers guide](../guides/watchers.md).

## Servers

### `ssync web`

Start the API and web app together, in the background, at `https://localhost:8042`.

| Option | Description |
| --- | --- |
| `--port INTEGER` | Port, default `8042`. |
| `--host TEXT` | Address to bind, default `127.0.0.1`. |
| `--no-https` | Serve over HTTP. |
| `--foreground` | Run in the foreground. |
| `--no-browser` | Do not open a browser. |
| `--skip-build` | Skip the frontend build check. |
| `--status` / `--stop` | Check or stop the running server. |

### `ssync api`

Start only the API, for the iPhone app and extensions. `--port`, `--host`, `--no-https`, `--stop`, and `--logs`.

### `ssync auth`

Manage API keys: `setup`, `show`, `test`, `migrate`, `disable`. See [Security](security.md).
