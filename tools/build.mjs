import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export function build() {
  const read = f => fs.readFileSync(path.join(root, f), 'utf8').replace(/\r\n/g, '\n');
  const template = read('src/index.template.html');
  if (!template.includes('@@STYLES@@') || !template.includes('@@APP@@')) throw Error('Missing template markers');
  const app = fs.readdirSync(path.join(root, 'src/js')).filter(f => f.endsWith('.js')).sort().map(f => read('src/js/' + f)).join('');
  return template.replace('@@STYLES@@', read('src/styles.css')).replace('@@APP@@', app);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const html = build(), out = path.join(root, 'docs/index.html');
  if (process.argv.includes('--check')) {
    if (fs.readFileSync(out, 'utf8').replace(/\r\n/g, '\n') !== html) throw Error('docs/index.html differs from source');
    console.log('Build matches source');
  } else { fs.writeFileSync(out, html); console.log('Built docs/index.html'); }
}
