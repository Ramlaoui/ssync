---
description: Install ssync on macOS or Linux with uv, including the web app.
---

# Installation

ssync runs on your own computer (macOS or Linux) and reaches your clusters over SSH. Nothing needs to be installed on the clusters themselves beyond Slurm and `rsync`, which they almost always have.

## Requirements

**On your computer**

- Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/) (recommended)
- SSH access to your clusters, ideally with keys
- `rsync`
- Node.js 18 or newer, only for the web app's first build

**On each cluster**

- Slurm (`sbatch`, `squeue`, `sacct`, `scancel`)
- `rsync`

!!! warning "Install from GitHub, not PyPI"
    The package called `ssync` on PyPI is an unrelated project. Always install ssync from its GitHub repository as shown below.

## Install ssync

=== "Full install (recommended)"

    Clone the repository and install it as an editable tool. This gives you the CLI **and** the web app, which is built from the repository the first time you run `ssync web`.

    ```bash
    git clone https://github.com/Ramlaoui/ssync.git
    cd ssync
    uv tool install --editable .
    ```

    To update later, pull the repository: `git pull`. The `ssync` command picks up the changes immediately.

=== "CLI only"

    If you only want the command line, you can install directly from GitHub:

    ```bash
    uv tool install git+https://github.com/Ramlaoui/ssync.git
    ```

    This install does not include the web app, because the frontend lives outside the Python package. Use the full install if you want `ssync web`.

=== "pip"

    Without uv, use a virtual environment:

    ```bash
    git clone https://github.com/Ramlaoui/ssync.git
    cd ssync
    python -m venv .venv && source .venv/bin/activate
    pip install -e .
    ```

Check that it works:

```bash
ssync --help
```

## Next steps

<div class="grid cards" markdown>

-   :material-flash-outline: __[Quickstart](quickstart.md)__

    Connect your first cluster and see your jobs in five minutes.

-   :material-cog-outline: __[Configuration](configuration.md)__

    Hosts, per-cluster Slurm defaults, caching, and timeouts.

</div>
