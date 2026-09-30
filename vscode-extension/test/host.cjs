const { mkdtempSync, mkdirSync, writeFileSync, readFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const esbuild = require('esbuild');

(async () => {
  const root = path.resolve(__dirname, '..');
  await esbuild.build({ entryPoints: ['test/host.ts'], outdir: 'out/test', bundle: true, platform: 'node', format: 'cjs', external: ['vscode'], absWorkingDir: root });
  const profile = mkdtempSync(path.join(tmpdir(), 'ssync-vscode-host-'));
  mkdirSync(path.join(profile, 'User'));
  writeFileSync(path.join(profile, 'User/settings.json'), JSON.stringify({
    'telemetry.telemetryLevel': 'off', 'workbench.startupEditor': 'none', 'update.mode': 'none',
    'extensions.autoCheckUpdates': false, 'extensions.autoUpdate': false, 'security.workspace.trust.enabled': false,
  }));
  const report = path.join(profile, 'test-result');
  let developmentPath = root;
  if (process.argv.includes('--package')) {
    const packageRoot = path.join(profile, 'package');
    const version = require('../package.json').version;
    const unpack = spawnSync('unzip', ['-q', path.join(root, `ssync-vscode-${version}.vsix`), '-d', packageRoot], { stdio: 'inherit' });
    if (unpack.status !== 0) throw new Error('Could not unpack the VSIX for testing.');
    developmentPath = path.join(packageRoot, 'extension');
  }
  const env = { ...process.env, SSYNC_TEST_REPORT: report };
  delete env.VSCODE_IPC_HOOK_CLI;
  const result = spawnSync(process.env.SSYNC_VSCODE_COMMAND || 'code', [
    '--user-data-dir', profile, '--extensions-dir', path.join(profile, 'extensions'),
    `--extensionDevelopmentPath=${developmentPath}`, `--extensionTestsPath=${path.join(root, 'out/test/host.js')}`,
    '--skip-welcome', '--skip-release-notes', '--disable-extensions', '--disable-workspace-trust', '--wait',
  ], { env, stdio: 'inherit', timeout: 60_000 });
  if (result.error) throw result.error;
  // Some VS Code CLI versions return zero even when the test runner fails.
  try { if (readFileSync(report, 'utf8') !== 'passed') throw new Error('No successful test report'); }
  catch { throw new Error(`Extension host tests failed. Inspect logs in ${path.join(profile, 'logs')}`); }
  console.log(`Passed real VS Code ${process.argv.includes('--package') ? 'VSIX' : 'source'} host tests: activation, commands, dashboard, and cross-host logs.`);
})().catch(error => { console.error(error.message); process.exitCode = 1; });
