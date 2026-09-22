import { describe, expect, it } from 'vitest';
import { createLaunchRequest } from './launchRequest';
import { parseSbatchDirectives, updateScriptWithParameters } from './sbatch-parser';

const sync = { exclude: ['*.tmp'], include: ['result.dat'], noGitignore: false };
const script = '#!/bin/bash\n#SBATCH --cpus-per-task=2\n#SBATCH --array=0-8\npython train.py --seed="$SLURM_ARRAY_TASK_ID"\n';

describe('Launch review request', () => {
  it('keeps the edited script and submits the existing backend resource contract', () => {
    const parameters = { sourceDir: '/work/training', jobName: 'training', cpus: 8, memory: 32, timeLimit: 120, nodes: 2, ntasksPerNode: 4, gpusPerNode: 2, partition: 'gpu', outputFile: 'out-%j.log' };
    const editedScript = updateScriptWithParameters(script, parameters);
    const request = createLaunchRequest(editedScript, 'cluster.test', parameters, sync);
    expect(request).toMatchObject({ script_content: editedScript, source_dir: '/work/training', host: 'cluster.test', cpus: 8, mem: 32, time: 120, nodes: 2, ntasks_per_node: 4, n_tasks_per_node: 4, gpus_per_node: 2, partition: 'gpu', output: 'out-%j.log' });
    expect(request.script_content).toContain('#SBATCH --array=0-8');
    expect(request.script_content).toContain('python train.py --seed="$SLURM_ARRAY_TASK_ID"');
    expect(parseSbatchDirectives(request.script_content).cpus).toBe(8);
  });

  it('freezes the reviewed values independently of later edits', () => {
    const parameters = { sourceDir: '/work', jobName: 'original', cpus: 2 };
    const rules = { ...sync, exclude: [...sync.exclude], include: [...sync.include] };
    const request = createLaunchRequest(script, 'cluster.test', parameters, rules);
    parameters.cpus = 16;
    rules.exclude.push('*.csv');
    expect(request.cpus).toBe(2);
    expect(request.exclude).toEqual(['*.tmp']);
  });

  it('leaves unspecified resources to the host', () => {
    expect(createLaunchRequest(script, 'cluster.test', { sourceDir: '/work' }, sync)).not.toHaveProperty('cpus');
  });

  it('rejects missing launch inputs before submission', () => {
    expect(() => createLaunchRequest(script, '', { sourceDir: '/work' }, sync)).toThrow('host');
    expect(() => createLaunchRequest(script, 'host', { sourceDir: ' ' }, sync)).toThrow('source directory');
    expect(() => createLaunchRequest(' ', 'host', { sourceDir: '/work' }, sync)).toThrow('script');
  });
});
