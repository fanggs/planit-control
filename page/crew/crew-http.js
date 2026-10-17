/* Frontend part 2
Commit: feat(crew): add authenticated backend connection adapters
Why: Keep authentication and configurable network contracts separate from the UI; a failed live request must never become a synthetic success.
*/
// Proposed HTTP adapter. Routes are configurable, not an assertion about the team's API.
export function createSSEDecoder(emit){
  let buffer='';
  return chunk=>{
    buffer+=chunk;
    let match;
    while((match=/\r?\n\r?\n/.exec(buffer))){
      const block=buffer.slice(0,match.index);buffer=buffer.slice(match.index+match[0].length);
      const lines=block.split(/\r?\n/),data=lines.filter(l=>l.startsWith('data:')).map(l=>l.slice(5).replace(/^ /,'')).join('\n');
      if(!data)continue;
      const event=lines.find(l=>l.startsWith('event:'))?.slice(6).trim();
      try{const payload=JSON.parse(data);emit({...payload,type:payload.type||event});}catch{/* Invalid data does not count as a heartbeat. */}
    }
  };
}
export function createHTTPAPI(settings,getToken,fetcher=fetch){
  function url(route,params={},query={}){
    if(!settings.baseURL)throw new Error('Set config.api.baseURL before using live HTTP mode.');
    const path=settings.routes[route]?.replace(/\{(\w+)\}/g,(_,key)=>encodeURIComponent(params[key]??''));
    if(!path)throw new Error(`Missing API route: ${route}`);
    const base=new URL(settings.baseURL.endsWith('/')?settings.baseURL:settings.baseURL+'/');
    const result=new URL(path.replace(/^\//,''),base);
    for(const [key,value] of Object.entries(query))if(value!==null&&value!==undefined)result.searchParams.set(key,value);
    return result;
  }
  async function request(route,{params,query,method='GET',body}={}){
    const token=await getToken(),controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),settings.timeoutMs||20000);
    try{
      const headers={Accept:'application/json',Authorization:`Bearer ${token}`};
      if(body&&!(body instanceof FormData))headers['Content-Type']='application/json';
      const response=await fetcher(url(route,params,query),{method,headers,body:body instanceof FormData?body:body?JSON.stringify(body):undefined,signal:controller.signal,cache:'no-store'});
      if(!response.ok)throw new Error(response.status===401?'Your session expired. Sign out and sign in again.':response.status===403?'Your account does not have permission for this action.':`Service request failed (${response.status}). Try again.`);
      return response.status===204?null:await response.json();
    }catch(error){if(error.name==='AbortError')throw new Error('The request timed out. Your report form has been kept; retry uses the same request ID.');throw error;}finally{clearTimeout(timer);}
  }
  async function list(route,options={}){
    let items=[],cursor,seen=new Set();
    do{const result=await request(route,{...options,query:{...options.query,limit:1000,...(cursor?{cursor}:{})}});
      if(Array.isArray(result))return items.concat(result);
      if(!Array.isArray(result?.items))throw new Error('Expected an array or {items, next_cursor} from the service.');
      items.push(...result.items);cursor=result.next_cursor;
      if(cursor&&seen.has(cursor))throw new Error('The service returned a repeated page cursor.');
      seen.add(cursor);
    }while(cursor);return items;
  }
  function subscribeEvents(siteId,onEvent,onConnection){
    let stopped=false,controller,retry,watchdog,attempt=0,lastSeen=Date.now();
    function watch(){clearInterval(watchdog);watchdog=setInterval(()=>{if(Date.now()-lastSeen>(settings.heartbeatMs||45000)){onConnection(false);controller?.abort();}},5000);}
    async function connect(){
      if(stopped)return;
      controller=new AbortController();lastSeen=Date.now();watch();onConnection(false);
      try{
        const token=await getToken();if(stopped)return;
        const response=await fetcher(url('events',{},siteId?{site_id:siteId}:{}),{headers:{Accept:'text/event-stream',Authorization:`Bearer ${token}`},signal:controller.signal,cache:'no-store'});
        if(!response.ok||!response.body||!response.headers.get('content-type')?.includes('text/event-stream'))throw new Error('Alert stream unavailable');
        const reader=response.body.getReader(),decoder=new TextDecoder();
        const parse=createSSEDecoder(event=>{if(stopped)return;if(!['heartbeat','site','alert','report','briefing'].includes(event.type))return;lastSeen=Date.now();attempt=0;onConnection(true);onEvent(event);});
        while(!stopped){const {done,value}=await reader.read();if(done)break;parse(decoder.decode(value,{stream:true}));}
      }catch{/* Reconnect with a new token; UI stays explicitly disconnected. */}
      finally{clearInterval(watchdog);if(!stopped){onConnection(false);retry=setTimeout(connect,Math.min(30000,1000*2**Math.min(attempt++,5)));}}
    }
    connect();return ()=>{stopped=true;controller?.abort();clearTimeout(retry);clearInterval(watchdog);};
  }
  return {
    listSites:()=>list('sites'), readSite:id=>request('site',{params:{id}}),
    listReports:id=>list('reports',{query:{site_id:id}}),
    submitReport:report=>{const form=new FormData();for(const [key,value] of Object.entries(report))if(value!==null&&value!==undefined)form.append(key,value);return request('reports',{method:'POST',body:form});},
    listBriefings:id=>list('briefings',{params:{id}}),
    readBriefing:(id,briefing_id)=>request('briefing',{params:{id,briefing_id}}),
    readPreferences:id=>request('preferences',{params:{id}}),
    savePreferences:(id,body)=>request('preferences',{params:{id},method:'PUT',body}),
    subscribeEvents
  };
}
