<script lang="ts">
  import { Play, Clock3, Check, CircleHelp, X, TriangleAlert, Hourglass, Pause } from 'lucide-svelte';
  import { jobStatus } from '../../lib/jobsPresentation';
  let { state }: {
    state: string;
  } = $props();
  const status = $derived(jobStatus(state));
  const glyphs = { running: Play, pending: Clock3, success: Check, danger: TriangleAlert, warning: Hourglass, cancelled: X, paused: Pause, unknown: CircleHelp };
  const Glyph = $derived(glyphs[status.tone]);
</script>

<span class="relay-status" data-tone={status.tone} title={state}>
  <Glyph size={13} aria-hidden="true"/>
  {status.label}
</span>
