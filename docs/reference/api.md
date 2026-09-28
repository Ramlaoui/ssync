---
description: The ssync REST and WebSocket API used by the web app, iPhone app, and extensions.
---

# API

Everything the apps do goes through a REST and WebSocket API served by `ssync web` or `ssync api`. You can use it from your own scripts too.

The server is a FastAPI application. Start it with `SSYNC_ENABLE_DOCS=true` to browse interactive documentation at `https://localhost:8042/docs`.

## Authentication

When API keys are required (see [Security](security.md)), send the key in the `X-API-Key` header:

```bash
curl --cacert ~/.config/ssync/certs/cert.pem \
  -H "X-API-Key: $SSYNC_API_KEY" \
  https://localhost:8042/api/status
```

The certificate path above is where `ssync web` stores its self-signed certificate. In a quick local test you can use `curl -k` instead.

## Examples

=== "Python"

    ```python
    import httpx

    client = httpx.Client(
        base_url="https://localhost:8042",
        headers={"X-API-Key": "your-api-key"},
        verify=False,  # or the path to ~/.config/ssync/certs/cert.pem
    )

    # Running and pending jobs on one host
    status = client.get("/api/status", params={"host": "my-cluster"}).json()

    # The last 50 lines of a job's stdout
    output = client.get("/api/jobs/12345/output",
                        params={"host": "my-cluster", "output_type": "stdout", "lines": 50}).json()
    print(output["stdout"])
    ```

=== "curl"

    ```bash
    curl -k -H "X-API-Key: $SSYNC_API_KEY" \
      "https://localhost:8042/api/jobs/12345/output?host=my-cluster&lines=50"
    ```

## Endpoints

### Jobs

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/status` | Jobs across hosts. Filters: `host`, `user`, `since`, `state`, `job_ids`, `active_only`, `completed_only`, `search`, `limit`. |
| GET | `/api/jobs/{job_id}` | One job's details (`host` query parameter). |
| GET | `/api/jobs/{job_id}/output` | Output content; `output_type`, `lines`, `max_bytes`, `metadata_only`. |
| GET | `/api/jobs/{job_id}/output/stream` | Live output as Server-Sent Events. |
| GET | `/api/jobs/{job_id}/output/download` | Download an output file, optionally compressed. |
| GET | `/api/jobs/{job_id}/script` | The submitted batch script. |
| GET | `/api/jobs/{job_id}/manifest` | The launch manifest of a recipe-submitted job. |
| GET | `/api/jobs/{job_id}/data` | Job info, script, and outputs in one request. |
| POST | `/api/jobs/{job_id}/cancel` | Cancel a job. |
| POST | `/api/jobs/launch` | Sync and submit a job. |
| GET | `/api/launches/{launch_id}` | Progress of a launch. |
| GET | `/api/launches/{launch_id}/events` | Launch progress as Server-Sent Events. |

### Hosts

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/hosts` | Configured hosts and their default Slurm settings. |
| GET / PUT | `/api/hosts/{hostname}/settings` | Read or update a host's default Slurm settings. |
| GET | `/api/partitions` | Partition capacity across hosts. |

### Watchers

| Method | Path | Description |
| --- | --- | --- |
| GET / POST | `/api/watchers` | List or create watchers. |
| PUT / DELETE | `/api/watchers/{watcher_id}` | Update or delete a watcher. |
| POST | `/api/watchers/{watcher_id}/pause` | Pause a watcher. |
| POST | `/api/watchers/{watcher_id}/resume` | Resume a watcher. |
| POST | `/api/watchers/{watcher_id}/trigger` | Run a watcher's actions now. |
| GET | `/api/watchers/events` | Recent watcher events; filter by `job_id` or `watcher_id`. |
| GET | `/api/watchers/stats` | Totals by state and action. |
| GET / POST | `/api/jobs/{job_id}/watchers` | Watchers of one job, or attach new ones. |

### Real-time updates

| Path | Description |
| --- | --- |
| `/ws/jobs` | WebSocket with an initial snapshot and job state changes across hosts. |
| `/ws/jobs/{job_id}` | Updates for one job. |
| `/ws/watchers` | Watcher changes and events. |

### Notifications

Endpoints under `/api/notifications/` register devices for push notifications (Apple Push Notification service and Web Push), manage preferences, and send test notifications.
