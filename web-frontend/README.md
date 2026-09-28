# Slurm Manager Web Interface

A modern Svelte web interface for monitoring and managing Slurm jobs across multiple clusters.

## Features

- **Real-time Job Monitoring**: Live updates every 30 seconds
- **Multi-Host Support**: Monitor jobs across multiple Slurm clusters
- **Advanced Filtering**: Filter by user, time range, job state, etc.
- **Job Details**: Detailed view with resource allocation, timing, and file paths
- **Output Viewing**: View stdout and stderr directly in the browser
- **Responsive Design**: Works on desktop and mobile devices

## Setup

### Prerequisites

- Node.js (v16 or higher)
- Running Slurm Manager API backend

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

### API Configuration

The frontend expects the Slurm Manager API to be running on `http://localhost:8000`. 

To start the API backend:

```bash
# From the main project directory
python -m ssync.web.app
# or if installed:
ssync-web
```

## Usage

1. **Start the API**: Run the FastAPI backend
2. **Start the UI**: Run `npm run dev` 
3. **Open browser**: Navigate to `http://localhost:5173`
4. **Monitor jobs**: View jobs across your configured Slurm hosts

## API Endpoints Used

- `GET /hosts` - List configured Slurm hosts
- `GET /status` - Get job status with filtering
- `GET /jobs/{job_id}` - Get detailed job information
- `GET /jobs/{job_id}/output` - Get job output files
- `POST /jobs/{job_id}/cancel` - Cancel a running job

## Development

The interface is built with:

- **Svelte 4** - Reactive UI framework
- **Vite** - Build tool and dev server
- **Axios** - HTTP client for API calls

### Project Structure

```
src/
├── main.ts                 # Application entry point
├── App.svelte              # Shell: sidebar, top bar, routes, quick find
├── pages/                  # Jobs, job detail, launch, watchers, hosts, settings
├── components/             # Output/script viewers, launcher, watcher UI
│   └── workspace/          # Shared job overview, activity, status, buttons
├── lib/                    # Job state manager, presentation helpers, actions
├── stores/                 # Preferences, workspace, watchers, theme
└── services/               # API client and realtime connections
```

## Configuration

The Vite development server proxies API requests to `http://localhost:8000`. 

For production deployment, configure your web server to proxy `/api` requests to the Slurm Manager API backend.
