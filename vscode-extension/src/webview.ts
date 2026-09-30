import * as vscode from 'vscode';
import { randomBytes } from 'crypto';
import { readFileSync } from 'fs';

/** Only packaged assets can load; job names and logs arrive as messages, never HTML. */
export function webviewHtml(webview: vscode.Webview, extensionUri: vscode.Uri, page: 'dashboard' | 'logs'): string {
  const media = vscode.Uri.joinPath(extensionUri, 'media');
  const nonce = randomBytes(16).toString('hex');
  const css = webview.asWebviewUri(vscode.Uri.joinPath(media, 'panels.css'));
  const script = webview.asWebviewUri(vscode.Uri.joinPath(media, `${page}.js`));
  const body = readFileSync(vscode.Uri.joinPath(media, `${page}.html`).fsPath, 'utf8');
  return `<!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
    <title>ssync ${page === 'dashboard' ? 'Jobs' : 'Job output'}</title>
    <link rel="stylesheet" href="${css}">
    </head><body>${body}<script nonce="${nonce}" src="${script}"></script></body></html>`;
}
