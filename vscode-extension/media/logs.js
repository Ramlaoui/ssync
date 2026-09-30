(() => {
  const vscode = acquireVsCodeApi();
  const byId = id => document.getElementById(id);
  const saved = vscode.getState() || {};
  let stream = saved.stream === 'stderr' ? 'stderr' : 'stdout';
  let data;
  byId('follow').checked = saved.follow !== false;
  byId('wrap').checked = saved.wrap !== false;
  function persist() { vscode.setState({ stream, follow: byId('follow').checked, wrap: byId('wrap').checked }); }
  function render() {
    if (!data) return;
    const job = data.job;
    byId('job-name').textContent = job.name;
    byId('identity').textContent = `${job.job_id} · ${job.hostname}`;
    byId('job-state').textContent = data.states[job.state]?.label || job.state;
    byId('job-state').className = `badge ${job.state}`;
    const fields = [
      ['Partition', job.partition], ['CPUs', job.cpus], ['Memory', job.memory], ['Nodes', job.nodes],
      ['Runtime', job.runtime], ['Time limit', job.time_limit], ['Account', job.account], ['Exit code', job.exit_code],
      ['Submitted', job.submit_time], ['Started', job.start_time], ['Finished', job.end_time], ['Directory', job.work_dir],
    ].filter(([, value]) => value != null && value !== '');
    const fragment = document.createDocumentFragment();
    for (const [label, value] of fields) {
      const field = document.createElement('dl'); field.className = label === 'Directory' ? 'detail wide' : 'detail';
      const term = document.createElement('dt'), description = document.createElement('dd');
      term.textContent = label; description.textContent = String(value); field.append(term, description); fragment.append(field);
    }
    byId('details').replaceChildren(fragment);
    byId('details').hidden = !fields.length;
    byId('queue-reason').hidden = job.state !== 'PD' || !job.reason;
    byId('queue-reason').textContent = job.reason ? `Waiting: ${job.reason}` : '';
    byId('log-error').hidden = !data.error;
    byId('log-error').textContent = data.error ? `${data.error}${data.updatedAt ? ' Showing the last fetched output.' : ''}` : '';
    const active = ['R', 'PD'].includes(job.state);
    byId('cancel').hidden = !active;
    byId('log-refresh').disabled = data.loading;
    byId('copy').disabled = !data[stream];
    document.querySelectorAll('[data-stream]').forEach(tab => {
      const selected = tab.dataset.stream === stream;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    byId('log-region').setAttribute('aria-labelledby', `${stream}-tab`);
    byId('stderr-count').textContent = data.stderr ? '•' : '';
    const output = byId('output'), region = byId('log-region');
    output.classList.toggle('wrap', byId('wrap').checked);
    const text = data[stream] || '';
    if (output.textContent !== text) {
      const scroll = region.scrollTop;
      output.textContent = text;
      region.scrollTop = byId('follow').checked ? region.scrollHeight : scroll;
    }
    output.hidden = !text;
    byId('log-empty').hidden = !!text;
    byId('log-empty').textContent = data.loading && !data.updatedAt ? 'Loading output…' : active ? `No ${stream} yet. Output will appear as the job writes it.` : `No ${stream} was returned for this job.`;
    const timestamp = data.updatedAt ? `Updated ${new Date(data.updatedAt).toLocaleTimeString()}` : 'Not fetched yet';
    byId('log-status').textContent = data.loading ? 'Refreshing output…' : `${timestamp} · ${active ? 'refreshes every 5s while visible' : 'job finished'}`;
    byId('line-count').textContent = `${text ? text.trimEnd().split('\n').length : 0} lines · latest 500 per stream`;
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.stream) { stream = button.dataset.stream; persist(); render(); return; }
    if (button.dataset.command) vscode.postMessage({ command: button.dataset.command, stream });
  });
  document.querySelector('.tabs').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    stream = event.key === 'Home' ? 'stdout' : event.key === 'End' ? 'stderr' : stream === 'stdout' ? 'stderr' : 'stdout';
    persist(); render(); byId(`${stream}-tab`).focus();
  });
  byId('follow').addEventListener('change', () => { persist(); if (byId('follow').checked) byId('log-region').scrollTop = byId('log-region').scrollHeight; });
  byId('wrap').addEventListener('change', () => { persist(); render(); });
  window.addEventListener('message', event => { if (event.data.type === 'output') { data = event.data; render(); } });
  vscode.postMessage({ command: 'ready' });
})();
