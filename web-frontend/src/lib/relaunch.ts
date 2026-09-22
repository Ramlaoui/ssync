import { api } from '../services/api';
import { resubmitStore } from '../stores/resubmit';
import type { JobInfo, JobScriptResponse } from '../types/api';
import type { WatchersResponse } from '../types/watchers';
// Stage the existing manual relaunch flow. Submission still happens in the launch review.
export async function prepareRelaunch(job: JobInfo): Promise<void> {
    const { data: script } = await api.get<JobScriptResponse>(`/api/jobs/${encodeURIComponent(job.job_id)}/script`, { params: { host: job.hostname } });
    if (!script.script_content)
        throw new Error('No script is available for this job.');
    let attached: WatchersResponse['watchers'] = [];
    try {
        const { data } = await api.get<WatchersResponse>(`/api/jobs/${encodeURIComponent(job.job_id)}/watchers`, { params: { host: job.hostname } });
        attached = data.watchers;
    }
    catch { /* The script can be relaunched when optional watcher data is unavailable. */ }
    const variables: Record<string, string> = {};
    attached.forEach(watcher => Object.entries(watcher.variables || {}).forEach(([key, value]) => variables[attached.length > 1 && watcher.name ? `${watcher.name}_${key}` : key] = value));
    resubmitStore.setResubmitData({ scriptContent: script.script_content, hostname: job.hostname, workDir: job.work_dir ?? undefined, localSourceDir: script.local_source_dir ?? undefined, originalJobId: job.job_id, jobName: job.name, submitLine: job.submit_line ?? undefined, watcherVariables: Object.keys(variables).length ? variables : undefined, watchers: attached.length ? attached.map(watcher => ({ ...watcher, type: 'pattern' })) : undefined });
}
