/**
 * Shared utilities for job-related functionality
 * Eliminates code duplication across components
 */

export interface JobState {
  R: 'running';
  PD: 'pending';
  CD: 'completed';
  F: 'failed';
  CA: 'cancelled';
  TO: 'timeout';
  CG: 'completing';
  S: 'suspended';
  PR: 'preempted';
  NF: 'node_fail';
  BF: 'boot_fail';
  DL: 'deadline';
  OOM: 'out_of_memory';
}

/**
 * Comprehensive SLURM job status definitions with consistent colors and labels
 * This is the single source of truth for all job status handling
 */
export const SLURM_JOB_STATES = {
  // Active states
  R: { label: 'RUNNING', color: '#10b981', category: 'active' },      // emerald-500
  CG: { label: 'COMPLETING', color: '#06b6d4', category: 'active' },  // cyan-500

  // Pending states
  PD: { label: 'PENDING', color: '#f59e0b', category: 'pending' },    // amber-500

  // Suspended states
  S: { label: 'SUSPENDED', color: '#8b5cf6', category: 'suspended' }, // violet-500
  PR: { label: 'PREEMPTED', color: '#a855f7', category: 'suspended' }, // purple-500

  // Terminal success states
  CD: { label: 'COMPLETED', color: '#3b82f6', category: 'success' },  // blue-500

  // Terminal failure states
  F: { label: 'FAILED', color: '#ef4444', category: 'failure' },      // red-500
  CA: { label: 'CANCELLED', color: '#6b7280', category: 'failure' },  // gray-500
  TO: { label: 'TIMEOUT', color: '#f97316', category: 'failure' },    // orange-500
  NF: { label: 'NODE_FAIL', color: '#dc2626', category: 'failure' },  // red-600
  BF: { label: 'BOOT_FAIL', color: '#b91c1c', category: 'failure' },  // red-700
  DL: { label: 'DEADLINE', color: '#ea580c', category: 'failure' },   // orange-600
  OOM: { label: 'OUT_OF_MEMORY', color: '#be123c', category: 'failure' } // rose-700
} as const;

