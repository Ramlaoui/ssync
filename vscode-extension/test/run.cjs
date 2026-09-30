const esbuild = require('esbuild');
const { spawnSync } = require('node:child_process');
const path = require('node:path');

(async () => {
  const root = path.resolve(__dirname, '..');
  await esbuild.build({
    entryPoints: ['test/core.test.ts', 'test/demo.ts', 'test/host.ts'],
    outdir: 'out/test', bundle: true, platform: 'node', format: 'cjs',
    external: ['vscode'], absWorkingDir: root,
  });
  const demo = process.argv.includes('--demo');
  if (!demo) await esbuild.build({
    entryPoints: ['test/panels.test.ts'], outfile: 'out/test/panels.test.mjs', bundle: true,
    platform: 'node', format: 'esm', external: ['happy-dom', 'ws'], absWorkingDir: root,
  });
  const result = spawnSync(process.execPath, demo ? ['out/test/demo.js'] : ['--test', 'out/test/core.test.js', 'out/test/panels.test.mjs'], { cwd: root, stdio: 'inherit' });
  process.exitCode = result.status ?? 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
