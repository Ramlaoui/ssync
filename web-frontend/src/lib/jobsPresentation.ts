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
    return view === 'all' || (view === 'running' ? status.category === 'active' : view === 'pending' ? status.category === 'pending' : status.category === 'historical');
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
/** One duration style everywhere: "45s", "12m", "3h 05m", "2d 4h". */
export function compactDuration(value: string | null | undefined): string {
    const seconds = durationSeconds(value ?? null);
    if (seconds === null)
        return value || '—';
    if (seconds < 60)
        return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60)
        return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24)
        return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`;
    return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}
/** The time column: elapsed for running work, queue standing for pending work, end for finished work. */
export function jobTiming(job: JobInfo): { primary: string; secondary: string; detail: string } {
    const category = jobStatus(job.state).category;
    if (category === 'pending') {
        const rank = job.priority_rank ? `#${job.priority_rank.toLocaleString()} in queue` : '';
        const queued = job.submit_time ? `queued ${relativeTime(job.submit_time).toLowerCase()}` : '';
        return { primary: rank || job.reason || 'Queued', secondary: '', detail: [job.reason, rank, queued].filter(Boolean).join(' · ') };
    }
    const elapsed = job.runtime ? compactDuration(job.runtime) : '—';
    if (category === 'active') {
        const limit = job.time_limit ? compactDuration(job.time_limit) : '';
        return { primary: elapsed, secondary: limit ? `/ ${limit}` : '', detail: limit ? `${elapsed} of ${limit} limit` : elapsed };
    }
    const ended = job.end_time ? relativeTime(job.end_time).toLowerCase() : '';
    return { primary: elapsed, secondary: ended, detail: ended ? `Ran ${elapsed}, ended ${ended}` : `Ran ${elapsed}` };
}
export type JobListEntry = {
    kind: 'job';
    key: string;
    job: JobInfo;
} | {
    kind: 'array';
    key: string;
    hostname: string;
    arrayId: string;
    name: string;
    tasks: JobInfo[];
};
/** Collapse tasks of the same array job on the same host into one entry, keeping list order. */
export function groupArrayTasks(jobs: JobInfo[]): JobListEntry[] {
    const counts = new Map<string, number>();
    for (const job of jobs)
        if (job.array_job_id && job.array_task_id)
            counts.set(`${job.hostname}:${job.array_job_id}`, (counts.get(`${job.hostname}:${job.array_job_id}`) ?? 0) + 1);
    const entries: JobListEntry[] = [];
    const arrays = new Map<string, Extract<JobListEntry, { kind: 'array' }>>();
    for (const job of jobs) {
        const arrayKey = job.array_job_id ? `${job.hostname}:${job.array_job_id}` : '';
        if (arrayKey && (counts.get(arrayKey) ?? 0) > 1) {
            let entry = arrays.get(arrayKey);
            if (!entry) {
                entry = { kind: 'array', key: `array:${arrayKey}`, hostname: job.hostname, arrayId: job.array_job_id!, name: job.name || job.array_job_id!, tasks: [] };
                arrays.set(arrayKey, entry);
                entries.push(entry);
            }
            entry.tasks.push(job);
        }
        else {
            entries.push({ kind: 'job', key: `${job.hostname}:${job.job_id}`, job });
        }
    }
    return entries;
}
/** "12 running · 18 queued · 3 done" for an array's tasks. */
export function summarizeTasks(tasks: JobInfo[]): string {
    const tally = { active: 0, pending: 0, historical: 0, unknown: 0 };
    for (const task of tasks)
        tally[jobStatus(task.state).category]++;
    return [tally.active && `${tally.active} running`, tally.pending && `${tally.pending} queued`, tally.historical && `${tally.historical} done`].filter(Boolean).join(' · ');
}
const placeholders = new Set(['', 'none', 'unknown', 'n/a', '(null)', 'null', 'invalid', '0:0:0']);
/** A scheduler value, or null when Slurm reports a placeholder. */
export function jobValue(value: string | number | null | undefined): string | null {
    if (value === null || value === undefined)
        return null;
    const text = String(value).trim();
    return placeholders.has(text.toLowerCase()) ? null : text;
}
/** A real timestamp from a scheduler field, or null for placeholders and unparseable values. */
export function jobDate(value: string | null | undefined): Date | null {
    const text = jobValue(value);
    const time = text ? Date.parse(text) : NaN;
    return Number.isFinite(time) ? new Date(time) : null;
}
export function formatMoment(date: Date, now = new Date()): string {
    const sameDay = date.toDateString() === now.toDateString();
    return date.toLocaleString(undefined, sameDay ? { hour: '2-digit', minute: '2-digit' } : { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
export interface JobFact {
    label: string;
    value: string;
    mono?: boolean;
}
function facts(pairs: [string, string | number | null | undefined, boolean?][]): JobFact[] {
    return pairs.flatMap(([label, raw, mono]) => {
        const value = jobValue(raw);
        return value ? [{ label, value, mono }] : [];
    });
}
/** Grouped, placeholder-free facts for job detail. Pending jobs' start time is Slurm's estimate. */
export function jobFacts(job: JobInfo, now = new Date()) {
    const category = jobStatus(job.state).category;
    const submitted = jobDate(job.submit_time);
    const started = jobDate(job.start_time);
    const ended = category === 'historical' ? jobDate(job.end_time) : null;
    const expectedStart = category === 'pending' && started && started > now ? started : null;
    const actualStart = category === 'pending' ? null : started;
    const elapsed = durationSeconds(job.runtime);
    const limit = durationSeconds(job.time_limit);
    const waited = submitted && actualStart && actualStart >= submitted
        ? compactDuration(String(Math.round((actualStart.getTime() - submitted.getTime()) / 60000)))
        : submitted && category === 'pending' ? `${compactDuration(String(Math.round((now.getTime() - submitted.getTime()) / 60000)))} so far` : null;
    const timeLeft = category === 'active' && elapsed !== null && limit && limit > elapsed ? compactDuration(`${Math.floor((limit - elapsed) / 60)}`) : null;
    const nodeList = jobValue(job.node_list)?.startsWith('(') ? null : job.node_list;
    return {
        timeline: facts([
            ['Submitted', submitted && formatMoment(submitted, now)],
            ['Waited', waited],
            ['Expected start', expectedStart && formatMoment(expectedStart, now)],
            ['Started', actualStart && formatMoment(actualStart, now)],
            ['Ended', ended && formatMoment(ended, now)],
            ['Elapsed', category === 'pending' ? null : job.runtime && compactDuration(job.runtime)],
            ['Time limit', job.time_limit && compactDuration(job.time_limit)],
            ['Time left', timeLeft],
        ]),
        queue: category === 'pending' ? facts([
            ['Reason', job.reason],
            ['Priority', job.priority],
            ['Position', job.priority_rank && job.priority_queue_size ? `${job.priority_rank.toLocaleString()} of ${job.priority_queue_size.toLocaleString()}` : job.priority_rank],
            ['Jobs ahead', job.priority_jobs_ahead?.toLocaleString()],
            ['Ahead of', job.priority_percentile !== null && job.priority_percentile !== undefined ? `${Math.round(job.priority_percentile)}% of the queue` : null],
        ]) : [],
        resources: facts([
            ['CPUs', job.cpus], ['Memory', job.memory], ['Nodes', job.nodes], ['GPUs', gpuCount(job)],
            ['Requested', job.req_tres, true], ['Allocated', job.alloc_tres, true],
            ['Node list', nodeList, true], ['Batch host', job.batch_host],
        ]),
        usage: facts([
            ['CPU time', job.cpu_time], ['Total CPU', job.total_cpu], ['User CPU', job.user_cpu], ['System CPU', job.system_cpu],
            ['Average CPU', job.ave_cpu], ['Peak memory', job.max_rss], ['Average memory', job.ave_rss],
            ['Peak virtual memory', job.max_vmsize], ['Disk read', job.max_disk_read], ['Disk written', job.max_disk_write],
            ['Energy', job.consumed_energy],
        ]),
        scheduling: facts([
            ['User', job.user], ['Account', job.account], ['QoS', job.qos], ['Partition', job.partition],
            ['Array task', job.array_task_id ? `${job.array_job_id ?? '?'}_${job.array_task_id}` : null],
            ['Exit code', job.exit_code], ['Scheduler state', job.state],
            ['Working directory', job.work_dir, true], ['stdout', job.stdout_file, true], ['stderr', job.stderr_file, true],
            ['Submitted with', job.submit_line, true],
        ]),
    };
}
