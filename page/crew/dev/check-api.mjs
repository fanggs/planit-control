// Read-only local smoke check: the API must reject anonymous data requests.
import assert from 'node:assert/strict';
const baseURL=process.env.PLANIT_API_BASE_URL||'http://127.0.0.1:8010';
const base=new URL(baseURL);
assert.equal(base.protocol,'http:','This check only targets the local HTTP API.');
assert.equal(base.hostname,'127.0.0.1','This check only targets 127.0.0.1.');
assert.equal(base.username+base.password+base.search+base.hash,'','Do not put credentials or tokens in the API URL.');
const options={signal:AbortSignal.timeout(5000),redirect:'error',credentials:'omit'};
const health=await fetch(new URL('/health',base),options);
assert.ok(health.ok,'The API must be running.');
const sites=await fetch(new URL('/sites',base),{signal:AbortSignal.timeout(5000),redirect:'error',credentials:'omit'});
assert.ok([401,503].includes(sites.status),`Anonymous /sites returned ${sites.status}; expected 401 or fail-closed 503.`);
if(sites.status===401)assert.equal(sites.headers.get('www-authenticate'),'Bearer');
console.log(`Local API health: ${health.status}; anonymous /sites: ${sites.status}. No bearer token was sent.`);
