<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher<{
    scriptChanged: { source: string; content: string; localPath?: string; uploadedName?: string };
    directorySelected: string;
  }>();

  // Script source: 'editor' | 'local' (file path relative to sourceDir) | 'upload'
  export let scriptSource: 'editor' | 'local' | 'upload' = 'editor';
  export let scriptContent = '#!/bin/bash\n\n# Your script here\necho "Hello, SLURM!"';
  export let localScriptPath = '';
  export let uploadedScriptName = '';

  // Handle uploaded script file
  function handleScriptUpload(e: Event): void {
    const input = e.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    
    const file = input.files[0];
    uploadedScriptName = file.name;
    
    const reader = new FileReader();
    reader.onload = () => {
      scriptContent = String(reader.result || '');
      scriptSource = 'upload';
      dispatchChange();
    };
    reader.readAsText(file);
  }

  function handleDirectoryPick(e: Event): void {
    const input = e.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    
    // webkitRelativePath gives a relative path; use the first file's root folder
    const first = input.files[0] as File & { webkitRelativePath?: string };
    const rel = first.webkitRelativePath || first.name;
    const root = rel.includes('/') ? rel.split('/')[0] : rel;
    
    // Dispatch the selected directory
    dispatch('directorySelected', root);
  }

  function dispatchChange(): void {
    dispatch('scriptChanged', {
      source: scriptSource,
      content: scriptContent,
      localPath: localScriptPath,
      uploadedName: uploadedScriptName
    });
  }

  // React to changes and dispatch
  $: {
    dispatchChange();
  }

  function handleScriptSourceChange(): void {
    // Reset relevant fields when source changes
    if (scriptSource === 'editor') {
      localScriptPath = '';
      uploadedScriptName = '';
    } else if (scriptSource === 'local') {
      uploadedScriptName = '';
    } else if (scriptSource === 'upload') {
      localScriptPath = '';
    }
    dispatchChange();
  }

  function handleContentChange(): void {
    dispatchChange();
  }

  function handleLocalPathChange(): void {
    dispatchChange();
  }
</script>

