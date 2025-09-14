import { derived, get, writable } from 'svelte/store';
import type { HostInfo } from '../types/api';

export type ParameterSource = 'default' | 'user' | 'script' | 'unset' | 'merged';
export type LaunchMode = 'quick' | 'script';
export type SyncMode = 'off' | 'toForm' | 'toScript' | 'bidirectional';

export interface JobParameter {
  name: string;
  displayName: string;
  value?: string | number | boolean;
  source: ParameterSource;
  hostDefault?: string | number | boolean;
  scriptValue?: string | number | boolean;
  enabled: boolean; // Whether this parameter should be sent to the API
  type: 'string' | 'number' | 'boolean' | 'time';
  unit?: string; // For display (e.g., 'GB', 'minutes')
  scriptLine?: number; // Line number in script where this parameter is defined
  hasConflict?: boolean; // True if script and form values differ
  syncedFromScript?: boolean; // True if this value was recently synced from script
}

export interface JobParametersState {
  mode: LaunchMode;
  parameters: Map<string, JobParameter>;
  scriptContent: string;
  rawScriptContent: string; // Original content before any modifications
  conflictResolution?: 'script' | 'form' | 'merge';
  scriptHasSbatch: boolean;
  selectedHost?: string;
  syncMode: SyncMode;
  lastScriptUpdate: number; // Timestamp of last script update
  scriptUpdateDebounceTimer?: number;
  isResubmit: boolean; // Flag to indicate we're in resubmit mode
}

// Default parameter definitions
const DEFAULT_PARAMETERS: JobParameter[] = [
  { name: 'partition', displayName: 'Partition', type: 'string', source: 'unset', enabled: false },
  { name: 'time', displayName: 'Time Limit', type: 'time', source: 'unset', enabled: false, unit: 'minutes' },
  { name: 'cpus', displayName: 'CPUs', type: 'number', source: 'unset', enabled: false },
  { name: 'mem', displayName: 'Memory', type: 'number', source: 'unset', enabled: false, unit: 'GB' },
  { name: 'nodes', displayName: 'Nodes', type: 'number', source: 'unset', enabled: false },
  { name: 'gpus_per_node', displayName: 'GPUs per Node', type: 'number', source: 'unset', enabled: false },
  { name: 'account', displayName: 'Account', type: 'string', source: 'unset', enabled: false },
  { name: 'job_name', displayName: 'Job Name', type: 'string', source: 'unset', enabled: false },
  { name: 'output', displayName: 'Output File', type: 'string', source: 'unset', enabled: false },
  { name: 'error', displayName: 'Error File', type: 'string', source: 'unset', enabled: false },
  { name: 'constraint', displayName: 'Constraint', type: 'string', source: 'unset', enabled: false },
  { name: 'gres', displayName: 'Generic Resources', type: 'string', source: 'unset', enabled: false },
  { name: 'ntasks_per_node', displayName: 'Tasks per Node', type: 'number', source: 'unset', enabled: false },
];

