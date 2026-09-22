import { writable } from 'svelte/store';
import type { JobInfo } from '../types/api';
export type JobView = 'all' | 'running' | 'pending' | 'attention' | 'historical';
export interface JobsWorkspace {
    query: string;
    host: string;
    user: string;
    view: JobView;
    newestFirst: boolean;
    selection: {
        id: string;
        host: string;
    } | null;
    tab: string;
    scrollTop: number;
}
// Keep list context across route changes without persisting cluster data or credentials.
export const jobsWorkspace = writable<JobsWorkspace>({
    query: '', host: '', user: '', view: 'all', newestFirst: true,
    selection: null, tab: 'details', scrollTop: 0,
});
export const selectJob = (job: JobInfo) => jobsWorkspace.update(state => ({
    ...state, selection: { id: job.job_id, host: job.hostname },
    tab: ['F', 'OOM', 'NF', 'BF'].includes(job.state) ? 'errors' : 'details',
}));
export function setJobView(view: JobView, host = ''): void {
    jobsWorkspace.update(state => ({ ...state, view, host, query: '', user: '', selection: null, scrollTop: 0 }));
}
