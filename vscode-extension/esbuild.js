const esbuild = require('esbuild');

const watch = process.argv.includes('--watch');
const minify = process.argv.includes('--minify');

esbuild.context({
  entryPoints: ['src/extension.ts'],
  bundle: true,
  outfile: 'out/extension.js',
  external: ['vscode'],
  format: 'cjs',
  platform: 'node',
  sourcemap: !minify,
  minify,
  logLevel: 'info',
}).then(async ctx => {
  if (watch) {
    await ctx.watch();
    console.log('Watching for changes...');
  } else {
    try { await ctx.rebuild(); } finally { await ctx.dispose(); }
  }
}).catch(error => { console.error(error); process.exitCode = 1; });
