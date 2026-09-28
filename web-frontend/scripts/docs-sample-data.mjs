// Fictional sample workspace used for documentation screenshots. No real clusters, users, or paths.
const now = Date.now();
// Slurm reports local wall-clock times without a timezone.
const local = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
const ago = minutes => local(new Date(now - minutes * 60000));
const ahead = minutes => local(new Date(now + minutes * 60000));
const clock = minutes => {
  const h = Math.floor(minutes / 60), m = Math.floor(minutes % 60);
  return h >= 24 ? `${Math.floor(h / 24)}-${String(h % 24).padStart(2, '0')}:${String(m).padStart(2, '0')}:00` : `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`;
};

function job(fields) {
  const { id, host, name, state, elapsed = 0, limit = 480, submitted = elapsed + 12, cpus = '16', memory = '64G', gpus = 0, partition, ...rest } = fields;
  const started = state === 'PD' ? null : ago(elapsed);
  const tres = `cpu=${cpus},mem=${memory}${gpus ? `,gres/gpu=${gpus}` : ''}`;
  return {
    job_id: id, name, state, hostname: host, user: 'alex', partition,
    nodes: '1', cpus, memory, time_limit: clock(limit), runtime: state === 'PD' ? '0:00' : clock(elapsed),
    reason: state === 'PD' ? 'Priority' : 'None', work_dir: `/scratch/alex/${name}`,
    stdout_file: `/scratch/alex/${name}/logs/${id}.out`, stderr_file: `/scratch/alex/${name}/logs/${id}.err`,
    submit_time: ago(submitted), submit_line: `sbatch launch/${name}.sh`, start_time: started ?? ahead(95),
    end_time: ['CD', 'F', 'CA', 'TO'].includes(state) ? ago(Math.max(1, submitted - elapsed - 15)) : 'Unknown',
    node_list: state === 'PD' ? '(Priority)' : `${host}-gpu0${(Number(id.slice(-1)) % 8) + 1}`,
    batch_host: state === 'PD' ? null : `${host}-gpu0${(Number(id.slice(-1)) % 8) + 1}`,
    account: 'ml-lab', qos: gpus ? 'gpu-normal' : 'normal',
    alloc_tres: state === 'PD' ? null : tres, req_tres: tres,
    cpu_time: null, total_cpu: null, user_cpu: null, system_cpu: null, ave_cpu: null, ave_cpu_freq: null,
    req_cpu_freq_min: null, req_cpu_freq_max: null, max_rss: null, ave_rss: null, max_vmsize: null, ave_vmsize: null,
    max_disk_read: null, max_disk_write: null, ave_disk_read: null, ave_disk_write: null, consumed_energy: null,
    exit_code: state === 'CD' ? '0:0' : state === 'F' ? '1:0' : null,
    ...rest,
  };
}

const finished = extra => ({ cpu_time: '2-04:11:00', total_cpu: '1-22:40:12', max_rss: '41.7G', ave_rss: '33.2G', max_disk_read: '184G', max_disk_write: '12G', consumed_energy: '6.4 kWh', ...extra });

