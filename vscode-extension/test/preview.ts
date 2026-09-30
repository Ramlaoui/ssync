import * as http from 'http';
import { readFileSync } from 'fs';
import { join } from 'path';
import { JobStore } from '../src/jobStore';
import { STATES } from '../src/model';

/** Browser adapter for the exact packaged UI assets; excluded from the VSIX. */
export function previewHandler(getStore: () => JobStore, setMode: (mode: 'ok' | 'error') => void) {
  return (request: http.IncomingMessage, response: http.ServerResponse): boolean => {
    const url = new URL(request.url ?? '', 'http://localhost');
    const send = (content: string, type: string) => {
      response.writeHead(200, { 'Content-Type': type }); response.end(content);
    };
    if (url.pathname === '/') {
      const page = url.searchParams.has('job') ? 'logs' : 'dashboard';
      const body = readFileSync(join(process.cwd(), 'media', `${page}.html`), 'utf8');
      const theme = url.searchParams.get('theme') === 'light' ? 'light' : url.searchParams.get('theme') === 'contrast' ? 'contrast' : 'dark';
      send(`<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self';"><title>ssync · UI preview</title><link rel="stylesheet" href="/media/panels.css"><link rel="stylesheet" href="/preview.css"></head><body class="${theme}${url.searchParams.has('narrow') ? ' narrow' : ''}"><aside class="demo-bar"><span>Demo fixtures · no cluster operations</span><button data-demo="error">Simulate outage</button><button data-demo="ok">Reconnect demo</button></aside>${body}<script src="/bridge.js"></script><script src="/media/${page}.js"></script></body></html>`, 'text/html');
    } else if (['/media/panels.css', '/media/dashboard.js', '/media/logs.js', '/bridge.js', '/preview.css'].includes(url.pathname)) {
      const file = url.pathname.startsWith('/media/') ? join(process.cwd(), url.pathname.slice(1)) : join(process.cwd(), 'test', url.pathname === '/bridge.js' ? 'preview.js' : 'preview.css');
      send(readFileSync(file, 'utf8'), url.pathname.endsWith('.css') ? 'text/css' : 'application/javascript');
    } else if (url.pathname === '/__preview/snapshot') {
      send(JSON.stringify({ type: 'snapshot', ...getStore().snapshot, states: STATES }), 'application/json');
    } else if (url.pathname === '/__preview/refresh') {
      void getStore().refresh(true).then(() => send('{}', 'application/json'));
    } else if (url.pathname === '/__preview/mode') {
      setMode(url.searchParams.get('value') === 'error' ? 'error' : 'ok');
      void getStore().refresh().then(() => send('{}', 'application/json'));
    } else return false;
    return true;
  };
}
