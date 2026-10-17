import fs from 'node:fs/promises';
import {atlasRoster} from '../crew-atlas-data.js';
const source=new URL('../../../get_data/generated/sites.json',import.meta.url);
const snapshot=new URL('../crew-data/monitored-sites.json',import.meta.url);
const text=await fs.readFile(source,'utf8');
atlasRoster(JSON.parse(text));
await fs.writeFile(snapshot,text);
console.log('Updated the crew atlas snapshot from the verified 60-site roster.');
