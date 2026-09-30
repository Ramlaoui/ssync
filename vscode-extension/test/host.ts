import * as vscode from 'vscode';
import * as assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { fixture, demoJobs } from './fixture';

/** Runs with --extensionTestsPath=.../out/test/host.js against a real VS Code host. */
export async function run(): Promise<void> {
  const api = await fixture();
  try {
    const config = vscode.workspace.getConfiguration('ssync');
    await config.update('apiUrl', api.url, vscode.ConfigurationTarget.Global);
    const extension = vscode.extensions.all.find(item => item.packageJSON.name === 'ssync-vscode');
    assert.ok(extension, 'extension must be installed in development host');
    await extension.activate();
    const commands = await vscode.commands.getCommands(true);
    for (const name of ['openDashboard', 'configure', 'refreshJobs', 'submitScript', 'viewLogs', 'cancelJob', 'syncWorkspace']) assert.ok(commands.includes(`ssync.${name}`));
    await vscode.commands.executeCommand('ssync.openDashboard');
    await vscode.commands.executeCommand('ssync.refreshJobs');
    await vscode.commands.executeCommand('ssync.viewLogs', { job: demoJobs[0] });
    const firstDeadline = Date.now() + 5000;
    while (!api.requests.some(request => request.url.includes('/output') && request.url.includes('host=atlas')) && Date.now() < firstDeadline) await new Promise(resolve => setTimeout(resolve, 50));
    assert.ok(api.requests.some(request => request.url.includes('/output') && request.url.includes('host=atlas')), 'first log panel must request atlas output');
    await vscode.commands.executeCommand('ssync.viewLogs', { job: demoJobs[2] });
    const deadline = Date.now() + 5000;
    while (api.requests.filter(request => request.url.includes('/output')).length < 2 && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 50));
    assert.ok(api.requests.some(request => request.url.includes('host=atlas') && request.url.includes('/output')));
    assert.ok(api.requests.some(request => request.url.includes('host=borealis') && request.url.includes('/output')));
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    console.log('SSYNC_HOST_TESTS_PASSED: activation, commands, dashboard, and distinct cross-host log panels.');
    if (process.env.SSYNC_TEST_REPORT) writeFileSync(process.env.SSYNC_TEST_REPORT, 'passed');
  } finally { await api.close(); }
}
