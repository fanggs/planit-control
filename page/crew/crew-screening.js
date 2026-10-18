// Contract v1.2 model output. This module never determines or clears an alert.
const shownStatuses=new Set(['research','validated_prototype']);
const unavailableStatuses=new Set(['no_data','stale','invalid','research_unapproved']);
const number=value=>typeof value==='number'&&Number.isFinite(value);
const stamp=value=>typeof value==='string'&&Number.isFinite(Date.parse(value))?value:null;
const twoHours=2*60*60*1000;
// Same wording as the supervisor dashboard (page/supervisor/domain.js).
export const FEATURE_LABELS=Object.freeze({
  temperature_max_f:'Maximum temperature',temperature_min_f:'Minimum temperature',
  humidity_mean_pct:'Average humidity',humidity_min_pct:'Minimum humidity',wind_max_mph:'Maximum wind',
  rain_max_1h_in:'Peak hourly rain',rain_total_24h_in:'24-hour rain',heat_index_max_f:'Maximum heat index',
  heat_index_max_f_missing:'Heat index not available',
  antecedent_forecast_rain_24h_in:'Previous 24-hour forecast rain',
  antecedent_forecast_rain_72h_in:'Previous 72-hour forecast rain',
  antecedent_forecast_rain_168h_in:'Previous 7-day forecast rain',
  latitude:'Latitude',longitude:'Longitude',elevation_m:'Elevation',
  month_sin:'Season (sine)',month_cos:'Season (cosine)',hour_sin:'Hour (sine)',hour_cos:'Hour (cosine)',
  soil_moisture:'Soil moisture'
});
export function featureLabel(feature){
  if(typeof feature!=='string'||!feature.trim()||feature.length>100)throw new Error('Invalid model feature.');
  return Object.hasOwn(FEATURE_LABELS,feature)?FEATURE_LABELS[feature]:feature.replace(/_/g,' ').replace(/^./,s=>s.toUpperCase());
}
export function screeningFactors(rows){
  if(!Array.isArray(rows))throw new Error('Screening factors must be a list.');
  return rows.map(f=>{
    if(!number(f?.contribution))throw new Error('Invalid screening contribution.');
    return {feature:f.feature,name:featureLabel(f.feature),contribution:f.contribution,unit:'score_points'};
  });
}
function unavailable(status,reason){
  return {score:null,baseline:null,factors:[],score_status:status,score_reason:reason,score_reconciles:false,
    score_updated_at:null,captured_at:null,valid_from:null,valid_until:null,score_target:null,clears_stop_work:false};
}
function freshness(value,now,{summary=false}={}){
  const scored=Date.parse(value.scored_at??value.score_updated_at),captured=Date.parse(value.captured_at);
  if(!Number.isFinite(scored)||scored>now)return 'invalid';
  if(Number.isFinite(captured)){
    if(captured>now||scored<captured)return 'invalid';
    if(now-captured>twoHours)return 'stale';
  }else if(!summary)return 'invalid';
  if(now-scored>twoHours)return 'stale';
  const start=Date.parse(value.valid_from),end=Date.parse(value.valid_until);
  if(Number.isFinite(start)&&Number.isFinite(end)){
    if(end<=start)return 'invalid';
    if(now>=end)return 'stale';
  }else if(!summary||value.valid_from!=null||value.valid_until!=null)return 'invalid';
  return null;
}
export function screeningSummary(raw,now=Date.now(),{requireFactors=false}={}){
  const status=raw.score_status;
  if(unavailableStatuses.has(status))return unavailable(status,raw.reason||raw.score_reason||'Screening index unavailable.');
  if(!shownStatuses.has(status))return unavailable('invalid','Screening status was not recognized.');
  if(!number(raw.score)||raw.score<0||raw.score>10)return unavailable('invalid','Screening score is invalid.');
  if(requireFactors){
    try{if(!screeningFactors(raw.top_factors).length)return unavailable('invalid','Screening explanation is unavailable.');}
    catch{return unavailable('invalid','Screening explanation is invalid.');}
  }
  const problem=freshness(raw,now,{summary:true});
  if(problem)return unavailable(problem,problem==='stale'?'Screening inputs or forecast window are out of date.':'Screening timestamps are incomplete or invalid.');
  return {score:raw.score,score_status:status,score_reason:null,score_updated_at:stamp(raw.scored_at??raw.score_updated_at),
    captured_at:stamp(raw.captured_at),valid_from:stamp(raw.valid_from),valid_until:stamp(raw.valid_until),
    score_target:raw.target??raw.score_target??null,clears_stop_work:false};
}
export function screeningDetail(raw,now=Date.now()){
  if(!raw||typeof raw!=='object')return unavailable('no_data','No screening prediction was supplied.');
  if(unavailableStatuses.has(raw.status))return unavailable(raw.status,raw.reason||'Screening index unavailable.');
  const summary=screeningSummary({...raw,score_status:raw.status},now);
  if(summary.score===null)return summary;
  if(freshness(raw,now)||raw.clears_stop_work!==false||typeof raw.target!=='string'||!raw.target.trim())return unavailable('invalid','Screening metadata is incomplete or invalid.');
  let factors;
  try{factors=screeningFactors(raw.factors);}catch{return unavailable('invalid','Screening explanation is invalid.');}
  if(!number(raw.baseline)||!factors.length||Math.abs(raw.baseline+factors.reduce((n,f)=>n+f.contribution,0)-raw.score)>1e-8)return unavailable('invalid','The explanation does not reconcile with the screening score.');
  return {...summary,baseline:raw.baseline,factors,score_reconciles:true,artifact_sha256:raw.artifact_sha256??null,snapshot_id:raw.snapshot_id??null};
}
// Expire cached predictions locally even when notifications or API reads stop.
export function expireScreening(site,now=Date.now()){
  if(!site||!shownStatuses.has(site.score_status)||site.score===null)return site;
  const problem=freshness(site,now,{summary:true});
  return problem?{...site,...unavailable(problem,'Screening inputs or forecast window are out of date. Fetch a fresh prediction.')}:site;
}
export function scoreBadgeText(site){
  if(site?.demo||site?.sample||site?.score_status==='sample')return 'Sample score';
  if(shownStatuses.has(site?.score_status))return 'Prototype';
  if(site?.score_status==='legacy')return 'Legacy API score';
  return 'No data';
}