export const jobs = [
  job({ id: '48192', host: 'atlas', name: 'protein-fold-v3', state: 'R', elapsed: 138, limit: 480, gpus: 4, cpus: '32', memory: '128G', partition: 'gpu-a100' }),
  job({ id: '48201', host: 'atlas', name: 'llm-finetune-7b', state: 'R', elapsed: 312, limit: 1440, gpus: 8, cpus: '64', memory: '512G', partition: 'gpu-h100' }),
  job({ id: '48207', host: 'atlas', name: 'diffusion-sampler-sweep', state: 'R', elapsed: 46, limit: 240, gpus: 2, cpus: '16', memory: '64G', partition: 'gpu-a100' }),
  job({ id: '82013', host: 'boreal', name: 'climate-downscaling', state: 'R', elapsed: 721, limit: 2880, cpus: '128', memory: '480G', partition: 'cpu-large' }),
  job({ id: '82040', host: 'boreal', name: 'md-solvated-lysozyme', state: 'R', elapsed: 95, limit: 720, cpus: '64', memory: '192G', partition: 'cpu' }),
  job({ id: '7731', host: 'nova', name: 'eval-baseline', state: 'R', elapsed: 12, limit: 60, gpus: 1, cpus: '8', memory: '32G', partition: 'short' }),
  ...[1, 2, 3, 4, 5, 6].map(task => job({ id: `48230_${task}`, host: 'atlas', name: 'hparam-sweep', state: task <= 4 ? 'R' : 'PD', elapsed: task <= 4 ? 38 + task : 0, submitted: 52, limit: 180, gpus: 1, cpus: '8', memory: '32G', partition: 'gpu-a100', array_job_id: '48230', array_task_id: String(task) })),
  job({ id: '48215', host: 'atlas', name: 'protein-fold-v4', state: 'PD', limit: 480, submitted: 18, gpus: 4, cpus: '32', memory: '128G', partition: 'gpu-a100', priority: '41275', priority_rank: 3, priority_jobs_ahead: 2, priority_queue_size: 41, priority_percentile: 95, priority_snapshot_at: ago(1) }),
  job({ id: '82055', host: 'boreal', name: 'ensemble-member-12', state: 'PD', limit: 1440, submitted: 64, cpus: '64', memory: '240G', partition: 'cpu-large', reason: 'Resources', priority_rank: 9, priority_jobs_ahead: 8, priority_queue_size: 23, priority_percentile: 64 }),
  job({ id: '48188', host: 'atlas', name: 'protein-fold-v2', state: 'CD', elapsed: 332, submitted: 540, limit: 480, gpus: 4, cpus: '32', memory: '128G', partition: 'gpu-a100', ...finished() }),
  job({ id: '48150', host: 'atlas', name: 'tokenizer-benchmark', state: 'CD', elapsed: 41, submitted: 900, limit: 120, gpus: 1, cpus: '8', memory: '32G', partition: 'gpu-a100', ...finished({ max_rss: '11.2G', consumed_energy: '0.8 kWh' }) }),
  job({ id: '81990', host: 'boreal', name: 'dataset-validation', state: 'F', elapsed: 3, submitted: 260, limit: 60, cpus: '16', memory: '64G', partition: 'cpu', ...finished({ max_rss: '3.1G', consumed_energy: '0.1 kWh' }) }),
  job({ id: '7702', host: 'nova', name: 'notebook-export', state: 'CA', elapsed: 22, submitted: 400, limit: 60, cpus: '4', memory: '16G', partition: 'short' }),
];

export const hosts = [
  { hostname: 'atlas', work_dir: '/scratch/alex', scratch_dir: '/scratch/alex', slurm_defaults: { partition: 'gpu-a100', account: 'ml-lab', cpus: 16, mem: 64, time: '08:00:00', gpus_per_node: 1 } },
  { hostname: 'boreal', work_dir: '/home/alex/work', scratch_dir: '/lustre/alex', slurm_defaults: { partition: 'cpu', account: 'ml-lab', cpus: 32, mem: 128, time: '12:00:00' } },
  { hostname: 'nova', work_dir: '/home/alex', scratch_dir: '/tmp/alex', slurm_defaults: { partition: 'short', cpus: 4, mem: 16, time: '01:00:00' } },
];

const partition = (name, cpusTotal, cpusAlloc, nodes, gpusTotal = 0, gpusUsed = 0, gpuType = null, states = ['mixed']) => ({
  partition: name, availability: 'up', states, nodes_total: nodes, cpus_alloc: cpusAlloc, cpus_idle: cpusTotal - cpusAlloc, cpus_other: 0, cpus_total: cpusTotal,
  gpus_total: gpusTotal || null, gpus_used: gpusTotal ? gpusUsed : null, gpus_idle: gpusTotal ? gpusTotal - gpusUsed : null,
  gpu_types: gpuType ? { [gpuType]: { total: gpusTotal, used: gpusUsed } } : undefined,
});
export const partitions = [
  { hostname: 'atlas', query_time: ago(0), updated_at: new Date(now - 40000).toISOString(), partitions: [partition('gpu-a100', 2048, 1536, 32, 256, 212, 'a100'), partition('gpu-h100', 1536, 1344, 16, 128, 120, 'h100'), partition('cpu', 8192, 5120, 64), partition('debug', 256, 32, 4, 16, 2, 'a100')] },
  { hostname: 'boreal', query_time: ago(0), updated_at: new Date(now - 65000).toISOString(), partitions: [partition('cpu', 24576, 20480, 192), partition('cpu-large', 12288, 11264, 48), partition('bigmem', 2048, 512, 8)] },
  { hostname: 'nova', query_time: ago(0), updated_at: new Date(now - 20000).toISOString(), partitions: [partition('short', 512, 96, 8, 16, 5, 'l40s'), partition('long', 1024, 700, 16)] },
];