export const jobUtils = {
  /**
   * Get color for job state
   */
  getStateColor(state: string): string {
    return SLURM_JOB_STATES[state as keyof typeof SLURM_JOB_STATES]?.color || '#6b7280';
  },

  /**
   * Get human-readable label for job state
   */
  getStateLabel(state: string): string {
    return SLURM_JOB_STATES[state as keyof typeof SLURM_JOB_STATES]?.label || 'UNKNOWN';
  },

  /**
   * Get state category (active, pending, suspended, success, failure)
   */
  getStateCategory(state: string): string {
    return SLURM_JOB_STATES[state as keyof typeof SLURM_JOB_STATES]?.category || 'unknown';
  },

  /**
   * Format time string for display
   */
  formatTime(timeStr: string | null): string {
    if (!timeStr || timeStr === 'N/A') return 'N/A';
    try {
      return new Date(timeStr).toLocaleString();
    } catch {
      return timeStr;
    }
  },

  /**
   * Format duration string (HH:MM:SS or DD-HH:MM:SS)
   */
  formatDuration(duration: string | null): string {
    if (!duration || duration === 'N/A') return 'N/A';
    
    // Parse duration (HH:MM:SS or DD-HH:MM:SS)
    const parts = duration.split(/[-:]/);
    if (parts.length === 3) {
      const [h, m, s] = parts.map(Number);
      if (h > 0) return `${h}h ${m}m`;
      if (m > 0) return `${m}m ${s}s`;
      return `${s}s`;
    } else if (parts.length === 4) {
      const [d, h, m, s] = parts.map(Number);
      if (d > 0) return `${d}d ${h}h`;
      return `${h}h ${m}m`;
    }
    
    return duration;
  },

  /**
   * Format file size in bytes to human readable
   */
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  },

  /**
   * Check if job can be cancelled
   */
  canCancelJob(state: string): boolean {
    const category = this.getStateCategory(state);
    return category === 'active' || category === 'pending' || category === 'suspended';
  },

  /**
   * Check if job is in terminal state
   */
  isTerminalState(state: string): boolean {
    const category = this.getStateCategory(state);
    return category === 'success' || category === 'failure';
  },

  /**
   * Check if job is active/running
   */
  isActiveJob(state: string): boolean {
    const category = this.getStateCategory(state);
    return category === 'active';
  },

  /**
   * Check if job is in a pending state
   */
  isPendingJob(state: string): boolean {
    const category = this.getStateCategory(state);
    return category === 'pending';
  },

  /**
   * Check if job is in a suspended state
   */
  isSuspendedJob(state: string): boolean {
    const category = this.getStateCategory(state);
    return category === 'suspended';
  },

  /**
   * Get semantic color class for job state (for CSS classes)
   */
  getStateColorClass(state: string): string {
    const category = this.getStateCategory(state);
    switch (category) {
      case 'active': return 'info';
      case 'pending': return 'warning';
      case 'success': return 'success';
      case 'failure': return 'error';
      case 'suspended': return 'warning';
      default: return 'default';
    }
  },

  /**
   * Get all available job states
   */
  getAllStates(): Array<{state: string, label: string, color: string, category: string}> {
    return Object.entries(SLURM_JOB_STATES).map(([state, info]) => ({
      state,
      label: info.label,
      color: info.color,
      category: info.category
    }));
  },

  /**
   * Parse SLURM submit line parameters
   */
  parseSubmitLine(submitLine: string): Record<string, string> {
    const params: Record<string, string> = {};
    
    // Match patterns like --partition=gpu, --time=1:00:00, --mem 32G, etc.
    const patterns = [
      /--([a-z-]+)=([^\s]+)/gi,  // --key=value
      /--([a-z-]+)\s+([^\s-]+)/gi  // --key value
    ];
    
    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(submitLine)) !== null) {
        const [, key, value] = match;
        // Normalize key names (e.g., cpus-per-task -> cpus_per_task)
        const normalizedKey = key.replace(/-/g, '_');
        params[normalizedKey] = value;
      }
    }
    
    return params;
  },

  /**
   * Calculate job progress (0-1) based on time limits
   */
  calculateProgress(job: any): number {
    if (!job.start_time || !job.time_limit) return 0;
    if (job.state !== 'R') return job.state === 'CD' ? 1 : 0;

    try {
      const startTime = new Date(job.start_time).getTime();
      const currentTime = Date.now();
      const elapsed = currentTime - startTime;
      
      // Parse time limit (could be in various formats)
      const timeLimitMs = this.parseTimeLimit(job.time_limit);
      if (!timeLimitMs) return 0;
      
      return Math.min(elapsed / timeLimitMs, 1);
    } catch {
      return 0;
    }
  },

  /**
   * Parse SLURM time limit to milliseconds
   */
  parseTimeLimit(timeLimit: string): number | null {
    if (!timeLimit || timeLimit === 'UNLIMITED') return null;
    
    // Handle formats like: 1:00:00, 1-00:00:00, 60, etc.
    const parts = timeLimit.split(/[-:]/);
    let totalMs = 0;
    
    if (parts.length === 1) {
      // Just minutes
      totalMs = parseInt(parts[0]) * 60 * 1000;
    } else if (parts.length === 2) {
      // MM:SS or HH:MM
      const [a, b] = parts.map(Number);
      totalMs = (a * 60 + b) * 1000;
    } else if (parts.length === 3) {
      // HH:MM:SS
      const [h, m, s] = parts.map(Number);
      totalMs = (h * 3600 + m * 60 + s) * 1000;
    } else if (parts.length === 4) {
      // DD-HH:MM:SS
      const [d, h, m, s] = parts.map(Number);
      totalMs = (d * 86400 + h * 3600 + m * 60 + s) * 1000;
    }
    
    return totalMs || null;
  },

  /**
   * Get estimated time remaining for running job
   */
  getTimeRemaining(job: any): string {
    if (job.state !== 'R' || !job.start_time || !job.time_limit) {
      return 'N/A';
    }

    try {
      const startTime = new Date(job.start_time).getTime();
      const currentTime = Date.now();
      const elapsed = currentTime - startTime;
      
      const timeLimitMs = this.parseTimeLimit(job.time_limit);
      if (!timeLimitMs) return 'Unlimited';
      
      const remaining = Math.max(0, timeLimitMs - elapsed);
      return this.formatDuration(this.msToTimeString(remaining));
    } catch {
      return 'N/A';
    }
  },

  /**
   * Convert milliseconds to time string
   */
  msToTimeString(ms: number): string {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) {
      return `${days}-${String(hours % 24).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    } else {
      return `${String(hours).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    }
  },

  /**
   * Format memory from various SLURM formats to GB
   */
  formatMemory(memory: string | null | undefined): string {
    if (!memory || memory === 'N/A') {
      return 'N/A';
    }

    // Remove any whitespace
    const cleanMemory = memory.trim();
    
    // Handle different SLURM memory formats
    // Examples: "8000M", "8G", "8000", "8Gn" (per node), "8000Mc" (per CPU)
    const match = cleanMemory.match(/^(\d+(?:\.\d+)?)\s*([KMGT]?)([nc]?)$/i);
    
    if (!match) {
      // If we can't parse it, return as-is
      return cleanMemory;
    }

    const [, value, unit, suffix] = match;
    const numValue = parseFloat(value);
    
    let bytes: number;
    
    // Convert to bytes based on unit
    switch (unit.toUpperCase()) {
      case 'K':
        bytes = numValue * 1024;
        break;
      case 'M':
      case '':
        // SLURM default is MB if no unit specified
        bytes = numValue * 1024 * 1024;
        break;
      case 'G':
        bytes = numValue * 1024 * 1024 * 1024;
        break;
      case 'T':
        bytes = numValue * 1024 * 1024 * 1024 * 1024;
        break;
      default:
        bytes = numValue * 1024 * 1024; // Default to MB
    }
    
    // Convert to GB
    const gb = bytes / (1024 * 1024 * 1024);
    
    // Add suffix information if present
    const suffixText = suffix === 'n' ? ' per node' : suffix === 'c' ? ' per CPU' : '';
    
    if (gb >= 1) {
      return `${gb.toFixed(gb >= 10 ? 0 : 1)} GB${suffixText}`;
    } else {
      // If less than 1 GB, show in MB
      const mb = bytes / (1024 * 1024);
      return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB${suffixText}`;
    }
  }
};