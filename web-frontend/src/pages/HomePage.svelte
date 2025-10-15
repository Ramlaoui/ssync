<script lang="ts">
  import { onMount } from 'svelte';
  import DashboardPage from './DashboardPage.svelte';
  import JobsPage from './JobsPage.svelte';

  let isMobile = $state(false);

  function checkMobile() {
    isMobile = window.innerWidth < 768;
  }

  onMount(() => {
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  });
</script>

{#if isMobile}
  <JobsPage />
{:else}
  <DashboardPage />
{/if}
