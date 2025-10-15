# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ssync** is a SLURM cluster manager that enables local development with seamless deployment and job management across multiple SSH-enabled SLURM clusters. It provides both CLI and web interfaces for syncing code, submitting jobs, and monitoring results.

## Architecture

### Backend (Python)
- **Core Module**: `src/ssync/` - Python package using FastAPI for web server
- **CLI Entry Point**: `ssync` - Main CLI with subcommands:
  - `ssync status/sync/submit/launch` - Job management operations
  - `ssync web` - Launch web interface (API + UI)
  - `ssync api` - Start API server only
  - `ssync auth` - Manage authentication
- **Key Components**:
  - `manager.py` - SLURM job management and SSH connections
  - `sync.py` - Rsync-based file synchronization with gitignore support
  - `launch.py` - Integrated job launch workflow (sync + submit)
  - `cache.py` - SQLite-based persistent caching for job scripts
  - `script_processor.py` - Structured script format handling with login/compute node separation
  - `web/app.py` - FastAPI server with WebSocket support for real-time updates
  - `web/security.py` - Authentication, rate limiting, and input validation
  - `slurm/client.py` - SLURM command interface and job management
  - `slurm/parser.py` - SLURM output parsing utilities

### Frontend (Svelte/TypeScript)
- **Location**: `web-frontend/`
- **Framework**: Svelte 4 with TypeScript and Vite
- **State Management**: Svelte stores in `src/stores/`
- **Components**: Modular UI components in `src/components/`
- **API Client**: Axios-based with WebSocket for real-time job updates

### Structured Script Format
Scripts can use `#LOGIN_SETUP_BEGIN` and `#LOGIN_SETUP_END` markers to separate login node setup commands from compute node execution. This is crucial for clusters without internet access on compute nodes.

## Development Commands

### Backend
```bash
# Install dependencies (using uv)
uv pip install -e .

# Run linting and formatting
ruff check src/
ruff format src/

# Type checking (no mypy configured currently)
# Tests (pytest is installed but no tests exist yet)

# Start complete web interface with HTTPS (serves API + UI on same port)
ssync web  # Builds frontend if needed, serves everything on port 8042 with HTTPS

# Start with HTTP instead
ssync web --no-https

# Start API server only (no UI)
ssync api  # or python -m ssync.web.app

# CLI usage examples
ssync status --host <hostname>
ssync sync <source_dir> --host <hostname>
ssync submit <script.sh> --host <hostname>
ssync launch <script.sh> <source_dir> --host <hostname>
```

### Frontend
```bash
cd web-frontend

# Install dependencies
npm install

# Development server (hot reload)
npm run dev

# Type checking
npm run check

# Production build
npm run build

# Preview production build
npm run preview
```

## Configuration

Configuration file location: `~/.config/ssync/config.yaml` (or `config.yaml` in project root for development)

Key configuration structure:
- `hosts`: List of SLURM hosts with SSH connection details
- `work_dir`: Remote working directory for job execution
- `slurm_defaults`: Default SLURM parameters (partition, account, resources, etc.)
- `api_key`: Optional API key for web API authentication

## Key Technical Details

### Job Caching System
- Jobs and their scripts are cached in SQLite database (`~/.config/ssync/cache.db`)
- Cache middleware preserves scripts even after jobs complete
- Script retrieval priority: Cache first, then SLURM query
- Configurable cleanup policies and size limits

### Sync Process
- Uses rsync with `.gitignore` awareness via `--filter` flags
- Validates directory size before sync to prevent accidental large transfers
- Supports include/exclude patterns
- Preserves symlinks and permissions

### WebSocket Protocol
- Real-time job status updates at `/ws/jobs/{job_id}`
- Log streaming for running jobs
- Bi-directional communication for interactive features
- Automatic reconnection with exponential backoff

### SSH Connection Management
- Connection pooling with fabric library
- Support for SSH config aliases and manual configuration
- Password and key-based authentication
- Connection timeout and retry mechanisms

### Security Features
- API key authentication (optional but recommended)
- Rate limiting per IP/API key (100 requests/minute burst, 10 requests/minute sustained)
- Path traversal protection with strict validation
- Script content validation and size limits
- Input sanitization for SLURM parameters
- Host header injection protection
- HTTPS with self-signed certificates by default

## Mobile UI Considerations
The script editor in `ScriptPreview.svelte` needs redesign for mobile devices - consider configuration-based approach rather than text editing on small screens.

## Critical Files for Understanding

1. **Backend Flow**: `src/ssync/launch.py` - Shows complete job launch workflow
2. **Web API**: `src/ssync/web/app.py` - All API endpoints and WebSocket handlers
3. **Security**: `src/ssync/web/security.py` - Authentication and validation logic
4. **Frontend State**: `web-frontend/src/stores/jobLaunch.ts` - Job launch validation logic
5. **Job Display**: `web-frontend/src/components/JobDetail.svelte` - Real-time job monitoring UI
6. **SLURM Integration**: `src/ssync/slurm/client.py` - Core SLURM command execution