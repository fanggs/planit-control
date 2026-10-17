/* Frontend part 3
Commit: feat(crew): isolate persistent demo data from live services
Why: Allow reproducible local demos while keeping browser-only storage and synthetic conditions clearly distinct from the real backend.
*/
import './crew-integration.js';
import {config} from './crew-config.js';
import {accessToken} from './crew-auth.js';
import {mockAPI} from './crew-mocks.js';
import {createHTTPAPI} from './crew-http.js';
const http=createHTTPAPI(config.api,accessToken);
async function call(name,...args){
  if(config.dataMode==='mock')return mockAPI[name](...args);
  const api=config.transport==='custom'?window.PlanITCrewAPI:http;
  if(typeof api?.[name]!=='function')throw new Error(`Live connection is not configured: ${name}. Sample data was not substituted.`);
  return config.transport==='custom'?api[name](...args,{accessToken:await accessToken()}):api[name](...args);
}
export const services=Object.fromEntries(['listSites','readSite','listReports','submitReport','listBriefings','readBriefing','readPreferences','savePreferences','subscribeEvents'].map(name=>[name,(...args)=>call(name,...args)]));
export function demoAction(name,...args){if(config.dataMode!=='mock')throw new Error('Demo controls are disabled in live mode.');return mockAPI[name](...args);}
