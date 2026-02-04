/**
 * SBATCH Script Parser and Generator
 *
 * Utilities for parsing and generating SBATCH directives in Slurm job scripts.
 */

/**
 * Job parameters interface with proper numeric types
 * All string fields are optional (can be undefined)
 */
export interface JobParameters {
  cpus?: number;
  memory?: number;
  timeLimit?: number;
  nodes?: number;
  partition?: string;
  account?: string;
  jobName?: string;
  constraint?: string;
  ntasksPerNode?: number;
  gpusPerNode?: number;
  gres?: string;
  outputFile?: string;
  errorFile?: string;
  sourceDir?: string;
}

/**
 * Directive mapping for known SBATCH options
 */
const KNOWN_DIRECTIVES = new Set([
  'job-name', 'J',
  'partition', 'p',
  'account', 'A',
  'nodes',
  'cpus-per-task', 'cpus',
  'mem', 'memory',
  'time',
  'constraint', 'C',
  'ntasks-per-node',
  'gpus-per-node',
  'gres',
  'output', 'o',
  'error', 'e'
]);

/**
 * Parse time string to minutes
 * Supports formats: HH:MM:SS, MM:SS, or minutes as integer
 */
function parseTimeToMinutes(timeStr: string): number | undefined {
  // Format: HH:MM:SS
  const hhmmss = timeStr.match(/^(\d+):(\d+):(\d+)$/);
  if (hhmmss) {
    const hours = parseInt(hhmmss[1], 10);
    const minutes = parseInt(hhmmss[2], 10);
    return hours * 60 + minutes;
  }

  // Format: MM:SS
  const mmss = timeStr.match(/^(\d+):(\d+)$/);
  if (mmss) {
    return parseInt(mmss[1], 10);
  }

  // Format: plain number (minutes)
  const plainNumber = timeStr.match(/^\d+$/);
  if (plainNumber) {
    return parseInt(timeStr, 10);
  }

  return undefined;
}

/**
 * Parse memory string to GB
 * Supports formats: 4G, 4096M, 4194304K, or plain number (assumed GB)
 */
function parseMemoryToGB(memStr: string): number | undefined {
  const match = memStr.match(/^(\d+)([GMK])?$/);
  if (!match) return undefined;

  let value = parseInt(match[1], 10);
  const unit = match[2];

  if (unit === 'K') {
    value = Math.ceil(value / 1024 / 1024); // K to G
  } else if (unit === 'M') {
    value = Math.ceil(value / 1024); // M to G
  }
  // G or no unit assumes GB

  return value;
}

/**
 * Format minutes to HH:MM:SS time string
 */
