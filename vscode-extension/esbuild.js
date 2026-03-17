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
}).then(ctx => {
  if (watch) {
    ctx.watch();
    console.log('Watching for changes...');
  } else {
    ctx.rebuild().then(() => ctx.dispose());
  }
});
