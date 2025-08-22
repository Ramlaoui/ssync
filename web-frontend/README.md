# SLURM Manager Web Interface

A modern Svelte web interface for monitoring and managing SLURM jobs across multiple clusters.

## Features

- **Real-time Job Monitoring**: Live updates every 30 seconds
- **Multi-Host Support**: Monitor jobs across multiple SLURM clusters
- **Advanced Filtering**: Filter by user, time range, job state, etc.
- **Job Details**: Detailed view with resource allocation, timing, and file paths
- **Output Viewing**: View stdout and stderr directly in the browser
- **Responsive Design**: Works on desktop and mobile devices

## Setup

### Prerequisites

- Node.js (v16 or higher)
- Running SLURM Manager API backend

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

The frontend expects the SLURM Manager API to be running on `http://localhost:8000`. 

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
4. **Monitor jobs**: View jobs across your configured SLURM hosts

## API Endpoints Used

- `GET /hosts` - List configured SLURM hosts
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
├── App.svelte              # Main application component
├── main.js                 # Application entry point
└── components/
    ├── FilterPanel.svelte  # Job filtering controls
    ├── JobList.svelte      # Job table display
    └── JobDetail.svelte    # Detailed job view
```

## Configuration

The Vite development server proxies API requests to `http://localhost:8000`. 

For production deployment, configure your web server to proxy `/api` requests to the SLURM Manager API backend.