function formatMinutesToTime(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}:${mins.toString().padStart(2, '0')}:00`;
}

/**
 * Parse SBATCH directives from script content
 *
 * @param scriptContent - The full script content
 * @returns Parsed job parameters
 */
export function parseSbatchDirectives(scriptContent: string): JobParameters {
  const parameters: JobParameters = {};
  const lines = scriptContent.split('\n');

  for (const line of lines) {
    // Only process SBATCH lines
    if (!line.startsWith('#SBATCH')) continue;

    // Handle both --option=value and --option value formats
    const match = line.match(/#SBATCH\s+--?([a-zA-Z-]+)(?:=(.+?))?(?:\s+(.+?))?$/);
    if (!match) continue;

    const [, directive, value1, value2] = match;
    const value = (value1 || value2 || '').trim();

    switch (directive) {
      case 'cpus-per-task':
      case 'cpus':
        if (value) {
          const parsed = parseInt(value, 10);
          if (!isNaN(parsed)) parameters.cpus = parsed;
        }
        break;

      case 'mem':
      case 'memory':
        if (value) {
          const parsed = parseMemoryToGB(value);
          if (parsed !== undefined) parameters.memory = parsed;
        }
        break;

      case 'time':
        if (value) {
          const parsed = parseTimeToMinutes(value);
          if (parsed !== undefined) parameters.timeLimit = parsed;
        }
        break;

      case 'nodes':
        if (value) {
          const parsed = parseInt(value, 10);
          if (!isNaN(parsed)) parameters.nodes = parsed;
        }
        break;

      case 'partition':
      case 'p':
        if (value) parameters.partition = value;
        break;

      case 'account':
      case 'A':
        if (value) parameters.account = value;
        break;

      case 'job-name':
      case 'J':
        if (value) parameters.jobName = value;
        break;

      case 'constraint':
      case 'C':
        if (value) parameters.constraint = value;
        break;

      case 'ntasks-per-node':
        if (value) {
          const parsed = parseInt(value, 10);
          if (!isNaN(parsed)) parameters.ntasksPerNode = parsed;
        }
        break;

      case 'gpus-per-node':
        if (value) {
          const parsed = parseInt(value, 10);
          if (!isNaN(parsed)) parameters.gpusPerNode = parsed;
        }
        break;

      case 'gres':
        if (value) parameters.gres = value;
        break;

      case 'output':
      case 'o':
        if (value) parameters.outputFile = value;
        break;

      case 'error':
      case 'e':
        if (value) parameters.errorFile = value;
        break;
    }
  }

  return parameters;
}

/**
 * Script parts after parsing
 */
interface ScriptParts {
  shebang: string;
  sbatchLines: string[];
  bodyLines: string[];
}

/**
 * Parse script into its constituent parts
 */
function parseScriptParts(scriptContent: string): ScriptParts {
  const lines = scriptContent.split('\n');
  const sbatchLines: string[] = [];
  let shebang = '';
  let bodyLines: string[] = [];
  let foundSbatch = false;
  let foundBody = false;

  lines.forEach((line, index) => {
    if (index === 0 && line.startsWith('#!')) {
      shebang = line;
    } else if (line.startsWith('#SBATCH')) {
      sbatchLines.push(line);
      foundSbatch = true;
      foundBody = false;
    } else if (foundSbatch || foundBody) {
      // Skip empty lines immediately after SBATCH directives
      if (!foundBody && line.trim() === '') {
        foundBody = true;
      } else {
        foundBody = true;
        bodyLines.push(line);
      }
    } else {
      bodyLines.push(line);
    }
  });

  return { shebang, sbatchLines, bodyLines };
}

/**
 * Generate SBATCH directive line for a parameter
 */
function generateSbatchLine(
  directive: string,
  value: string | number | undefined,
  formatter?: (v: any) => string
): string | null {
  if (value === undefined || value === null || value === '') return null;

  const formattedValue = formatter ? formatter(value) : value;
  return `#SBATCH --${directive}=${formattedValue}`;
}

/**
 * Update script content with new parameters
 * Preserves unknown SBATCH directives and script body
 *
 * @param scriptContent - Original script content
 * @param parameters - Job parameters to apply
 * @returns Updated script content
 */
