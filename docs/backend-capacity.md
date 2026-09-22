# Backend capacity and responsiveness

Heavy filesystem scans, SQLite work, SSH commands, launches, and log decoding
used to contend with the API event loop or an unbounded thread queue. Requests
could also copy cached log blobs while only asking for job metadata. This change
isolates these workloads and rejects excess work before it builds a large queue.

## Defaults

| Work | Workers | Queued calls |
| --- | ---: | ---: |
| Local cache/filesystem/serialization | 4 | 64 |
| Interactive SSH | up to 8 by default | 16 |
| Background refresh SSH | 4 | 16 |
| Launch | 2 | 4 |
| Output decoding | 2 | 8 |
| File transfers and archiving | 2 | 4 |

Existing `SSYNC_THREAD_POOL_SIZE`, `SSYNC_BACKGROUND_THREAD_POOL_SIZE`, and
`SSYNC_LAUNCH_THREAD_POOL_SIZE` overrides still apply. Worker counts are not SSH
host limits: all SSH/SCP still passes through the existing per-host command slot
(default 8, with the existing global/per-host overrides) and ControlMaster reuse.

Admission also bounds response lifetimes: 64 ordinary requests, 8 output/data
requests, 16 streams/downloads/events, 2 filesystem/catalog scans, 2 manual watcher
scans, and 64 WebSockets. Health checks bypass these budgets. Six launches may be
active or queued. HTTP overload returns **503 with `Retry-After: 1`**; excess WebSockets
close with code 1013. A slow reader retains its streaming reservation until the
response closes. `/api/cache/stats` includes worker capacities, outstanding work,
and rejection counters.

Cancelled queued calls retain their queue slot until a worker dequeues them.
Running calls retain it until the thread finishes. A timed-out host refresh keeps
its host reservation while the SSH operation is still running; subsequent
requests use cached results and existing backoff. Shared fetches survive a
viewer disconnecting. Forced output refresh waits behind a normal refresh rather
than starting a simultaneous transfer for the same job.

The request coalescer drains one worker per host in batches of at most 50 jobs,
with at most 256 outstanding unique requests. Arrivals during a running batch are
included in a subsequent batch. Existing status/priority snapshot caches,
watcher throttling, polling intervals, and failed-query backoff remain in place.
Missing or inaccessible files do not reset ControlMaster or retry authentication.
Completion-output markers survive metadata refreshes, preventing repeated fetches
of already archived logs.

## Output and cache memory

Status and script reads select metadata without copying output blobs. WAL readers
can proceed while another thread writes the cache. Output previews decode gzip
in 64 KiB chunks and retain only the requested byte/line window. Full output and
complete-job JSON responses stream escaped UTF-8 chunks. Downloads stream binary
chunks, including when decompression is required.

Background log harvesting and uncached downloads transfer through temporary
files and incrementally compress/store complete logs. Uncached terminal SSE
previews use the same shared archive, avoiding whole base64 response buffers.
This shifts large transfers to disk; enough
space is still required for temporary files and the persistent cache. SQLite
output readers use incremental blobs rather than loading the compressed file
into Python memory. The callback-based SSH launch path retains at most 1 MiB of
stdout and stderr diagnostics while forwarding the complete output to callbacks.
Launch events apply their backlog limit before scheduling a loop callback, with
one pending wakeup and bounded fragments even for output without newlines.
Notification cache work also runs off the event loop. At most 64 notification
batches are pending; producers wait for space, and admitted batches wait for
local cache capacity without dropping transitions during a burst.
Accepted notification batches drain during shutdown so durable claims cannot
be stranded before dispatch. Watcher action admission checks cancellation and
shutdown before starting work, and refresh callbacks are bounded before they
enter the event loop.

