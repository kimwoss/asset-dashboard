import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { build, root } from './build.mjs';
import { fixture } from '../tests/preview-fixture.mjs';
const types={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.webp':'image/webp','.jpg':'image/jpeg','.woff2':'font/woff2','.svg':'image/svg+xml','.mp4':'video/mp4'};
const server=http.createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,'http://localhost'), pathname=decodeURIComponent(url.pathname);
    if(pathname==='/' || pathname==='/preview.html'){
      const data=fixture();
      const bootstrap='gate = async () => ['+JSON.stringify(data.snap)+','+JSON.stringify(data.history)+']; loadLive = async () => '+'('+JSON.stringify(data.live)+'); document.body.insertAdjacentHTML("afterbegin", "<div class=\\"preview-notice\\">디자인 미리보기 · 모든 재무 수치와 매물 조건은 가상 데이터입니다</div>"); main();';
      const html=build().replace(/\nmain\(\);\s*(?=<\/script>)/, '\n'+bootstrap+'\n');
      res.writeHead(200,{'Content-Type':types['.html'],'Cache-Control':'no-store'}); res.end(html); return;
    }
    // Only public assets; encrypted personal data and source files are never served.
    if(!pathname.startsWith('/assets/')){res.writeHead(404);res.end('Not found');return;}
    const file=path.resolve(root,'docs','.'+pathname), allowed=path.resolve(root,'docs/assets')+path.sep;
    if(!file.startsWith(allowed)){res.writeHead(403);res.end();return;}
    res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'});res.end(await fs.readFile(file));
  } catch {res.writeHead(404);res.end('Not found');}
});
server.listen(8788,'127.0.0.1',()=>console.log('Preview: http://127.0.0.1:8788/preview.html'));
