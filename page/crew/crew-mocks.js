/* Why: Allow reproducible local demos while keeping browser-only storage and synthetic conditions clearly distinct from the real backend. */
import {hazards,strikeDeadline,nextSixPM,timezoneValid,localParts} from './crew-domain.js';
import {atlasRoster} from './crew-atlas-data.js';
import {localRead,localWrite} from './crew-local-store.js';
import {featureLabel} from './crew-screening.js';
let catalogPromise;
const demoSource={source_name:'Synthetic demonstration fixture',source_url:null};
const listeners=new Set(),memory=new Map();
const channel=typeof BroadcastChannel!=='undefined'?new BroadcastChannel('planit-crew-demo-v2'):null;
channel?.addEventListener('message',event=>{if(event.data.type==='site')memory.delete(String(event.data.site_id));listeners.forEach(fn=>fn(event.data));});
const now=()=>new Date().toISOString();
const hash=id=>Array.from(id).reduce((a,c)=>(a*31+c.charCodeAt(0))>>>0,7);
// Use the same approved roster as the primary map. Only conditions are synthetic.
async function catalog(){
  if(!catalogPromise)catalogPromise=fetch(new URL('crew-data/monitored-sites.json',import.meta.url)).then(r=>{
    if(!r.ok)throw new Error('Monitored plant reference file unavailable.');return r.json();
  }).then(rows=>atlasRoster(rows).map(r=>({...r,operator:r.utility,
    score:Math.round((2+hash(r.id)%76/10)*10)/10,
    provenance:{source_name:r.source_name,source_url:r.source_url,retrieved_at:r.retrieved_at},
    score_status:'sample',valid_from:now(),valid_until:new Date(Date.now()+86400000).toISOString(),score_updated_at:now(),demo:true})));
  return catalogPromise;
}
function emit(event){listeners.forEach(fn=>fn(event));channel?.postMessage(event);}
function readState(id){
  if(memory.has(id))return memory.get(id);
  let saved;try{saved=JSON.parse(localStorage.getItem('planit-crew-v2-state-'+id));}catch{}
  const value=saved||{revision:1,alert:{site_id:id,version:0,status:'unknown',all_clear_at:null},floodWarning:false};memory.set(id,value);return value;
}
function saveState(id,value){memory.set(id,value);try{localStorage.setItem('planit-crew-v2-state-'+id,JSON.stringify(value));}catch{}emit({type:'site',site_id:id});}
async function site(id){
  id=String(id);const base=(await catalog()).find(s=>s.id===id);if(!base)throw new Error('Unknown plant reference.');
  const value=readState(id),high=base.score>=7,stamp=now();
  const readings=[['Partly cloudy · wind 12 mph','Check local visibility before vehicle movements.'],['Heat index 110°F','Plan water, shade and heat breaks.'],[value.alert.status==='hold'?`${value.alert.distance_miles?.toFixed(1)} mi · sample strike`:'No measured strike data','Use designated shelter when a hold is active.'],[value.floodWarning?'68 mm overnight · flood warning':'12 mm overnight · sample','Inspect access roads before entering.'],['Smoke outlook · sample elevated','Check smoke and fire updates before travel.'],['Soil saturation 86% · sample','Review access and equipment stability.'],['Unverified wildlife observation','Keep clear and share confirmed sightings.']];
  return {...base,revision:value.revision,server_time:stamp,timezone:base.timezone||null,
    hazards:Object.fromEntries(hazards.map(([key],i)=>[key,{reading:readings[i][0],advice:readings[i][1],severity:key==='flood'&&value.floodWarning||key==='lightning'&&value.alert.status==='hold'?'high':high&&['heat','soil'].includes(key)?'high':'elevated',observed_at:stamp,...demoSource}])),
    score_method:'Synthetic demo index. No trained model is connected.',model:{name:'Demo fixture',version:'sample-v3',training_period:'Not trained',trained_at:null,evaluation:'No historical model evaluation'},baseline:1,
    score_reconciles:true,
    factors:[['rain_total_24h_in',.45],['wind_max_mph',.35],['heat_index_max_f',.25],['month_cos',-.05]].map(([feature,weight])=>({feature,name:featureLabel(feature),contribution:(base.score-1)*weight,unit:'score_points',reading:'Synthetic example contribution',scored_at:stamp,...demoSource})),wildlife_context:{site_id:id,status:'sample_no_evidence',sightings:[],encounter_probability:null,numeric_score_contribution:null,limitations:'Demo mode has no historical sighting feed. Crew reports are stored separately.'},alert:value.alert,
    flood:{status:value.floodWarning?'warning':'unknown',message:value.floodWarning?'Sample river-side scenario: heavy overnight rain may flood access roads. Check with your supervisor before entering.':'Live flood assessment is not connected.',river_name:value.floodWarning?(id==='6072'?'Mississippi River':'Demo river scenario — not verified for this plant'):null,river_distance_miles:value.floodWarning?1.1:null,overnight_rain_mm:value.floodWarning?68:null,window_label:value.floodWarning?'Previous night, 6 PM–6 AM (sample)':null,observed_at:stamp,rule_description:value.floodWarning?'Demo scenario only: river proximity and heavy rain; backend must supply its own hydrologic criteria.':null,...demoSource}};
}
export const mockAPI={
  async listSites(){return (await catalog()).map(s=>({...s}));},readSite:site,
  async ask(){throw new Error('Questions require live data. The sample preview does not call Gemini.');},
  subscribeEvents(siteId,onEvent,onConnection){
    const listener=event=>{if(!siteId||!event.site_id||String(event.site_id)===String(siteId))onEvent(event);};listeners.add(listener);onConnection(true);
    const timer=setInterval(()=>{onConnection(navigator.onLine);onEvent({type:'heartbeat',server_time:now()});},10000);
    return ()=>{listeners.delete(listener);clearInterval(timer);};
  },
  async strike(id,miles=4.2){
    const p=await site(id),value=readState(String(id));
    const strike={latitude:p.latitude+miles/3958.7613*180/Math.PI,longitude:p.longitude,occurred_at:now()};
    const deadline=strikeDeadline(p,strike,value.alert);
    if(!deadline)return {triggered:false};
    const alert={site_id:String(id),version:value.alert.version+1,status:'hold',all_clear_at:deadline,last_strike_at:strike.occurred_at,distance_miles:miles};
    saveState(String(id),{...value,revision:value.revision+1,alert});emit({type:'alert',site_id:String(id),alert,server_time:now()});return {triggered:true};
  },
  async clear(id){const value=readState(String(id));saveState(String(id),{...value,revision:value.revision+1,alert:{site_id:String(id),version:value.alert.version+1,status:'cleared',all_clear_at:null}});},
  async flood(id,active){const value=readState(String(id));saveState(String(id),{...value,revision:value.revision+1,floodWarning:active});},
  async listReports(id){return (await localRead('reports')).filter(r=>String(r.site_id)===String(id)).sort((a,b)=>b.created_at.localeCompare(a.created_at));},
  async submitReport(report){
    const previous=await localRead('reports',report.request_id);if(previous)return previous;
    const record={...report,id:report.request_id,created_at:now(),status:'open',shared:false,demo:true};
    await localWrite('reports',record);emit({type:'report',site_id:String(report.site_id),report:record});return record;
  },
  async readPreferences(id){return await localRead('preferences',String(id))||{site_id:String(id),enabled:false,local_time:'18:00',timezone:(await catalog()).find(s=>s.id===String(id))?.timezone||'',channels:['in_app'],next_run_at:null,delivery_status:'not_scheduled',demo:true};},
  async savePreferences(id,prefs){
    if(!timezoneValid(prefs.timezone))throw new Error('Choose a valid site timezone.');
    const record={...prefs,site_id:String(id),local_time:'18:00',next_run_at:prefs.enabled?nextSixPM(prefs.timezone):null,delivery_status:'demo_only',demo:true};
    await localWrite('preferences',record);emit({type:'briefing',site_id:String(id)});return record;
  },
  async listBriefings(id){const zone=(await catalog()).find(s=>s.id===String(id))?.timezone;const parts=zone?localParts(Date.now(),zone):null;const valid_date=parts?new Date(Date.UTC(parts.year,parts.month-1,parts.day+1)).toISOString().slice(0,10):'Sample next day — site timezone unverified';return [{id:'demo-next-day',site_id:String(id),title:'Tomorrow’s safety briefing',valid_date,generated_at:now(),delivery_status:'sample_not_sent',demo:true}];},
  async readBriefing(id,briefingId){
    if(briefingId!=='demo-next-day')throw new Error('Unknown sample briefing.');
    const p=await site(id),[meta]=await mockAPI.listBriefings(id);
    return {...meta,timezone:p.timezone,body:'Sample briefing: review heat breaks, lightning shelter, flood access, smoke exposure, saturated ground, and wildlife observations with your supervisor. These values are synthetic and are not a next-day forecast.',forecast:hazards.map(([key,name])=>({name,reading:p.hazards[key].reading,advice:p.hazards[key].advice})),sources:[demoSource],demo:true};
  }
};
