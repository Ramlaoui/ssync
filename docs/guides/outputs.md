---
description: Read, follow, and copy Slurm job output from the CLI, web app, and iPhone.
---

# Job output

ssync finds a job's stdout and stderr files for you, on whichever host the job ran, and caches what it reads so outputs stay available after the job is gone from Slurm.

## From the command line

```bash
ssync output 12345                # the end of stdout (bounded, for speed)
ssync output 12345 --lines 200    # the last 200 lines
ssync output 12345 --stderr       # stderr instead
ssync output 12345 --both         # both streams
ssync output 12345 --all          # the complete file
ssync output 12345 --force-refresh
```

ssync looks up which host the job ran on. Add `--host` if the same job ID exists on more than one cluster.

To save output files locally:

```bash
ssync copy-output 12345 ./results                   # stdout and stderr
ssync copy-output 12345 ./results --output-type stderr
ssync copy-output 12345 ./results --compressed      # keep them gzip-compressed
```

## In the web app

A job's **Output** tab streams new lines as the job writes them. Search within the output, follow the end of the file, or scroll back through history. The overview also shows the latest lines, so you can check on progress at a glance.

![Live output in the web app](../assets/screenshots/web-job-output.webp){ .ss-shot }

## On iPhone

Swipe right on any job, or tap its output preview, to read output full screen. Switch between stdout and stderr at the bottom and search from the toolbar.

<div class="ss-phones" markdown>
![Live output on iPhone](../assets/screenshots/ios-output.webp)
</div>
