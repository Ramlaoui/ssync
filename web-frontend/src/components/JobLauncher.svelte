<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { slide, fade, fly } from 'svelte/transition';
  import { cn } from '../lib/utils';
  import Button from '../lib/components/ui/Button.svelte';
  import Input from '../lib/components/ui/Input.svelte';
  import Label from '../lib/components/ui/Label.svelte';
  import Select from '../lib/components/ui/Select.svelte';
  import Card from '../lib/components/ui/Card.svelte';
  import CodeMirrorEditor from './CodeMirrorEditor.svelte';
  import NavigationHeader from './NavigationHeader.svelte';
  import FileBrowser from './FileBrowser.svelte';
  import SyncSettings from './SyncSettings.svelte';
  import ScriptHistory from './ScriptHistory.svelte';
  import type { HostInfo } from '../types/api';

  // Icons
  import {
    Play,
    Settings,
    ChevronDown,
    ChevronRight,
    Zap,
    Clock,
    Cpu,
    HardDrive,
    Server,
    Monitor,
    RefreshCw,
    FolderOpen,
    FileText,
    History,
    MoreHorizontal,
    Palette,
    Type,
    ToggleLeft,
    ToggleRight,
    Folder,
    GitBranch,
    ArrowUpDown,
    X,
    Sliders,
    Check,
    AlertCircle,
    Plus,
    Edit2,
    Trash2,
    Save,
    Beaker,
    Database,
    Cloud,
    Rocket,
    Brain,
    Shield,
    Code,
    Terminal,
    ChevronLeft,
    Download
  } from 'lucide-svelte';

  const dispatch = createEventDispatcher();

  // Props
  export let script = `#!/bin/bash
#SBATCH --job-name=my_job
#SBATCH --time=1:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1

# Your commands here
echo "Starting job..."
`;
  export let launching = false;
  export let hosts: HostInfo[] = [];
  export let selectedHost = '';
  export let loading = false;
  export let validationDetails: any = { isValid: false };

  // Script Templates
  interface ScriptTemplate {
    id: string;
    name: string;
    description?: string;
    script_content: string;
    parameters: any;
    tags?: string[];
    created_at: string;
    last_used?: string;
    use_count: number;
  }

  let scriptTemplates: ScriptTemplate[] = loadScriptTemplates();
  let showSaveTemplateDialog = false;
  let templateName = '';
  let templateDescription = '';

  // Simple shared state for parameters - this is the single source of truth
  let parameters = {
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

  // State
  let showAdvanced = false;
  let showPresets = false; // Keep for mobile dropdown compatibility
  let showHistory = false;
  let showTemplates = false;
  let showEditorOptions = false;
  let showFileBrowser = false;
  let showSyncSettings = false;
  let showHostDropdown = false;
  let isMobile = false;
  let showMobileConfig = false;
  let isClosingConfig = false;
  let mobileConfigView = 'main'; // 'main', 'directory', 'sync'
  let showValidationInfo = false;
  let showPresetManager = false;
  let showPresetSidebar = false; // New unified preset sidebar for desktop/mobile
  let editingPreset: Preset | null = null;
  let newPreset: Partial<Preset> = {
    name: '',
    icon: Zap,
    color: 'bg-blue-500'
  };
  let showIconDropdown = false;
  let showColorDropdown = false;

  // Sync settings state
  let excludePatterns = ['*.log', '*.tmp', '__pycache__/'];
  let includePatterns = [];
  let noGitignore = false;

  // Parse SBATCH directives from script
  function parseSbatchFromScript(scriptContent: string) {
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

  // Update script with SBATCH directives
  function updateScriptWithParameters() {
    const lines = script.split('\n');
    const allSbatchLines = [];
    const knownDirectives = new Set(['job-name', 'J', 'partition', 'p', 'account', 'A',
                                     'nodes', 'cpus-per-task', 'cpus', 'mem', 'memory',
                                     'time', 'constraint', 'C', 'ntasks-per-node',
                                     'gpus-per-node', 'gres', 'output', 'o', 'error', 'e']);
    let shebangLine = '';
    let bodyLines = [];
    let foundSbatch = false;
    let foundBody = false;

    // Parse existing script and preserve all SBATCH lines
    lines.forEach((line, index) => {
      if (index === 0 && line.startsWith('#!')) {
        shebangLine = line;
      } else if (line.startsWith('#SBATCH')) {
        allSbatchLines.push(line);
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

    // Process SBATCH lines - update known ones, preserve unknown ones
    const updatedSbatchLines = [];
    const processedDirectives = new Set();

    allSbatchLines.forEach(line => {
      const match = line.match(/#SBATCH\s+--?([a-zA-Z-]+)/);
      if (match) {
        const directive = match[1];

        // Check if this is a directive we manage
        if (knownDirectives.has(directive)) {
          // Skip it if we've already processed this directive type
          if (!processedDirectives.has(directive)) {
            processedDirectives.add(directive);

            // Add updated version based on parameters
            let updatedLine = null;
            switch(directive) {
              case 'job-name':
              case 'J':
                if (parameters.jobName) updatedLine = `#SBATCH --job-name=${parameters.jobName}`;
                break;
              case 'partition':
              case 'p':
                if (parameters.partition) updatedLine = `#SBATCH --partition=${parameters.partition}`;
                break;
              case 'account':
              case 'A':
                if (parameters.account) updatedLine = `#SBATCH --account=${parameters.account}`;
                break;
              case 'nodes':
                if (parameters.nodes) updatedLine = `#SBATCH --nodes=${parameters.nodes}`;
                break;
              case 'cpus-per-task':
              case 'cpus':
                if (parameters.cpus) updatedLine = `#SBATCH --cpus-per-task=${parameters.cpus}`;
                break;
              case 'mem':
              case 'memory':
                if (parameters.memory) updatedLine = `#SBATCH --mem=${parameters.memory}G`;
                break;
              case 'time':
                if (parameters.timeLimit) {
                  const hours = Math.floor(parameters.timeLimit / 60);
                  const minutes = parameters.timeLimit % 60;
                  updatedLine = `#SBATCH --time=${hours}:${minutes.toString().padStart(2, '0')}:00`;
                }
                break;
              case 'constraint':
              case 'C':
                if (parameters.constraint) updatedLine = `#SBATCH --constraint=${parameters.constraint}`;
                break;
              case 'ntasks-per-node':
                if (parameters.ntasksPerNode) updatedLine = `#SBATCH --ntasks-per-node=${parameters.ntasksPerNode}`;
                break;
              case 'gpus-per-node':
                if (parameters.gpusPerNode) updatedLine = `#SBATCH --gpus-per-node=${parameters.gpusPerNode}`;
                break;
              case 'gres':
                if (parameters.gres) updatedLine = `#SBATCH --gres=${parameters.gres}`;
                break;
              case 'output':
              case 'o':
                if (parameters.outputFile) updatedLine = `#SBATCH --output=${parameters.outputFile}`;
                break;
              case 'error':
              case 'e':
                if (parameters.errorFile) updatedLine = `#SBATCH --error=${parameters.errorFile}`;
                break;
            }

            if (updatedLine) {
              updatedSbatchLines.push(updatedLine);
            }
          }
        } else {
          // Preserve unknown directives as-is
          updatedSbatchLines.push(line);
        }
      } else {
        // Preserve malformed SBATCH lines as-is
        updatedSbatchLines.push(line);
      }
    });

    // Add new directives that weren't in the original script
    if (parameters.jobName && !processedDirectives.has('job-name') && !processedDirectives.has('J')) {
      updatedSbatchLines.push(`#SBATCH --job-name=${parameters.jobName}`);
    }
    if (parameters.partition && !processedDirectives.has('partition') && !processedDirectives.has('p')) {
      updatedSbatchLines.push(`#SBATCH --partition=${parameters.partition}`);
    }
    if (parameters.account && !processedDirectives.has('account') && !processedDirectives.has('A')) {
      updatedSbatchLines.push(`#SBATCH --account=${parameters.account}`);
    }
    if (parameters.nodes && !processedDirectives.has('nodes')) {
      updatedSbatchLines.push(`#SBATCH --nodes=${parameters.nodes}`);
    }
    if (parameters.cpus && !processedDirectives.has('cpus-per-task') && !processedDirectives.has('cpus')) {
      updatedSbatchLines.push(`#SBATCH --cpus-per-task=${parameters.cpus}`);
    }
    if (parameters.memory && !processedDirectives.has('mem') && !processedDirectives.has('memory')) {
      updatedSbatchLines.push(`#SBATCH --mem=${parameters.memory}G`);
    }
    if (parameters.timeLimit && !processedDirectives.has('time')) {
      const hours = Math.floor(parameters.timeLimit / 60);
      const minutes = parameters.timeLimit % 60;
      updatedSbatchLines.push(`#SBATCH --time=${hours}:${minutes.toString().padStart(2, '0')}:00`);
    }
    if (parameters.constraint && !processedDirectives.has('constraint') && !processedDirectives.has('C')) {
      updatedSbatchLines.push(`#SBATCH --constraint=${parameters.constraint}`);
    }
    if (parameters.ntasksPerNode && !processedDirectives.has('ntasks-per-node')) {
      updatedSbatchLines.push(`#SBATCH --ntasks-per-node=${parameters.ntasksPerNode}`);
    }
    if (parameters.gpusPerNode && !processedDirectives.has('gpus-per-node')) {
      updatedSbatchLines.push(`#SBATCH --gpus-per-node=${parameters.gpusPerNode}`);
    }
    if (parameters.gres && !processedDirectives.has('gres')) {
      updatedSbatchLines.push(`#SBATCH --gres=${parameters.gres}`);
    }
    if (parameters.outputFile && !processedDirectives.has('output') && !processedDirectives.has('o')) {
      updatedSbatchLines.push(`#SBATCH --output=${parameters.outputFile}`);
    }
    if (parameters.errorFile && !processedDirectives.has('error') && !processedDirectives.has('e')) {
      updatedSbatchLines.push(`#SBATCH --error=${parameters.errorFile}`);
    }

    // Rebuild script
    let newLines = [];

    // Add shebang
    newLines.push(shebangLine || '#!/bin/bash');

    // Add all SBATCH directives (updated and preserved)
    if (updatedSbatchLines.length > 0) {
      newLines.push(...updatedSbatchLines);
    }

    // Add body with proper spacing
    if (bodyLines.length > 0) {
      // Remove leading empty lines from bodyLines
      while (bodyLines.length > 0 && bodyLines[0].trim() === '') {
        bodyLines.shift();
      }

      // Only add content if there's actual content
      if (bodyLines.length > 0) {
        // Add single blank line between SBATCH and body if there are SBATCH lines
        if (updatedSbatchLines.length > 0) {
          newLines.push('');
        }
        newLines.push(...bodyLines);
      }
    }

    script = newLines.join('\n');
  }

  // Handle script changes from editor
  function handleScriptEdit(newScript: string) {
    script = newScript;
    // Parse SBATCH directives from the new script
    parseSbatchFromScript(script);
  }

  // Editor options with localStorage persistence
  let editorOptions = {
    vimMode: typeof localStorage !== 'undefined' ? localStorage.getItem('editor-vim-mode') === 'true' : true,
    theme: typeof localStorage !== 'undefined' ? localStorage.getItem('editor-theme') || 'light' : 'light',
    fontSize: typeof localStorage !== 'undefined' ? parseInt(localStorage.getItem('editor-font-size') || '14') : 14,
    lineNumbers: typeof localStorage !== 'undefined' ? localStorage.getItem('editor-line-numbers') !== 'false' : true,
    wordWrap: typeof localStorage !== 'undefined' ? localStorage.getItem('editor-word-wrap') === 'true' : false,
    tabSize: typeof localStorage !== 'undefined' ? parseInt(localStorage.getItem('editor-tab-size') || '2') : 2,
    autoIndent: typeof localStorage !== 'undefined' ? localStorage.getItem('editor-auto-indent') !== 'false' : true
  };

  // Legacy vim mode for backwards compatibility
  $: vimMode = editorOptions.vimMode;

  // Quick presets for fast job launching
  // Preset types and data
  interface Preset {
    id: string;
    name: string;
    icon: any;
    time: number;
    memory: number;
    cpus: number;
    gpus?: number;
    nodes?: number;
    partition?: string;
    account?: string;
    color: string;
    isCustom?: boolean;
    isDefault?: boolean;
  }

  const iconOptions = [
    { name: 'Zap', icon: Zap },
    { name: 'Clock', icon: Clock },
    { name: 'CPU', icon: Cpu },
    { name: 'Monitor', icon: Monitor },
    { name: 'Server', icon: Server },
    { name: 'Database', icon: Database },
    { name: 'Cloud', icon: Cloud },
    { name: 'Rocket', icon: Rocket },
    { name: 'Beaker', icon: Beaker },
    { name: 'Brain', icon: Brain },
    { name: 'Shield', icon: Shield },
    { name: 'Code', icon: Code },
    { name: 'Terminal', icon: Terminal }
  ];

  const colorOptions = [
    { name: 'Yellow', class: 'bg-yellow-500' },
    { name: 'Blue', class: 'bg-blue-500' },
    { name: 'Green', class: 'bg-green-500' },
    { name: 'Purple', class: 'bg-purple-500' },
    { name: 'Red', class: 'bg-red-500' },
    { name: 'Pink', class: 'bg-pink-500' },
    { name: 'Indigo', class: 'bg-indigo-500' },
    { name: 'Teal', class: 'bg-teal-500' },
    { name: 'Orange', class: 'bg-orange-500' },
    { name: 'Gray', class: 'bg-gray-500' }
  ];

  let defaultPresets: Preset[] = [
    { id: 'quick', name: 'Quick Test', icon: Zap, time: 10, memory: 2, cpus: 1, color: 'bg-yellow-500', isDefault: true },
    { id: 'standard', name: 'Standard', icon: Cpu, time: 60, memory: 4, cpus: 2, color: 'bg-blue-500', isDefault: true },
    { id: 'long', name: 'Long Run', icon: Clock, time: 1440, memory: 8, cpus: 4, color: 'bg-green-500', isDefault: true },
    { id: 'gpu', name: 'GPU', icon: Monitor, time: 240, memory: 16, cpus: 4, gpus: 1, color: 'bg-purple-500', isDefault: true }
  ];

  // Load custom presets from localStorage
  function loadCustomPresets(): Preset[] {
    try {
      // Load customized default presets
      const savedDefaults = localStorage.getItem('ssync_default_presets');
      if (savedDefaults) {
        const parsedDefaults = JSON.parse(savedDefaults);
        defaultPresets = parsedDefaults.map(p => ({
          ...p,
          icon: iconOptions.find(io => io.name === p.iconName)?.icon || Zap,
          isDefault: true
        }));
      }

      // Load custom presets
      const stored = localStorage.getItem('ssync_custom_presets');
      if (stored) {
        const presets = JSON.parse(stored);
        // Restore icon references
        return presets.map(p => ({
          ...p,
          icon: iconOptions.find(io => io.name === p.iconName)?.icon || Zap,
          isCustom: true
        }));
      }
    } catch (e) {
      console.error('Failed to load presets:', e);
    }
    return [];
  }

  // Save custom presets to localStorage
  function saveCustomPresets() {
    try {
      const toSave = customPresets.map(p => ({
        ...p,
        iconName: iconOptions.find(io => io.icon === p.icon)?.name || 'Zap',
        icon: undefined // Don't save the component reference
      }));
      localStorage.setItem('ssync_custom_presets', JSON.stringify(toSave));
    } catch (e) {
      console.error('Failed to save custom presets:', e);
    }
  }

  // Save default presets to localStorage
  function saveDefaultPresets() {
    try {
      const toSave = defaultPresets.map(p => ({
        ...p,
        iconName: iconOptions.find(io => io.icon === p.icon)?.name || 'Zap',
        icon: undefined // Don't save the component reference
      }));
      localStorage.setItem('ssync_default_presets', JSON.stringify(toSave));
    } catch (e) {
      console.error('Failed to save default presets:', e);
    }
  }

  let customPresets: Preset[] = loadCustomPresets();
  // Combine all presets without distinction
  $: allPresets = [...defaultPresets, ...customPresets];

  $: canLaunch = validationDetails.isValid && selectedHost;

  // Get specific message about what's preventing launch
  $: launchDisabledReason = !selectedHost
    ? 'Select a host to continue'
    : !validationDetails.isValid
    ? (validationDetails.missingText || 'Complete required fields')
    : '';

  function handleScriptChange(event: CustomEvent) {
    handleScriptEdit(event.detail.content);
    dispatch('scriptChanged', { content: event.detail.content });
  }

  function applyPreset(preset: Preset) {
    parameters.timeLimit = preset.time;
    parameters.memory = preset.memory;
    parameters.cpus = preset.cpus;
    parameters.gpusPerNode = preset.gpus || 0;
    parameters.nodes = preset.nodes || 1;
    if (preset.partition) parameters.partition = preset.partition;
    if (preset.account) parameters.account = preset.account;
    handleConfigChange();
    showPresets = false;
  }

  function createPresetFromCurrent() {
    newPreset = {
      name: '',
      time: parameters.timeLimit || 60,
      memory: parameters.memory || 4,
      cpus: parameters.cpus || 1,
      gpus: parameters.gpusPerNode,
      nodes: parameters.nodes,
      partition: parameters.partition,
      account: parameters.account,
      icon: Zap,
      color: 'bg-blue-500'
    };
    editingPreset = null;
  }

  function savePreset() {
    if (!newPreset.name) return;

    const preset: Preset = {
      id: editingPreset?.id || `custom-${Date.now()}`,
      name: newPreset.name,
      time: newPreset.time || parameters.timeLimit || 60,
      memory: newPreset.memory || parameters.memory || 4,
      cpus: newPreset.cpus || parameters.cpus || 1,
      gpus: newPreset.gpus,
      nodes: newPreset.nodes,
      partition: newPreset.partition,
      account: newPreset.account,
      icon: newPreset.icon || Zap,
      color: newPreset.color || 'bg-blue-500',
      isCustom: editingPreset?.isCustom !== false,
      isDefault: editingPreset?.isDefault
    };

    if (editingPreset) {
      // Check if editing a default preset
      if (editingPreset.isDefault) {
        const index = defaultPresets.findIndex(p => p.id === editingPreset.id);
        if (index >= 0) {
          defaultPresets[index] = preset;
          defaultPresets = [...defaultPresets];
          saveDefaultPresets();
        }
      } else {
        // Update existing custom preset
        const index = customPresets.findIndex(p => p.id === editingPreset.id);
        if (index >= 0) {
          customPresets[index] = preset;
          customPresets = [...customPresets];
          saveCustomPresets();
        }
      }
    } else {
      // Add new preset
      customPresets = [...customPresets, preset];
      saveCustomPresets();
    }

    resetPresetForm();
    editingPreset = null;
    // After saving, go back to preset selection view
    showPresetManager = false;
    // Keep sidebar open to show the new/updated preset
    showPresetSidebar = true;
  }

  function editPreset(preset: Preset) {
    editingPreset = preset;
    newPreset = {
      name: preset.name,
      time: preset.time,
      memory: preset.memory,
      cpus: preset.cpus,
      gpus: preset.gpus,
      nodes: preset.nodes,
      partition: preset.partition,
      account: preset.account,
      icon: preset.icon,
      color: preset.color
    };
  }

  function deletePreset(preset: Preset) {
    if (preset.isDefault) {
      // Remove from default presets
      defaultPresets = defaultPresets.filter(p => p.id !== preset.id);
      saveDefaultPresets();
    } else {
      // Remove from custom presets
      customPresets = customPresets.filter(p => p.id !== preset.id);
      saveCustomPresets();
    }
  }

  function resetPresetForm() {
    newPreset = {
      name: '',
      icon: Zap,
      color: 'bg-blue-500'
    };
  }

  function handleConfigChange() {
    // Trigger script update when form changes
    updateScriptWithParameters();
    dispatch('configChanged', { detail: parameters });
  }

  function handleLaunch() {
    if (canLaunch) {
      // Save script to localStorage for history
      saveScriptToLocalHistory();
      dispatch('launch');
    }
  }

  function saveScriptToLocalHistory() {
    try {
      const history = JSON.parse(localStorage.getItem('scriptHistory') || '[]');
      const entry = {
        script_content: script,
        job_name: parameters.jobName || 'Unnamed Job',
        hostname: selectedHost || 'unknown',
        submit_time: new Date().toISOString(),
        state: 'PENDING',
        job_id: `local_${Date.now()}`
      };

      // Add to beginning of history
      history.unshift(entry);

      // Keep only last 50 scripts
      if (history.length > 50) {
        history.length = 50;
      }

      localStorage.setItem('scriptHistory', JSON.stringify(history));
    } catch (e) {
      console.error('Failed to save script to history:', e);
    }
  }

  // Script Template Functions
  function loadScriptTemplates(): ScriptTemplate[] {
    try {
      const stored = localStorage.getItem('scriptTemplates');
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (e) {
      console.error('Failed to load script templates:', e);
    }
    return [];
  }

  function saveScriptTemplates() {
    try {
      localStorage.setItem('scriptTemplates', JSON.stringify(scriptTemplates));
    } catch (e) {
      console.error('Failed to save script templates:', e);
    }
  }

  function saveAsTemplate() {
    if (!templateName.trim()) {
      alert('Please enter a template name');
      return;
    }

    const template: ScriptTemplate = {
      id: `template_${Date.now()}`,
      name: templateName.trim(),
      description: templateDescription.trim(),
      script_content: script,
      parameters: {
        ...parameters,
        selectedHost,
        sourceDir: parameters.sourceDir
      },
      tags: [],
      created_at: new Date().toISOString(),
      use_count: 0
    };

    scriptTemplates = [template, ...scriptTemplates];
    saveScriptTemplates();

    // Reset dialog
    showSaveTemplateDialog = false;
    templateName = '';
    templateDescription = '';

    // Show success message (you could make this a toast)
    console.log('Template saved:', template.name);
  }

  function loadTemplate(template: ScriptTemplate) {
    // Update script - just set the value, don't call handleScriptEdit
    // The editor will pick up the change through reactive binding
    script = template.script_content;

    // Parse SBATCH directives from the loaded script
    parseSbatchFromScript(script);

    // Update parameters
    if (template.parameters) {
      // Load job parameters
      const { selectedHost: savedHost, sourceDir: savedDir, ...jobParams } = template.parameters;
      Object.assign(parameters, jobParams);

      // Load host and directory if saved
      if (savedHost) selectedHost = savedHost;
      if (savedDir) parameters.sourceDir = savedDir;

      handleConfigChange();
    }

    // Update last used and use count
    template.last_used = new Date().toISOString();
    template.use_count = (template.use_count || 0) + 1;
    saveScriptTemplates();
  }

  function deleteTemplate(templateId: string) {
    if (confirm('Are you sure you want to delete this template?')) {
      scriptTemplates = scriptTemplates.filter(t => t.id !== templateId);
      saveScriptTemplates();
    }
  }

  function handleHistoryClick() {
    showHistory = !showHistory;
    dispatch('openHistory');
  }

  function handleDirectorySelect(event: CustomEvent) {
    parameters.sourceDir = event.detail;
    handleConfigChange();
    // Dispatch pathSelected event for parent to handle with store action
    dispatch('pathSelected', event.detail);
    showFileBrowser = false;
    // Close mobile config sidebar if open
    if (isMobile && showMobileConfig) {
      showMobileConfig = false;
      mobileConfigView = 'main';
    }
  }

  function handleSyncSettingsChange(event: CustomEvent) {
    excludePatterns = event.detail.excludePatterns;
    includePatterns = event.detail.includePatterns;
    noGitignore = event.detail.noGitignore;
    dispatch('syncSettingsChanged', event.detail);
  }

  // Editor options handlers
  function updateEditorOption(key: keyof typeof editorOptions, value: any) {
    editorOptions = { ...editorOptions, [key]: value };
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(`editor-${key.replace(/([A-Z])/g, '-$1').toLowerCase()}`, value.toString());
    }
  }

  // Theme options
  const themeOptions = [
    { id: 'light', name: 'Light', description: 'Classic light theme' },
    { id: 'dark', name: 'Dark', description: 'Dark theme for low-light' },
    { id: 'material', name: 'Material', description: 'Material design theme' },
    { id: 'dracula', name: 'Dracula', description: 'Popular dark theme' }
  ];

  // Font size options
  const fontSizeOptions = [10, 12, 14, 16, 18, 20, 22];

  // Tab size options
  const tabSizeOptions = [2, 4, 8];

  // Initialize component - ensure FileBrowser uses persisted directory
  onMount(async () => {
    // Load hosts if not provided or empty
    if (!hosts || hosts.length === 0) {
      try {
        const { api } = await import('../services/api');
        const response = await api.get('/api/hosts');
        hosts = response.data;

        // Auto-select first host if none selected
        if (hosts.length > 0 && !selectedHost) {
          selectedHost = hosts[0].hostname;
        }
      } catch (error) {
        console.error('Failed to load hosts:', error);
      }
    }

    // If we have a persisted sourceDir but FileBrowser isn't showing it, update the initialPath
    if (parameters.sourceDir && parameters.sourceDir.trim()) {
      // The FileBrowser will use the initialPath from the parameters.sourceDir automatically
      // No additional action needed as the store already loads from localStorage
    }

    // Parse initial script if provided
    if (script) {
      parseSbatchFromScript(script);
    }

    // Apply host defaults if host is selected (removed - no longer using store)

    // Check if mobile
    checkMobile();
    window.addEventListener('resize', checkMobile);

    // Click outside handler for dropdowns
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;

      // Check for host dropdown
      if (!target.closest('.host-dropdown-container') && showHostDropdown) {
        showHostDropdown = false;
      }

      // Check for editor options dropdown
      if (!target.closest('.editor-options-dropdown') && showEditorOptions) {
        showEditorOptions = false;
      }
    };

    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
      window.removeEventListener('resize', checkMobile);
    };
  });

  function checkMobile() {
    isMobile = window.innerWidth < 768;
  }
</script>

<div class="modern-launcher">
  <!-- Mobile Header -->
  {#if isMobile}
    <header class="mobile-header">
      <button class="mobile-back-btn" on:click={() => window.history.back()}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>
      <div class="mobile-divider"></div>
      <select bind:value={selectedHost} class="mobile-host-select">
        <option value="">Host</option>
        {#each hosts as host}
          <option value={host.hostname}>{host.hostname}</option>
        {/each}
      </select>
      <div class="mobile-icon-group">
        <!-- Validation Status Dot -->
        <button
          class="mobile-icon-btn validation-dot-mobile"
          class:valid={validationDetails.isValid}
          class:invalid={!validationDetails.isValid}
          on:click={() => showValidationInfo = !showValidationInfo}
          title={validationDetails.isValid ? 'Valid' : 'Invalid'}
        >
          <div class="status-dot-small" class:valid={validationDetails.isValid} class:invalid={!validationDetails.isValid}></div>
        </button>

        <!-- Editor Options -->
        <button
          class="mobile-icon-btn"
          on:click={(e) => {
            e.stopPropagation();
            showEditorOptions = !showEditorOptions;
          }}
          title="Editor"
        >
          <MoreHorizontal class="w-3.5 h-3.5" />
        </button>

        <div class="mobile-divider-vertical"></div>

        <button
          class="mobile-icon-btn"
          on:click={handleHistoryClick}
          title="History"
        >
          <History class="w-3.5 h-3.5" />
        </button>
        <button
          class="mobile-icon-btn"
          on:click={() => {
            showPresets = !showPresets;
            if (showPresets) {
              showPresetManager = false;
            }
          }}
          title="Templates"
        >
          <Zap class="w-3.5 h-3.5" />
        </button>
        <button
          class="mobile-icon-btn"
          on:click={() => showMobileConfig = !showMobileConfig}
          title="Options"
        >
          <Sliders class="w-3.5 h-3.5" />
        </button>
      </div>
    </header>

    <!-- Mobile Validation Info Popup -->
    {#if showValidationInfo}
      <div class="mobile-validation-popup" transition:slide={{ duration: 200 }}>
        {#if validationDetails.isValid}
          <div class="validation-info-content valid">
            <Check class="w-4 h-4" />
            <span>Script is valid and ready to launch</span>
          </div>
        {:else}
          <div class="validation-info-content invalid">
            <AlertCircle class="w-4 h-4" />
            <span>{validationDetails.missingText || 'Script needs configuration'}</span>
          </div>
        {/if}
      </div>
    {/if}

    <!-- Mobile Editor Options Dropdown -->
    {#if showEditorOptions && isMobile}
      <div class="mobile-options-backdrop" on:click={() => showEditorOptions = false}></div>
      <div class="mobile-editor-options-menu" transition:slide={{ duration: 200 }} on:click|stopPropagation>
        <!-- Copy same options as desktop -->
        <!-- Vim Mode Toggle -->
        <div class="option-item">
          <div class="option-info">
            <span class="option-label">Vim Mode</span>
            <span class="option-description">Vi/Vim key bindings</span>
          </div>
          <button
            class="option-toggle {editorOptions.vimMode ? 'active' : ''}"
            on:click={() => updateEditorOption('vimMode', !editorOptions.vimMode)}
          >
            <svelte:component this={editorOptions.vimMode ? ToggleRight : ToggleLeft} class="w-5 h-5" />
          </button>
        </div>

        <!-- Theme Selection -->
        <div class="option-item">
          <div class="option-info">
            <span class="option-label">Theme</span>
            <span class="option-description">Editor color scheme</span>
          </div>
          <select
            class="option-select"
            bind:value={editorOptions.theme}
            on:change={(e) => updateEditorOption('theme', e.target.value)}
          >
            {#each themeOptions as theme}
              <option value={theme.id}>{theme.name}</option>
            {/each}
          </select>
        </div>

        <!-- Font Size -->
        <div class="option-item">
          <div class="option-info">
            <span class="option-label">Font Size</span>
            <span class="option-description">Editor font size</span>
          </div>
          <select
            class="option-select"
            bind:value={editorOptions.fontSize}
            on:change={(e) => updateEditorOption('fontSize', parseInt(e.target.value))}
          >
            {#each fontSizeOptions as size}
              <option value={size}>{size}px</option>
            {/each}
          </select>
        </div>
      </div>
    {/if}

    <!-- Mobile Presets Dropdown -->
    {#if showPresets}
      <div class="mobile-preset-dropdown" transition:slide={{ duration: 200 }}>
        <div class="preset-dropdown-header">
          <span class="preset-dropdown-title">Presets</span>
          <button
            class="preset-manage-btn"
            on:click={() => {
              showPresetManager = !showPresetManager;
              showPresets = false;
            }}
            title="Manage Presets"
          >
            <Settings class="w-3.5 h-3.5" />
          </button>
        </div>
        {#each allPresets as preset}
          <button
            class="mobile-preset-option"
            on:click={() => applyPreset(preset)}
          >
            <div class="preset-icon {preset.color}">
              <svelte:component this={preset.icon} class="w-3 h-3 text-white" />
            </div>
            <span class="mobile-preset-name">{preset.name}</span>
            <span class="mobile-preset-details">
              {preset.time}m • {preset.memory}GB
              {#if preset.gpus} • {preset.gpus}GPU{/if}
            </span>
          </button>
        {/each}
        <button
          class="mobile-preset-add"
          on:click={() => {
            createPresetFromCurrent();
            showPresetManager = true;
            showPresets = false;
          }}
        >
          <Plus class="w-3.5 h-3.5" />
          <span>Create from current</span>
        </button>
      </div>
    {/if}
  {/if}

  <!-- Unified Preset Sidebar (Selection + Management) - Works for both mobile and desktop -->
  <!-- Unified Preset Sidebar (Selection + Management) - Works for both mobile and desktop -->
  {#if showPresetSidebar || showPresetManager}
    <div
      class="preset-manager-overlay"
      on:click={() => { showPresetSidebar = false; showPresetManager = false; }}
      transition:fade={{ duration: 200 }}
      on:introstart
      on:outrostart
      on:introend
      on:outroend
    >
      <div
        class="preset-manager-sidebar"
        on:click|stopPropagation
        transition:fly={{ x: 400, duration: 300, opacity: 1 }}
      >
        <div class="preset-manager-header">
          <h3>{showPresetManager ? 'Manage Presets' : 'Presets'}</h3>
          <button class="preset-manager-close" on:click={() => { showPresetSidebar = false; showPresetManager = false; }}>
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="preset-manager-content">
          {#if !showPresetManager}
            <!-- Preset Selection Mode -->
            <div class="preset-selection-section">
              <div class="preset-section-header">
                <h4>Quick Apply</h4>
                <button
                  class="preset-manage-toggle-btn"
                  on:click={() => showPresetManager = true}
                  title="Manage Presets"
                >
                  <Settings class="w-4 h-4" />
                </button>
              </div>

              <div class="preset-quick-grid">
                {#each allPresets as preset}
                  <button
                    class="preset-quick-item"
                    on:click={() => {
                      applyPreset(preset);
                      showPresetSidebar = false;
                    }}
                  >
                    <div class="preset-icon {preset.color}">
                      <svelte:component this={preset.icon} class="h-4 w-4 text-white" />
                    </div>
                    <div class="preset-quick-info">
                      <span class="preset-name">{preset.name}</span>
                      <span class="preset-specs">
                        {preset.time}min • {preset.memory}GB • {preset.cpus}CPU{preset.cpus > 1 ? 's' : ''}
                        {#if preset.gpus} • {preset.gpus}GPU{/if}
                      </span>
                    </div>
                  </button>
                {/each}
              </div>

              <button
                class="preset-create-from-current"
                on:click={() => {
                  createPresetFromCurrent();
                  showPresetManager = true;
                }}
              >
                <Plus class="w-4 h-4" />
                <span>Create from current settings</span>
              </button>
            </div>
          {:else}
            <!-- Preset Management Mode -->
            <div class="preset-management-section">
              <div class="preset-section-header">
                <button
                  class="preset-back-btn"
                  on:click={() => showPresetManager = false}
                  title="Back to presets"
                >
                  <ChevronLeft class="w-4 h-4" />
                  <span>Back</span>
                </button>
              </div>

              <!-- Create/Edit Form -->
              <div class="preset-form">
                <h4>{editingPreset ? 'Edit Preset' : 'New Preset'}</h4>

                <div class="preset-form-field">
                  <label>Name</label>
                  <input
                    type="text"
                    bind:value={newPreset.name}
                    placeholder="Enter preset name"
                    class="preset-input"
                  />
                </div>

                <div class="preset-form-row">
                  <div class="preset-form-field">
                    <label>Icon</label>
                    <div class="dropdown-container">
                      <button
                        type="button"
                        class="dropdown-trigger"
                        on:click={() => showIconDropdown = !showIconDropdown}
                      >
                        <svelte:component this={newPreset.icon || Zap} class="w-4 h-4" />
                        <span>{iconOptions.find(o => o.icon === newPreset.icon)?.name || 'Select Icon'}</span>
                        <ChevronDown class="w-4 h-4 ml-auto" />
                      </button>
                      {#if showIconDropdown}
                        <div class="dropdown-menu icon-dropdown">
                          {#each iconOptions as opt}
                            <button
                              type="button"
                              class="dropdown-item {newPreset.icon === opt.icon ? 'selected' : ''}"
                              on:click={() => {
                                newPreset.icon = opt.icon;
                                showIconDropdown = false;
                              }}
                            >
                              <svelte:component this={opt.icon} class="w-4 h-4" />
                              <span>{opt.name}</span>
                            </button>
                          {/each}
                        </div>
                      {/if}
                    </div>
                  </div>

                  <div class="preset-form-field">
                    <label>Color</label>
                    <div class="dropdown-container">
                      <button
                        type="button"
                        class="dropdown-trigger"
                        on:click={() => showColorDropdown = !showColorDropdown}
                      >
                        <span class="color-preview {newPreset.color}"></span>
                        <span>{colorOptions.find(o => o.class === newPreset.color)?.name || 'Select Color'}</span>
                        <ChevronDown class="w-4 h-4 ml-auto" />
                      </button>
                      {#if showColorDropdown}
                        <div class="dropdown-menu color-dropdown">
                          {#each colorOptions as color}
                            <button
                              type="button"
                              class="dropdown-item {newPreset.color === color.class ? 'selected' : ''}"
                              on:click={() => {
                                newPreset.color = color.class;
                                showColorDropdown = false;
                              }}
                            >
                              <span class="color-preview {color.class}"></span>
                              <span>{color.name}</span>
                            </button>
                          {/each}
                        </div>
                      {/if}
                    </div>
                  </div>
                </div>

                <div class="preset-form-row">
                  <div class="preset-form-field">
                    <label>CPUs</label>
                    <input
                      type="number"
                      bind:value={newPreset.cpus}
                      min="1"
                      class="preset-input"
                    />
                  </div>
                  <div class="preset-form-field">
                    <label>Memory (GB)</label>
                    <input
                      type="number"
                      bind:value={newPreset.memory}
                      min="1"
                      class="preset-input"
                    />
                  </div>
                </div>

                <div class="preset-form-row">
                  <div class="preset-form-field">
                    <label>Time (minutes)</label>
                    <input
                      type="number"
                      bind:value={newPreset.time}
                      min="1"
                      class="preset-input"
                    />
                  </div>
                  <div class="preset-form-field">
                    <label>GPUs (optional)</label>
                    <input
                      type="number"
                      bind:value={newPreset.gpus}
                      min="0"
                      class="preset-input"
                    />
                  </div>
                </div>

                <div class="preset-form-actions">
                  <button
                    class="preset-save-btn"
                    on:click={savePreset}
                    disabled={!newPreset.name}
                  >
                    {editingPreset ? 'Update' : 'Create'} Preset
                  </button>
                  {#if editingPreset}
                    <button
                      class="preset-cancel-btn"
                      on:click={() => {
                        resetPresetForm();
                      }}
                    >
                      Cancel
                    </button>
                  {/if}
                </div>
              </div>

              <!-- All Presets List -->
              <div class="preset-list">
                <h4>All Presets</h4>
                {#each allPresets as preset}
                  <div class="preset-item">
                    <div class="preset-item-info">
                      <div class="preset-icon {preset.color}">
                        <svelte:component this={preset.icon} class="w-3 h-3 text-white" />
                      </div>
                      <div>
                        <div class="preset-item-name">{preset.name}</div>
                        <div class="preset-item-details">
                          {preset.time}m • {preset.memory}GB • {preset.cpus}CPU
                          {#if preset.gpus} • {preset.gpus}GPU{/if}
                        </div>
                      </div>
                    </div>
                    <div class="preset-item-actions">
                      <button
                        class="preset-action-btn"
                        on:click={() => editPreset(preset)}
                        title="Edit"
                      >
                        <Edit2 class="w-3.5 h-3.5" />
                      </button>
                      <button
                        class="preset-action-btn delete"
                        on:click={() => deletePreset(preset)}
                        title="Delete"
                      >
                        <Trash2 class="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                {/each}
              </div>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <!-- Template Browser Dialog -->
  {#if showTemplates}
    <div class="modal-backdrop" on:click={() => showTemplates = false}>
      <div class="template-browser-dialog" on:click|stopPropagation>
        <div class="dialog-header">
          <h3>Script Templates</h3>
          <button
            class="close-btn"
            on:click={() => showTemplates = false}
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="dialog-content">
          {#if scriptTemplates.length === 0}
            <div class="empty-state">
              <FileText class="w-12 h-12 text-gray-400 mx-auto mb-3" />
              <p class="text-gray-600 mb-2">No templates saved yet</p>
              <p class="text-sm text-gray-500">Save your frequently used scripts as templates for quick reuse</p>
            </div>
          {:else}
            <div class="template-grid">
              {#each scriptTemplates as template}
                <div class="template-card">
                  <div class="template-header">
                    <h4 class="template-name">{template.name}</h4>
                    <div class="template-actions">
                      <button
                        class="template-action-btn"
                        on:click={() => {
                          loadTemplate(template);
                          showTemplates = false;
                        }}
                        title="Load template"
                      >
                        <Download class="w-4 h-4" />
                      </button>
                      <button
                        class="template-action-btn delete"
                        on:click={() => {
                          deleteTemplate(template.id);
                        }}
                        title="Delete template"
                      >
                        <Trash2 class="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {#if template.description}
                    <p class="template-description">{template.description}</p>
                  {/if}

                  <div class="template-details">
                    <div class="detail-row">
                      <span class="detail-label">Created:</span>
                      <span class="detail-value">
                        {new Date(template.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    {#if template.last_used}
                      <div class="detail-row">
                        <span class="detail-label">Last used:</span>
                        <span class="detail-value">
                          {new Date(template.last_used).toLocaleDateString()}
                        </span>
                      </div>
                    {/if}
                    <div class="detail-row">
                      <span class="detail-label">Used:</span>
                      <span class="detail-value">{template.use_count} times</span>
                    </div>
                  </div>

                  <div class="template-preview">
                    <pre>{template.script_content.split('\n').slice(0, 5).join('\n')}...</pre>
                  </div>

                  <div class="template-params">
                    <span class="param-chip">
                      {template.parameters.time || '60'}m
                    </span>
                    <span class="param-chip">
                      {template.parameters.memory || '4'}GB
                    </span>
                    <span class="param-chip">
                      {template.parameters.cpus || '1'}CPU
                    </span>
                    {#if template.parameters.gpus}
                      <span class="param-chip">
                        {template.parameters.gpus}GPU
                      </span>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <!-- Save Template Dialog -->
  {#if showSaveTemplateDialog}
    <div class="modal-backdrop" on:click={() => showSaveTemplateDialog = false}>
      <div class="save-template-dialog" on:click|stopPropagation>
        <div class="dialog-header">
          <h3>Save as Template</h3>
          <button
            class="close-btn"
            on:click={() => showSaveTemplateDialog = false}
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="dialog-content">
          <div class="form-group">
            <label for="template-name">Template Name *</label>
            <input
              id="template-name"
              type="text"
              bind:value={templateName}
              placeholder="e.g., GPU Training Script"
              class="form-input"
            />
          </div>

          <div class="form-group">
            <label for="template-description">Description (optional)</label>
            <textarea
              id="template-description"
              bind:value={templateDescription}
              placeholder="Describe what this script does..."
              class="form-textarea"
              rows="3"
            />
          </div>

          <div class="form-group">
            <label>Script Preview</label>
            <div class="script-preview">
              <pre>{script.split('\n').slice(0, 10).join('\n')}...</pre>
            </div>
          </div>

          <div class="form-group">
            <label>Saved Parameters</label>
            <div class="saved-params">
              <div class="param-row">
                <span class="param-label">Host:</span>
                <span class="param-value">{selectedHost || 'Not selected'}</span>
              </div>
              <div class="param-row">
                <span class="param-label">Directory:</span>
                <span class="param-value">{parameters.sourceDir || 'Not selected'}</span>
              </div>
              <div class="param-row">
                <span class="param-label">Time:</span>
                <span class="param-value">{parameters.time || '60'} minutes</span>
              </div>
              <div class="param-row">
                <span class="param-label">Memory:</span>
                <span class="param-value">{parameters.memory || '4'}GB</span>
              </div>
              <div class="param-row">
                <span class="param-label">CPUs:</span>
                <span class="param-value">{parameters.cpus || '1'}</span>
              </div>
              {#if parameters.gpus}
                <div class="param-row">
                  <span class="param-label">GPUs:</span>
                  <span class="param-value">{parameters.gpus}</span>
                </div>
              {/if}
            </div>
          </div>
        </div>

        <div class="dialog-footer">
          <button
            class="btn-secondary"
            on:click={() => showSaveTemplateDialog = false}
          >
            Cancel
          </button>
          <button
            class="btn-primary"
            on:click={saveAsTemplate}
            disabled={!templateName.trim()}
          >
            Save Template
          </button>
        </div>
      </div>
    </div>
  {/if}

  {#if !isMobile}
    <!-- Desktop only content starts here -->
    <!-- Desktop Navigation Header -->
    <NavigationHeader>
    <div slot="left" class="host-selector-modern">
      <div class="host-dropdown-container">
        <button
          class="host-dropdown-trigger {showHostDropdown ? 'active' : ''}"
          on:click={() => showHostDropdown = !showHostDropdown}
        >
          <div class="host-trigger-content">
            <Server class="w-4 h-4" />
            <span class="host-label">
              {#if selectedHost}
                <span class="host-name">{selectedHost}</span>
              {:else}
                <span class="placeholder">Select cluster</span>
              {/if}
            </span>
          </div>
          <ChevronDown class="w-4 h-4 chevron {showHostDropdown ? 'rotate-180' : ''}" />
        </button>

        {#if showHostDropdown}
          <div class="host-dropdown" transition:slide={{ duration: 200 }}>
            {#each hosts as host}
              <button
                class="host-option {selectedHost === host.hostname ? 'selected' : ''}"
                on:click={() => {
                  selectedHost = host.hostname;
                  showHostDropdown = false;
                  handleConfigChange();
                }}
              >
                <div class="host-option-content">
                  <Server class="w-4 h-4" />
                  <span class="host-option-name">{host.hostname}</span>
                </div>
                {#if selectedHost === host.hostname}
                  <Check class="w-4 h-4 check-icon" />
                {/if}
              </button>
            {/each}
            {#if hosts.length === 0}
              <div class="host-empty">
                <AlertCircle class="w-4 h-4" />
                <span>No clusters available</span>
              </div>
            {/if}
          </div>
        {/if}
      </div>

      {#if selectedHost}
        <div class="connection-indicator">
          <div class="pulse-dot"></div>
        </div>
      {/if}
    </div>

    <div slot="actions" class="flex items-center space-x-3">
      <!-- Presets - Now opens sidebar on desktop too -->
      <button
        class="flex items-center gap-2 p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
        on:click={() => showPresetSidebar = !showPresetSidebar}
        title="Presets"
      >
        <Zap class="w-4 h-4" />
        <span class="hidden sm:inline">Presets</span>
      </button>


      <!-- Script Templates -->
      <button
        class="flex items-center gap-2 p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
        on:click={() => showTemplates = !showTemplates}
        title="Script Templates"
      >
        <FileText class="w-4 h-4" />
        <span class="hidden sm:inline">Templates</span>
      </button>

      <!-- Script History -->
      <button
        class="flex items-center gap-2 p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
        on:click={handleHistoryClick}
        title="Script History"
      >
        <History class="w-4 h-4" />
        <span class="hidden sm:inline">History</span>
      </button>

      <!-- Save as Template -->
      <button
        class="flex items-center gap-2 p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
        on:click={() => showSaveTemplateDialog = true}
        title="Save current script as template"
        disabled={!script || script.trim() === ''}
      >
        <Save class="w-4 h-4" />
        <span class="hidden sm:inline">Save Template</span>
      </button>


      <!-- Launch Button -->
      <Button
        on:click={handleLaunch}
        disabled={!canLaunch || launching}
        class="launch-header-button"
        size="default"
        title={!canLaunch ? launchDisabledReason : ''}
      >
        {#if launching}
          <RefreshCw class="mr-2 h-4 w-4 animate-spin" />
          Launching...
        {:else}
          <Play class="mr-2 h-4 w-4" />
          Launch Job
        {/if}
      </Button>
    </div>
  </NavigationHeader>
  {/if}

  <!-- Main Content -->
  <div class="launcher-content" class:mobile-with-sidebar={isMobile && showMobileConfig}>
    <!-- Script Editor - Takes most space -->
    <div class="editor-section">
      {#if !isMobile}
        <div class="editor-header">
          <div class="editor-controls">
            <Label class="editor-label">Script Editor</Label>
          </div>

          <div class="editor-status">
            <!-- Editor Options Dropdown -->
            <div class="editor-options-dropdown">
              <button
                class="editor-options-trigger"
                on:click={(e) => {
                  e.stopPropagation();
                  showEditorOptions = !showEditorOptions;
                }}
                title="Editor Options"
              >
                <MoreHorizontal class="w-4 h-4" />
              </button>

            {#if showEditorOptions}
              <div class="editor-options-menu" transition:slide={{ duration: 200 }} on:click|stopPropagation>
                <!-- Vim Mode Toggle -->
                <div class="option-item">
                  <div class="option-info">
                    <span class="option-label">Vim Mode</span>
                    <span class="option-description">Vi/Vim key bindings</span>
                  </div>
                  <button
                    class="option-toggle {editorOptions.vimMode ? 'active' : ''}"
                    on:click={() => updateEditorOption('vimMode', !editorOptions.vimMode)}
                  >
                    <svelte:component this={editorOptions.vimMode ? ToggleRight : ToggleLeft} class="w-5 h-5" />
                  </button>
                </div>

                <!-- Theme Selection -->
                <div class="option-item">
                  <div class="option-info">
                    <span class="option-label">Theme</span>
                    <span class="option-description">Editor color scheme</span>
                  </div>
                  <select
                    class="option-select"
                    bind:value={editorOptions.theme}
                    on:change={(e) => updateEditorOption('theme', e.target.value)}
                  >
                    {#each themeOptions as theme}
                      <option value={theme.id}>{theme.name}</option>
                    {/each}
                  </select>
                </div>

                <!-- Font Size -->
                <div class="option-item">
                  <div class="option-info">
                    <span class="option-label">Font Size</span>
                    <span class="option-description">Editor font size</span>
                  </div>
                  <select
                    class="option-select"
                    bind:value={editorOptions.fontSize}
                    on:change={(e) => updateEditorOption('fontSize', parseInt(e.target.value))}
                  >
                    {#each fontSizeOptions as size}
                      <option value={size}>{size}px</option>
                    {/each}
                  </select>
                </div>

                <!-- Line Numbers -->
                <div class="option-item">
                  <div class="option-info">
                    <span class="option-label">Line Numbers</span>
                    <span class="option-description">Show line numbers</span>
                  </div>
                  <button
                    class="option-toggle {editorOptions.lineNumbers ? 'active' : ''}"
                    on:click={() => updateEditorOption('lineNumbers', !editorOptions.lineNumbers)}
                  >
                    <svelte:component this={editorOptions.lineNumbers ? ToggleRight : ToggleLeft} class="w-5 h-5" />
                  </button>
                </div>

                <!-- Word Wrap -->
                <div class="option-item">
                  <div class="option-info">
                    <span class="option-label">Word Wrap</span>
                    <span class="option-description">Wrap long lines</span>
                  </div>
                  <button
                    class="option-toggle {editorOptions.wordWrap ? 'active' : ''}"
                    on:click={() => updateEditorOption('wordWrap', !editorOptions.wordWrap)}
                  >
                    <svelte:component this={editorOptions.wordWrap ? ToggleRight : ToggleLeft} class="w-5 h-5" />
                  </button>
                </div>

                <!-- Tab Size -->
                <div class="option-item">
                  <div class="option-info">
                    <span class="option-label">Tab Size</span>
                    <span class="option-description">Spaces per tab</span>
                  </div>
                  <select
                    class="option-select"
                    bind:value={editorOptions.tabSize}
                    on:change={(e) => updateEditorOption('tabSize', parseInt(e.target.value))}
                  >
                    {#each tabSizeOptions as size}
                      <option value={size}>{size} spaces</option>
                    {/each}
                  </select>
                </div>

                <!-- Auto Indent -->
                <div class="option-item">
                  <div class="option-info">
                    <span class="option-label">Auto Indent</span>
                    <span class="option-description">Automatic indentation</span>
                  </div>
                  <button
                    class="option-toggle {editorOptions.autoIndent ? 'active' : ''}"
                    on:click={() => updateEditorOption('autoIndent', !editorOptions.autoIndent)}
                  >
                    <svelte:component this={editorOptions.autoIndent ? ToggleRight : ToggleLeft} class="w-5 h-5" />
                  </button>
                </div>
              </div>
            {/if}
          </div>

          {#if validationDetails.isValid}
            <div class="validation-status valid">
              <div class="status-dot valid"></div>
              <span>Valid</span>
            </div>
          {:else if validationDetails.missingText}
            <div class="validation-status invalid">
              <div class="status-dot invalid"></div>
              <span>{validationDetails.missingText}</span>
            </div>
          {/if}
        </div>
      </div>
      {/if}

      <div class="editor-container" class:mobile={isMobile}>
        <CodeMirrorEditor
          value={script}
          on:change={handleScriptChange}
          vimMode={editorOptions.vimMode}
          theme={editorOptions.theme}
          fontSize={editorOptions.fontSize}
          lineNumbers={editorOptions.lineNumbers}
          wordWrap={editorOptions.wordWrap}
          tabSize={editorOptions.tabSize}
          autoIndent={editorOptions.autoIndent}
          disabled={false}
          class="launcher-editor"
        />
      </div>
    </div>

    <!-- Configuration Panel -->
    <div class="config-section">
      <!-- Directory Selection Card -->
      <Card class="mb-4">
        <div class="section-header">
          <h3 class="section-title">
            <FolderOpen class="w-4 h-4 inline-block mr-2" />
            Source Directory
          </h3>
          <p class="section-description">Choose the local directory to sync to the remote host</p>
        </div>

        <div class="form-group">
          <div class="directory-input-row">
            <input
              id="source-dir"
              type="text"
              bind:value={parameters.sourceDir}
              placeholder="/path/to/your/project"
              class="directory-input-full"
              on:input={handleConfigChange}
            />
            <button
              class="directory-browse-btn-inline"
              on:click={() => showFileBrowser = !showFileBrowser}
              title="{showFileBrowser ? 'Close' : 'Browse'} directory browser"
            >
              {#if showFileBrowser}
                <X class="w-4 h-4" />
                <span>Close</span>
              {:else}
                <Folder class="w-4 h-4" />
                <span>Browse</span>
              {/if}
            </button>
          </div>
        </div>

        {#if showFileBrowser}
          <div class="directory-browser-seamless" transition:slide={{ duration: 200 }}>
            <FileBrowser
              sourceDir={parameters.sourceDir}
              initialPath={parameters.sourceDir || '/'}
              on:pathSelected={handleDirectorySelect}
            />
          </div>
        {/if}
      </Card>

      <!-- Sync Settings Card -->
      <Card class="mb-4">
        <div class="section-header">
          <button
            class="section-header-toggle {showSyncSettings ? 'active' : ''}"
            on:click={() => showSyncSettings = !showSyncSettings}
          >
            <div class="section-header-content">
              <h3 class="section-title">
                <GitBranch class="w-4 h-4 inline-block mr-2" />
                Sync Settings
              </h3>
              <p class="section-description">Configure file synchronization options</p>
            </div>
            <ChevronDown class="section-toggle-icon {showSyncSettings ? 'rotate-180' : ''}" />
          </button>
        </div>

        {#if showSyncSettings}
          <div class="sync-settings-content" transition:slide={{ duration: 200 }}>
            <SyncSettings
              {excludePatterns}
              {includePatterns}
              {noGitignore}
              on:settingsChanged={handleSyncSettingsChange}
            />
          </div>
        {/if}
      </Card>

      <!-- Job Configuration Card -->
      <Card class="mb-4">
        <div class="section-header">
          <h3 class="section-title">
            <Settings class="w-4 h-4 inline-block mr-2" />
            Job Configuration
          </h3>
          <p class="section-description">Basic SLURM job parameters</p>
        </div>

        <div class="form-grid">
          <div class="form-group">
            <Label for="job-name">Job Name</Label>
            <Input
              id="job-name"
              bind:value={parameters.jobName}
              placeholder="my-awesome-job"
              on:input={handleConfigChange}
            />
          </div>

          <div class="form-group">
            <Label for="partition">Partition</Label>
            <Input
              id="partition"
              type="text"
              bind:value={parameters.partition}
              placeholder="default"
              on:input={handleConfigChange}
            />
          </div>

          <div class="form-group">
            <Label for="account">Account</Label>
            <Input
              id="account"
              bind:value={parameters.account}
              placeholder="project-123"
              on:input={handleConfigChange}
            />
          </div>

          <div class="form-group">
            <Label for="constraint">Constraint</Label>
            <Input
              id="constraint"
              bind:value={parameters.constraint}
              placeholder="gpu, bigmem, intel"
              on:input={handleConfigChange}
            />
          </div>
        </div>
      </Card>

      <!-- Resource Requirements Card -->
      <Card class="mb-4">
        <div class="section-header" style="display: flex; align-items: center; justify-content: space-between;">
          <div>
            <h3 class="section-title">
              <Cpu class="w-4 h-4 inline-block mr-2" />
              Resource Requirements
            </h3>
            <p class="section-description">Compute resources for your job</p>
          </div>
          <button
            class="flex items-center gap-2 px-3 py-1.5 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 transition-colors"
            on:click={() => showAdvanced = !showAdvanced}
          >
            <Settings class="w-4 h-4" />
            {showAdvanced ? 'Hide Advanced' : 'Show Advanced'}
          </button>
        </div>

        <div class="form-grid">
          <div class="form-group">
            <Label for="cpus">CPUs</Label>
            <Input
              id="cpus"
              type="number"
              bind:value={parameters.cpus}
              placeholder="1"
              min="1"
              on:input={handleConfigChange}
            />
          </div>

          <div class="form-group">
            <Label for="memory">Memory (GB)</Label>
            <Input
              id="memory"
              type="number"
              bind:value={parameters.memory}
              placeholder="4"
              min="1"
              on:input={handleConfigChange}
            />
          </div>

          <div class="form-group">
            <Label for="time-limit">Time Limit (minutes)</Label>
            <Input
              id="time-limit"
              type="number"
              bind:value={parameters.timeLimit}
              placeholder="60"
              min="1"
              on:input={handleConfigChange}
            />
          </div>

          <div class="form-group">
            <Label for="nodes">Nodes</Label>
            <Input
              id="nodes"
              type="number"
              bind:value={parameters.nodes}
              placeholder="1"
              min="1"
              on:input={handleConfigChange}
            />
          </div>

          {#if showAdvanced}
            <div class="form-group" transition:slide={{ duration: 200 }}>
              <Label for="ntasks-per-node">Tasks per Node</Label>
              <Input
                id="ntasks-per-node"
                type="number"
                bind:value={parameters.ntasksPerNode}
                placeholder="1"
                min="1"
                on:input={handleConfigChange}
              />
            </div>

            <div class="form-group" transition:slide={{ duration: 200 }}>
              <Label for="gpus-per-node">GPUs per Node</Label>
              <Input
                id="gpus-per-node"
                type="number"
                bind:value={parameters.gpusPerNode}
                placeholder="0"
                min="0"
                on:input={handleConfigChange}
              />
            </div>

            <div class="form-group" transition:slide={{ duration: 200 }}>
              <Label for="gres">GRES</Label>
              <Input
                id="gres"
                bind:value={parameters.gres}
                placeholder="gpu:1"
                on:input={handleConfigChange}
              />
            </div>

            <div class="form-group" transition:slide={{ duration: 200 }}>
              <Label for="output-file">Output File</Label>
              <Input
                id="output-file"
                bind:value={parameters.outputFile}
                placeholder="%j.out"
                on:input={handleConfigChange}
              />
            </div>

            <div class="form-group" transition:slide={{ duration: 200 }}>
              <Label for="error-file">Error File</Label>
              <Input
                id="error-file"
                bind:value={parameters.errorFile}
                placeholder="%j.err"
                on:input={handleConfigChange}
              />
            </div>
          {/if}
        </div>
      </Card>

      <!-- Directory Info -->
      {#if parameters.sourceDir}
        <div transition:slide={{ duration: 200 }}>
          <Card class="mb-4" variant="glass">
            <div class="directory-info">
              <div class="flex items-center gap-3">
                <FolderOpen class="w-5 h-5 text-blue-600" />
                <div>
                  <div class="font-medium text-gray-900">Working Directory</div>
                  <div class="text-sm text-gray-500">Source files will be synced from here</div>
                </div>
              </div>
              <div class="mt-3 p-2 bg-gray-100 rounded font-mono text-sm">
                {parameters.sourceDir}
              </div>
            </div>
          </Card>
        </div>
      {/if}

      <!-- Status Card -->
      <Card>
        <div class="status-card-content">
          {#if canLaunch}
            <div class="flex items-center gap-2">
              <div class="status-indicator">
                <div class="pulse-dot valid"></div>
              </div>
              <p class="text-sm text-green-600 font-medium">
                Ready to launch on {selectedHost}
              </p>
            </div>
          {:else}
            <div class="flex items-center gap-2">
              <AlertCircle class="w-4 h-4 text-amber-500" />
              <p class="text-sm text-amber-600 font-medium">
                {launchDisabledReason}
              </p>
            </div>
            {#if !selectedHost}
              <p class="text-xs text-gray-500 mt-1 ml-5">
                Choose a SLURM cluster from the dropdown above
              </p>
            {:else if !validationDetails.isValid}
              <p class="text-xs text-gray-500 mt-1 ml-5">
                Check the script editor for missing SBATCH directives
              </p>
            {/if}
          {/if}
        </div>
      </Card>
    </div>
  </div>

  <!-- Mobile Configuration Sidebar -->
  {#if isMobile && showMobileConfig}
    <div class="mobile-config-overlay" class:closing={isClosingConfig} on:click={() => {
      isClosingConfig = true;
      setTimeout(() => {
        showMobileConfig = false;
        isClosingConfig = false;
      }, 300);
    }}>
      <div class="mobile-config-sidebar" on:click|stopPropagation>
        <div class="mobile-config-header">
          {#if mobileConfigView !== 'main'}
            <button class="mobile-config-back" on:click={() => mobileConfigView = 'main'}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
          {/if}
          <h3>
            {#if mobileConfigView === 'directory'}
              Select Directory
            {:else if mobileConfigView === 'sync'}
              Sync Settings
            {:else}
              Configuration
            {/if}
          </h3>
          <button class="mobile-config-close" on:click={() => {
            isClosingConfig = true;
            setTimeout(() => {
              showMobileConfig = false;
              isClosingConfig = false;
              mobileConfigView = 'main';
            }, 300);
          }}>
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="mobile-config-content">
          {#if mobileConfigView === 'main'}
            <!-- Directory Selection -->
            <div class="mobile-config-section">
              <button
                class="mobile-dir-selector"
                on:click={() => mobileConfigView = 'directory'}
              >
                <Folder class="w-4 h-4 flex-shrink-0" />
                <span>{parameters.sourceDir || 'Select directory...'}</span>
                <ChevronRight class="w-4 h-4 ml-auto flex-shrink-0" />
              </button>
            </div>

          <!-- Basic Configuration -->
          <div class="mobile-config-section">
            <div class="mobile-config-row">
              <div class="mobile-config-field">
                <span class="mobile-config-label">CPUs</span>
                <Input
                  type="number"
                  bind:value={parameters.cpus}
                  min="1"
                  max="128"
                  class="mobile-config-input"
                  on:change={handleConfigChange}
                />
              </div>
              <div class="mobile-config-field">
                <span class="mobile-config-label">Memory (GB)</span>
                <Input
                  type="number"
                  bind:value={parameters.memory}
                  min="1"
                  max="512"
                  class="mobile-config-input"
                  on:change={handleConfigChange}
                />
              </div>
            </div>
            <div class="mobile-config-row">
              <div class="mobile-config-field">
                <span class="mobile-config-label">Time (min)</span>
                <Input
                  type="number"
                  bind:value={parameters.timeLimit}
                  min="1"
                  max="10080"
                  class="mobile-config-input"
                  on:change={handleConfigChange}
                />
              </div>
              <div class="mobile-config-field">
                <span class="mobile-config-label">Nodes</span>
                <Input
                  type="number"
                  bind:value={parameters.nodes}
                  min="1"
                  max="100"
                  class="mobile-config-input"
                  on:change={handleConfigChange}
                />
              </div>
            </div>
          </div>

          <!-- Job Name -->
          <div class="mobile-config-section">
            <Label>Job Name</Label>
            <Input
              type="text"
              bind:value={parameters.jobName}
              placeholder="my-job"
              class="mobile-config-input-full"
              on:change={handleConfigChange}
            />
          </div>

          <!-- Partition -->
          <div class="mobile-config-section">
            <Label>Partition</Label>
            <Input
              type="text"
              bind:value={parameters.partition}
              placeholder="default"
              class="mobile-config-input-full"
              on:change={handleConfigChange}
            />
          </div>

            <!-- Sync Settings -->
            <div class="mobile-config-section">
              <button
                class="mobile-sync-settings-btn"
                on:click={() => mobileConfigView = 'sync'}
              >
                <GitBranch class="w-4 h-4 flex-shrink-0" />
                <span>Sync Settings</span>
                <ChevronRight class="w-4 h-4 ml-auto flex-shrink-0" />
              </button>
            </div>

            <!-- Launch Button in Sidebar -->
            <div class="mobile-config-section">
              <Button
                on:click={() => { handleLaunch(); showMobileConfig = false; mobileConfigView = 'main'; }}
                disabled={!canLaunch || launching}
                class="w-full"
                size="lg"
              >
                {#if launching}
                  <RefreshCw class="mr-2 h-4 w-4 animate-spin" />
                  Launching...
                {:else}
                  <Play class="mr-2 h-4 w-4" />
                  Launch Job
                {/if}
              </Button>
            </div>
          {:else if mobileConfigView === 'directory'}
            <!-- Directory Browser View -->
            <div class="mobile-nested-view">
              <FileBrowser
                initialPath={parameters.sourceDir || ''}
                on:pathSelected={handleDirectorySelect}
                class="mobile-file-browser"
              />
            </div>
          {:else if mobileConfigView === 'sync'}
            <!-- Sync Settings View -->
            <div class="mobile-nested-view">
              <SyncSettings
                bind:excludePatterns
                bind:includePatterns
                bind:noGitignore
                on:change={handleSyncSettingsChange}
                class="mobile-sync-settings"
              />
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  <!-- Mobile Floating Launch Button -->
  {#if isMobile && !showMobileConfig}
    <button
      class="mobile-launch-fab"
      on:click={handleLaunch}
      disabled={!canLaunch || launching}
    >
      {#if launching}
        <RefreshCw class="w-5 h-5 animate-spin" />
      {:else}
        <Play class="w-5 h-5" />
      {/if}
    </button>
  {/if}

  <!-- Script History Modal -->
  {#if showHistory}
    <ScriptHistory
      isOpen={true}
      currentHost={selectedHost}
      on:select={(e) => {
        script = e.detail.content || e.detail.script || e.detail.script_content || '';
        parseSbatchFromScript(script);
        showHistory = false;
      }}
      on:close={() => showHistory = false}
    />
  {/if}
</div>

<style>
  .modern-launcher {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: #f8fafc;
    overflow: hidden;
  }

  /* Host Selector Styles */
  .host-selector {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .host-select {
    min-width: 200px;
  }

  .connection-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    color: #16a34a;
    font-weight: 500;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #16a34a;
  }

  /* Modern Host Selector Styles */
  .host-selector-modern {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .host-dropdown-container {
    position: relative;
  }

  .host-dropdown-trigger {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.625rem 0.875rem;
    min-width: 200px;
    background: white;
    border: 1.5px solid #e5e7eb;
    border-radius: 0.625rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #1f2937;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }

  .host-dropdown-trigger::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    opacity: 0;
    transition: opacity 0.2s;
    pointer-events: none;
  }

  .host-dropdown-trigger:hover {
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .host-dropdown-trigger.active {
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
  }

  .host-trigger-content {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    position: relative;
    z-index: 1;
  }

  .host-trigger-content .placeholder {
    color: #9ca3af;
  }

  .host-name {
    font-weight: 600;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .chevron {
    transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    color: #6b7280;
    position: relative;
    z-index: 1;
  }

  .host-dropdown {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    right: 0;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.75rem;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
    overflow: hidden;
    z-index: 50;
    min-width: 240px;
  }

  .host-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 0.75rem 1rem;
    background: white;
    border: none;
    font-size: 0.875rem;
    color: #374151;
    cursor: pointer;
    transition: all 0.15s;
    position: relative;
  }

  .host-option::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    transform: scaleX(0);
    transform-origin: left;
    transition: transform 0.2s;
  }

  .host-option:hover {
    background: #f9fafb;
  }

  .host-option:hover::before {
    transform: scaleX(1);
  }

  .host-option.selected {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.05), rgba(139, 92, 246, 0.05));
    color: #3b82f6;
    font-weight: 500;
  }

  .host-option.selected::before {
    transform: scaleX(1);
  }

  .host-option-content {
    display: flex;
    align-items: center;
    gap: 0.625rem;
  }

  .host-option-name {
    font-weight: inherit;
  }

  .check-icon {
    color: #3b82f6;
  }

  .host-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 1.5rem;
    color: #9ca3af;
    font-size: 0.875rem;
  }

  .connection-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem;
    background: linear-gradient(135deg, rgba(34, 197, 94, 0.1), rgba(16, 185, 129, 0.1));
    border: 1px solid rgba(34, 197, 94, 0.2);
    border-radius: 9999px;
    animation: fade-in 0.3s;
  }

  /* Launch button wrapper */
  .launch-button-wrapper {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 0.75rem;
  }

  .launch-disabled-reason {
    font-size: 0.75rem;
    color: #ef4444;
    font-weight: 500;
    white-space: nowrap;
  }

  .pulse-dot {
    width: 8px;
    height: 8px;
    background: #10b981;
    border-radius: 50%;
    position: relative;
  }

  .pulse-dot.valid {
    background: #10b981;
  }

  .pulse-dot::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: #10b981;
    border-radius: 50%;
    animation: pulse-ring 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }

  @keyframes pulse-ring {
    0% {
      transform: scale(1);
      opacity: 1;
    }
    50% {
      transform: scale(1.5);
      opacity: 0.5;
    }
    100% {
      transform: scale(2);
      opacity: 0;
    }
  }

  @keyframes fade-in {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Presets Dropdown */
  .preset-dropdown {
    position: relative;
  }

  .preset-menu {
    position: absolute;
    top: calc(100% + 0.5rem);
    right: 0;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
    padding: 0.5rem;
    min-width: 250px;
    z-index: 50;
  }

  .preset-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.75rem;
    border: none;
    background: transparent;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s ease;
    text-align: left;
  }

  .preset-item:hover {
    background: #f8fafc;
  }

  .preset-icon {
    width: 24px;
    height: 24px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .preset-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .preset-name {
    font-weight: 500;
    color: #1e293b;
    font-size: 0.875rem;
  }

  .preset-specs {
    font-size: 0.75rem;
    color: #64748b;
  }

  /* Main Content - Master Container with Fixed Height */
  .launcher-content {
    height: calc(100vh - 120px); /* Fixed height master container */
    display: flex;
    flex-direction: row;
    gap: 1.5rem;
    padding: 1.5rem 2rem;
    box-sizing: border-box;
  }

  /* Editor Section - Left Side Fixed Height */
  .editor-section {
    width: 66.67%; /* Fixed width, not flex */
    height: 100%; /* Fixed height within master container */
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .editor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    flex-shrink: 0; /* Don't allow header to shrink */
    padding: 0.75rem 1rem;
    background: transparent;
    border-bottom: 1px solid rgba(229, 231, 235, 0.2);
  }

  .editor-controls {
    display: flex;
    align-items: center;
  }

  .editor-label {
    font-size: 1.125rem;
    font-weight: 600;
    color: #1e293b;
  }

  .editor-status {
    display: flex;
    align-items: center;
    gap: 1.5rem;
  }

  /* Editor Options Dropdown */
  .editor-options-dropdown {
    position: relative;
  }

  .editor-options-trigger {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem;
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #64748b;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .editor-options-trigger:hover {
    background: #f1f5f9;
    color: #1e293b;
  }

  .editor-options-menu {
    position: absolute;
    top: calc(100% + 0.5rem);
    right: 0;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
    padding: 0.75rem;
    min-width: 280px;
    max-width: calc(100vw - 2rem);
    z-index: 50;
  }

  .mobile-options-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 49;
  }

  @media (max-width: 768px) {
    .editor-options-menu {
      position: fixed;
      top: auto;
      bottom: 1rem;
      left: 1rem;
      right: 1rem;
      max-height: 70vh;
      overflow-y: auto;
      min-width: auto;
      z-index: 100;
      border-radius: 16px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
    }

    .option-item {
      padding: 0.875rem;
    }

    .option-label {
      font-size: 0.9375rem;
    }

    .option-description {
      font-size: 0.75rem;
    }
  }

  .option-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem;
    border-radius: 8px;
    transition: background 0.2s ease;
  }

  .option-item:hover {
    background: #f8fafc;
  }

  .option-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .option-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #1e293b;
  }

  .option-description {
    font-size: 0.75rem;
    color: #64748b;
  }

  .option-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    cursor: pointer;
    color: #94a3b8;
    transition: all 0.2s ease;
  }

  .option-toggle:hover {
    color: #64748b;
  }

  .option-toggle.active {
    color: #3b82f6;
  }

  .option-select {
    padding: 0.375rem 0.5rem;
    font-size: 0.875rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #1e293b;
    min-width: 100px;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.5rem center;
    padding-right: 2rem;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .option-select:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .option-select:hover {
    border-color: #cbd5e1;
  }

  .validation-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .validation-status.valid {
    color: #16a34a;
  }

  .validation-status.invalid {
    color: #dc2626;
  }

  .status-dot.valid {
    background: #16a34a;
  }

  .status-dot.invalid {
    background: #dc2626;
  }

  /* Conflict Resolution UI */
  .conflict-indicator {
    position: relative;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .conflict-icon {
    font-size: 1rem;
  }

  .conflict-dropdown {
    position: relative;
  }

  .conflict-button {
    padding: 0.375rem 0.75rem;
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #f59e0b;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .conflict-button:hover {
    background: #fde68a;
    border-color: #d97706;
  }

  .conflict-menu {
    position: absolute;
    top: calc(100% + 0.5rem);
    right: 0;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
    padding: 0.5rem;
    min-width: 200px;
    z-index: 50;
  }

  .conflict-header {
    padding: 0.5rem;
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
    border-bottom: 1px solid #e5e7eb;
    margin-bottom: 0.5rem;
  }

  .conflict-option {
    display: block;
    width: 100%;
    padding: 0.75rem;
    background: transparent;
    border: none;
    border-radius: 6px;
    text-align: left;
    font-size: 0.875rem;
    color: #374151;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .conflict-option:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .editor-container {
    flex: 1;
    border-radius: 8px;
    overflow: hidden;
    background: #fafbfc;
    border: 1px solid rgba(229, 231, 235, 0.3);
    min-height: 0; /* Critical for nested flex */
    box-sizing: border-box;
    position: relative; /* Contain any absolutely positioned children */
    display: flex;
    flex-direction: column;
  }

  :global(.launcher-editor) {
    height: 100% !important;
    max-height: 100% !important;
  }

  :global(.launcher-editor .cm-editor) {
    height: 100% !important;
  }

  :global(.launcher-editor .cm-scroller) {
    overflow: auto !important;
  }

  /* Configuration Section */
  /* Config Section - Right Side Scrollable Only */
  .config-section {
    width: 33.33%; /* Fixed width, independent of editor */
    height: 100%; /* Fixed height within master container */
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto; /* ONLY this section scrolls */
    overflow-x: hidden;
    padding-right: 0.5rem; /* Add padding for scrollbar */
  }

  /* Custom scrollbar for config section */
  .config-section::-webkit-scrollbar {
    width: 6px;
  }

  .config-section::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 3px;
  }

  .config-section::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;
  }

  .config-section::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
  }

  .config-card {
    padding: 1.5rem;
  }

  .config-header {
    margin-bottom: 1.5rem;
  }

  .config-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: #1e293b;
    margin: 0;
  }

  .config-form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .form-row {
    display: flex;
    gap: 1rem;
  }

  .form-field {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .config-input {
    width: 100%;
  }

  .advanced-section {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #e2e8f0;
  }

  .directory-card {
    padding: 1rem;
  }

  .directory-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .directory-details {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .directory-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .directory-path {
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 0.875rem;
    color: #1e293b;
  }

  :global(.launch-header-button) {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    color: white !important;
    font-weight: 500 !important;
    padding: 0.5rem 1rem !important;
    border-radius: 0.5rem !important;
    transition: all 0.2s !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 0.5rem !important;
  }

  :global(.launch-header-button:hover:not(:disabled)) {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25) !important;
  }

  :global(.launch-header-button:disabled) {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
  }

  .status-card-content {
    padding: 0.5rem;
  }

  .status-indicator {
    display: inline-flex;
  }

  /* Clean Configuration Panel Styles */
  .section-header {
    margin-bottom: 1rem;
  }

  .section-title {
    font-size: 1rem;
    font-weight: 600;
    color: #1e293b;
    margin: 0 0 0.25rem 0;
  }

  .section-description {
    font-size: 0.875rem;
    color: #64748b;
    margin: 0;
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-group:last-child {
    margin-bottom: 0;
  }

  .form-grid {
    display: grid;
    gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }

  /* Directory Input Row */
  .directory-input-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .directory-input-full {
    flex: 1;
    width: 100%;
    height: 40px;
    padding: 0.5rem 0.75rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 0.875rem;
    background: white;
    transition: all 0.15s;
  }

  .directory-input-full:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .directory-input-full:disabled {
    background: #f9fafb;
    cursor: not-allowed;
    opacity: 0.5;
  }

  .directory-browse-btn-inline {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    color: #4b5563;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }

  .directory-browse-btn-inline:hover {
    background: #f9fafb;
    border-color: #3b82f6;
    color: #3b82f6;
  }

  .directory-browser-seamless {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #e5e7eb;
  }

  /* Chevron rotation animation */
  :global(.transition-transform) {
    transition: transform 0.2s ease;
  }
  :global(.rotate-180) {
    transform: rotate(180deg);
  }

  /* Section header toggle styles */
  .section-header-toggle {
    width: 100%;
    padding: 0;
    background: none;
    border: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    transition: all 0.2s;
  }

  .section-header-toggle:hover .section-header-content {
    opacity: 0.8;
  }

  .section-header-content {
    text-align: left;
    transition: opacity 0.2s;
  }

  .section-toggle-icon {
    width: 20px;
    height: 20px;
    color: #6b7280;
    transition: transform 0.2s;
  }

  .section-toggle-icon.rotate-180 {
    transform: rotate(180deg);
  }

  .sync-settings-content {
    padding-top: 1rem;
    border-top: 1px solid #f1f5f9;
    margin-top: 1rem;
  }

  .directory-info {
    /* Uses default Card styling */
  }

  .mb-4 {
    margin-bottom: 1rem;
  }

  /* Mobile Header Styles */
  .mobile-header {
    display: flex;
    align-items: center;
    height: 52px;
    padding: 0 0.75rem;
    background: white;
    border-bottom: 1px solid #e5e7eb;
    gap: 0.5rem;
  }

  .mobile-back-btn {
    padding: 0;
    border: none;
    background: none;
    color: #111827;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
  }

  .mobile-back-btn svg {
    width: 18px;
    height: 18px;
  }

  .mobile-divider {
    width: 1px;
    height: 20px;
    background: #e5e7eb;
    margin: 0 0.25rem;
  }

  .mobile-host-select {
    flex: 0 0 auto;
    max-width: 120px;
    padding: 0.25rem 0.5rem;
    font-size: 0.6875rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    background: white;
    color: #111827;
  }

  .mobile-icon-group {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .mobile-icon-btn {
    padding: 0.375rem;
    border: none;
    background: none;
    color: #6b7280;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.375rem;
    transition: all 0.15s;
  }

  .mobile-icon-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }

  /* Mobile Validation Dot */
  .validation-dot-mobile {
    position: relative;
  }

  .status-dot-small {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    transition: all 0.2s;
  }

  .status-dot-small.valid {
    background: #10b981;
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1);
  }

  .status-dot-small.invalid {
    background: #ef4444;
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
  }

  .mobile-divider-vertical {
    width: 1px;
    height: 16px;
    background: rgba(0, 0, 0, 0.1);
    margin: 0 0.25rem;
  }

  .mobile-validation-popup {
    position: absolute;
    top: 44px;
    left: 0.75rem;
    right: 0.75rem;
    z-index: 50;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    padding: 0.75rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  }

  .mobile-options-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.1);
    z-index: 49;
  }

  .mobile-editor-options-menu {
    position: absolute;
    top: 44px;
    right: 0.75rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    padding: 0.75rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    z-index: 50;
    min-width: 250px;
    max-width: calc(100vw - 1.5rem);
  }

  .validation-info-content {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
  }

  .validation-info-content.valid {
    color: #10b981;
  }

  .validation-info-content.invalid {
    color: #ef4444;
  }

  .mobile-preset-dropdown {
    position: absolute;
    top: 44px;
    right: 0.75rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    z-index: 50;
    padding: 0;
    min-width: 240px;
    max-width: 320px;
  }

  .preset-dropdown-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem;
    border-bottom: 1px solid #e5e7eb;
  }

  .preset-dropdown-title {
    font-size: 0.875rem;
    font-weight: 600;
    color: #111827;
  }

  .preset-manage-btn {
    padding: 0.25rem;
    background: transparent;
    border: none;
    color: #6b7280;
    border-radius: 0.25rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .preset-manage-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .mobile-preset-option {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.625rem 0.75rem;
    border: none;
    background: none;
    text-align: left;
    font-size: 0.75rem;
    color: #374151;
    transition: background 0.15s;
  }

  .mobile-preset-option:hover {
    background: #f9fafb;
  }

  .mobile-preset-add {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.625rem 0.75rem;
    border: none;
    background: none;
    text-align: left;
    font-size: 0.75rem;
    color: #6366f1;
    font-weight: 500;
    border-top: 1px solid #e5e7eb;
    transition: background 0.15s;
  }

  .mobile-preset-add:hover {
    background: #f9fafb;
  }

  .mobile-preset-name {
    font-weight: 500;
    flex: 1;
  }

  .mobile-preset-details {
    font-size: 0.625rem;
    color: #9ca3af;
  }

  /* Preset Manager Sidebar */
  .preset-manager-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 100;
    display: flex;
    justify-content: flex-end;
  }

  .preset-manager-sidebar {
    width: 380px;
    max-width: 90%;
    height: 100%;
    background: white;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
  }

  .preset-manager-header {
    padding: 1.25rem;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .preset-manager-header h3 {
    font-size: 1.125rem;
    font-weight: 600;
    color: #111827;
    margin: 0;
  }

  .preset-manager-close {
    padding: 0.375rem;
    background: transparent;
    border: none;
    color: #6b7280;
    border-radius: 0.375rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .preset-manager-close:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .preset-manager-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.25rem;
  }

  /* Preset Form */
  .preset-form {
    background: #f9fafb;
    border-radius: 0.5rem;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .preset-form h4 {
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
    margin: 0 0 1rem 0;
  }

  .preset-form-field {
    margin-bottom: 1rem;
  }

  .preset-form-field label {
    display: block;
    font-size: 0.75rem;
    font-weight: 500;
    color: #6b7280;
    margin-bottom: 0.375rem;
  }

  .preset-input,
  .preset-select {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 0.375rem;
    font-size: 0.875rem;
    color: #111827;
    background: white;
    transition: all 0.15s;
  }

  .preset-input:focus,
  .preset-select:focus {
    outline: none;
    border-color: #6366f1;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
  }

  .dropdown-container {
    position: relative;
    width: 100%;
  }

  .dropdown-trigger {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.875rem;
  }

  .dropdown-trigger:hover {
    border-color: #6366f1;
    background: #f9fafb;
  }

  .dropdown-menu {
    position: absolute;
    top: calc(100% + 0.25rem);
    left: 0;
    right: 0;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
    max-height: 250px;
    overflow-y: auto;
    z-index: 100;
  }

  .dropdown-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.625rem 0.75rem;
    background: white;
    border: none;
    cursor: pointer;
    transition: all 0.15s;
    font-size: 0.875rem;
    text-align: left;
  }

  .dropdown-item:hover {
    background: #f3f4f6;
  }

  .dropdown-item.selected {
    background: #eef2ff;
    color: #6366f1;
  }

  .color-preview {
    width: 1.25rem;
    height: 1.25rem;
    border-radius: 0.25rem;
    flex-shrink: 0;
  }

  .preset-form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .preset-preview {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    margin-bottom: 1rem;
  }

  .preset-preview span {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }

  .preset-form-actions {
    display: flex;
    gap: 0.5rem;
  }

  .preset-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 0.375rem;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .preset-btn.save {
    background: #6366f1;
    color: white;
  }

  .preset-btn.save:hover:not(:disabled) {
    background: #4f46e5;
  }

  .preset-btn.save:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .preset-btn.cancel {
    background: #f3f4f6;
    color: #374151;
  }

  .preset-btn.cancel:hover {
    background: #e5e7eb;
  }

  /* Preset List */
  .preset-list h4 {
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
    margin: 0 0 0.75rem 0;
  }

  .preset-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    margin-bottom: 0.5rem;
    transition: all 0.15s;
  }

  .preset-item:hover {
    border-color: #d1d5db;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }

  .preset-item-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex: 1;
  }

  .preset-item-name {
    font-size: 0.875rem;
    font-weight: 500;
    color: #111827;
  }

  .preset-item-details {
    font-size: 0.75rem;
    color: #6b7280;
    margin-top: 0.125rem;
  }

  .preset-item-actions {
    display: flex;
    gap: 0.25rem;
  }

  .preset-action-btn {
    padding: 0.375rem;
    background: transparent;
    border: none;
    color: #6b7280;
    border-radius: 0.25rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .preset-action-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .preset-action-btn.delete:hover {
    background: #fee2e2;
    color: #dc2626;
  }

  .preset-empty {
    text-align: center;
    padding: 2rem 1rem;
    color: #6b7280;
  }

  .preset-empty p {
    margin: 0;
    font-size: 0.875rem;
  }

  .preset-empty-hint {
    margin-top: 0.5rem !important;
    font-size: 0.75rem !important;
    color: #9ca3af !important;
  }

  /* Mobile Responsive */
  @media (max-width: 1024px) {
    .launcher-content {
      height: calc(100vh - 100px); /* Adjust for mobile header */
      flex-direction: column;
    }

    .editor-section {
      width: 100%; /* Full width on mobile */
      height: 60%; /* Fixed height portion for editor */
    }

    .editor-container {
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }

    .config-section {
      width: 100%; /* Full width on mobile */
      height: 40%; /* Fixed height portion for config */
      overflow-y: auto; /* Ensure config scrolls on mobile */
    }
  }

  /* Mobile Config Sidebar */
  .mobile-config-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 100;
    animation: fadeIn 0.3s ease-out;
  }

  .mobile-config-overlay.closing {
    animation: fadeOut 0.3s ease-out;
  }

  .mobile-config-sidebar {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 85%;
    max-width: 320px;
    background: white;
    box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    animation: slideInRight 0.3s ease-out;
  }

  .mobile-config-overlay.closing .mobile-config-sidebar {
    animation: slideOutRight 0.3s ease-out;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes fadeOut {
    from { opacity: 1; }
    to { opacity: 0; }
  }

  @keyframes slideInRight {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }

  @keyframes slideOutRight {
    from { transform: translateX(0); }
    to { transform: translateX(100%); }
  }

  .mobile-config-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    border-bottom: 1px solid #e5e7eb;
  }

  .mobile-config-header h3 {
    flex: 1;
    font-size: 1.125rem;
    font-weight: 600;
    color: #111827;
    text-align: center;
    margin-right: 28px; /* Balance with close button */
  }

  .mobile-config-back {
    padding: 0;
    border: none;
    background: none;
    color: #111827;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    margin-right: 0.5rem;
  }

  .mobile-config-back svg {
    width: 20px;
    height: 20px;
  }

  .mobile-config-close {
    padding: 0.25rem;
    border: none;
    background: none;
    color: #6b7280;
    border-radius: 0.375rem;
    transition: all 0.15s;
  }

  .mobile-config-close:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .mobile-config-content {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }

  .mobile-config-section {
    margin-bottom: 1.5rem;
  }

  .mobile-dir-selector {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 0.75rem;
    padding: 1rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.625rem;
    background: linear-gradient(to bottom, #ffffff, #fafafa);
    color: #374151;
    font-size: 0.9rem;
    font-weight: 500;
    text-align: left;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
    position: relative;
    overflow: hidden;
  }

  .mobile-dir-selector:hover {
    border-color: #6366f1;
    background: linear-gradient(to bottom, #fafafa, #f5f5f5);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    transform: translateY(-1px);
  }

  .mobile-dir-selector:active {
    transform: translateY(0);
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  }

  .mobile-dir-selector span,
  .mobile-sync-settings-btn span {
    flex: 1;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mobile-config-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .mobile-config-field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .mobile-config-label {
    font-size: 0.75rem;
    color: #6b7280;
  }

  .mobile-config-input {
    padding: 0.5rem;
    font-size: 0.875rem;
  }

  .mobile-config-input-full {
    width: 100%;
    padding: 0.5rem;
    font-size: 0.875rem;
  }

  .mobile-sync-settings-btn {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 0.75rem;
    padding: 1rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.625rem;
    background: linear-gradient(to bottom, #ffffff, #fafafa);
    color: #374151;
    font-size: 0.9rem;
    font-weight: 500;
    text-align: left;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
    position: relative;
    overflow: hidden;
  }

  .mobile-sync-settings-btn:hover {
    border-color: #6366f1;
    background: linear-gradient(to bottom, #fafafa, #f5f5f5);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    transform: translateY(-1px);
  }

  .mobile-sync-settings-btn:active {
    transform: translateY(0);
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  }

  .mobile-nested-view {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .mobile-file-browser,
  .mobile-sync-settings {
    flex: 1;
    overflow-y: auto;
  }

  /* Mobile Floating Action Button */
  .mobile-launch-fab {
    position: fixed;
    bottom: 1rem;
    right: 1rem;
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: #111827;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    border: none;
    z-index: 90;
    transition: all 0.2s;
  }

  .mobile-launch-fab:not(:disabled):hover {
    transform: scale(1.05);
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
  }

  .mobile-launch-fab:not(:disabled):active {
    transform: scale(0.95);
  }

  .mobile-launch-fab:disabled {
    opacity: 0.5;
    background: #6b7280;
  }

  @media (max-width: 768px) {
    .modern-launcher {
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .launcher-content {
      height: calc(100vh - 80px); /* Fixed height master container for small mobile */
      padding: 0;
      gap: 0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
    }

    .launcher-content.mobile-with-sidebar {
      /* Keep same height when sidebar is open */
    }

    .editor-section {
      width: 100%; /* Full width on mobile */
      height: 100%; /* Full height on mobile (no config panel visible) */
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .editor-container {
      flex: 1;
      min-height: 0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      height: 100%;
      border-radius: 0;
      border: none;
      background: #fafbfc;
    }

    .editor-container.mobile {
      padding: 0.75rem;
      background: #f9fafb;
    }

    .editor-container.mobile :global(.cm-editor) {
      border-radius: 0.75rem;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
      border: 1px solid rgba(0, 0, 0, 0.05);
    }

    /* Hide config section on mobile - it's in the sidebar now */
    .config-section {
      display: none;
    }

    .editor-header {
      padding: 0.5rem 0.75rem;
      border-bottom: none;
      margin-bottom: 0;
      background: transparent;
      position: relative;
    }

    .editor-label {
      font-size: 0.875rem;
    }

    /* Hide desktop launch section on mobile */
    .launcher-content Card:last-child {
      display: none;
    }

    .form-row {
      flex-direction: column;
    }

    .preset-menu {
      left: 0;
      right: 0;
      min-width: auto;
    }
  }

  /* Unified Preset Sidebar Styles */
  .preset-manager-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    backdrop-filter: blur(2px);
    z-index: 999;
    display: flex;
    align-items: center;
    justify-content: flex-end;
  }

  .preset-manager-sidebar {
    width: 380px;
    max-width: 90%;
    height: 100%;
    background: white;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    animation: slideIn 0.3s ease-out;
  }

  @keyframes slideIn {
    from {
      transform: translateX(100%);
    }
    to {
      transform: translateX(0);
    }
  }

  .preset-manager-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    background: white;
  }

  .preset-manager-header h3 {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: #111827;
  }

  .preset-manager-close {
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    padding: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.5rem;
    transition: all 0.2s;
  }

  .preset-manager-close:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .preset-manager-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
  }

  /* Preset Selection Mode */
  .preset-selection-section {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  .preset-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }

  .preset-section-header h4 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #111827;
  }

  .preset-manage-toggle-btn {
    background: none;
    border: 1px solid #e5e7eb;
    color: #6b7280;
    cursor: pointer;
    padding: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.5rem;
    transition: all 0.2s;
  }

  .preset-manage-toggle-btn:hover {
    background: #f3f4f6;
    color: #111827;
    border-color: #d1d5db;
  }

  .preset-back-btn {
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    padding: 0.5rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    transition: color 0.2s;
  }

  .preset-back-btn:hover {
    color: #111827;
  }

  .preset-quick-grid {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
  }

  .preset-quick-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 0.75rem;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
  }

  .preset-quick-item:hover {
    background: #f3f4f6;
    border-color: #d1d5db;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  }

  .preset-quick-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .preset-quick-info .preset-name {
    font-weight: 600;
    color: #111827;
    font-size: 0.875rem;
  }

  .preset-quick-info .preset-specs {
    font-size: 0.75rem;
    color: #6b7280;
  }

  .preset-create-from-current {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.75rem;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: white;
    border: none;
    border-radius: 0.75rem;
    cursor: pointer;
    font-weight: 500;
    font-size: 0.875rem;
    position: relative;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    transform: translateY(0);
  }

  .preset-create-from-current::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.2), transparent);
    opacity: 0;
    transition: opacity 0.3s;
  }

  .preset-create-from-current:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow:
      0 10px 20px -5px rgba(99, 102, 241, 0.35),
      0 6px 12px -3px rgba(139, 92, 246, 0.2),
      0 3px 6px -2px rgba(99, 102, 241, 0.15);
    background: linear-gradient(135deg, #7c7fff, #9f7aea);
  }

  .preset-create-from-current:hover::before {
    opacity: 1;
  }

  .preset-create-from-current:active {
    transform: translateY(-1px) scale(1.01);
    box-shadow:
      0 5px 10px -3px rgba(99, 102, 241, 0.3),
      0 3px 6px -2px rgba(139, 92, 246, 0.15);
  }

  /* Template Dialogs */
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    animation: fadeIn 0.2s ease;
  }

  .template-browser-dialog,
  .save-template-dialog {
    background: white;
    border-radius: 12px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
    max-width: 800px;
    width: 90%;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    animation: slideUp 0.3s ease;
  }

  .save-template-dialog {
    max-width: 500px;
  }

  .dialog-header {
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .dialog-header h3 {
    font-size: 1.25rem;
    font-weight: 600;
    color: #111827;
  }

  .close-btn {
    background: none;
    border: none;
    padding: 0.5rem;
    border-radius: 6px;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .dialog-content {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
  }

  .empty-state {
    text-align: center;
    padding: 3rem 1.5rem;
  }

  .template-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1rem;
  }

  .template-card {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
    transition: all 0.2s;
  }

  .template-card:hover {
    background: #f3f4f6;
    border-color: #d1d5db;
  }

  .template-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }

  .template-name {
    font-size: 0.95rem;
    font-weight: 600;
    color: #111827;
    margin: 0;
  }

  .template-actions {
    display: flex;
    gap: 0.5rem;
  }

  .template-action-btn {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 0.375rem;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.2s;
  }

  .template-action-btn:hover {
    background: #f3f4f6;
    color: #111827;
    border-color: #d1d5db;
  }

  .template-action-btn.delete:hover {
    background: #fef2f2;
    color: #dc2626;
    border-color: #fecaca;
  }

  .template-description {
    font-size: 0.85rem;
    color: #6b7280;
    margin: 0 0 0.75rem 0;
    line-height: 1.4;
  }

  .template-details {
    font-size: 0.8rem;
    color: #6b7280;
    margin-bottom: 0.75rem;
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.25rem;
  }

  .detail-label {
    font-weight: 500;
  }

  .detail-value {
    color: #9ca3af;
  }

  .template-preview {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 0.75rem;
    margin-bottom: 0.75rem;
    overflow: hidden;
  }

  .template-preview pre {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.75rem;
    color: #4b5563;
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
  }

  .template-params {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .param-chip {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    color: #6b7280;
  }

  /* Save Template Dialog Specific Styles */
  .form-group {
    margin-bottom: 1.25rem;
  }

  .form-group label {
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
    margin-bottom: 0.5rem;
  }

  .form-input,
  .form-textarea {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.875rem;
    transition: all 0.2s;
  }

  .form-input:focus,
  .form-textarea:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .form-textarea {
    resize: vertical;
    font-family: inherit;
  }

  .script-preview {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 1rem;
    max-height: 200px;
    overflow-y: auto;
  }

  .script-preview pre {
    font-family: 'Monaco', 'Courier New', monospace;
    font-size: 0.8rem;
    color: #4b5563;
    margin: 0;
  }

  .saved-params {
    background: #f9fafb;
    border-radius: 6px;
    padding: 1rem;
  }

  .param-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    font-size: 0.85rem;
  }

  .param-row:last-child {
    margin-bottom: 0;
  }

  .param-label {
    font-weight: 500;
    color: #374151;
  }

  .param-value {
    color: #6b7280;
  }

  .dialog-footer {
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
  }

  .btn-primary,
  .btn-secondary {
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-primary {
    background: #3b82f6;
    color: white;
    border: none;
  }

  .btn-primary:hover:not(:disabled) {
    background: #2563eb;
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-secondary {
    background: white;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .btn-secondary:hover {
    background: #f9fafb;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  @keyframes slideUp {
    from {
      transform: translateY(20px);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }
</style>