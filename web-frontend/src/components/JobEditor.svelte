<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { slide, fade } from 'svelte/transition';
  import { cn } from '../lib/utils';
  import Button from '../lib/components/ui/Button.svelte';
  import Input from '../lib/components/ui/Input.svelte';
  import Label from '../lib/components/ui/Label.svelte';
  import Select from '../lib/components/ui/Select.svelte';
  import Card from '../lib/components/ui/Card.svelte';
  import CodeMirrorEditor from './CodeMirrorEditor.svelte';
  import FileBrowser from './FileBrowser.svelte';
  import SyncSettings from './SyncSettings.svelte';
  import type { HostInfo } from '../types/api';
  
  // Icons as components
  import { 
    ChevronRight,
    Play,
    Settings,
    FolderOpen,
    RefreshCw,
    FileText,
    Zap,
    Clock,
    Cpu,
    HardDrive,
    Server,
    Monitor,
    ChevronDown
  } from 'lucide-svelte';
  
  const dispatch = createEventDispatcher();
  
  
  interface Props {
    // Props
    script?: string;
    launching?: boolean;
    hosts?: HostInfo[];
    selectedHost?: string;
    loading?: boolean;
    validationDetails?: any;
    config?: any;
  }

  let {
    script = $bindable(''),
    launching = false,
    hosts = [],
    selectedHost = $bindable(''),
    loading = false,
    validationDetails = { isValid: false },
    config = $bindable({})
  }: Props = $props();
  
  // State
  let sidebarOpen = $state(true);
  let activeSection: 'presets' | 'config' | 'directory' | 'sync' | 'templates' = $state('config');
  let showAdvanced = $state(false);
  let searchQuery = $state('');
  
  // Presets
  const presets = [
    { id: 'quick', name: 'Quick Test', icon: Zap, time: 10, memory: 2, cpus: 1 },
    { id: 'standard', name: 'Standard', icon: Cpu, time: 60, memory: 4, cpus: 2 },
    { id: 'long', name: 'Long Running', icon: Clock, time: 1440, memory: 8, cpus: 4 },
    { id: 'gpu', name: 'GPU Compute', icon: Monitor, time: 240, memory: 16, cpus: 4, gpus: 1 },
    { id: 'memory', name: 'Big Memory', icon: HardDrive, time: 720, memory: 64, cpus: 8 },
    { id: 'distributed', name: 'Distributed', icon: Server, time: 480, memory: 32, cpus: 16, nodes: 4 }
  ];
  
  // Templates
  const templates = [
    {
      category: 'Machine Learning',
      items: [
        { name: 'PyTorch Training', description: 'Basic PyTorch training script' },
        { name: 'TensorFlow Model', description: 'TensorFlow model training' },
        { name: 'Hyperparameter Tuning', description: 'Grid search template' }
      ]
    },
    {
      category: 'Data Processing',
      items: [
        { name: 'Batch Processing', description: 'Process data in batches' },
        { name: 'ETL Pipeline', description: 'Extract, transform, load' },
        { name: 'Data Validation', description: 'Validate and clean data' }
      ]
    }
  ];
  
  let canLaunch = $derived(validationDetails.isValid && selectedHost);
  
  function handleScriptChange(event: CustomEvent) {
    script = event.detail.content;
    dispatch('scriptChanged', { content: script });
  }
  
  function applyPreset(preset: typeof presets[0]) {
    config = {
      ...config,
      timeLimit: preset.time,
      memory: preset.memory,
      cpus: preset.cpus,
      gpusPerNode: preset.gpus || 0,
      nodes: preset.nodes || 1
    };
    dispatch('configChanged', { detail: config });
  }
  
  function handleConfigChange() {
    dispatch('configChanged', { detail: config });
  }
  
  function handlePathSelected(event: CustomEvent) {
    dispatch('pathSelected', event.detail);
  }
  
  function handleSyncSettingsChange(event: CustomEvent) {
    dispatch('syncSettingsChanged', event.detail);
  }
  
  function handleLaunch() {
    if (canLaunch) {
      dispatch('launch');
    }
  }
</script>

