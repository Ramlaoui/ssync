// Emulates only the VS Code bridge. Rendering uses the production HTML, CSS and JS.
(() => {
  const query = new URLSearchParams(location.search);
  let snapshot, output;
  let saved = {};
  function message(data) { window.dispatchEvent(new MessageEvent('message', { data })); }
  async function refresh() {
    snapshot = await (await fetch('/__preview/snapshot')).json();
    if (!query.has('job')) { message(snapshot); return; }
    const job = snapshot.jobs.find(job => job.job_id === query.get('job') && job.hostname === query.get('host'));
    if (!job) return;
    message({ type: 'output', job, states: snapshot.states, ...output });
    output = await (await fetch(`/api/jobs/${encodeURIComponent(job.job_id)}/output?host=${encodeURIComponent(job.hostname)}&lines=500`)).json();
    message({ type: 'output', job, states: snapshot.states, ...output, updatedAt: Date.now() });
  }
  window.acquireVsCodeApi = () => ({
    getState: () => saved,
    setState: value => { saved = value; },
    async postMessage(data) {
      if (data.command === 'open') {
        const [host, job] = JSON.parse(data.key); location.href = `/?host=${encodeURIComponent(host)}&job=${encodeURIComponent(job)}`;
      } else if (data.command === 'refresh') {
        await fetch('/__preview/refresh'); await refresh();
      } else if (data.command === 'ready') await refresh();
      else if (data.command === 'copy') await navigator.clipboard.writeText(output?.[data.stream] || '');
      else alert('Use the VS Code Extension Development Host to test this command.');
    },
  });
  document.querySelectorAll('[data-demo]').forEach(button => button.addEventListener('click', async () => {
    await fetch(`/__preview/mode?value=${button.dataset.demo}`); await refresh();
  }));
  setInterval(refresh, 5000);
})();
