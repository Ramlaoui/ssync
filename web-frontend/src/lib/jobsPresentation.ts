import type { JobInfo } from '../types/api';
import type { JobView } from '../stores/workspace';
type Tone = 'running' | 'pending' | 'success' | 'danger' | 'warning' | 'cancelled' | 'paused' | 'unknown';
const states: Record<string, {
    label: string;
    tone: Tone;
    category: 'active' | 'pending' | 'historical' | 'unknown';
    attention?: boolean;
}> = {
    R: { label: 'Running', tone: 'running', category: 'active' },
    CG: { label: 'Completing', tone: 'running', category: 'active' },
    PD: { label: 'Pending', tone: 'pending', category: 'pending' },
    CF: { label: 'Configuring', tone: 'pending', category: 'pending' },
    CD: { label: 'Completed', tone: 'success', category: 'historical' },
    F: { label: 'Failed', tone: 'danger', category: 'historical', attention: true },
    OOM: { label: 'Out of memory', tone: 'danger', category: 'historical', attention: true },
    NF: { label: 'Node failed', tone: 'danger', category: 'historical', attention: true },
    BF: { label: 'Boot failed', tone: 'danger', category: 'historical', attention: true },
    TO: { label: 'Timed out', tone: 'warning', category: 'historical', attention: true },
    DL: { label: 'Deadline', tone: 'warning', category: 'historical', attention: true },
    CA: { label: 'Cancelled', tone: 'cancelled', category: 'historical' },
    S: { label: 'Suspended', tone: 'paused', category: 'active' },
    PR: { label: 'Preempted', tone: 'warning', category: 'historical', attention: true },
};
const names: Record<string, string> = { RUNNING: 'R', COMPLETING: 'CG', PENDING: 'PD', CONFIGURING: 'CF', COMPLETED: 'CD', FAILED: 'F', OUT_OF_MEMORY: 'OOM', NODE_FAIL: 'NF', BOOT_FAIL: 'BF', TIMEOUT: 'TO', DEADLINE: 'DL', CANCELLED: 'CA', SUSPENDED: 'S', PREEMPTED: 'PR' };
export function jobStatus(state: string) {
    const raw = state.toUpperCase().split(/[+\s]/)[0];
    return states[names[raw] || raw] ?? { label: 'Unknown', tone: 'unknown' as Tone, category: 'unknown' as const };
}
export function matchesJobView(job: JobInfo, view: JobView): boolean {
    const status = jobStatus(job.state);
    return view === 'all' || (view === 'running' ? status.category === 'active' : view === 'pending' ? status.category === 'pending' : view === 'attention' ? Boolean(status.attention) : status.category === 'historical');
}
// Active jobs stay visible even when they started before the history window.
export function withinHistoryWindow(job: JobInfo, since: string, now = Date.now()): boolean {
    if (jobStatus(job.state).category !== 'historical')
        return true;
    const days = since.match(/^(\d+)d$/);
    const timestamp = Date.parse(job.end_time || job.submit_time || '');
    if (!days || !Number.isFinite(timestamp))
        return true;
    return timestamp >= now - Number(days[1]) * 86400000;
}
export function filterJobs(jobs: JobInfo[], filters: {
    query: string;
    host: string;
    user: string;
    view: JobView;
    newestFirst: boolean;
}): JobInfo[] {
    const query = filters.query.trim().toLowerCase();
    return jobs.filter(job => (!filters.host || job.hostname === filters.host) && (!filters.user || job.user?.toLowerCase().includes(filters.user.toLowerCase())) && matchesJobView(job, filters.view) && (!query || [job.job_id, job.name, job.hostname, job.partition, job.user].some(value => value?.toLowerCase().includes(query))))
        .sort((a, b) => {
        const time = (Date.parse(b.submit_time || '') || 0) - (Date.parse(a.submit_time || '') || 0);
        const result = time || b.job_id.localeCompare(a.job_id, undefined, { numeric: true });
        return filters.newestFirst ? result : -result;
    });
}
export const jobRoute = (id: string, host: string, tab = 'details') => `/jobs/${encodeURIComponent(id)}/${encodeURIComponent(host)}${tab === 'details' ? '' : `?tab=${encodeURIComponent(tab)}`}`;
export function gpuCount(job: JobInfo): number | null {
    for (const raw of [job.alloc_tres, job.req_tres, job.gres, job.tres_per_node]) {
        if (!raw)
            continue;
        const total = raw.match(/(?:^|,)gres\/gpu=(\d+)/);
        if (total)
            return Number(total[1]);
        const typed = [...raw.matchAll(/(?:gres\/)?gpu(?::[^:=,()]+)?[=:](\d+)/g)];
        if (typed.length)
            return typed.reduce((sum, m) => sum + Number(m[1]), 0);
    }
    return null;
}
export function relativeTime(value: string | number | null | undefined): string {
    if (!value)
        return 'Not synced';
    const milliseconds = typeof value === 'number' ? value : Date.parse(value);
    if (!Number.isFinite(milliseconds))
        return String(value);
    const minutes = Math.max(0, Math.floor((Date.now() - milliseconds) / 60000));
    return minutes < 1 ? 'Just now' : minutes < 60 ? `${minutes}m ago` : minutes < 1440 ? `${Math.floor(minutes / 60)}h ago` : new Date(milliseconds).toLocaleDateString();
}
export function durationSeconds(value: string | null): number | null {
    if (!value || !/^\d+(?:-\d+)?(?::\d+){0,2}$/.test(value))
        return null;
    const [days, clock] = value.includes('-') ? value.split('-') : ['0', value];
    const parts = clock.split(':').map(Number);
    if (value.includes('-'))
        return Number(days) * 86400 + parts[0] * 3600 + (parts[1] || 0) * 60 + (parts[2] || 0);
    if (parts.length === 1)
        return parts[0] * 60;
    return Number(days) * 86400 + (parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : parts[0] * 60 + parts[1]);
}
