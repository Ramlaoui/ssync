<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import type { JobInfo } from '../types/api';
  
  export let hostname: string;
  export let jobs: JobInfo[];
  export let queryTime: string;
  export let getStateColor: (state: string) => string;
  export let loading = false;
  
  const dispatch = createEventDispatcher<{
    jobSelect: JobInfo;
  }>();
  
  // Mobile detection
  let isMobile = false;
  
  function checkMobile() {
    isMobile = window.innerWidth <= 768;
  }
  
  function selectJob(job: JobInfo): void {
    if (loading) return;
    dispatch('jobSelect', job);
  }
  
  function formatTime(timeStr: string | null): string {
    if (!timeStr || timeStr === 'N/A') return 'N/A';
    try {
      const date = new Date(timeStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      const diffDays = Math.floor(diffHours / 24);
      
      // Show relative time for recent submissions
      if (diffHours < 1) {
        const diffMinutes = Math.floor(diffMs / (1000 * 60));
        return `${diffMinutes}m ago`;
      } else if (diffHours < 24) {
        return `${diffHours}h ago`;
      } else if (diffDays < 7) {
        return `${diffDays}d ago`;
      } else {
        // Show actual date for older submissions
        return date.toLocaleDateString('en-US', { 
          month: 'short', 
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      }
    } catch {
      return timeStr;
    }
  }
  
  function truncate(str: string | null, length = 20): string {
    if (!str || str.length <= length) return str || '';
    return str.substring(0, length) + '...';
  }

  function smartTruncate(str: string | null, maxLength = 30): string {
    if (!str || str.length <= maxLength) return str || '';
    // Try to break at word boundaries if possible
    const truncated = str.substring(0, maxLength);
    const lastSpace = truncated.lastIndexOf(' ');
    if (lastSpace > maxLength * 0.6) {
      return str.substring(0, lastSpace) + '...';
    }
    return truncated + '...';
  }
  
  onMount(() => {
    checkMobile();
    window.addEventListener('resize', checkMobile);
  });
  
  onDestroy(() => {
    window.removeEventListener('resize', checkMobile);
  });
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
  {:else if isMobile}
    <!-- Mobile Card Layout -->
    <div class="mobile-job-cards">
      {#each jobs as job}
        <div 
          class="job-card" 
          on:click={() => selectJob(job)}
          on:keydown={(e) => e.key === 'Enter' && selectJob(job)}
          class:loading={loading}
          class:clickable={!loading}
          role="button"
          tabindex="0"
          aria-label="View job details for job {job.job_id}"
        >
          <div class="card-header">
            <div class="job-info">
              <span class="job-id">{job.job_id}</span>
              <span class="job-user">{job.user || 'N/A'}</span>
            </div>
            <span 
              class="state-badge mobile" 
              style="background-color: {getStateColor(job.state)}"
            >
              {job.state}
            </span>
          </div>
          
          <div class="card-body">
            <h4 class="job-name" title={job.name}>
              {smartTruncate(job.name, 60)}
            </h4>
            
            <div class="job-meta">
              <span class="runtime">{job.runtime || 'N/A'}</span>
              {#if job.submit_time}
                <span class="submitted" title={new Date(job.submit_time).toLocaleString()}>
                  {formatTime(job.submit_time)}
                </span>
              {/if}
            </div>
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <!-- Desktop Table Layout -->
    <div class="job-table-container">
      <div class="table-header">
        <div class="col job-id">Job ID</div>
        <div class="col name">Name</div>
        <div class="col user">User</div>
        <div class="col state">State</div>
        <div class="col runtime">Runtime</div>
        <div class="col resources">Resources</div>
        <div class="col partition">Partition</div>
        <div class="col submitted">Submitted</div>
      </div>
      
      <div class="job-table-body">
        {#each jobs as job}
          <div 
            class="job-row" 
            on:click={() => selectJob(job)}
            on:keydown={(e) => e.key === 'Enter' && selectJob(job)}
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
              <span class="job-name">{smartTruncate(job.name, 35)}</span>
            </div>
            <div class="col user">
              {job.user || 'N/A'}
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
              {#if job.cpus || job.memory || job.nodes}
                <div class="resource-grid">
                  {#if job.nodes && job.nodes !== 'N/A'}
                    <div class="resource-item" title="Nodes: {job.nodes}">
                      <span class="resource-label">Nodes</span>
                      <span class="resource-value">{job.nodes}</span>
                    </div>
                  {/if}
                  {#if job.cpus && job.cpus !== 'N/A'}
                    <div class="resource-item" title="CPUs: {job.cpus}">
                      <span class="resource-label">CPUs</span>
                      <span class="resource-value">{job.cpus}</span>
                    </div>
                  {/if}
                  {#if job.memory && job.memory !== 'N/A'}
                    <div class="resource-item" title="Memory: {job.memory}">
                      <span class="resource-label">Memory</span>
                      <span class="resource-value">{job.memory}</span>
                    </div>
                  {/if}
                </div>
              {:else}
                <span class="no-resources">N/A</span>
              {/if}
            </div>
            <div class="col partition">
              {job.partition || 'N/A'}
            </div>
            <div class="col submitted">
              <span class="submitted-time" title={job.submit_time ? new Date(job.submit_time).toLocaleString() : 'N/A'}>
                {job.submit_time ? formatTime(job.submit_time) : 'N/A'}
              </span>
            </div>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .job-list {
    background: white;
    border-radius: 0.5rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    overflow: visible;
    flex-shrink: 0;
    margin-bottom: 1rem;
    display: flex;
    flex-direction: column;
  }

  .header {
    background: #f8f9fa;
    padding: 1rem;
    border-bottom: 1px solid #dee2e6;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
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

  .job-table-container {
    display: flex;
    flex-direction: column;
    background: white;
    flex-shrink: 0;
  }

  .table-header {
    display: grid;
    grid-template-columns: 90px 1fr 140px 130px 100px 170px 120px 150px;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: #f8f9fa;
    border-bottom: 1px solid #dee2e6;
    font-weight: 600;
    color: #495057;
    font-size: 0.9rem;
    flex-shrink: 0;
  }

  .job-table-body {
    background: white;
  }

  .job-row {
    display: grid;
    grid-template-columns: 90px 1fr 140px 130px 100px 170px 120px 150px;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid #f1f3f4;
    transition: background-color 0.2s;
    min-height: 3.5rem;
    background: white;
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
    font-size: 0.85rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .col.name {
    font-size: 0.9rem;
  }

  .col.resources {
    align-items: center;
    overflow: hidden;
    min-width: 0;
  }

  .job-name {
    font-weight: 500;
    color: #374151;
    line-height: 1.3;
  }

  .col.job-id strong {
    color: #007bff;
  }

  .state-badge {
    color: white;
    padding: 0.2rem 0.6rem;
    border-radius: 0.75rem;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    text-align: center;
    min-width: fit-content;
    white-space: nowrap;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    display: inline-block;
  }

  .resource-grid {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    align-items: flex-start;
    width: 100%;
  }

  .resource-item {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.75rem;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    width: 100%;
    max-width: 100%;
  }

  .resource-label {
    color: #6c757d;
    font-weight: 500;
    min-width: 45px;
    font-size: 0.7rem;
    flex-shrink: 0;
  }

  .resource-value {
    color: #374151;
    font-weight: 600;
    font-size: 0.75rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
    flex: 1;
  }

  .no-resources {
    color: #9ca3af;
    font-size: 0.8rem;
  }

  .submitted-time {
    font-size: 0.75rem;
    color: #6b7280;
    font-weight: 500;
    white-space: nowrap;
  }

  .col.submitted {
    font-size: 0.8rem;
  }

  @media (max-width: 1400px) {
    .table-header,
    .job-row {
      grid-template-columns: 80px 1fr 130px 120px 90px 150px;
    }
    
    .col.partition,
    .col.submitted {
      display: none;
    }
  }

  @media (max-width: 1000px) {
    .table-header,
    .job-row {
      grid-template-columns: 80px 1fr 120px 110px 140px;
    }
    
    .col.user {
      display: none;
    }
  }

  @media (max-width: 800px) {
    .job-table-container {
      display: none; /* Hide table on mobile, use cards instead */
    }
    
    .mobile-job-cards {
      padding: 0.25rem;
      gap: 0.375rem;
    }
    
    .job-card {
      padding: 0.625rem;
      min-height: 70px;
    }
    
    .job-id {
      font-size: 0.95rem;
    }
    
    .job-user {
      font-size: 0.7rem;
    }
    
    .job-name {
      font-size: 0.85rem;
    }
    
    .job-meta {
      font-size: 0.7rem;
    }
  }

  /* Scrollbar styling for job table body */
  .job-table-body::-webkit-scrollbar {
    width: 8px;
  }

  .job-table-body::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.05);
    border-radius: 4px;
  }

  .job-table-body::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 4px;
  }

  .job-table-body::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.3);
  }

  /* Firefox scrollbar */
  .job-table-body {
    scrollbar-width: thin;
    scrollbar-color: rgba(0, 0, 0, 0.2) rgba(0, 0, 0, 0.05);
  }

  /* Mobile Card Layout Styles */
  .mobile-job-cards {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.5rem;
    background: transparent;
    flex-shrink: 0;
  }

  .job-card {
    background: white;
    border-radius: 8px;
    border: 1px solid #e9ecef;
    padding: 0.75rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    transition: all 0.2s ease;
    cursor: pointer;
    min-height: 80px;
    height: auto;
    flex-shrink: 0;
  }

  .job-card.clickable:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    transform: translateY(-1px);
    border-color: #007bff;
  }

  .job-card.clickable:active {
    transform: translateY(0);
  }

  .job-card.loading {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .job-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .job-id {
    font-size: 1rem;
    font-weight: 700;
    color: #007bff;
    line-height: 1;
  }

  .job-user {
    font-size: 0.75rem;
    color: #6c757d;
    font-weight: 500;
  }

  .state-badge.mobile {
    padding: 0.25rem 0.5rem;
    font-size: 0.7rem;
    border-radius: 8px;
    font-weight: 600;
    text-transform: uppercase;
  }

  .card-body {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .job-name {
    margin: 0;
    font-size: 0.9rem;
    font-weight: 600;
    color: #374151;
    line-height: 1.3;
  }

  .job-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
    color: #6c757d;
  }

  .runtime {
    font-weight: 500;
  }

  .submitted {
    font-weight: 400;
  }

  /* Mobile scrollbar */
  .mobile-job-cards::-webkit-scrollbar {
    width: 4px;
  }

  .mobile-job-cards::-webkit-scrollbar-track {
    background: transparent;
  }

  .mobile-job-cards::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.2);
    border-radius: 2px;
  }

  .mobile-job-cards::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.3);
  }

  /* Mobile layout fixes */
  @media (max-width: 768px) {
    .job-list {
      margin-bottom: 0.75rem;
      border-radius: 8px;
    }
    
    .header {
      padding: 0.75rem;
    }
    
    .header h3 {
      font-size: 0.95rem;
    }
    
    .job-count {
      font-size: 0.75rem;
    }
    
    .last-updated {
      font-size: 0.75rem;
    }
  }
</style>