Watcher cache fallback reads also decode only the next byte window. Manual scans
retain at most 8 MiB of selected output and return **413** when it is larger;
the same limit applies to uploaded test samples before JSON parsing. The limit
is explicit because arbitrary regular expressions can span the entire input.
Automatic watchers continue reading incrementally. Watcher patterns use
[`regex` VERSION0](https://pypi.org/project/regex/) for standard-pattern
compatibility, concurrent matching, and a two-second matching time budget.
Patterns that exceed the budget disable the watcher and report the reason.
This also prevents a pathological regex from holding Python's interpreter lock
and freezing unrelated requests.

## Reproduce the local measurements

```sh
uv run --no-sync python benchmarks/backend_load.py
uv run --no-sync python benchmarks/backend_mixed_load.py
uv run --no-sync pytest
cd web-frontend
npm run check
npm run test:run
npm run build
```

To compare another checkout without reinstalling it, run the same benchmark with
`PYTHONPATH=/path/to/checkout/src` and the same uv environment. Recorded results
are in [`backend-before.json`](../benchmarks/results/backend-before.json) and
[`backend-after.json`](../benchmarks/results/backend-after.json). The before
checkout is commit `a0141c8860f224938a899b3306eb620f36a19453`; the after measurement
uses this branch. Both workloads make **no SSH connections**.

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| Median health scheduling delay during a 250 ms catalog scan (5 samples) | 241.114 ms | 1.097 ms |
| Peak Python allocations: 64 MiB gzip log, 512 KiB preview | 141.662 MiB | 1.870 MiB |
| Peak Python allocations: metadata for 32 jobs storing 32 MiB of logs | 32.136 MiB | 0.089 MiB |

Allocation figures use `tracemalloc`; they are not total process RSS. These are
controlled local checks, not production throughput or live-cluster measurements.
Concurrency tests additionally gate slow workers and verify responsive local and
health routes, retryable overload, cancellation, batch arrivals, shared fetches,
WAL read isolation, and recovery after the blocked work finishes.

The separate-process [mixed-load probe](../benchmarks/backend_mixed_load.py)
uses the production admission/worker defaults with a temporary cache and private
localhost HTTP server. It fills all 24 interactive, 20 background, and 6 transfer
slots with gated synthetic work, requests cached metadata/previews concurrently,
and downloads four complete 64 MiB logs, two as gzip and two decompressed by the
server. The client incrementally checks every download's SHA-256; its checksum
and gzip decompression work is kept off the
latency-measurement loop. Raw fixture setup buffers are freed before RSS sampling.

The [recorded run](../benchmarks/results/backend-mixed-load.json) returned 95/95
health checks successfully, with **1.408 ms p95** and **3.199 ms maximum** latency.
All 16 metadata and 16 preview requests succeeded. Server RSS rose from
**61,320 KiB to 72,208 KiB** during the workload, measured from the child server's
`/proc` entry. Each saturated worker pool rejected three excess requests with
503 and `Retry-After: 1`; after release, all executor and admission counters
returned to zero and follow-up requests succeeded. This is a local synthetic
measurement with no SSH traffic, not a live-server throughput guarantee.

The test updates also repair pre-existing test drift: old references to the
removed monolithic web route helpers now exercise registered endpoints and the
current service modules. Frontend-route tests create their own temporary build
fixture. Launch traceback capture explicitly restores logger propagation changed
by earlier CLI tests, preserving the traceback assertion across the full suite.

Final validation: **715 backend tests passed, 2 existing timing-related tests
skipped**; **147 frontend tests passed, 1 skipped**. Changed Python files pass
Ruff and formatting checks; Svelte checking reports no errors or warnings, and
the production frontend build succeeds. The build still reports its existing
bundle-size and stale browser-data advisories. Automated tests and synthetic
benchmarks above do not contact live SSH hosts.

A subsequent read-only observation of the running backend on this branch on
2026-09-22 returned **45/45 successful health checks over 45.79 seconds**, with
**2.168 ms p95** and **5.620 ms maximum** latency. RSS ranged from **316.83 to
317.84 MiB**, and sampled worker-pool rejection counters were all zero. This
short observation does not establish long-term memory stability. Runtime logs
also contained repeated watcher resubmission/dependency failures and host Slurm
availability warnings; those failures remain unresolved by this performance
change. The check queried only local health, cache statistics, and existing logs.
