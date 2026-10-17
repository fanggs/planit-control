/* Frontend part 2
Commit: feat(crew): add authenticated backend connection adapters
Why: Keep authentication and configurable network contracts separate from the UI; a failed live request must never become a synthetic success.
*/
// UI boundary only. Alan/Aryan can map their agreed API into these shapes.
type Source = {source_name?:string;source_url?:string|null;retrieved_at?:string};
type LightningAlert = {site_id:string;version:number;status:'hold'|'cleared'|'unknown';all_clear_at:string|null;last_strike_at?:string;distance_miles?:number};
type HazardKey = 'weather'|'heat'|'lightning'|'flood'|'wildfire'|'soil'|'wildlife';
type Hazard = Source & {reading:string|null;severity:'lower'|'elevated'|'high'|'unknown';advice?:string;observed_at:string|null};
type Factor = Source & {name:string;contribution:number|null;unit:string;reading?:string};
type SiteSummary = {id:string;name:string;state:string;latitude:number;longitude:number;score:number|null;score_updated_at?:string;operator?:string;provenance?:Source};
type Site = SiteSummary & {revision:number;server_time:string;timezone:string|null;hazards:Partial<Record<HazardKey,Hazard>>;alert:LightningAlert;score_method?:string;baseline?:number;factors:Factor[];model?:{name?:string;version?:string;training_period?:string;trained_at?:string|null;evaluation?:string};flood?:Source & {status:'normal'|'warning'|'unknown';message?:string;river_name?:string|null;river_distance_miles?:number|null;overnight_rain_mm?:number|null;window_label?:string;observed_at?:string;rule_description?:string}};
type ReportInput = {site_id:string;request_id:string;category:string;severity:'low'|'medium'|'high';description:string;latitude:number;longitude:number;photo:File};
type Report = {id:string;site_id:string;category:string;description:string;latitude:number;longitude:number;created_at:string;status:'open'|'resolved'|'archived';photo_url?:string;shared?:boolean};
type BriefingSummary = {id:string;site_id:string;title:string;valid_date:string;generated_at:string;delivery_status:string};
type Briefing = BriefingSummary & {timezone:string|null;body:string;forecast:{name:string;reading:string|null;advice?:string}[];sources:Source[]};
type Preferences = {site_id:string;enabled:boolean;local_time:'18:00';timezone:string;channels:('in_app'|'email')[];email?:string|null;next_run_at:string|null;delivery_status:string};
type StreamEvent = {type:'heartbeat'|'site'|'alert'|'report'|'briefing';site_id?:string;server_time?:string;site?:Site;alert?:LightningAlert;report?:Report};
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
declare global {interface Window {PlanITCrewAPI?:PlanITCrewAPI;}}
export {Site,SiteSummary,LightningAlert,Hazard,Report,ReportInput,Briefing,Preferences,StreamEvent,PlanITCrewAPI};
