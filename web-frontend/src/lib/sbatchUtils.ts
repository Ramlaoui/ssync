export interface JobParameters {
  cpus?: number;
  memory?: number;
  timeLimit?: number;
  nodes?: number;
  partition: string;
  account: string;
  jobName: string;
  constraint: string;
  ntasksPerNode?: number;
  gpusPerNode?: number;
  gres: string;
  outputFile: string;
  errorFile: string;
  sourceDir: string;
}

export interface ValidationDetails {
  isValid: boolean;
  missing: string[];
  missingText: string;
}

export function createDefaultParameters(): JobParameters {
  return {
    cpus: undefined,
    memory: undefined,
    timeLimit: undefined,
    nodes: undefined,
    partition: '',
    account: '',
    jobName: '',
    constraint: '',
    ntasksPerNode: undefined,
    gpusPerNode: undefined,
    gres: '',
    outputFile: '',
    errorFile: '',
    sourceDir: ''
  };
}

/**
 * Parse SBATCH directives from script content and update parameters
 */
export function parseSbatchFromScript(scriptContent: string, parameters: JobParameters): void {
  const lines = scriptContent.split('\n');

  for (const line of lines) {
    if (line.startsWith('#SBATCH')) {
      // Handle both --option=value and --option value formats
      const match = line.match(/#SBATCH\s+--?([a-zA-Z-]+)(?:=(.+?))?(?:\s+(.+?))?$/);
      if (match) {
        const [, directive, value1, value2] = match;
        const value = (value1 || value2 || '').trim();

        switch(directive) {
          case 'cpus-per-task':
          case 'cpus':
            if (value) parameters.cpus = parseInt(value) || undefined;
            break;
          case 'mem':
          case 'memory':
            const memMatch = value?.match(/(\d+)([GMK])?/);
            if (memMatch) {
              let mem = parseInt(memMatch[1]);
              if (memMatch[2] === 'M' || memMatch[2] === 'K') mem = Math.ceil(mem / 1024);
              parameters.memory = mem;
            }
            break;
          case 'time':
            // Convert time to minutes
            const timeMatch = value?.match(/(\d+):(\d+):(\d+)/);
            if (timeMatch) {
              parameters.timeLimit = parseInt(timeMatch[1]) * 60 + parseInt(timeMatch[2]);
            } else if (value?.match(/^\d+$/)) {
              parameters.timeLimit = parseInt(value);
            }
            break;
          case 'nodes':
            if (value) parameters.nodes = parseInt(value) || undefined;
            break;
          case 'partition':
          case 'p':
            parameters.partition = value || '';
            break;
          case 'account':
          case 'A':
            parameters.account = value || '';
            break;
          case 'job-name':
          case 'J':
            parameters.jobName = value || '';
            break;
          case 'constraint':
          case 'C':
            parameters.constraint = value || '';
            break;
          case 'ntasks-per-node':
            if (value) parameters.ntasksPerNode = parseInt(value) || undefined;
            break;
          case 'gpus-per-node':
            if (value) parameters.gpusPerNode = parseInt(value) || undefined;
            break;
          case 'gres':
            parameters.gres = value || '';
            break;
          case 'output':
          case 'o':
            parameters.outputFile = value || '';
            break;
          case 'error':
          case 'e':
            parameters.errorFile = value || '';
            break;
        }
      }
    }
  }
}

/**
 * Generate SBATCH directives from parameters and update script
 */
export function updateScriptWithParameters(script: string, parameters: JobParameters): string {
  const lines = script.split('\n');
  const allSbatchLines: string[] = [];
  const knownDirectives = new Set([
    'job-name', 'J', 'partition', 'p', 'account', 'A',
    'nodes', 'cpus-per-task', 'cpus', 'mem', 'memory',
    'time', 'constraint', 'C', 'ntasks-per-node',
    'gpus-per-node', 'gres', 'output', 'o', 'error', 'e'
  ]);

  let shebangLine = '';
  const bodyLines: string[] = [];
  let foundSbatch = false;
  let foundBody = false;

  // Extract existing structure
  for (const line of lines) {
    if (line.startsWith('#!') && !foundSbatch && !foundBody) {
      shebangLine = line;
    } else if (line.startsWith('#SBATCH')) {
      foundSbatch = true;
      const match = line.match(/#SBATCH\s+--?([a-zA-Z-]+)/);
      if (match && !knownDirectives.has(match[1])) {
        // Keep unknown SBATCH directives
        allSbatchLines.push(line);
      }
    } else if (line.trim() === '' || line.startsWith('#')) {
      if (foundSbatch && !foundBody) {
        // Skip empty lines and comments between SBATCH and body
        continue;
      } else if (!foundSbatch && !foundBody) {
        // Keep comments before SBATCH
        continue;
      } else {
        foundBody = true;
        bodyLines.push(line);
      }
    } else {
      foundBody = true;
      bodyLines.push(line);
    }
  }

  // Generate new SBATCH directives from parameters
  const newSbatchLines: string[] = [];

  if (parameters.jobName) {
    newSbatchLines.push(`#SBATCH --job-name=${parameters.jobName}`);
  }
  if (parameters.partition) {
    newSbatchLines.push(`#SBATCH --partition=${parameters.partition}`);
  }
  if (parameters.account) {
    newSbatchLines.push(`#SBATCH --account=${parameters.account}`);
  }
  if (parameters.nodes) {
    newSbatchLines.push(`#SBATCH --nodes=${parameters.nodes}`);
  }
  if (parameters.cpus) {
    newSbatchLines.push(`#SBATCH --cpus-per-task=${parameters.cpus}`);
  }
  if (parameters.memory) {
    newSbatchLines.push(`#SBATCH --mem=${parameters.memory}G`);
  }
  if (parameters.timeLimit) {
    const hours = Math.floor(parameters.timeLimit / 60);
    const minutes = parameters.timeLimit % 60;
    newSbatchLines.push(`#SBATCH --time=${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:00`);
  }
  if (parameters.constraint) {
    newSbatchLines.push(`#SBATCH --constraint=${parameters.constraint}`);
  }
  if (parameters.ntasksPerNode) {
    newSbatchLines.push(`#SBATCH --ntasks-per-node=${parameters.ntasksPerNode}`);
  }
  if (parameters.gpusPerNode) {
    newSbatchLines.push(`#SBATCH --gpus-per-node=${parameters.gpusPerNode}`);
  }
  if (parameters.gres) {
    newSbatchLines.push(`#SBATCH --gres=${parameters.gres}`);
  }
  if (parameters.outputFile) {
    newSbatchLines.push(`#SBATCH --output=${parameters.outputFile}`);
  }
  if (parameters.errorFile) {
    newSbatchLines.push(`#SBATCH --error=${parameters.errorFile}`);
  }

  // Combine all SBATCH lines (new + preserved unknown ones)
  allSbatchLines.push(...newSbatchLines);

  // Reconstruct script
  const newLines: string[] = [];

  if (shebangLine) {
    newLines.push(shebangLine);
    newLines.push('');
  }

  if (allSbatchLines.length > 0) {
    newLines.push(...allSbatchLines);
    newLines.push('');
  }

  newLines.push(...bodyLines);

  return newLines.join('\n');
}

/**
 * Format time limit from minutes to HH:MM format for display
 */
export function formatTimeLimit(minutes?: number): string {
  if (!minutes) return '';
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
}

/**
 * Parse time limit from HH:MM format to minutes
 */
export function parseTimeLimit(timeString: string): number | undefined {
  const match = timeString.match(/(\d+):(\d+)/);
  if (match) {
    return parseInt(match[1]) * 60 + parseInt(match[2]);
  }
  const numMatch = timeString.match(/^\d+$/);
  if (numMatch) {
    return parseInt(timeString);
  }
  return undefined;
}

/**
 * Validate job parameters
 */
export function validateParameters(parameters: JobParameters): {
  isValid: boolean;
  missing: string[];
  missingText: string;
} {
  const missing: string[] = [];

  if (!parameters.jobName?.trim()) missing.push('Job Name');
  if (!parameters.sourceDir?.trim()) missing.push('Source Directory');

  const isValid = missing.length === 0;
  const missingText = missing.length > 0
    ? `Missing: ${missing.join(', ')}`
    : 'Ready to launch';

  return { isValid, missing, missingText };
}