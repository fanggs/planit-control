import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
for(const name of await fs.readdir(new URL('../',import.meta.url))){if(name.endsWith('.js'))execFileSync(process.execPath,['--check',fileURLToPath(new URL('../'+name,import.meta.url))],{stdio:'inherit'});}
console.log('All application JavaScript syntax checks passed.');
