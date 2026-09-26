import {build} from 'esbuild';
import {mkdir, copyFile, writeFile} from 'node:fs/promises';
await mkdir('web/assets', {recursive:true});
await build({entryPoints:['frontend/app.js'], bundle:true, minify:true, outfile:'web/assets/app.js',
  loader:{'.woff2':'file','.woff':'file','.ttf':'file'}, assetNames:'fonts/[name]-[hash]',
  target:['chrome110'], legalComments:'linked'});
const packages = ['markdown-it','markdown-it-texmath','katex','dompurify','highlight.js'];
await mkdir('web/licenses',{recursive:true});
for (const name of packages) {
  const filename = name === 'markdown-it-texmath' ? 'license.txt' : name === 'dompurify' ? 'LICENSE' : 'LICENSE';
  await copyFile(`node_modules/${name}/${filename}`, `web/licenses/${name}.txt`);
}
await writeFile('web/licenses/README.txt', 'Bundled offline renderer libraries. Versions are pinned in package-lock.json.\nMarkdown-it, markdown-it-texmath, KaTeX, highlight.js: MIT/BSD licenses in this folder.\nDOMPurify: Apache-2.0 OR MPL-2.0.\n');
console.log('Offline frontend built in web/assets.');
