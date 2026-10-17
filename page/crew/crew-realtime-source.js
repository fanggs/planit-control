// Load Alan's shared listener only when live HTTP mode subscribes. Demo mode
// never imports it or opens a WebSocket. These settings are public identifiers.
export function createCrewRealtimeProvider(settings,{loadSource=()=>import('../realtime/deepspace-source.js'),getBrowser=()=>globalThis.window}={}){
  let pending;
  return async()=>{
    const override=settings.realtimeSource||getBrowser()?.PlanITCrewRealtime;
    if(override)return override;
    const {baseURL,appId}=settings.realtime||{};
    if(!baseURL||!appId)throw new Error('The DeepSpace listener needs a public URL and app ID.');
    pending??=Promise.resolve().then(loadSource).then(module=>module.createDeepSpaceSource({baseURL,appId,...(settings.realtime.WebSocketImpl?{WebSocketImpl:settings.realtime.WebSocketImpl}:{})}));
    const attempt=pending;
    try{return await attempt;}catch(error){if(pending===attempt)pending=undefined;throw error;}
  };
}
