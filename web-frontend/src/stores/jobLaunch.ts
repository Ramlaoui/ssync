import { derived, get, writable } from 'svelte/store';
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
  scriptContent: '#!/bin/bash\n\n#LOGIN_SETUP_BEGIN\n# Environment setup commands (run on login node)\n# Example: conda activate myenv\n# Example: pip install -r requirements.txt\n#LOGIN_SETUP_END\n\n# Main job commands (run on compute node)\necho "Job started on $(hostname)"\necho "Hello from ssync!"\n',
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

// Create a single store
const { subscribe, update, set } = writable<JobLaunchState>(initialState);

// Derived stores for individual state slices for easier component binding
export const config = derived({ subscribe }, $state => $state.config);
export const hosts = derived({ subscribe }, $state => $state.hosts);
export const loading = derived({ subscribe }, $state => $state.loading);
export const launching = derived({ subscribe }, $state => $state.launching);
export const error = derived({ subscribe }, $state => $state.error);
export const success = derived({ subscribe }, $state => $state.success);

// Derived store for generated SLURM script
export const generatedScript = derived(config, $config => generateSlurmScript($config));
console.log(generatedScript);

// Helper function to get validation details
function getValidationDetails(config: JobLaunchConfig) {
  const missing: string[] = [];
  const hasHost = config.selectedHost && config.selectedHost.trim();
  const hasSourceDir = config.sourceDir && config.sourceDir.trim();
  const hasScript = 
    (config.scriptSource === 'editor' && config.scriptContent.trim()) ||
    (config.scriptSource === 'local' && config.localScriptPath.trim()) ||
    (config.scriptSource === 'upload' && config.uploadedScriptName);

  if (!hasHost) missing.push('Select a host');
  if (!hasSourceDir) missing.push('Select source directory');
  if (!hasScript) {
    if (config.scriptSource === 'editor') missing.push('Add script content');
    else if (config.scriptSource === 'local') missing.push('Select local script file');
    else if (config.scriptSource === 'upload') missing.push('Upload script file');
  }

  return {
    isValid: missing.length === 0,
    missing,
    missingText: missing.length > 0 ? `Missing: ${missing.join(', ')}` : 'Ready to launch'
  };
}

// Derived store for validation
export const isValid = derived(config, $config => {
  return getValidationDetails($config).isValid;
});

// Derived store for validation details
export const validationDetails = derived(config, $config => {
  return getValidationDetails($config);
});

// Actions to update the store
export const jobLaunchActions = {
  updateJobConfig: (newConfig: Partial<JobLaunchConfig>) => {
    update(state => ({
      ...state,
      config: { ...state.config, ...newConfig }
    }));
  },

  setSelectedHost: (host: string) => {
    update(state => ({
      ...state,
      config: { ...state.config, selectedHost: host }
    }));
  },

  setSourceDir: (dir: string) => {
    update(state => ({
      ...state,
      config: { ...state.config, sourceDir: dir }
    }));
  },

  setScriptConfig: (scriptConfig: { source: string; content: string; localPath?: string; uploadedName?: string }) => {
    update(state => ({
      ...state,
      config: {
        ...state.config,
        scriptSource: scriptConfig.source as 'editor' | 'local' | 'upload',
        scriptContent: scriptConfig.content,
        localScriptPath: scriptConfig.localPath || '',
        uploadedScriptName: scriptConfig.uploadedName || ''
      }
    }));
  },

  setScriptContent: (content: string) => {
    update(state => ({
      ...state,
      config: {
        ...state.config,
        scriptContent: content,
        scriptSource: 'editor'
      }
    }));
  },

  setSyncSettings: (syncSettings: { excludePatterns: string[]; includePatterns: string[]; noGitignore: boolean }) => {
    update(state => ({
      ...state,
      config: { ...state.config, ...syncSettings }
    }));
  },

  setLoading: (isLoading: boolean) => update(state => ({ ...state, loading: isLoading })),
  setLaunching: (isLaunching: boolean) => update(state => ({ ...state, launching: isLaunching })),
  setError: (errorMessage: string | null) => update(state => ({ ...state, error: errorMessage })),
  setSuccess: (successMessage: string | null) => update(state => ({ ...state, success: successMessage })),

  setHosts: (hostList: HostInfo[]) => update(state => ({ ...state, hosts: hostList })),

  resetState: () => set(initialState),

  resetMessages: () => {
    update(state => ({
      ...state,
      error: null,
      success: null
    }));
  },

  applyHostDefaults: (hostname: string) => {
    const state = get({ subscribe });
    const host = state.hosts.find(h => h.hostname === hostname);

    if (host && host.slurm_defaults) {
      const defaults = host.slurm_defaults;
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

      update(s => ({
        ...s,
        config: { ...s.config, ...updates }
      }));
    }
  }
};


