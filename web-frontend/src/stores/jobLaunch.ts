import { writable, derived, get } from 'svelte/store';
import type { HostInfo } from '../types/api';

// Types for our store
export interface JobLaunchConfig {
  // Host and directory
  selectedHost: string;
  sourceDir: string;
  
  // Script configuration
  scriptSource: 'editor' | 'local' | 'upload';
  scriptContent: string;
  localScriptPath: string;
  uploadedScriptName: string;
  
  // SLURM parameters
  jobName: string;
  partition: string;
  constraint: string;
  account: string;
  cpus: number;
  useMemory: boolean;
  memory: number; // GB
  timeLimit: number; // minutes
  nodes: number;
  ntasksPerNode: number;
  gpusPerNode: number;
  gres: string;
  outputFile: string;
  errorFile: string;
  pythonEnv: string;
  
  // Sync settings
  excludePatterns: string[];
  includePatterns: string[];
  noGitignore: boolean;
}

export interface JobLaunchState {
  config: JobLaunchConfig;
  hosts: HostInfo[];
  loading: boolean;
  launching: boolean;
  error: string | null;
  success: string | null;
}

// Initial state
const initialConfig: JobLaunchConfig = {
  selectedHost: '',
  sourceDir: '',
  scriptSource: 'editor',
  scriptContent: '#!/bin/bash\n\n# Your script here\necho "Hello, SLURM!"',
  localScriptPath: '',
  uploadedScriptName: '',
  jobName: '',
  partition: '',
  constraint: '',
  account: '',
  cpus: 1,
  useMemory: false,
  memory: 4,
  timeLimit: 60,
  nodes: 1,
  ntasksPerNode: 1,
  gpusPerNode: 0,
  gres: '',
  outputFile: '',
  errorFile: '',
  pythonEnv: '',
  excludePatterns: ['*.log', '*.tmp', '__pycache__/'],
  includePatterns: [],
  noGitignore: false
};

const initialState: JobLaunchState = {
  config: initialConfig,
  hosts: [],
  loading: false,
  launching: false,
  error: null,
  success: null
};

// Create the main store
export const jobLaunchStore = writable<JobLaunchState>(initialState);

// Individual config stores for easier component binding
export const config = writable<JobLaunchConfig>(initialConfig);
export const hosts = writable<HostInfo[]>([]);
export const loading = writable<boolean>(false);
export const launching = writable<boolean>(false);
export const error = writable<string | null>(null);
export const success = writable<string | null>(null);

// Sync individual stores with main store
config.subscribe(configValue => {
  jobLaunchStore.update(state => ({ ...state, config: configValue }));
});

hosts.subscribe(hostsValue => {
  jobLaunchStore.update(state => ({ ...state, hosts: hostsValue }));
});

loading.subscribe(loadingValue => {
  jobLaunchStore.update(state => ({ ...state, loading: loadingValue }));
});

launching.subscribe(launchingValue => {
  jobLaunchStore.update(state => ({ ...state, launching: launchingValue }));
});

error.subscribe(errorValue => {
  jobLaunchStore.update(state => ({ ...state, error: errorValue }));
});

success.subscribe(successValue => {
  jobLaunchStore.update(state => ({ ...state, success: successValue }));
});

// Derived store for generated SLURM script
export const generatedScript = derived(
  config,
  ($config) => generateSlurmScript($config)
);

// Derived store for validation
export const isValid = derived(
  config,
  ($config) => {
    return $config.selectedHost && $config.sourceDir && (
      ($config.scriptSource === 'editor' && $config.scriptContent.trim()) ||
      ($config.scriptSource === 'local' && $config.localScriptPath.trim()) ||
      ($config.scriptSource === 'upload' && $config.uploadedScriptName)
    );
  }
);

