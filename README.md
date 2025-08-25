# ssync

A tool for managing SLURM job workflows across multiple HPC clusters. ssync bridges local development environments with remote SLURM systems, for unified job submission, monitoring, and file synchronization capabilities.

## Overview

ssync helps researchers and developers working with SLURM-based HPC systems by providing:

- **Local Development** - Maintain your development workflow on local machines
- **Automated Deployment** - Synchronize code to multiple clusters for quick prototyping
- **Job Management** - Submit and monitor jobs without manual SSH sessions to each cluster
- **Monitoring** - Track job status and outputs across all configured clusters from a single interface
- **Web Interface** - UI for job submission and monitoring

## Installation

```bash
uv pip install git+https://github.com/Ramlaoui/ssync.git
```

## Configuration

Create a configuration file at `~/.config/ssync/config.yaml`:

```yaml
hosts:
  - name: cluster1
    hostname: login.cluster1.edu
    username: your_username
    work_dir: /scratch/your_username/projects
    
  - name: cluster2  
    hostname: hpc.university.edu
    username: your_username
    work_dir: /home/your_username/work

    # Optional: Default SLURM parameters for a given cluster
    # These can be overridden in job scripts / cli submissions
    slurm_defaults:
    partition: gpu
    time: 60  # minutes
    cpus: 4
    mem: 16  # GB
```

## Command Line Interface

### Job Status Monitoring
```bash
# View all jobs across clusters
ssync status

# Filter by specific host
ssync status --host cluster1

# Show only running jobs
ssync status --state R

# Display recent completed jobs
ssync status --since 1d
```

### File Synchronization
```bash
# Sync local directory to remote cluster
ssync sync ./project-dir --host cluster1

# Exclude specific patterns
ssync sync ./project-dir --host cluster1 --exclude "*.log"
```

### Job Submission
```bash
# Submit a job script
ssync submit job.sh --host cluster1

# Combined sync and submit operation
ssync launch job.sh ./project-dir --host cluster1
```

### Output Retrieval
```bash
# View job output
ssync status --job-id 12345 --cat-output
```

## Web Interface

Launch the complete web interface (serves both API and UI):
```bash
# Start in background with HTTPS (default)
ssync web

# Use HTTP instead of HTTPS
ssync web --no-https

# Stop the server
ssync web --stop

# Check if running
ssync web --status

# Run in foreground for debugging
ssync web --foreground
```

The `ssync web` command:
- Uses HTTPS by default with auto-generated self-signed certificates
- Runs in the background by default (doesn't block your terminal)
- Builds the frontend automatically if needed
- Serves both API and UI on the same port
- Opens your browser automatically

Access at https://localhost:8042

**Note on HTTPS**: The first time you access the site, your browser will warn about the self-signed certificate. This is normal for local development. Accept the certificate to proceed.

For API-only mode (no UI):
```bash
ssync api
```

Features include:
- Real-time job status dashboard
- Interactive script editor with SLURM directive validation
- Directory browser for source selection
- Job submission interface
- Live log streaming for running jobs

## Advanced Features

### Structured Script Format

ssync supports a structured script format that separates login node setup from compute node execution. This is particularly useful for clusters where compute nodes lack internet access:

```bash
#!/bin/bash
#SBATCH --job-name=experiment
#SBATCH --time=2:00:00

#LOGIN_SETUP_BEGIN
# Commands executed on login node
pip install -r requirements.txt
module load cuda/11.4
#LOGIN_SETUP_END

# Compute node execution
python train.py --epochs 100
```

### Version Control Integration

The synchronization process automatically respects `.gitignore` patterns, preventing unnecessary transfer of build artifacts, virtual environments, and other excluded files.

### Persistent Job Information

Job scripts and metadata are cached locally, allowing retrieval of job information even after SLURM's job history expiration.

## API Usage

ssync provides a REST API for programmatic access:

```python
import requests

# Query job status
response = requests.get("https://localhost:8042/api/status", verify=False)  # verify=False for self-signed cert
jobs = response.json()

# Submit a job
response = requests.post("https://localhost:8042/api/jobs/launch", json={
    "host": "cluster1",
    "script_content": "#!/bin/bash\npython train.py",
    "source_dir": "/path/to/project"
})
```

## Security

For production deployments or multi-user environments, enable API authentication:

```bash
# Generate API key
ssync auth setup

# Enable authentication requirement
export SSYNC_REQUIRE_API_KEY=true
ssync api
```

## System Requirements

- Python 3.11 or higher
- SSH access to target SLURM clusters
- rsync (typically pre-installed on Unix systems)

## Development

To modify the web interface:

```bash
cd web-frontend
npm install
npm run dev  # Development server with hot reload
npm run build  # Production build
```

## Troubleshooting

### SSH Connectivity
- Verify SSH access: `ssh <cluster-hostname>`
- Configure SSH keys for passwordless access: `ssh-copy-id <cluster-hostname>`

### Synchronization Performance
- Review `.gitignore` patterns for large file exclusions
- Use `--exclude` flag for additional pattern-based filtering

### Job Output Access
- Ensure job completion before attempting output retrieval
- Verify `work_dir` configuration matches actual job execution directory

## Contributing

Contributions are welcome. Please submit issues and pull requests through the project repository.

## License

Apache 2.0 - See [LICENSE](LICENSE) file for details.