// SLURM script generation function
function generateSlurmScript(config: JobLaunchConfig): string {
  if (!config) return '#!/bin/bash\n';

  let script = '#!/bin/bash\n\n';

  // Header comment
  script += `# Generated by ssync\n`;
  script += `# Host: ${config.selectedHost || '[Please select a host]'}\n`;
  script += `# Source: ${config.sourceDir || '[Please select source directory]'}\n\n`;

  // Add SLURM directives
  if (config.jobName) script += `#SBATCH --job-name=${config.jobName}\n`;
  if (config.partition) script += `#SBATCH --partition=${config.partition}\n`;
  if (config.constraint) script += `#SBATCH --constraint=${config.constraint}\n`;
  if (config.account) script += `#SBATCH --account=${config.account}\n`;

  script += `#SBATCH --cpus-per-task=${config.cpus}\n`;
  if (config.useMemory) script += `#SBATCH --mem=${config.memory}GB\n`;

  const hours = Math.floor(config.timeLimit / 60);
  const minutes = config.timeLimit % 60;
  const hoursStr = hours < 10 ? '0' + hours : hours.toString();
  const minutesStr = minutes < 10 ? '0' + minutes : minutes.toString();
  script += `#SBATCH --time=${hoursStr}:${minutesStr}:00\n`;

  script += `#SBATCH --nodes=${config.nodes}\n`;
  script += `#SBATCH --ntasks-per-node=${config.ntasksPerNode}\n`;

  if (config.gpusPerNode > 0) script += `#SBATCH --gpus-per-node=${config.gpusPerNode}\n`;
  if (config.gres) script += `#SBATCH --gres=${config.gres}\n`;
  if (config.outputFile) script += `#SBATCH --output=${config.outputFile}\n`;
  if (config.errorFile) script += `#SBATCH --error=${config.errorFile}\n`;

  // Add user script content
  if (config.scriptSource === 'editor') {
    // Clean up the content to avoid duplicating comments and headers
    let cleanContent = config.scriptContent;
    
    // Remove shebang if present (we already have one)
    cleanContent = cleanContent.replace(/^#![^\n]*\n?/, '');
    
    // Remove duplicate "Generated by ssync" comments if they exist
    cleanContent = cleanContent.replace(/^# Generated by ssync\n# Host:.*\n# Source:.*\n\n?/m, '');
    
    // Remove duplicate "Main job script" comment if it exists
    cleanContent = cleanContent.replace(/^# Main job script \(runs on compute node\)\n/m, '');
    
    // Only add the comment if the content doesn't start with a SLURM directive or login setup
    // and isn't empty
    const trimmedContent = cleanContent.trim();
    if (trimmedContent !== '' && 
        !trimmedContent.startsWith('#SBATCH') && 
        !trimmedContent.startsWith('#LOGIN_SETUP_BEGIN')) {
      script += '\n# Main job script (runs on compute node)\n';
    } else if (trimmedContent !== '') {
      script += '\n';
    }
    
    script += cleanContent;
  } else if (config.scriptSource === 'local') {
    script += '\n# Main job script (runs on compute node)\n';
    script += `# Execute local script: ${config.localScriptPath}\n`;
    script += `if [ -f "./${config.localScriptPath}" ]; then\n`;
    script += `    chmod +x "./${config.localScriptPath}"\n`;
    script += `    ./${config.localScriptPath}\n`;
    script += 'else\n';
    script += `    echo "ERROR: Script ${config.localScriptPath} not found!"\n`;
    script += '    exit 1\n';
    script += 'fi\n';
  } else if (config.scriptSource === 'upload') {
    script += `# Uploaded script: ${config.uploadedScriptName}\n`;
    script += config.scriptContent.replace(/^#![^\n]*\n?/, ''); // Remove only the shebang line
  }

  return script;
}

// Export the store and actions for use in components
export default { subscribe, set, update };