<div class="flex h-full bg-background">
  <!-- Main Editor -->
  <div class="flex-1 flex flex-col">
    <!-- Top Bar -->
    <div class="border-b px-4 py-3 flex items-center justify-between bg-card">
      <div class="flex items-center gap-4">
        <h2 class="text-lg font-semibold">Job Editor</h2>
        <Select bind:value={selectedHost} class="w-48">
          <option value="">Select cluster...</option>
          {#each hosts as host}
            <option value={host.hostname}>{host.hostname}</option>
          {/each}
        </Select>
        {#if selectedHost}
          <span class="flex items-center gap-1.5 text-sm text-muted-foreground">
            <span class="w-2 h-2 bg-green-500 rounded-full"></span>
            Connected
          </span>
        {/if}
      </div>
      
      <div class="flex items-center gap-2">
        {#if validationDetails.isValid}
          <span class="text-sm text-green-600 font-medium">✓ Valid</span>
        {:else if validationDetails.missingText}
          <span class="text-sm text-destructive">{validationDetails.missingText}</span>
        {/if}
        
        <Button
          variant="ghost"
          size="icon"
          on:click={() => sidebarOpen = !sidebarOpen}
        >
          <Settings class="h-4 w-4" />
        </Button>
      </div>
    </div>
    
    <!-- Editor -->
    <div class="flex-1 overflow-hidden">
      <CodeMirrorEditor
        value={script}
        on:change={handleScriptChange}
        vimMode={false}
        disabled={false}
      />
    </div>
    
    <!-- Launch Button -->
    <div class="border-t p-4 bg-card">
      <Button
        on:click={handleLaunch}
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
  </div>
  
  <!-- Sidebar -->
  {#if sidebarOpen}
    <div class="w-96 border-l bg-card flex flex-col" transition:slide={{ axis: 'x' }}>
      <!-- Sidebar Tabs -->
      <div class="flex p-2 gap-1 border-b">
        {#each [
          { id: 'presets', icon: Zap, label: 'Presets' },
          { id: 'config', icon: Settings, label: 'Config' },
          { id: 'directory', icon: FolderOpen, label: 'Directory' },
          { id: 'sync', icon: RefreshCw, label: 'Sync' },
          { id: 'templates', icon: FileText, label: 'Templates' }
        ] as tab}
          <button
            class={cn(
              "flex-1 flex flex-col items-center gap-1 p-2 rounded-md text-xs transition-colors",
              activeSection === tab.id
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted text-muted-foreground hover:text-foreground"
            )}
            onclick={() => activeSection = tab.id}
          >
            <tab.icon class="h-4 w-4" />
            {tab.label}
          </button>
        {/each}
      </div>
      
      <!-- Sidebar Content -->
      <div class="flex-1 overflow-y-auto p-4">
        {#if activeSection === 'presets'}
          <div class="space-y-3">
            {#each presets as preset}
              <Card 
                class="p-4 cursor-pointer hover:shadow-md transition-shadow"
                on:click={() => applyPreset(preset)}
              >
                <div class="flex items-start gap-3">
                  <div class="p-2 rounded-lg bg-primary/10">
                    <preset.icon class="h-5 w-5 text-primary" />
                  </div>
                  <div class="flex-1">
                    <h4 class="font-medium">{preset.name}</h4>
                    <p class="text-sm text-muted-foreground mt-1">
                      {preset.time} min • {preset.memory}GB • {preset.cpus} CPU{preset.cpus > 1 ? 's' : ''}
                      {#if preset.gpus} • {preset.gpus} GPU{/if}
                      {#if preset.nodes} • {preset.nodes} nodes{/if}
                    </p>
                  </div>
                </div>
              </Card>
            {/each}
          </div>
          
        {:else if activeSection === 'config'}
          <div class="space-y-4">
            <div>
              <Label for="job-name">Job Name</Label>
              <Input 
                id="job-name"
                bind:value={config.jobName}
                placeholder="my-job"
                class="mt-1.5"
              />
            </div>
            
            <div class="grid grid-cols-2 gap-4">
              <div>
                <Label for="partition">Partition</Label>
                <Select 
                  id="partition"
                  bind:value={config.partition}
                  class="mt-1.5"
                >
                  <option value="">Default</option>
                  <option value="cpu">CPU</option>
                  <option value="gpu">GPU</option>
                  <option value="bigmem">Big Memory</option>
                </Select>
              </div>
              
              <div>
                <Label for="time">Time (min)</Label>
                <Input 
                  id="time"
                  type="number"
                  bind:value={config.timeLimit}
                  placeholder="60"
                  class="mt-1.5"
                />
              </div>
              
              <div>
                <Label for="cpus">CPUs</Label>
                <Input 
                  id="cpus"
                  type="number"
                  bind:value={config.cpus}
                  placeholder="1"
                  class="mt-1.5"
                />
              </div>
              
              <div>
                <Label for="memory">Memory (GB)</Label>
                <Input 
                  id="memory"
                  type="number"
                  bind:value={config.memory}
                  placeholder="4"
                  class="mt-1.5"
                />
              </div>
              
              <div>
                <Label for="nodes">Nodes</Label>
                <Input 
                  id="nodes"
                  type="number"
                  bind:value={config.nodes}
                  placeholder="1"
                  class="mt-1.5"
                />
              </div>
              
              <div>
                <Label for="gpus">GPUs</Label>
                <Input 
                  id="gpus"
                  type="number"
                  bind:value={config.gpusPerNode}
                  placeholder="0"
                  class="mt-1.5"
                />
              </div>
            </div>
            
            <!-- Advanced Options -->
            <div class="pt-2">
              <button
                class="flex items-center gap-2 text-sm font-medium hover:text-primary transition-colors"
                onclick={() => showAdvanced = !showAdvanced}
              >
                <ChevronDown class={cn("h-4 w-4 transition-transform", showAdvanced && "rotate-180")} />
                Advanced Options
              </button>
              
              {#if showAdvanced}
                <div class="mt-4 space-y-4" transition:slide>
                  <div>
                    <Label for="account">Account</Label>
                    <Input 
                      id="account"
                      bind:value={config.account}
                      placeholder="project-account"
                      class="mt-1.5"
                    />
                  </div>
                  
                  <div>
                    <Label for="output">Output File</Label>
                    <Input 
                      id="output"
                      bind:value={config.outputFile}
                      placeholder="%j.out"
                      class="mt-1.5"
                    />
                  </div>
                  
                  <div>
                    <Label for="error">Error File</Label>
                    <Input 
                      id="error"
                      bind:value={config.errorFile}
                      placeholder="%j.err"
                      class="mt-1.5"
                    />
                  </div>
                </div>
              {/if}
            </div>
          </div>
          
        {:else if activeSection === 'directory'}
          <div class="space-y-4">
            <Card class="p-3">
              <Label class="text-xs uppercase tracking-wider text-muted-foreground">Current Directory</Label>
              <p class="mt-1 font-mono text-sm">{config.sourceDir || '/home/user'}</p>
            </Card>
            
            <div class="border rounded-lg p-3">
              <FileBrowser
                sourceDir={config.sourceDir}
                initialPath="/home"
                on:pathSelected
                on:change
              />
            </div>
          </div>
          
        {:else if activeSection === 'sync'}
          <div class="border rounded-lg p-3">
            <SyncSettings
              excludePatterns={config.excludePatterns}
              includePatterns={config.includePatterns}
              noGitignore={config.noGitignore}
              on:settingsChanged
            />
          </div>
          
        {:else if activeSection === 'templates'}
          <div class="space-y-4">
            <Input 
              bind:value={searchQuery}
              placeholder="Search templates..."
              class="w-full"
            />
            
            {#each templates as category}
              <div>
                <h3 class="font-medium text-sm uppercase tracking-wider text-muted-foreground mb-2">
                  {category.category}
                </h3>
                <div class="space-y-2">
                  {#each category.items as template}
                    <Card 
                      class="p-3 cursor-pointer hover:shadow-sm transition-shadow"
                      on:click
                    >
                      <h4 class="font-medium text-sm">{template.name}</h4>
                      <p class="text-xs text-muted-foreground mt-0.5">{template.description}</p>
                    </Card>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  :global(.lucide) {
    width: 1rem;
    height: 1rem;
  }
</style>