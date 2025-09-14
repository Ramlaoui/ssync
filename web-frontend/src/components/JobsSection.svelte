<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import JobTable from './JobTable.svelte';
  import type { JobInfo } from '../types/api';

  export let jobs: JobInfo[] = [];
  export let loading = false;

  const dispatch = createEventDispatcher<{
    jobSelect: JobInfo;
  }>();

  function handleJobSelect(event: CustomEvent<JobInfo>) {
    dispatch('jobSelect', event.detail);
  }
</script>

<div class="jobs-section">
  <div class="jobs-content">
    <JobTable
      {jobs}
      {loading}
      on:jobSelect={handleJobSelect}
    />
  </div>
</div>

<style>
  .jobs-section {
    flex: 1;
    min-width: 500px;
    display: flex;
    flex-direction: column;
    background: white;
    position: relative;
    height: calc(100vh - 140px); /* Fixed height: full viewport minus header/margins */
  }

  .jobs-content {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1rem 1.5rem;
    overscroll-behavior: contain;
    touch-action: pan-y;
    scroll-behavior: smooth;
    position: relative;
  }
</style>