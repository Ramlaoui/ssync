import type { JobParameters } from './sbatch-parser';
import type { LaunchJobRequest } from '../types/api';
export function createLaunchRequest(script: string, host: string, parameters: JobParameters, sync: {
    exclude: string[];
    include: string[];
    noGitignore: boolean;
}): LaunchJobRequest {
    if (!host)
        throw new Error('Select a host.');
    if (!parameters.sourceDir?.trim())
        throw new Error('Select a source directory.');
    if (!script.trim())
        throw new Error('The job script is empty.');
    const request: LaunchJobRequest = { script_content: script, source_dir: parameters.sourceDir.trim(), host, job_name: parameters.jobName || 'Unnamed Job', exclude: [...sync.exclude], include: [...sync.include], no_gitignore: sync.noGitignore };
    if (parameters.partition)
        request.partition = parameters.partition;
    if (parameters.account)
        request.account = parameters.account;
    if (parameters.constraint)
        request.constraint = parameters.constraint;
    if (parameters.cpus)
        request.cpus = parameters.cpus;
    if (parameters.memory)
        request.mem = parameters.memory;
    if (parameters.timeLimit)
        request.time = parameters.timeLimit;
    if (parameters.nodes)
        request.nodes = parameters.nodes;
    if (parameters.ntasksPerNode) {
        request.ntasks_per_node = parameters.ntasksPerNode;
        request.n_tasks_per_node = parameters.ntasksPerNode;
    }
    if (parameters.gpusPerNode)
        request.gpus_per_node = parameters.gpusPerNode;
    if (parameters.gres)
        request.gres = parameters.gres;
    if (parameters.outputFile)
        request.output = parameters.outputFile;
    if (parameters.errorFile)
        request.error = parameters.errorFile;
    return request;
}
