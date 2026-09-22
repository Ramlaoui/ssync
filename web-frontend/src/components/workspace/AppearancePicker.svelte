<script lang="ts">
  import { Sun, Moon, Monitor, Check } from 'lucide-svelte';
  import { theme } from '../../stores/theme';
  import tokens from '../../lib/design/relay-tokens.json';
  const choices = [{ id: 'light', name: 'Light', icon: Sun }, { id: 'dark', name: 'Dark', icon: Moon }, { id: 'system', name: 'System', icon: Monitor }] as const;
</script>

<div class="appearance-choices" aria-label="Appearance">
  {#each choices as option}
    {@const Icon=option.icon}
    {@const palette=option.id==='dark'?'dark':'light'}
    <button class:active={$theme===option.id} aria-pressed={$theme===option.id} onclick={()=>theme.set(option.id)}>
      <span class="appearance-preview" style={`--preview-canvas:${tokens.colors.Canvas[palette]};--preview-surface:${tokens.colors.SurfaceSecondary[palette]};--preview-ink:${tokens.colors.Separator[palette]};--preview-accent:${tokens.colors.Accent[palette]}`}>
        <span class="preview-sidebar">
          <i></i>
          <i></i>
          <i></i>
        </span>
        <span class="preview-content" class:system={option.id==='system'}>
          <i></i>
          <b></b>
          <b></b>
          <b></b>
        </span>
      </span>
      <span class="appearance-label">
        <Icon size={16}/>
        {option.name}
        {#if $theme===option.id}
          <Check size={16}/>
        {/if}
      </span>
    </button>
  {/each}
</div>

<style>
  .appearance-choices {
    display: grid;
    grid-template-columns: repeat(3,minmax(0,1fr));
    gap: 14px;
  }

  .appearance-choices>button {
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 7px;
    background: transparent;
    min-width: 0;
    transition: background var(--motion-state),border-color var(--motion-state);
  }

  .appearance-choices>button:hover {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .appearance-choices>button.active {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }

  .appearance-preview {
    display: flex;
    height: 100px;
    overflow: hidden;
    background: var(--preview-canvas);
    border: 1px solid var(--preview-ink);
    border-radius: 6px;
  }

  .preview-sidebar {
    width: 28%;
    padding: 18px 9px;
    background: var(--preview-surface);
    border-right: 1px solid var(--preview-ink);
  }

  .preview-sidebar i {
    display: block;
    height: 5px;
    background: var(--preview-ink);
    border-radius: 3px;
    margin-bottom: 9px;
  }

  .preview-sidebar i:first-child {
    background: var(--preview-accent);
  }

  .preview-content {
    padding: 18px 12px;
    flex: 1;
  }

  .preview-content i {
    display: block;
    width: 45%;
    height: 5px;
    background: var(--preview-accent);
    border-radius: 3px;
    margin-bottom: 15px;
  }

  .preview-content b {
    display: block;
    height: 8px;
    background: var(--preview-ink);
    border-radius: 3px;
    margin-bottom: 6px;
  }

  .preview-content.system {
    background: linear-gradient(110deg,transparent 50%,#10141d 50%);
  }

  .appearance-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: .875rem;
    padding: 12px 5px 5px;
    color: var(--muted-foreground);
  }

  .appearance-label :global(svg:last-child:not(:first-child)) {
    margin-left: auto;
    color: var(--accent);
  }

  @media (max-width:500px) {
    .appearance-choices {
      gap: 9px;
    }
    .appearance-preview {
      height: 80px;
    }
    .preview-sidebar {
      padding: 15px 6px;
    }
    .preview-content {
      padding: 15px 8px;
    }
    .appearance-label {
      gap: 5px;
      font-size: .8125rem;
    }
  }
</style>
