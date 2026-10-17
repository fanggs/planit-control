// Serve only page/, with a loopback-only listener. Never expose the repo or .env.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const port = Number(process.env.PORT || 4175);
const types = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml'};
const server = http.createServer(async (req, res) => {
  try {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405); res.end(); return; }
    const requested = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
    let target = await fs.realpath(path.resolve(root, '.' + (requested === '/' ? '/supervisor/index.html' : requested)));
    if ((await fs.stat(target)).isDirectory()) {
      if (!requested.endsWith('/')) { res.writeHead(308, {Location: requested + '/'}); res.end(); return; }
      target = await fs.realpath(path.join(target, 'index.html'));
    }
    if (!target.startsWith(root + path.sep) || !types[path.extname(target)] || target.split(path.sep).some(part => part.startsWith('.'))) {
      res.writeHead(403); res.end('Forbidden'); return;
    }
    const data = await fs.readFile(target);
    res.writeHead(200, {'Content-Type': types[path.extname(target)], 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'});
    res.end(req.method === 'HEAD' ? undefined : data);
  } catch { res.writeHead(404); res.end('Not found'); }
});
server.on('error', error => { console.error(error.message); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`PlanIT supervisor: http://127.0.0.1:${server.address().port}/supervisor/index.html`));
