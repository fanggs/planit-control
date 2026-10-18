// Serve the crew plus the existing supervisor/shared/realtime frontend folders.
// Files outside page/ and hidden files are never served, including through links.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const crewRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const pageRoot=path.dirname(crewRoot);
const publicFolders=new Set(['crew','supervisor','shared','realtime']);
const types={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.json':'application/json','.svg':'image/svg+xml','.ico':'image/x-icon','.woff':'font/woff','.woff2':'font/woff2','.txt':'text/plain'};
export function createPreviewServer(){return http.createServer(async(req,res)=>{
  try{
    if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
    const url=new URL(req.url,'http://localhost'),name=decodeURIComponent(url.pathname);
    if(name.includes('\\')||name.split('/').some(part=>part.startsWith('.'))){res.writeHead(403);res.end('Forbidden');return;}
    const first=name.split('/')[1],base=publicFolders.has(first)?pageRoot:crewRoot;
    let target=await fs.realpath(path.resolve(base,'.'+(name==='/'?'/index.html':name)));
    const inside=file=>file.startsWith(pageRoot+path.sep)&&publicFolders.has(path.relative(pageRoot,file).split(path.sep)[0])&&!path.relative(pageRoot,file).split(path.sep).some(part=>part.startsWith('.'));
    if(!inside(target)){res.writeHead(403);res.end('Forbidden');return;}
    if((await fs.stat(target)).isDirectory()){
      if(!name.endsWith('/')){res.writeHead(308,{Location:url.pathname+'/'+url.search});res.end();return;}
      target=await fs.realpath(path.join(target,'index.html'));
    }
    const type=types[path.extname(target)];
    if(!inside(target)||!type){res.writeHead(403);res.end('Forbidden');return;}
    const data=await fs.readFile(target);
    res.writeHead(200,{'Content-Type':type,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
    res.end(req.method==='HEAD'?undefined:data);
  }catch{res.writeHead(404);res.end('Not found');}
});}
