export type JobState = 'Running' | 'Pending' | 'Completed' | 'Failed' | 'Timed out' | 'Cancelled';
export type View = 'jobs' | 'launch' | 'watchers' | 'hosts' | 'settings';
export type JobTab = 'Overview' | 'Output' | 'Script' | 'Activity';
export interface Job {
  id: string; host: string; name: string; project: string; state: JobState;
  partition: string; gpu: number; cpus: number; memory: number; runtime: string;
  elapsed: number; limit: number; submitted: string; reason?: string; rank?: number;
  watcher?: string; array?: number; loss?: string; script?: string;
}
export const hosts = [
  { name: 'atlas', address: 'atlas.hpc.example', detail: 'GPU compute', gpus: 48, gpuUsed: 34, cpus: 768, cpuUsed: 412, partition: 'gpu-a100', lastSync: '2 seconds ago' },
  { name: 'borealis', address: 'borealis.hpc.example', detail: 'General compute', gpus: 16, gpuUsed: 6, cpus: 1024, cpuUsed: 638, partition: 'compute', lastSync: '5 seconds ago' },
];
export const initialJobs: Job[] = [
  { id:'48216',host:'atlas',name:'equivariant-potential-v4',project:'Potential v4',state:'Running',partition:'gpu-a100',gpu:2,cpus:16,memory:64,runtime:'3h 14m',elapsed:194,limit:720,submitted:'09:42',watcher:'Checkpoint continuation',loss:'0.0248' },
  { id:'48215',host:'atlas',name:'phonon-dispersion',project:'Crystal screening',state:'Running',partition:'gpu-a100',gpu:1,cpus:8,memory:32,runtime:'1h 08m',elapsed:68,limit:360,submitted:'11:48' },
  { id:'48213',host:'atlas',name:'relaxation-sweep',project:'Crystal screening',state:'Pending',partition:'gpu-a100',gpu:4,cpus:32,memory:128,runtime:'—',elapsed:0,limit:240,submitted:'12:04',reason:'Waiting for resources',rank:3,array:24 },
  { id:'48209',host:'atlas',name:'embedding-evaluation',project:'Potential v4',state:'Failed',partition:'gpu-a100',gpu:1,cpus:8,memory:16,runtime:'42m',elapsed:42,limit:180,submitted:'10:16',reason:'Exit code 1 · CUDA out of memory in stderr' },
  { id:'48201',host:'atlas',name:'dataset-validation',project:'Potential v4',state:'Completed',partition:'compute',gpu:0,cpus:8,memory:16,runtime:'18m',elapsed:18,limit:60,submitted:'09:10' },
  { id:'48194',host:'atlas',name:'baseline-training',project:'Potential v4',state:'Completed',partition:'gpu-a100',gpu:2,cpus:16,memory:64,runtime:'8h 12m',elapsed:492,limit:720,submitted:'Yesterday',loss:'0.0312' },
  { id:'73142',host:'borealis',name:'structure-search',project:'Crystal screening',state:'Running',partition:'compute',gpu:0,cpus:64,memory:128,runtime:'5h 32m',elapsed:332,limit:1440,submitted:'07:24',array:12 },
  { id:'73140',host:'borealis',name:'force-field-benchmark',project:'Potential v4',state:'Running',partition:'gpu',gpu:1,cpus:8,memory:32,runtime:'26m',elapsed:26,limit:120,submitted:'12:30' },
  { id:'73138',host:'borealis',name:'ab-initio-reference',project:'Crystal screening',state:'Pending',partition:'compute',gpu:0,cpus:32,memory:64,runtime:'—',elapsed:0,limit:720,submitted:'12:18',reason:'Waiting for priority',rank:7 },
  { id:'73131',host:'borealis',name:'temperature-sweep',project:'Crystal screening',state:'Timed out',partition:'compute',gpu:0,cpus:32,memory:64,runtime:'4h 00m',elapsed:240,limit:240,submitted:'08:40',reason:'Reached the 4-hour time limit' },
  { id:'73126',host:'borealis',name:'trajectory-analysis',project:'Crystal screening',state:'Completed',partition:'compute',gpu:0,cpus:16,memory:32,runtime:'54m',elapsed:54,limit:120,submitted:'Yesterday' },
  { id:'73120',host:'borealis',name:'descriptor-generation',project:'Potential v4',state:'Completed',partition:'compute',gpu:0,cpus:16,memory:32,runtime:'1h 36m',elapsed:96,limit:180,submitted:'Yesterday' },
];
export const keyFor = (job: Job) => `${job.host}:${job.id}`;
export const needsAttention = (job: Job) => job.state === 'Failed' || job.state === 'Timed out';
export function scriptFor(job: Job) {
  if (job.script) return job.script;
  return `#!/bin/bash\n#SBATCH --job-name=${job.name}\n#SBATCH --partition=${job.partition}\n#SBATCH --cpus-per-task=${job.cpus}\n#SBATCH --mem=${job.memory}G\n#SBATCH --time=${String(Math.floor(job.limit / 60)).padStart(2, '0')}:00:00${job.gpu ? `\n#SBATCH --gres=gpu:${job.gpu}` : ''}\n\nmodule load cuda/12.4\nsource .venv/bin/activate\n\npython train.py \\\n  --config configs/potential-v4.yaml \\\n  --checkpoint latest \\\n  --epochs 400`;
}
export function outputFor(job: Job, stream = 'stdout'): string[] {
  if (job.state === 'Pending') return ['Waiting for scheduling. No output yet.'];
  if (stream === 'stderr') return job.state === 'Failed' ? [
    'Traceback (most recent call last):', '  File "train.py", line 184, in train_step',
    '    loss.backward()', 'torch.cuda.OutOfMemoryError: CUDA out of memory.',
    'Tried to allocate 2.00 GiB. GPU 0 has 512 MiB free.',
    'Consider reducing batch_size or using gradient accumulation.',
  ] : ['No stderr output for this job.'];
  return [
    `[09:42:01] Starting ${job.name}`, '[09:42:02] Loaded configuration: potential-v4.yaml',
    '[09:42:03] Dataset: 128,640 structures · 80 / 10 / 10 split', '[09:42:04] Device: NVIDIA A100 80GB × 2',
    '[09:42:06] Resuming from checkpoint: epoch_160.pt', '',
    ...Array.from({length:18},(_,i)=>`[${String(12 + Math.floor(i / 14)).padStart(2,'0')}:${String((i*4)%60).padStart(2,'0')}:08] epoch=${167+i}  loss=${(0.047-i*0.0013).toFixed(4)}  val_mae=${(0.033-i*0.0005).toFixed(4)}  lr=1.0e-04`),
    '[12:54:12] checkpoint saved: checkpoints/epoch_184.pt', '[12:54:12] Watcher: checkpoint path captured',
    '[12:54:13] Epoch 185 / 400 · batch 32 / 256',
  ];
}
export interface Watcher { id:number; name:string; jobId:string; host:string; jobName:string; state:'Active'|'Paused'; source:string; pattern:string; action:string; lastEvent:string; count:number; }
export const initialWatchers: Watcher[] = [
  {id:1,name:'Checkpoint continuation',jobId:'48216',host:'atlas',jobName:'equivariant-potential-v4',state:'Active',source:'stdout',pattern:'checkpoint saved: (?<path>.+)',action:'Resubmit from checkpoint',lastEvent:'Checkpoint captured',count:8},
  {id:2,name:'Training metrics',jobId:'48216',host:'atlas',jobName:'equivariant-potential-v4',state:'Active',source:'stdout',pattern:'loss=(?<loss>[0-9.]+)',action:'Record metric',lastEvent:'loss = 0.0248',count:184},
  {id:3,name:'Completion notification',jobId:'73142',host:'borealis',jobName:'structure-search',state:'Active',source:'Job state',pattern:'Completed or failed',action:'Send notification',lastEvent:'Waiting for job to finish',count:0},
  {id:4,name:'Memory alert',jobId:'73140',host:'borealis',jobName:'force-field-benchmark',state:'Paused',source:'stderr',pattern:'out of memory',action:'Send notification',lastEvent:'Paused by you',count:1},
];
export function readPreference<T>(key: string, fallback: T): T {
  try { const stored = localStorage.getItem(`ssync-design-${key}`); return stored ? JSON.parse(stored) as T : fallback; } catch { return fallback; }
}
export function savePreference(key: string, value: unknown) {
  try { localStorage.setItem(`ssync-design-${key}`, JSON.stringify(value)); } catch { /* A preview remains usable without storage. */ }
}

