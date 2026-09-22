<script lang="ts">
  import JobStatus from '../../../components/workspace/JobStatus.svelte';
  let { status, class: className = '' }: { status: string; class?: string } = $props();
</script>

<span class={className}><JobStatus state={status}/></span>
