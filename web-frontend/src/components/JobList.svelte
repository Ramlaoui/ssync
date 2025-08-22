<script>
  import { createEventDispatcher } from 'svelte';
  
  export let hostname;
  export let jobs;
  export let queryTime;
  export let getStateColor;
  export let loading = false;
  
  const dispatch = createEventDispatcher();
  
  function selectJob(job) {
    if (loading) return;
    dispatch('jobSelect', job);
  }
  
  function formatTime(timeStr) {
    if (!timeStr || timeStr === 'N/A') return 'N/A';
    try {
      return new Date(timeStr).toLocaleString();
    } catch {
      return timeStr;
    }
  }
  
  function truncate(str, length = 20) {
    if (!str || str.length <= length) return str;
    return str.substring(0, length) + '...';
  }
</script>

<div class="job-list">
  <div class="header">
    <h3>
      <svg class="host-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4,6H20V16H4M20,18A2,2 0 0,0 22,16V6C22,4.89 21.1,4 20,4H4C2.89,4 2,4.89 2,6V16A2,2 0 0,0 4,18H0V20H24V18H20Z"/>
      </svg>
      {hostname}
      <span class="job-count">({jobs.length} jobs)</span>
    </h3>
    <div class="last-updated" class:updating={loading}>
      {#if loading}
        <svg class="loading-indicator" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z"/>
        </svg>
        Updating...
      {:else}
        Last updated: {formatTime(queryTime)}
      {/if}
    </div>
  </div>
  
  {#if jobs.length === 0}
    <div class="no-jobs">
      No jobs found
    </div>
  {:else}
    <div class="job-table">
      <div class="table-header">
        <div class="col job-id">Job ID</div>
        <div class="col name">Name</div>
        <div class="col state">State</div>
        <div class="col runtime">Runtime</div>
        <div class="col resources">Resources</div>
        <div class="col submitted">Submitted</div>
      </div>
      
      {#each jobs as job}
        <div 
          class="job-row" 
          on:click={() => selectJob(job)}
          class:loading={loading}
          class:clickable={!loading}
          role="button"
          tabindex="0"
          aria-label="View job details for job {job.job_id}"
        >
          <div class="col job-id">
            <strong>{job.job_id}</strong>
          </div>
          <div class="col name" title={job.name}>
            {truncate(job.name)}
          </div>
          <div class="col state">
            <span 
              class="state-badge" 
              style="background-color: {getStateColor(job.state)}"
            >
              {job.state}
            </span>
          </div>
          <div class="col runtime">
            {job.runtime || 'N/A'}
          </div>
          <div class="col resources">
            {#if job.cpus || job.memory}
              <div class="resource-info">
                {#if job.cpus && job.cpus !== 'N/A'}
                  <span>CPU: {job.cpus}</span>
                {/if}
                {#if job.memory && job.memory !== 'N/A'}
                  <span>Mem: {job.memory}</span>
                {/if}
              </div>
            {:else}
              N/A
            {/if}
          </div>
          <div class="col submitted">
            {job.submit_time ? formatTime(job.submit_time) : 'N/A'}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .job-list {
    background: white;
    border-radius: 0.5rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    overflow: hidden;
  }

  .header {
    background: #f8f9fa;
    padding: 1rem;
    border-bottom: 1px solid #dee2e6;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .header h3 {
    margin: 0;
    color: #495057;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .host-icon {
    width: 20px;
    height: 20px;
    color: #6c757d;
  }

  .job-count {
    font-size: 0.8rem;
    font-weight: normal;
    color: #6c757d;
  }

  .last-updated {
    font-size: 0.8rem;
    color: #6c757d;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .last-updated.updating {
    color: #f39c12;
    font-weight: 500;
  }
  
  .loading-indicator {
    width: 14px;
    height: 14px;
    animation: spin 1s infinite linear;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .no-jobs {
    padding: 2rem;
    text-align: center;
    color: #6c757d;
  }

  .job-table {
    display: flex;
    flex-direction: column;
  }

  .table-header {
    display: grid;
    grid-template-columns: 100px 1fr 80px 100px 120px 140px;
    gap: 1rem;
    padding: 0.75rem 1rem;
    background: #f8f9fa;
    border-bottom: 1px solid #dee2e6;
    font-weight: 600;
    color: #495057;
    font-size: 0.9rem;
  }

  .job-row {
    display: grid;
    grid-template-columns: 100px 1fr 80px 100px 120px 140px;
    gap: 1rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #f1f3f4;
    transition: background-color 0.2s;
  }
  
  .job-row.clickable {
    cursor: pointer;
  }
  
  .job-row.loading {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .job-row.clickable:hover {
    background: #f8f9fa;
  }
  
  .job-row:focus {
    outline: 2px solid #007bff;
    outline-offset: -2px;
  }

  .job-row:last-child {
    border-bottom: none;
  }

  .col {
    display: flex;
    align-items: center;
    font-size: 0.9rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .col.job-id strong {
    color: #007bff;
  }

  .state-badge {
    color: white;
    padding: 0.2rem 0.6rem;
    border-radius: 1rem;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
  }

  .resource-info {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .resource-info span {
    font-size: 0.75rem;
    color: #6c757d;
  }

  @media (max-width: 1200px) {
    .table-header,
    .job-row {
      grid-template-columns: 80px 1fr 70px 80px 100px;
    }
    
    .col.submitted {
      display: none;
    }
  }

  @media (max-width: 900px) {
    .table-header,
    .job-row {
      grid-template-columns: 80px 1fr 70px 80px;
    }
    
    .col.resources {
      display: none;
    }
  }
</style>