const watcher = (id, fields) => ({ id, captures: [], actions: [], state: 'active', trigger_count: 0, interval_seconds: 60, created_at: ago(200), last_check: ago(1), ...fields });
export const watchers = [
  watcher(1, { job_id: '48192', hostname: 'atlas', job_name: 'protein-fold-v3', name: 'Resume from checkpoint', pattern: 'checkpoint saved: (\\S+)', captures: ['checkpoint'], trigger_on_job_end: true, trigger_job_states: ['timeout'], actions: [{ type: 'resubmit', config: { remaining_resubmits: 3 } }], trigger_count: 4 }),
  watcher(2, { job_id: '48201', hostname: 'atlas', job_name: 'llm-finetune-7b', name: 'Stop on NaN loss', pattern: 'loss[:=]\\s*nan', actions: [{ type: 'cancel_job', config: {} }], interval_seconds: 30 }),
  watcher(3, { job_id: '48201', hostname: 'atlas', job_name: 'llm-finetune-7b', name: 'Sync W&B run', pattern: 'wandb: Run data is saved locally in (\\S+)', captures: ['run_dir'], actions: [{ type: 'run_command', config: { command: 'wandb sync $run_dir' } }], interval_seconds: 300, trigger_count: 12 }),
  watcher(4, { job_id: '82013', hostname: 'boreal', job_name: 'climate-downscaling', name: 'Log validation score', pattern: 'val_score=([0-9.]+)', captures: ['score'], actions: [{ type: 'store_metric', config: { name: 'val_score' } }], trigger_count: 31 }),
  watcher(5, { job_id: '48207', hostname: 'atlas', job_name: 'diffusion-sampler-sweep', name: 'Email when FID improves', pattern: 'FID: ([0-9.]+)', captures: ['fid'], condition: 'float(fid) < 12', actions: [{ type: 'notify_email', config: {} }], state: 'paused' }),
];
export const watcherEvents = [
  { id: 101, watcher_id: 1, watcher_name: 'Resume from checkpoint', job_id: '48192', hostname: 'atlas', timestamp: ago(6), matched_text: 'checkpoint saved: ckpt/epoch-24.pt', captured_vars: { checkpoint: 'ckpt/epoch-24.pt' }, action_type: 'log_event', action_result: 'Checkpoint captured; waiting for job end', success: true },
  { id: 102, watcher_id: 4, watcher_name: 'Log validation score', job_id: '82013', hostname: 'boreal', timestamp: ago(14), matched_text: 'val_score=0.9412', captured_vars: { score: '0.9412' }, action_type: 'store_metric', action_result: 'val_score = 0.9412', success: true },
  { id: 103, watcher_id: 3, watcher_name: 'Sync W&B run', job_id: '48201', hostname: 'atlas', timestamp: ago(33), matched_text: 'wandb: Run data is saved locally in wandb/run-7b-lora', captured_vars: { run_dir: 'wandb/run-7b-lora' }, action_type: 'run_command', action_result: 'Synced 1 run', success: true },
];
export const watcherStats = {
  total_watchers: watchers.length, watchers_by_state: { active: 4, paused: 1, completed: 0, static: 0 }, total_events: 47,
  events_by_action: { resubmit: { total: 4, success: 4, failed: 0 } }, events_last_hour: 9, top_watchers: [],
};

export function output(jobId) {
  const lines = [];
  if (jobId.startsWith('48192')) {
    for (let step = 1180; step <= 1259; step++)
      lines.push(`[${String(9 + Math.floor(step / 60) % 3).padStart(2, '0')}:${String(step % 60).padStart(2, '0')}:14] step ${step}  loss ${(0.42 - step / 6200).toFixed(4)}  lr 3.0e-04  tok/s 18,432`);
    lines.push('[11:59:02] checkpoint saved: ckpt/epoch-24.pt', '[11:59:05] epoch 24/40  val_rmsd 1.87Å  best 1.84Å');
  } else if (jobId.startsWith('81990')) {
    lines.push('Validating shard 1/48 … ok', 'Validating shard 2/48 … ok', 'Traceback (most recent call last):', '  File "validate.py", line 88, in <module>', 'ValueError: shard 3 has 12 rows with missing labels');
  } else {
    for (let step = 1; step <= 60; step++) lines.push(`epoch ${1 + Math.floor(step / 20)}  step ${step * 50}  loss ${(1.8 - step / 45).toFixed(3)}  throughput 912 samples/s`);
  }
  return lines.join('\n') + '\n';
}

export const script = name => `#!/bin/bash
#SBATCH --job-name=${name}
#SBATCH --partition=gpu-a100
#SBATCH --gpus-per-node=4
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=08:00:00

#LOGIN_SETUP_BEGIN
uv sync --frozen
#LOGIN_SETUP_END

#WATCHER_BEGIN
# name: Resume from checkpoint
# pattern: "checkpoint saved: (\\S+)"
# captures: [checkpoint]
# trigger_on_job_end: true
# trigger_job_states: [timeout]
# actions:
#   - resubmit()
#WATCHER_END

source .venv/bin/activate
srun python train.py --config configs/${name}.yaml --resume "\${CHECKPOINT:-}"
`;