// Action creators for updating specific parts of config
export const jobLaunchActions = {
  // Host and directory actions
  setSelectedHost: (host: string) => {
    config.update(c => ({ ...c, selectedHost: host }));
  },
  
  setSourceDir: (dir: string) => {
    config.update(c => ({ ...c, sourceDir: dir }));
  },
  
  // Script actions
  setScriptConfig: (scriptConfig: { source: string; content: string; localPath?: string; uploadedName?: string }) => {
    config.update(c => ({
      ...c,
      scriptSource: scriptConfig.source as 'editor' | 'local' | 'upload',
      scriptContent: scriptConfig.content,
      localScriptPath: scriptConfig.localPath || '',
      uploadedScriptName: scriptConfig.uploadedName || ''
    }));
  },

  // Set script content directly (for manual edits)
  setScriptContent: (content: string) => {
    config.update(c => ({
      ...c,
      scriptContent: content,
      scriptSource: 'editor' // Switch to editor mode when manually editing
    }));
  },
  
  // Job config actions
  updateJobConfig: (jobConfig: Partial<JobLaunchConfig>) => {
    config.update(c => ({ ...c, ...jobConfig }));
  },
  
  // Sync settings actions
  setSyncSettings: (syncSettings: { excludePatterns: string[]; includePatterns: string[]; noGitignore: boolean }) => {
    config.update(c => ({
      ...c,
      excludePatterns: syncSettings.excludePatterns,
      includePatterns: syncSettings.includePatterns,
      noGitignore: syncSettings.noGitignore
    }));
  },
  
  // State management actions
  setLoading: (isLoading: boolean) => loading.set(isLoading),
  setLaunching: (isLaunching: boolean) => launching.set(isLaunching),
  setError: (errorMessage: string | null) => error.set(errorMessage),
  setSuccess: (successMessage: string | null) => success.set(successMessage),
  
  // Host management
  setHosts: (hostList: HostInfo[]) => hosts.set(hostList),
  
  // Reset actions
  resetState: () => {
    jobLaunchStore.set(initialState);
    config.set(initialConfig);
    hosts.set([]);
    loading.set(false);
    launching.set(false);
    error.set(null);
    success.set(null);
  },
  
  resetMessages: () => {
    error.set(null);
    success.set(null);
  },
  
  // Apply host defaults when host is selected
  applyHostDefaults: (hostname: string) => {
    const currentHosts = get(hosts);
    const host = currentHosts.find(h => h.hostname === hostname);
    
    if (host && host.slurm_defaults) {
      const defaults = host.slurm_defaults;
      config.update(c => {
        const updates: Partial<JobLaunchConfig> = {};
        
        if (defaults.partition) updates.partition = defaults.partition;
        if (defaults.account) updates.account = defaults.account;
        if (defaults.constraint) updates.constraint = defaults.constraint;
        if (defaults.cpus) updates.cpus = defaults.cpus;
        if (defaults.time) {
          const timeParts = defaults.time.split(':');
          const hours = parseInt(timeParts[0], 10) || 0;
          const minutes = parseInt(timeParts[1], 10) || 0;
          updates.timeLimit = hours * 60 + minutes;
        }
        
        return { ...c, ...updates };
      });
    }
  }
};

// SLURM script generation function
function generateSlurmScript(config: JobLaunchConfig): string {
  let script = '#!/bin/bash\n\n';
  
  // Header comment
  script += `# SLURM Job Script - Generated ${new Date().toLocaleString()}\n`;
  script += `# Host: ${config.selectedHost || '[Please select a host]'}\n`;
  script += `# Source: ${config.sourceDir || '[Please select source directory]'}\n\n`;
  
  // Add SLURM directives
  script += '# SLURM Configuration\n';
  if (config.jobName) script += `#SBATCH --job-name=${config.jobName}\n`;
  if (config.partition) script += `#SBATCH --partition=${config.partition}\n`;
  if (config.constraint) script += `#SBATCH --constraint=${config.constraint}\n`;
  if (config.account) script += `#SBATCH --account=${config.account}\n`;
  
  script += `#SBATCH --cpus-per-task=${config.cpus}\n`;
  if (config.useMemory) script += `#SBATCH --mem=${config.memory}GB\n`;
  const minutes = config.timeLimit % 60;
  const minutesStr = minutes < 10 ? '0' + minutes : minutes.toString();
  script += `#SBATCH --time=${Math.floor(config.timeLimit/60)}:${minutesStr}:00\n`;
  script += `#SBATCH --nodes=${config.nodes}\n`;
  script += `#SBATCH --ntasks-per-node=${config.ntasksPerNode}\n`;
  
  if (config.gpusPerNode > 0) script += `#SBATCH --gpus-per-node=${config.gpusPerNode}\n`;
  if (config.gres) script += `#SBATCH --gres=${config.gres}\n`;
  if (config.outputFile) script += `#SBATCH --output=${config.outputFile}\n`;
  if (config.errorFile) script += `#SBATCH --error=${config.errorFile}\n`;
  
  if (config.pythonEnv) {
    script += '\n# Python environment activation\n';
    script += `${config.pythonEnv}\n`;
  }
  
  script += '\n# Job execution\n';
  script += 'cd "$SLURM_SUBMIT_DIR" || exit 1\n';
  script += 'echo "=== Job Information ==="\n';
  script += 'echo "Job ID: $SLURM_JOB_ID"\n';
  script += 'echo "Node: $(hostname)"\n';
  script += 'echo "Started: $(date)"\n';
  script += 'echo "Working directory: $(pwd)"\n';
  script += 'echo "======================"\n\n';
  
  // Add user script content
  script += '# User Script Content\n';
  if (config.scriptSource === 'editor') {
    const lines = config.scriptContent.split('\n');
    script += lines.map(line => line.startsWith('#') ? line : line).join('\n');
  } else if (config.scriptSource === 'local') {
    script += `# Execute local script: ${config.localScriptPath}\n`;
    script += `if [ -f "./${config.localScriptPath}" ]; then\n`;
    script += `    chmod +x "./${config.localScriptPath}"\n`;
    script += `    ./${config.localScriptPath}\n`;
    script += 'else\n';
    script += `    echo "ERROR: Script ${config.localScriptPath} not found!"\n`;
    script += '    exit 1\n';
    script += 'fi';
  } else if (config.scriptSource === 'upload') {
    script += `# Uploaded script: ${config.uploadedScriptName}\n`;
    script += config.scriptContent;
  }
  
  script += '\n\n# Job completion\n';
  script += 'echo "=== Job Completed ==="\n';
  script += 'echo "Finished: $(date)"\n';
  script += 'echo "Exit code: $?"\n';
  script += 'echo "===================="\n';
  
  return script;
}

// Export the store and actions for use in components
export default jobLaunchStore;