<div class="script-editor">
  <div class="editor-header">
    <h3>Job Script</h3>
    <div class="script-source-selector">
      <label class="radio-option">
        <input 
          type="radio" 
          bind:group={scriptSource} 
          value="editor" 
          on:change={handleScriptSourceChange}
        />
        <span class="radio-label">
          <svg class="radio-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M14.06,9L15,9.94L5.92,19H5V18.08L14.06,9M17.66,3C17.41,3 17.15,3.1 16.96,3.29L15.13,5.12L18.88,8.87L20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18.17,3.09 17.92,3 17.66,3M14.06,6.19L3,17.25V21H6.75L17.81,9.94L14.06,6.19Z"/>
          </svg>
          Editor
        </span>
      </label>
      
      <label class="radio-option">
        <input 
          type="radio" 
          bind:group={scriptSource} 
          value="local" 
          on:change={handleScriptSourceChange}
        />
        <span class="radio-label">
          <svg class="radio-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M10,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8C22,6.89 21.1,6 20,6H12L10,4Z"/>
          </svg>
          Local file
        </span>
      </label>
      
      <label class="radio-option">
        <input 
          type="radio" 
          bind:group={scriptSource} 
          value="upload" 
          on:change={handleScriptSourceChange}
        />
        <span class="radio-label">
          <svg class="radio-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
          </svg>
          Upload
        </span>
      </label>
    </div>
  </div>

  <div class="editor-content">
    {#if scriptSource === 'editor'}
      <div class="editor-section">
        <label for="script-content">Script Content *</label>
        <textarea
          id="script-content"
          bind:value={scriptContent}
          on:input={handleContentChange}
          rows="12"
          placeholder="#!/bin/bash&#10;&#10;# Your SLURM job script here&#10;echo 'Starting job...'&#10;&#10;# Add your commands here"
          required
          class="script-textarea"
        ></textarea>
        <div class="editor-help">
          Write your shell script or SLURM batch script. SLURM directives will be added automatically.
        </div>
      </div>
    {/if}

    {#if scriptSource === 'local'}
      <div class="local-section">
        <label for="local-script-path">Local script path (relative to source dir) *</label>
        <input 
          id="local-script-path" 
          type="text" 
          bind:value={localScriptPath}
          on:input={handleLocalPathChange}
          placeholder="scripts/run.sh" 
          required
          class="path-input"
        />
        <div class="local-help">
          <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z"/>
          </svg>
          Provide the path to the script inside the source directory you selected above.
        </div>
      </div>
    {/if}

    {#if scriptSource === 'upload'}
      <div class="upload-section">
        <label for="script-upload" class="upload-label">Upload script file *</label>
        <div class="upload-area">
          <input 
            id="script-upload"
            type="file" 
            accept=".sh,.bash,.py,.pl,.r,.R,application/x-shellscript,text/*" 
            on:change={handleScriptUpload}
            class="upload-input"
          />
          <div class="upload-placeholder">
            <svg class="upload-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
            </svg>
            <span class="upload-text">
              {#if uploadedScriptName}
                <strong>{uploadedScriptName}</strong>
              {:else}
                Click to choose a script file
              {/if}
            </span>
          </div>
        </div>
        
        {#if uploadedScriptName}
          <div class="upload-success">
            <svg class="success-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M17,9L12,14L7,9L8.41,7.59L12,11.17L15.59,7.59L17,9Z"/>
            </svg>
            Successfully uploaded: <strong>{uploadedScriptName}</strong>
          </div>
        {/if}

        <div class="upload-help">
          Upload shell scripts (.sh), Python (.py), Perl (.pl), R (.r), or other text-based scripts.
        </div>
      </div>
    {/if}

    <!-- Directory picker for convenience (optional feature) -->
    <div class="directory-picker">
      <label for="directory-picker" class="picker-label">
        <svg class="folder-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M10,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8C22,6.89 21.1,6 20,6H12L10,4Z"/>
        </svg>
        Or pick directory from local filesystem
      </label>
      <input
        id="directory-picker"
        type="file"
        {...{ webkitdirectory: '' }}
        on:change={handleDirectoryPick}
        class="directory-input"
      />
      <div class="picker-help">
        <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M11,9H13V7H11M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M11,17H13V11H11V17Z"/>
        </svg>
        Browser-based directory selection (best-effort in browsers)
      </div>
    </div>
  </div>
</div>

<style>
  .script-editor {
    background: #fafbfc;
    border: 1px solid #e1e5e9;
    border-radius: 10px;
    overflow: hidden;
    transition: all 0.2s ease;
  }

  .script-editor:hover {
    border-color: #c7d2fe;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
  }

  .editor-header {
    padding: 1.25rem;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-bottom: 1px solid #e1e5e9;
  }

  .editor-header h3 {
    margin: 0 0 1rem 0;
    color: #374151;
    font-size: 1.125rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .editor-header h3::before {
    content: '';
    width: 4px;
    height: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 2px;
  }

  .script-source-selector {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .radio-option {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    border: 1px solid #e5e7eb;
    background: white;
    transition: all 0.2s ease;
  }

  .radio-option:hover {
    border-color: #c7d2fe;
    background: #f8fafc;
  }

  .radio-option:has(input:checked) {
    border-color: #667eea;
    background: #eef2ff;
    box-shadow: 0 2px 4px rgba(102, 126, 234, 0.1);
  }

  .radio-option input[type="radio"] {
    margin: 0;
    cursor: pointer;
  }

  .radio-label {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.9rem;
    font-weight: 500;
    color: #374151;
  }

  .radio-icon {
    width: 16px;
    height: 16px;
    color: #6b7280;
  }

  .radio-option:has(input:checked) .radio-icon {
    color: #667eea;
  }

  .editor-content {
    padding: 1.25rem;
  }

  .editor-section, .local-section, .upload-section {
    margin-bottom: 1rem;
  }

  .editor-section label,
  .local-section label,
  .upload-section .upload-label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
    color: #374151;
    font-size: 0.9rem;
  }

  .script-textarea {
    width: 100%;
    padding: 0.75rem;
    border: 1.5px solid #e5e7eb;
    border-radius: 8px;
    background: white;
    color: #374151;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.9rem;
    line-height: 1.5;
    resize: vertical;
    min-height: 250px;
    transition: all 0.2s ease;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .script-textarea:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1), 0 2px 4px rgba(0, 0, 0, 0.1);
    transform: translateY(-1px);
  }

  .path-input {
    width: 100%;
    padding: 0.75rem;
    border: 1.5px solid #e5e7eb;
    border-radius: 8px;
    background: white;
    color: #374151;
    font-family: inherit;
    font-size: 0.9rem;
    transition: all 0.2s ease;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .path-input:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1), 0 2px 4px rgba(0, 0, 0, 0.1);
    transform: translateY(-1px);
  }

  .upload-area {
    position: relative;
    border: 2px dashed #d1d5db;
    border-radius: 8px;
    padding: 2rem;
    text-align: center;
    transition: all 0.2s ease;
    background: #fafafa;
    cursor: pointer;
  }

  .upload-area:hover {
    border-color: #667eea;
    background: #f8fafc;
  }

  .upload-input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
  }

  .upload-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    pointer-events: none;
  }

  .upload-icon {
    width: 2rem;
    height: 2rem;
    color: #9ca3af;
  }

  .upload-text {
    font-size: 0.9rem;
    color: #6b7280;
  }

  .upload-success {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 6px;
    color: #16a34a;
    font-size: 0.9rem;
    margin-top: 0.75rem;
  }

  .success-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .editor-help, .local-help, .upload-help, .picker-help {
    margin-top: 0.5rem;
    font-size: 0.8rem;
    color: #6b7280;
    display: flex;
    align-items: flex-start;
    gap: 0.375rem;
    line-height: 1.4;
  }

  .info-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
    margin-top: 0.1rem;
    color: #9ca3af;
  }

  .directory-picker {
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid #e5e7eb;
  }

  .picker-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    color: #6b7280;
    cursor: pointer;
    margin-bottom: 0.5rem;
  }

  .folder-icon {
    width: 16px;
    height: 16px;
    color: #f59e0b;
  }

  .directory-input {
    font-size: 0.85rem;
    color: #6b7280;
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .editor-header {
      padding: 1rem;
    }

    .script-source-selector {
      flex-direction: column;
      gap: 0.5rem;
    }

    .radio-option {
      justify-content: flex-start;
      padding: 0.625rem 0.875rem;
    }

    .editor-content {
      padding: 1rem;
    }

    .script-textarea {
      min-height: 200px;
      font-size: 0.85rem;
    }

    .upload-area {
      padding: 1.5rem 1rem;
    }

    .upload-placeholder {
      gap: 0.5rem;
    }

    .upload-icon {
      width: 1.5rem;
      height: 1.5rem;
    }

    .upload-text {
      font-size: 0.85rem;
    }
  }
</style>