export interface LaunchDraft { name:string; host:string; partition:string; cpus:number; gpu:number; memory:number; hours:number; source:string; script:string; recipe:string; originalId?:string; account?:string; exclude?:string; dependency?:string; respectIgnore?:boolean; onlyChanged?:boolean; }
export function draftFromJob(job:Job=initialJobs[0]):LaunchDraft {
  return {name:job.name,host:job.host,partition:job.partition,cpus:job.cpus,gpu:job.gpu,memory:job.memory,hours:job.limit/60,source:'/home/research/projects/potential-v4',script:scriptFor(job),recipe:'Train potential',originalId:undefined,account:'',exclude:'',dependency:'',respectIgnore:true,onlyChanged:true};
}
export function scriptFromDraft(draft:LaunchDraft):string {
  // Resource edits update the known directives without replacing the user's script body.
  const directives:Record<string,string> = {
    'job-name':draft.name, partition:draft.partition, 'cpus-per-task':String(draft.cpus),
    mem:`${draft.memory}G`, time:`${String(draft.hours).padStart(2,'0')}:00:00`,
    gres:draft.gpu?`gpu:${draft.gpu}`:'', account:draft.account||'',
    exclude:draft.exclude||'', dependency:draft.dependency||'',
  };
  const lines=(draft.script||'#!/bin/bash\n').split('\n');
  let insertion=lines[0].startsWith('#!')?1:0;
  for(const [name,value] of Object.entries(directives)){
    const pattern=new RegExp(`^#SBATCH\\s+--${name}(?:=|\\s|$)`);
    const index=lines.findIndex(line=>pattern.test(line));
    if(index>=0){if(value)lines[index]=`#SBATCH --${name}=${value}`;else lines.splice(index,1);}
    else if(value)lines.splice(insertion++,0,`#SBATCH --${name}=${value}`);
  }
  return lines.join('\n');
}
