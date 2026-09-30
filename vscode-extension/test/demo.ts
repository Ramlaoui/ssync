import { fixture } from './fixture';
import { previewHandler } from './preview';
import { SsyncClient } from '../src/client';
import { JobStore } from '../src/jobStore';

let store: JobStore;
let setMode: (mode: 'ok' | 'error') => void;
fixture(8052, previewHandler(() => store, mode => setMode(mode))).then(api => {
  setMode = mode => api.setMode(mode);
  store = new JobStore(new SsyncClient(api.url, ''), { pollInterval: 120, showCompleted: true, since: '3d' });
  store.start();
  console.log(`ssync demo API and UI preview: ${api.url}\nSet ssync.apiUrl to this address in the Extension Development Host. No cluster operations are performed.`);
  const close = async () => { store.dispose(); await api.close(); process.exit(); };
  process.on('SIGINT', close); process.on('SIGTERM', close);
}).catch(error => { console.error(error); process.exitCode = 1; });