function createJobParametersStore() {
  const initialState: JobParametersState = {
    mode: 'quick',
    parameters: new Map(DEFAULT_PARAMETERS.map(p => [p.name, { ...p }])),
    scriptContent: '',
    rawScriptContent: '',
    scriptHasSbatch: false,
    syncMode: 'bidirectional',
    lastScriptUpdate: Date.now(),
    isResubmit: false,
  };

  const store = writable<JobParametersState>(initialState);

  // Parse #SBATCH directives from script with line numbers
  function parseSbatchDirectives(script: string): Map<string, { value: string | number, line: number }> {
    const directives = new Map<string, { value: string | number, line: number }>();
    const lines = script.split('\n');

    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      if (!trimmed.startsWith('#SBATCH')) continue;

      // Parse different formats: #SBATCH --key=value or #SBATCH --key value
      const match = trimmed.match(/#SBATCH\s+--([a-z-]+)(?:=|\s+)(.+)/i);
      if (match) {
        let [, key, valueStr] = match;
        let value: string | number = valueStr.trim().replace(/^["']|["']$/g, '');

        // Normalize key names
        key = key.replace(/-/g, '_');

        // Map SBATCH keys to our parameter names
        const keyMap: Record<string, string> = {
          'cpus_per_task': 'cpus',
          'mem': 'mem',
          'time': 'time',
          'job_name': 'job_name',
          'gpus_per_node': 'gpus_per_node',
          'ntasks_per_node': 'ntasks_per_node',
          'partition': 'partition',
          'nodes': 'nodes',
          'account': 'account',
          'output': 'output',
          'error': 'error',
          'constraint': 'constraint',
          'gres': 'gres',
        };

        const mappedKey = keyMap[key] || key;

        // Parse memory values (e.g., "16G" -> 16, "4096M" -> 4)
        if (mappedKey === 'mem' && typeof value === 'string') {
          const memMatch = value.match(/^(\d+)([GMT]?)B?$/i);
          if (memMatch) {
            let memValue = parseInt(memMatch[1]);
            const unit = memMatch[2]?.toUpperCase();
            if (unit === 'M') {
              memValue = Math.ceil(memValue / 1024); // Convert MB to GB
            } else if (unit === 'T') {
              memValue = memValue * 1024; // Convert TB to GB
            }
            value = memValue;
          }
        }

        // Parse time values (e.g., "1:00:00" -> 60, "2-00:00:00" -> 2880)
        if (mappedKey === 'time' && typeof value === 'string') {
          // Handle days-hours:minutes:seconds format
          const dayMatch = value.match(/^(\d+)-(.+)$/);
          let totalMinutes = 0;

          if (dayMatch) {
            totalMinutes = parseInt(dayMatch[1]) * 24 * 60; // Days to minutes
            value = dayMatch[2];
          }

          if (value.includes(':')) {
            const parts = value.split(':').map(Number);
            if (parts.length === 3) {
              totalMinutes += parts[0] * 60 + parts[1]; // hours:minutes:seconds
            } else if (parts.length === 2) {
              totalMinutes += parts[0] * 60 + parts[1]; // hours:minutes
            } else if (parts.length === 1) {
              totalMinutes += parts[0]; // just minutes
            }
            value = totalMinutes;
          } else if (!isNaN(Number(value))) {
            value = Number(value);
          }
        }

        // Parse numeric values
        const numericParams = ['cpus', 'nodes', 'gpus_per_node', 'ntasks_per_node'];
        if (numericParams.includes(mappedKey) && typeof value === 'string') {
          const parsed = parseInt(value);
          if (!isNaN(parsed)) {
            value = parsed;
          }
        }

        directives.set(mappedKey, { value, line: i + 1 });
      }
    }

    return directives;
  }

  // Generate SBATCH directive line for a parameter
  function generateSbatchLine(param: JobParameter): string {
    const sbatchMap: Record<string, string> = {
      'cpus': 'cpus-per-task',
      'mem': 'mem',
      'time': 'time',
      'job_name': 'job-name',
      'gpus_per_node': 'gpus-per-node',
      'ntasks_per_node': 'ntasks-per-node',
      'partition': 'partition',
      'nodes': 'nodes',
      'account': 'account',
      'output': 'output',
      'error': 'error',
      'constraint': 'constraint',
      'gres': 'gres',
    };

    const sbatchKey = sbatchMap[param.name] || param.name;
    let value = param.value;

    // Format special values
    if (param.name === 'mem' && typeof value === 'number') {
      value = `${value}G`;
    } else if (param.name === 'time' && typeof value === 'number') {
      const minutes = value as number;
      const hours = Math.floor(minutes / 60);
      const mins = minutes % 60;
      value = `${hours}:${mins.toString().padStart(2, '0')}:00`;
    }

    return `#SBATCH --${sbatchKey}=${value}`;
  }

  // Update script with form parameter values
  function updateScriptWithParameters(script: string, parameters: Map<string, JobParameter>): string {
    const lines = script.split('\n');
    const processedParams = new Set<string>();
    const linesToRemove = new Set<number>();

    // First pass: identify existing SBATCH lines and mark for update/removal
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      if (!trimmed.startsWith('#SBATCH')) continue;

      // Parse to find which parameter this line represents
      const match = trimmed.match(/#SBATCH\s+--([a-z-]+)/i);
      if (match) {
        let key = match[1].replace(/-/g, '_');
        const keyMap: Record<string, string> = {
          'cpus_per_task': 'cpus',
          'mem': 'mem',
          'time': 'time',
          'job_name': 'job_name',
          'gpus_per_node': 'gpus_per_node',
          'ntasks_per_node': 'ntasks_per_node',
          'partition': 'partition',
          'nodes': 'nodes',
          'account': 'account',
          'output': 'output',
          'error': 'error',
          'constraint': 'constraint',
          'gres': 'gres',
        };
        const mappedKey = keyMap[key] || key;
        const param = parameters.get(mappedKey);

        if (param) {
          if (param.enabled) {
            // Update this line with new value
            lines[i] = generateSbatchLine(param);
            processedParams.add(mappedKey);
          } else {
            // Mark this line for removal (parameter disabled)
            linesToRemove.add(i);
          }
        }
      }
    }

    // Filter out removed lines
    const filteredLines = lines.filter((_, idx) => !linesToRemove.has(idx));

    // Collect new SBATCH lines for parameters not in script
    const newLines: string[] = [];
    for (const [name, param] of parameters) {
      if (param.enabled && !processedParams.has(name)) {
        newLines.push(generateSbatchLine(param));
      }
    }

    // Find best insertion point for new SBATCH lines
    if (newLines.length > 0) {
      let insertIndex = -1;

      // Try to insert after existing SBATCH lines
      for (let i = filteredLines.length - 1; i >= 0; i--) {
        if (filteredLines[i].trim().startsWith('#SBATCH')) {
          insertIndex = i + 1;
          break;
        }
      }

      // If no SBATCH lines, insert after shebang with a blank line
      if (insertIndex === -1) {
        const shebangIndex = filteredLines.findIndex(l => l.startsWith('#!'));
        if (shebangIndex >= 0) {
          insertIndex = shebangIndex + 1;
          // Only add blank line if next line isn't already blank
          if (insertIndex < filteredLines.length && filteredLines[insertIndex].trim() !== '') {
            newLines.unshift('');
          }
        } else {
          insertIndex = 0;
        }
      }

      filteredLines.splice(insertIndex, 0, ...newLines);
    }

    return filteredLines.join('\n');
  }

  // Check if script has SBATCH directives
  function hasSbatchDirectives(script: string): boolean {
    return script.split('\n').some(line => line.trim().startsWith('#SBATCH'));
  }

  return {
    subscribe: store.subscribe,

    // Set launch mode
    setMode(mode: LaunchMode) {
      store.update(state => ({ ...state, mode }));
    },

    // Toggle parameter enabled state
    toggleParameter(name: string, enabled?: boolean) {
      store.update(state => {
        const param = state.parameters.get(name);
        if (param) {
          param.enabled = enabled !== undefined ? enabled : !param.enabled;
          if (param.enabled && param.source === 'unset') {
            param.source = 'user';
          } else if (!param.enabled) {
            param.source = 'unset';
          }
        }
        return state;
      });
    },

    // Set parameter value
    setParameterValue(name: string, value: string | number | boolean | undefined) {
      store.update(state => {
        const param = state.parameters.get(name);
        if (param) {
          param.value = value;
          param.source = value !== undefined ? 'user' : 'unset';
          param.enabled = value !== undefined;
        }
        return state;
      });
    },

    // Apply host defaults
    applyHostDefaults(host: HostInfo) {
      store.update(state => {
        state.selectedHost = host.hostname;

        if (host.slurm_defaults) {
          const defaults = host.slurm_defaults;

          // Map host defaults to parameters
          const defaultMappings: Record<string, keyof typeof defaults> = {
            'partition': 'partition',
            'cpus': 'cpus',
            'mem': 'mem',
            'time': 'time',
            'nodes': 'nodes',
            'gpus_per_node': 'gpus_per_node',
            'account': 'account',
            'job_name': 'job_name_prefix',
            'output': 'output_pattern',
            'error': 'error_pattern',
            'constraint': 'constraint',
            'gres': 'gres',
            'ntasks_per_node': 'ntasks_per_node',
          };

          for (const [paramName, defaultKey] of Object.entries(defaultMappings)) {
            const param = state.parameters.get(paramName);
            const defaultValue = defaults[defaultKey];

            if (param && defaultValue !== undefined && defaultValue !== null) {
              param.hostDefault = defaultValue;
              // Only apply default if parameter hasn't been explicitly set by user
              if (param.source !== 'user') {
                param.value = defaultValue;
                param.source = 'default';
              }
            }
          }
        }

        return state;
      });
    },

    // Set script content with real-time sync
    setScriptContent(content: string, skipFormSync: boolean = false) {
      store.update(state => {
        state.rawScriptContent = content;
        state.scriptContent = content;
        state.scriptHasSbatch = hasSbatchDirectives(content);
        state.lastScriptUpdate = Date.now();

        // Parse SBATCH directives from the new content
        const directives = parseSbatchDirectives(content);

        // Track which parameters are in the script
        const scriptParamNames = new Set<string>();

        // Update parameters based on script content
        for (const param of state.parameters.values()) {
          const scriptDirective = directives.get(param.name);

          if (scriptDirective) {
            scriptParamNames.add(param.name);
            const { value, line } = scriptDirective;

            // Check if value has changed from what's in script
            const scriptValueChanged = param.scriptValue !== value;
            param.scriptValue = value;
            param.scriptLine = line;

            // Determine if there's a conflict
            const hasConflict = param.enabled && param.source === 'user' && param.value !== value;
            param.hasConflict = hasConflict;

            // Sync logic based on mode and conditions
            if (!skipFormSync && state.syncMode !== 'off') {
              const shouldSyncToForm =
                (state.syncMode === 'toForm' && scriptValueChanged) ||
                (state.syncMode === 'bidirectional' && !hasConflict) ||
                (param.source === 'unset');

              if (shouldSyncToForm) {
                param.value = value;
                param.enabled = true;
                param.source = 'script';
                param.syncedFromScript = true;
                param.hasConflict = false;
              }
            }
          } else {
            // Parameter not in script anymore
            if (param.scriptLine !== undefined) {
              // It was in the script before but removed
              param.scriptValue = undefined;
              param.scriptLine = undefined;
              param.hasConflict = false;

              // In bidirectional mode, might want to disable in form too
              if (state.syncMode === 'bidirectional' && param.source === 'script') {
                param.enabled = false;
                param.source = 'unset';
              }
            }
          }
        }

        // Handle parameters that are only in script (not in our default set)
        for (const [key, { value, line }] of directives) {
          if (!state.parameters.has(key)) {
            // Could add as a custom parameter in the future
          }
        }

        // Auto-switch to script mode if we detect SBATCH directives
        if (state.scriptHasSbatch && state.mode === 'quick') {
          state.mode = 'script';
        }

        return state;
      });
    },

    // Update form parameter and optionally sync to script
    updateParameter(name: string, value: string | number | boolean | undefined, enabled: boolean) {
      store.update(state => {
        const param = state.parameters.get(name);
        if (!param) return state;

        // Don't update if this was just synced from script (prevent feedback loop)
        if (param.syncedFromScript) {
          param.syncedFromScript = false;
          return state;
        }

        // Store previous values for comparison
        const prevValue = param.value;
        const prevEnabled = param.enabled;

        // Update parameter
        param.value = value;
        param.enabled = enabled;
        param.source = enabled && value !== undefined ? 'user' : 'unset';

        // Check for conflicts with script value
        if (param.scriptValue !== undefined) {
          param.hasConflict = enabled && param.value !== param.scriptValue;
        } else {
          param.hasConflict = false;
        }

        // Always sync form changes to script (bidirectional) unless in resubmit mode
        const valueChanged = prevValue !== value || prevEnabled !== enabled;
        const shouldSyncToScript = valueChanged && !state.isResubmit;

        if (shouldSyncToScript) {
          // Clear any existing debounce timer
          if (state.scriptUpdateDebounceTimer) {
            clearTimeout(state.scriptUpdateDebounceTimer);
          }

          // Immediate update for enable/disable, debounced for value changes
          const debounceDelay = prevEnabled !== enabled ? 0 : 300;

          state.scriptUpdateDebounceTimer = setTimeout(() => {
            store.update(innerState => {
              // Update the script with current parameters
              const updatedScript = updateScriptWithParameters(
                innerState.rawScriptContent || innerState.scriptContent,
                innerState.parameters
              );

              // Update both script contents
              innerState.scriptContent = updatedScript;
              innerState.rawScriptContent = updatedScript;
              innerState.scriptUpdateDebounceTimer = undefined;

              // Re-parse to update line numbers
              const directives = parseSbatchDirectives(updatedScript);
              for (const [key, { line }] of directives) {
                const p = innerState.parameters.get(key);
                if (p) {
                  p.scriptLine = line;
                }
              }

              return innerState;
            });
          }, debounceDelay) as unknown as number;
        }

        return state;
      });
    },

    // Handle real-time script editing (called as user types)
    handleScriptEdit(content: string) {
      store.update(state => {
        // Update raw content immediately for responsive editing
        state.rawScriptContent = content;
        state.scriptContent = content;
        state.scriptHasSbatch = hasSbatchDirectives(content);

        // Clear any existing parse timer
        if (state.scriptUpdateDebounceTimer) {
          clearTimeout(state.scriptUpdateDebounceTimer);
        }

        // Debounce the parsing and syncing
        state.scriptUpdateDebounceTimer = setTimeout(() => {
          store.update(innerState => {
            // Always sync from script to form (script is source of truth)
            const directives = parseSbatchDirectives(content);

            for (const param of innerState.parameters.values()) {
              const scriptDirective = directives.get(param.name);

              if (scriptDirective) {
                const { value, line } = scriptDirective;
                const valueChanged = param.scriptValue !== value;

                param.scriptValue = value;
                param.scriptLine = line;

                // Always update form value when script changes (script is source of truth)
                if (valueChanged) {
                  param.value = value;
                  param.enabled = true;
                  param.source = 'script';
                  param.hasConflict = false;
                  param.syncedFromScript = true;
                }
              } else {
                // Parameter was removed from script
                if (param.scriptLine !== undefined) {
                  param.scriptValue = undefined;
                  param.scriptLine = undefined;
                  param.hasConflict = false;

                  // Disable in form if it was from script
                  if (param.source === 'script') {
                    param.enabled = false;
                    param.source = 'unset';
                  }
                }
              }
            }

            innerState.scriptUpdateDebounceTimer = undefined;
            return innerState;
          });
        }, 300) as unknown as number;

        return state;
      });
    },

    // Set sync mode
    setSyncMode(mode: SyncMode) {
      store.update(state => ({ ...state, syncMode: mode }));
    },

    // Set conflict resolution strategy
    setConflictResolution(strategy: 'script' | 'form' | 'merge') {
      store.update(state => {
        state.conflictResolution = strategy;

        // Apply resolution immediately
        if (strategy === 'script') {
          // Use script values for all parameters with script values
          for (const param of state.parameters.values()) {
            if (param.scriptValue !== undefined) {
              param.value = param.scriptValue;
              param.source = 'script';
              param.enabled = true;
              param.hasConflict = false;
              param.syncedFromScript = true; // Mark to prevent feedback
            }
          }
        } else if (strategy === 'form') {
          // Keep form values and update script to match
          for (const param of state.parameters.values()) {
            param.hasConflict = false;
          }
          // Update script with form values
          const updatedScript = updateScriptWithParameters(
            state.rawScriptContent || state.scriptContent,
            state.parameters
          );
          state.scriptContent = updatedScript;
          state.rawScriptContent = updatedScript;
        } else if (strategy === 'merge') {
          // Form values override script where explicitly set
          for (const param of state.parameters.values()) {
            if (param.scriptValue !== undefined && param.source !== 'user') {
              param.value = param.scriptValue;
              param.source = 'merged';
              param.syncedFromScript = true;
            }
            param.hasConflict = false;
          }
        }

        return state;
      });
    },

    // Get final parameters for API submission
    getFinalParameters(): Record<string, any> {
      const state = get(store);
      const result: Record<string, any> = {};

      for (const [name, param] of state.parameters) {
        if (!param.enabled || param.source === 'unset') continue;

        let value = param.value;

        // Handle conflict resolution if in script mode with SBATCH directives
        if (state.mode === 'script' && state.scriptHasSbatch && param.scriptValue !== undefined) {
          switch (state.conflictResolution) {
            case 'script':
              value = param.scriptValue;
              break;
            case 'form':
              // Keep form value
              break;
            case 'merge':
              // Form overrides script only if explicitly set by user
              value = param.source === 'user' ? param.value : param.scriptValue;
              break;
          }
        }

        // Map internal names to API names
        const apiNameMap: Record<string, string> = {
          'cpus': 'cpus',
          'mem': 'mem',
          'gpus_per_node': 'gpus_per_node',
          'ntasks_per_node': 'n_tasks_per_node',
          // Add more mappings as needed
        };

        const apiName = apiNameMap[name] || name;
        result[apiName] = value;
      }

      return result;
    },

    // Set resubmit mode
    setResubmitMode(isResubmit: boolean) {
      store.update(state => ({ ...state, isResubmit }));
    },

    // Set script content for resubmit (bypasses form sync)
    setResubmitScript(content: string) {
      store.update(state => {
        state.rawScriptContent = content;
        state.scriptContent = content;
        state.scriptHasSbatch = hasSbatchDirectives(content);
        state.lastScriptUpdate = Date.now();
        state.isResubmit = true;

        // Parse SBATCH directives but don't sync to form
        const directives = parseSbatchDirectives(content);

        // Update parameters with script values but keep them as 'script' source
        for (const param of state.parameters.values()) {
          const scriptDirective = directives.get(param.name);

          if (scriptDirective) {
            const { value, line } = scriptDirective;
            param.scriptValue = value;
            param.scriptLine = line;
            param.value = value;
            param.enabled = true;
            param.source = 'script';
            param.hasConflict = false;
          } else {
            // Parameter not in script
            param.scriptValue = undefined;
            param.scriptLine = undefined;
            param.hasConflict = false;
          }
        }

        // Auto-switch to script mode if we detect SBATCH directives
        if (state.scriptHasSbatch && state.mode === 'quick') {
          state.mode = 'script';
        }

        return state;
      });
    },

    // Reset to initial state
    reset() {
      store.set(initialState);
    },
  };
}

export const jobParameters = createJobParametersStore();

// Derived store for validation
export const parametersValid = derived(
  jobParameters,
  $params => {
    // At minimum, we need a host selected
    return $params.selectedHost !== undefined;
  }
);

// Derived store for detecting conflicts
export const hasParameterConflicts = derived(
  jobParameters,
  $params => {
    if ($params.mode !== 'script' || !$params.scriptHasSbatch) return false;

    for (const param of $params.parameters.values()) {
      if (param.enabled && param.scriptValue !== undefined &&
        param.value !== param.scriptValue && param.source === 'user') {
        return true;
      }
    }
    return false;
  }
);
