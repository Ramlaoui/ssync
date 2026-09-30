(() => {
  const vscode = acquireVsCodeApi();
  const saved = vscode.getState() || {};
  const byId = id => document.getElementById(id);
  const search = byId('search'), host = byId('host'), state = byId('state');
  search.value = saved.search || '';
  state.value = saved.state || 'all';
  let selectedHost = saved.host || '';
  let snapshot = { jobs: [], hosts: [], states: {}, connection: 'connecting' };
  let previousRows = '';
  const key = job => JSON.stringify([job.hostname, job.job_id]);
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function action(label, command, job, className = 'quiet') {
    const button = element('button', label, className);
    button.dataset.command = command;
    button.dataset.key = key(job);
    button.title = `${label} ${job.name} (${job.job_id}) on ${job.hostname}`;
    return button;
  }
  function persist() { vscode.setState({ search: search.value, host: selectedHost, state: state.value }); }
  function render() {
    const jobs = snapshot.jobs;
    const running = jobs.filter(job => job.state === 'R').length;
    const queued = jobs.filter(job => job.state === 'PD').length;
    const failed = jobs.filter(job => ['F', 'TO'].includes(job.state)).length;
    for (const [id, value] of Object.entries({ all: jobs.length, running, queued, failed })) byId(`count-${id}`).textContent = value;
    byId('connection').className = `connection ${snapshot.connection}`;
    const labels = { connecting: 'Connecting', live: 'Live updates', polling: 'Polling · reconnecting', offline: 'Disconnected', paused: 'Updates paused' };
    byId('connection-label').textContent = labels[snapshot.connection] || 'Connecting';
    byId('updated').textContent = snapshot.updatedAt ? `Updated ${new Date(snapshot.updatedAt).toLocaleTimeString()}` : 'Waiting for the first update';
    byId('refresh').disabled = !!snapshot.refreshing;
    byId('refresh').textContent = snapshot.refreshing ? 'Refreshing…' : '↻ Refresh';
    byId('warning').hidden = !snapshot.error;
    byId('error').textContent = snapshot.error || '';
    byId('stale-note').textContent = jobs.length ? 'Showing last known jobs. Their status may have changed.' : 'Configure the connection or start your local ssync server, then retry.';
    const hostOptions = JSON.stringify(snapshot.hosts);
    if (host.dataset.options !== hostOptions) {
      host.replaceChildren(element('option', 'All clusters'));
      host.firstChild.value = '';
      for (const hostname of snapshot.hosts) { const option = element('option', hostname); option.value = hostname; host.append(option); }
      if (selectedHost && !snapshot.hosts.includes(selectedHost)) {
        const option = element('option', `${selectedHost} (unavailable)`); option.value = selectedHost; host.append(option);
      }
      host.value = selectedHost;
      host.dataset.options = hostOptions;
    }
    document.querySelectorAll('[data-filter]').forEach(button => {
      const selected = button.dataset.filter === state.value;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    const query = search.value.trim().toLowerCase();
    const filtered = jobs.filter(job => (!selectedHost || job.hostname === selectedHost) &&
      (state.value === 'all' || job.state === state.value || (state.value === 'failed' && ['F', 'TO'].includes(job.state))) &&
      (!query || [job.name, job.job_id, job.hostname, job.partition, job.reason].filter(Boolean).join(' ').toLowerCase().includes(query)));
    // Keep DOM and keyboard focus intact for connection-only updates.
    const signature = JSON.stringify(filtered);
    if (signature !== previousRows) {
      const focused = document.activeElement;
      const focusKey = focused?.dataset.key, focusCommand = focused?.dataset.command;
      const fragment = document.createDocumentFragment();
      for (const job of filtered) {
        const row = element('tr');
        const name = element('td');
        name.append(action(job.name || job.job_id, 'open', job, 'job-link'), element('span', `#${job.job_id}`, 'secondary-line mono'));
        const status = element('td');
        status.append(element('span', snapshot.states[job.state]?.label || job.state, `badge ${job.state}`));
        if (job.state === 'PD' && job.reason) status.append(element('span', job.reason, 'secondary-line reason'));
        if (job.stale) status.append(element('span', 'Cached status', 'secondary-line'));
        const cluster = element('td');
        cluster.append(element('span', job.hostname), element('span', job.partition || 'Default partition', 'secondary-line'));
        const runtime = element('td');
        runtime.append(element('span', job.runtime || '—', 'mono'), element('span', job.time_limit ? `of ${job.time_limit}` : 'No time limit reported', 'secondary-line'));
        const actions = element('td'), controls = element('div', null, 'row-actions');
        controls.append(action('Inspect', 'open', job));
        if (['R', 'PD'].includes(job.state)) controls.append(action('Cancel', 'cancel', job, 'danger'));
        actions.append(controls);
        row.append(name, status, cluster, runtime, actions);
        fragment.append(row);
      }
      byId('jobs').replaceChildren(fragment);
      previousRows = signature;
      if (focusKey) {
        const buttons = [...byId('jobs').querySelectorAll('button')];
        buttons.find(button => button.dataset.key === focusKey && button.dataset.command === focusCommand)?.focus({ preventScroll: true });
      }
    }
    const filtering = !!(query || selectedHost || state.value !== 'all');
    byId('empty').hidden = filtered.length > 0;
    document.querySelector('.table-wrap').hidden = !filtered.length;
    const waiting = !snapshot.updatedAt && (snapshot.connection === 'connecting' || snapshot.refreshing);
    byId('empty-title').textContent = waiting ? 'Connecting to your clusters…' : filtering ? 'No matching jobs' : snapshot.error ? 'Your clusters are out of reach' : 'Ready for your next experiment';
    byId('empty-description').textContent = waiting ? 'Your jobs will appear here when the server responds.' : filtering ? 'Try a different search or clear your filters.' : snapshot.error ? 'Check the server address and API key to reconnect.' : 'Submit a script to see its progress and output here.';
    const emptyAction = byId('empty-action');
    emptyAction.hidden = waiting;
    emptyAction.dataset.command = filtering ? 'clearFilters' : snapshot.error ? 'configure' : 'submit';
    emptyAction.textContent = filtering ? 'Clear filters' : snapshot.error ? 'Configure connection' : 'Submit script';
    byId('results').textContent = `${filtered.length} of ${jobs.length} jobs${snapshot.error ? ' · last known status' : ''}`;
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.filter) { state.value = button.dataset.filter; persist(); render(); return; }
    if (button.dataset.command === 'clearFilters') {
      search.value = ''; state.value = 'all'; selectedHost = ''; host.value = ''; persist(); render(); return;
    }
    if (button.dataset.command) vscode.postMessage({ command: button.dataset.command, key: button.dataset.key });
  });
  search.addEventListener('input', () => { persist(); render(); });
  state.addEventListener('change', () => { persist(); render(); });
  host.addEventListener('change', () => { selectedHost = host.value; persist(); render(); });
  window.addEventListener('message', event => { if (event.data.type === 'snapshot') { snapshot = event.data; render(); } });
  render();
  vscode.postMessage({ command: 'ready' });
})();