export function updateScriptWithParameters(
  scriptContent: string,
  parameters: JobParameters
): string {
  const { shebang, sbatchLines, bodyLines } = parseScriptParts(scriptContent);

  // Track which directives we've processed
  const processedDirectives = new Set<string>();
  const updatedSbatchLines: string[] = [];

  // Process existing SBATCH lines
  for (const line of sbatchLines) {
    const match = line.match(/#SBATCH\s+--?([a-zA-Z-]+)/);
    if (!match) {
      // Preserve malformed lines as-is
      updatedSbatchLines.push(line);
      continue;
    }

    const directive = match[1];

    // Check if this is a directive we manage
    if (!KNOWN_DIRECTIVES.has(directive)) {
      // Preserve unknown directives as-is
      updatedSbatchLines.push(line);
      continue;
    }

    // Skip if we've already processed this directive type
    if (processedDirectives.has(directive)) continue;

    processedDirectives.add(directive);

    // Generate updated line based on parameters
    let updatedLine: string | null = null;

    switch (directive) {
      case 'job-name':
      case 'J':
        updatedLine = generateSbatchLine('job-name', parameters.jobName);
        break;
      case 'partition':
      case 'p':
        updatedLine = generateSbatchLine('partition', parameters.partition);
        break;
      case 'account':
      case 'A':
        updatedLine = generateSbatchLine('account', parameters.account);
        break;
      case 'nodes':
        updatedLine = generateSbatchLine('nodes', parameters.nodes);
        break;
      case 'cpus-per-task':
      case 'cpus':
        updatedLine = generateSbatchLine('cpus-per-task', parameters.cpus);
        break;
      case 'mem':
      case 'memory':
        updatedLine = generateSbatchLine('mem', parameters.memory, (v) => `${v}G`);
        break;
      case 'time':
        updatedLine = generateSbatchLine('time', parameters.timeLimit, formatMinutesToTime);
        break;
      case 'constraint':
      case 'C':
        updatedLine = generateSbatchLine('constraint', parameters.constraint);
        break;
      case 'ntasks-per-node':
        updatedLine = generateSbatchLine('ntasks-per-node', parameters.ntasksPerNode);
        break;
      case 'gpus-per-node':
        updatedLine = generateSbatchLine('gpus-per-node', parameters.gpusPerNode);
        break;
      case 'gres':
        updatedLine = generateSbatchLine('gres', parameters.gres);
        break;
      case 'output':
      case 'o':
        updatedLine = generateSbatchLine('output', parameters.outputFile);
        break;
      case 'error':
      case 'e':
        updatedLine = generateSbatchLine('error', parameters.errorFile);
        break;
    }

    if (updatedLine) {
      updatedSbatchLines.push(updatedLine);
    }
  }

  // Add new directives that weren't in the original script
  const addDirectiveIfNew = (
    directives: string[],
    paramValue: any,
    line: string | null
  ) => {
    const hasAny = directives.some(d => processedDirectives.has(d));
    if (!hasAny && line) {
      updatedSbatchLines.push(line);
    }
  };

  addDirectiveIfNew(
    ['job-name', 'J'],
    parameters.jobName,
    generateSbatchLine('job-name', parameters.jobName)
  );

  addDirectiveIfNew(
    ['partition', 'p'],
    parameters.partition,
    generateSbatchLine('partition', parameters.partition)
  );

  addDirectiveIfNew(
    ['account', 'A'],
    parameters.account,
    generateSbatchLine('account', parameters.account)
  );

  addDirectiveIfNew(
    ['nodes'],
    parameters.nodes,
    generateSbatchLine('nodes', parameters.nodes)
  );

  addDirectiveIfNew(
    ['cpus-per-task', 'cpus'],
    parameters.cpus,
    generateSbatchLine('cpus-per-task', parameters.cpus)
  );

  addDirectiveIfNew(
    ['mem', 'memory'],
    parameters.memory,
    generateSbatchLine('mem', parameters.memory, (v) => `${v}G`)
  );

  addDirectiveIfNew(
    ['time'],
    parameters.timeLimit,
    generateSbatchLine('time', parameters.timeLimit, formatMinutesToTime)
  );

  addDirectiveIfNew(
    ['constraint', 'C'],
    parameters.constraint,
    generateSbatchLine('constraint', parameters.constraint)
  );

  addDirectiveIfNew(
    ['ntasks-per-node'],
    parameters.ntasksPerNode,
    generateSbatchLine('ntasks-per-node', parameters.ntasksPerNode)
  );

  addDirectiveIfNew(
    ['gpus-per-node'],
    parameters.gpusPerNode,
    generateSbatchLine('gpus-per-node', parameters.gpusPerNode)
  );

  addDirectiveIfNew(
    ['gres'],
    parameters.gres,
    generateSbatchLine('gres', parameters.gres)
  );

  addDirectiveIfNew(
    ['output', 'o'],
    parameters.outputFile,
    generateSbatchLine('output', parameters.outputFile)
  );

  addDirectiveIfNew(
    ['error', 'e'],
    parameters.errorFile,
    generateSbatchLine('error', parameters.errorFile)
  );

  // Rebuild script
  const newLines: string[] = [];

  // Add shebang
  newLines.push(shebang || '#!/bin/bash');

  // Add all SBATCH directives (updated and preserved)
  if (updatedSbatchLines.length > 0) {
    newLines.push(...updatedSbatchLines);
  }

  // Remove leading empty lines from bodyLines
  while (bodyLines.length > 0 && bodyLines[0].trim() === '') {
    bodyLines.shift();
  }

  // Add body with proper spacing
  if (bodyLines.length > 0) {
    // Add single blank line between SBATCH and body if there are SBATCH lines
    if (updatedSbatchLines.length > 0) {
      newLines.push('');
    }
    newLines.push(...bodyLines);
  }

  return newLines.join('\n');
}
