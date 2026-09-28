---
description: Configure ssync hosts, SSH connections, per-cluster Slurm defaults, caching, and timeouts.
---

# Configuration

ssync reads one YAML file, by default `~/.config/ssync/config.yaml`. Point it elsewhere with `SSYNC_CONFIG_PATH=/path/to/config.yaml`, or set `XDG_CONFIG_HOME`.

A complete example lives in the repository as [`config.example.yaml`](https://github.com/Ramlaoui/ssync/blob/main/config.example.yaml).

## Hosts

Each entry under `hosts` is one cluster.

```yaml
hosts:
  - hostname: my-cluster              # alias from ~/.ssh/config, or a DNS name
    work_dir: /home/your-username/work
    scratch_dir: /scratch/your-username
```

| Field | Required | Description |
| --- | --- | --- |
| `hostname` | yes | An alias from `~/.ssh/config` (recommended) or a hostname. This is also the name ssync shows for the host. |
| `work_dir` | yes | Remote directory projects are synced into. `ssync launch job.sh ./my-project` syncs to `<work_dir>/my-project`. |
| `scratch_dir` | yes | Remote scratch space. ssync keeps a small cache under `<scratch_dir>/.cache/ssync`. |
| `username` | no | Only needed when not using SSH config. |
| `port` | no | SSH port, default `22`. |
| `key_file` | no | Private key path when not using SSH config. |
| `use_ssh_config` | no | Default `true`. Set `false` to connect only with the fields above. |
| `password` | no | Avoid when possible; if you must, reference an environment variable: `password: ${CLUSTER_PASSWORD}`. |
| `slurm_defaults` | no | Your usual Slurm settings for this host, shown in the apps (below). |

!!! tip "Prefer your SSH config"
    Using an alias from `~/.ssh/config` means ssync inherits your keys, `ProxyJump` bastions, `ControlMaster` multiplexing, and usernames, exactly as your terminal does.

### Connecting without SSH config

```yaml
hosts:
  - hostname: login.cluster.example.edu
    username: your-username
    port: 22
    key_file: ~/.ssh/cluster_key
    use_ssh_config: false
    work_dir: /home/your-username/projects
    scratch_dir: /scratch/your-username
```

## Slurm defaults per host

`slurm_defaults` records the settings you normally use on a host. The API exposes them to the apps, where they appear in host settings and can be edited (for example from Raycast's **Hosts & Defaults**).

!!! note
    `ssync launch` does not currently inject these defaults into your script. Keep the `#SBATCH` lines a job needs in the script itself, or pass them as options such as `--partition` and `--time`.

```yaml
hosts:
  - hostname: gpu-cluster
    work_dir: /home/your-username/work
    scratch_dir: /scratch/your-username
    slurm_defaults:
      partition: gpu
      account: my-project
      qos: normal
      constraint: a100
      cpus: 8                 # CPUs per task
      mem: 64                 # GB
      time: "04:00:00"        # HH:MM:SS or minutes
      nodes: 1
      ntasks_per_node: 1
      gpus_per_node: 1
      gres: "gpu:1"
      job_name_prefix: "exp"
      output_pattern: "logs/%x_%j.out"
      error_pattern: "logs/%x_%j.err"
      python_env: "source .venv/bin/activate"
```

## Cache

ssync caches job metadata, scripts, and outputs locally so you can still inspect jobs after Slurm forgets them.

```yaml
cache:
  enabled: true
  cache_dir: ~/.cache/ssync
  max_age_days: 365            # 0 keeps entries forever
  script_max_age_days: 0       # keep submitted scripts forever, for reproducibility
  max_size_mb: 1024
  auto_cleanup: false
```

## Connections

```yaml
connections:
  connect_timeout: 5      # seconds to establish SSH per host
  command_timeout: 120    # seconds for remote commands
```

## Environment variables

| Variable | Effect |
| --- | --- |
| `SSYNC_CONFIG_PATH` | Use a different config file. |
| `SSYNC_API_KEY` | API key used by the server and clients. See [Security](../reference/security.md). |
| `SSYNC_REQUIRE_API_KEY` | Set to `true` to require an API key on every request. |
| `SSYNC_ENABLE_DOCS` | Set to `true` to serve interactive API docs at `/docs`. |
| `SSYNC_PRIORITY_SNAPSHOT_TTL_SECONDS` | How long a per-host pending-queue snapshot is reused for queue positions (default 60, minimum 5). |
