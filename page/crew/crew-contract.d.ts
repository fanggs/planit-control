/* API DTOs follow api/CONTRACT.md v1.1. UI types below intentionally retain
   display aliases so contract changes do not leak into the screen components. */
export type HazardType = 'heat'|'lightning'|'flooding'|'wildfire'|'soil_saturation'|'wildlife'|'other';
type Source = {source_name?:string; source_url?:string|null; retrieved_at?:string|null};
export type APIFactor = {hazard_type:HazardType; contribution:number};
export type APIScore = {site_id:number; score:number; baseline:number; scored_at:string; horizon_hours:number; model_version:string; factors:APIFactor[]};
export type APIAlert = {id:number; site_id:number; hazard_type:HazardType; level:'warning'|'stop_work'; message:string; started_at:string; last_trigger_at:string|null; clear_at:string|null; trigger:{strike_id?:string; distance_mi?:number; report_id?:string; event_id?:number}};
export type APISiteSummary = {site_id:number; name:string; state:string; latitude:number; longitude:number; timezone:string; hazard_region:string; score:number|null; scored_at:string|null; top_factors:APIFactor[]|null; active_alert:Pick<APIAlert,'level'|'hazard_type'|'clear_at'>|null; open_report_count:number};
export type APIWeather = Source & {observed_at:string; temperature_f:number|null; heat_index_f:number|null; wind_mph:number|null; precip_1h_in:number|null; precip_24h_in:number|null; soil_moisture:number|null};
export type APIEnvironmentalEvent = Source & {id:number; hazard_type:HazardType; event_kind:string; title:string; severity:string|null; starts_at:string; ends_at:string|null};
export type APIReportCreate = {site_id:number; hazard_type:HazardType; severity:'low'|'medium'|'high'; description:string; latitude?:number|null; longitude?:number|null; photo_key?:string|null};
export type APIReport = APIReportCreate & {id:string; reporter_id:string; status:'open'|'resolved'; created_at:string; resolved_at:string|null; resolved_by:string|null};
export type APISiteDetail = {site_id:number; name:string; utility:string; state:string; county:string; latitude:number; longitude:number; timezone:string; plant_type:string; hazard_region:string; latest_weather:APIWeather|null; score:APIScore|null; active_alerts:APIAlert[]; environmental_events:APIEnvironmentalEvent[]; recent_reports:APIReport[]};
export type APIBriefing = {site_id:number; for_date:string; generated_at:string; text:string; inputs:{forecast_valid_from:string; score_scored_at:string}};
export type APIError = {error:{code:string; message:string}};
export type ContractNotice =
  | {type:'alert.started'|'alert.cleared'; alert_id:number; site_id:number}
  | {type:'alert.updated'; alert_id:number; site_id:number; clear_at:string}
  | {type:'report.created'; report_id:string; site_id:number; created_at:string}
  | {type:'report.resolved'; report_id:string; site_id:number};

// UI-only types. revision/version are local request-order counters, not API fields.
type LightningAlert = {site_id:string; version:number; status:'hold'|'cleared'|'unknown'; all_clear_at:string|null; last_strike_at?:string|null; distance_miles?:number|null; contract_id?:number|string|null};
type HazardKey = 'weather'|'heat'|'lightning'|'flood'|'wildfire'|'soil'|'wildlife';
type Hazard = Source & {reading:string|null; severity:'lower'|'elevated'|'high'|'unknown'; advice?:string; observed_at:string|null};
type Factor = Source & {name:string; hazard_type?:HazardType; contribution:number|null; unit:string; reading?:string; scored_at?:string|null};
type SiteSummary = {id:string; name:string; state:string; latitude:number; longitude:number; score:number|null; score_updated_at?:string|null; operator?:string; provenance?:Source};
type Site = SiteSummary & {revision:number; server_time:string|null; timezone:string|null; hazards:Partial<Record<HazardKey,Hazard>>; alert:LightningAlert; active_alerts?:APIAlert[]; warnings?:APIAlert[]; score_method?:string; baseline?:number|null; score_reconciles?:boolean; horizon_hours?:number|null; factors:Factor[]; model?:{name?:string; version?:string; training_period?:string; trained_at?:string|null; evaluation?:string}; flood?:Source & {status:'normal'|'warning'|'unknown'; message?:string; river_name?:string|null; river_distance_miles?:number|null; overnight_rain_mm?:number|null; rainfall_label?:string; rainfall_reading?:string; window_label?:string; observed_at?:string|null; rule_description?:string}};
type ReportInput = {site_id:string; request_id:string; category:string; severity:'low'|'medium'|'high'; description:string; latitude?:number|null; longitude?:number|null; photo?:File|null};
type Report = {id:string; site_id:string; category:string; hazard_type?:HazardType; severity?:'low'|'medium'|'high'; description:string; latitude:number|null; longitude:number|null; created_at:string; status:'open'|'resolved'; photo_key?:string|null; photo?:Blob; photo_error?:string; photo_url?:string; shared?:boolean; demo?:boolean};
type BriefingSummary = {id:string; site_id:string; title:string; valid_date:string; generated_at:string; delivery_status:string|null};
type Briefing = BriefingSummary & {timezone:string|null; body:string; forecast:{name:string; reading:string|null; advice?:string}[]; sources:Source[]; inputs?:APIBriefing['inputs']};
// Retained for postponed functionality and local storage; not API v1.1 endpoints.
type Preferences = {site_id:string; enabled:boolean; local_time:'18:00'; timezone:string; channels:('in_app'|'email')[]; email?:string|null; next_run_at:string|null; delivery_status:string};
type StreamEvent = {type:'heartbeat'|'site'|'alert'|'report'|'briefing'; site_id?:string; server_time?:string; site?:Site; alert?:LightningAlert; report?:Report};
type AuthOptions = {accessToken:string};
interface PlanITCrewAPI {
  listSites(options?:AuthOptions):Promise<SiteSummary[]>;
  readSite(id:string,options?:AuthOptions):Promise<Site>;
  listReports(id:string,options?:AuthOptions):Promise<Report[]>;
  submitReport(report:ReportInput,options?:AuthOptions):Promise<Report>;
  listBriefings(id:string,options?:AuthOptions):Promise<BriefingSummary[]>;
  readBriefing(id:string,briefingId:string,options?:AuthOptions):Promise<Briefing>;
  readPreferences(id:string,options?:AuthOptions):Promise<Preferences>;
  savePreferences(id:string,value:Pick<Preferences,'enabled'|'local_time'|'timezone'|'channels'|'email'>,options?:AuthOptions):Promise<Preferences>;
  subscribeEvents(siteId:string|null,onEvent:(event:StreamEvent)=>void,onConnection:(connected:boolean)=>void,options?:AuthOptions):Promise<()=>void>|(()=>void);
}
interface PlanITCrewRealtime {
  subscribe(options:{site_id:number|null; accessToken:string; onEvent:(notice:ContractNotice)=>void; onConnection:(connected:boolean)=>void; onError:(error?:unknown)=>void}):Promise<()=>void>|(()=>void);
}
declare global {interface Window {PlanITCrewAPI?:PlanITCrewAPI; PlanITCrewRealtime?:PlanITCrewRealtime;}}
export {Site,SiteSummary,LightningAlert,Hazard,Report,ReportInput,Briefing,Preferences,StreamEvent,PlanITCrewAPI,PlanITCrewRealtime};
