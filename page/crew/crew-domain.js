/* Why: Keep absolute deadlines, version ordering and missing-data handling independent of rendering so safety behavior can be tested. */
export const hazards = [
  ['weather','Weather','Wind, rain & visibility'], ['heat','Extreme heat','Heat exposure'],
  ['lightning','Lightning','Nearby strikes'], ['flood','Flooding','River & surface water'],
  ['wildfire','Wildfire','Fire & smoke'], ['soil','Soil saturation','Ground & access'],
  ['wildlife','Wildlife','Crew observations']
];
export const validScore = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 10;
export const riskLabel = value => !validScore(value) ? 'Unavailable' : value >= 7 ? 'High' : value >= 4 ? 'Elevated' : 'Lower';
export function distanceMiles(a,b) {
  const rad=d=>d*Math.PI/180, dlat=rad(b.latitude-a.latitude), dlng=rad(b.longitude-a.longitude);
  const h=Math.sin(dlat/2)**2+Math.cos(rad(a.latitude))*Math.cos(rad(b.latitude))*Math.sin(dlng/2)**2;
  return 3958.7613*2*Math.asin(Math.sqrt(Math.min(1,h)));
}
export function strikeDeadline(site,strike,previous=null) {
  const time=Date.parse(strike.occurred_at);
  if(!Number.isFinite(time)||![site.latitude,site.longitude,strike.latitude,strike.longitude].every(Number.isFinite))return null;
  if([site,strike].some(p=>Math.abs(p.latitude)>90||Math.abs(p.longitude)>180))return null;
  if(distanceMiles(site,strike)>10+1e-9)return null;
  return new Date(Math.max(time+1800000,Date.parse(previous?.all_clear_at)||0)).toISOString();
}
export function rankSites(sites,{query='',region='',minimum=0}={}) {
  const q=query.trim().toLowerCase();
  return sites.filter(s=>(!q||[s.name,s.state,s.id,s.operator].some(v=>String(v||'').toLowerCase().includes(q)))&&(!region||s.state===region)&&(!minimum||validScore(s.score)&&s.score>=minimum))
    .sort((a,b)=>(validScore(b.score)?b.score:-1)-(validScore(a.score)?a.score:-1)||a.name.localeCompare(b.name));
}
export function timezoneValid(zone){try{new Intl.DateTimeFormat('en',{timeZone:zone}).format();return Boolean(zone);}catch{return false;}}
export function localParts(time,zone){
  return Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(time).filter(p=>p.type!=='literal').map(p=>[p.type,Number(p.value)]));
}
// Preview only. The backend owns actual scheduling. UTC conversion accounts for DST.
export function nextSixPM(zone,now=Date.now()){
  if(!timezoneValid(zone))return null;
  const p=localParts(now,zone);let local=Date.UTC(p.year,p.month-1,p.day,18);
  if(p.hour>=18)local+=86400000;
  let utc=local;
  for(let n=0;n<4;n++){const z=localParts(utc,zone);const asUTC=Date.UTC(z.year,z.month-1,z.day,z.hour,z.minute,z.second);utc+=local-asUTC;}
  return new Date(utc).toISOString();
}
export function acceptSnapshot(previous,incoming,id){
  if(!incoming||String(incoming.id)!==String(id)||!Number.isSafeInteger(incoming.revision)||incoming.revision<0)return previous;
  if(previous&&incoming.revision<=previous.revision)return previous;
  return incoming;
}
