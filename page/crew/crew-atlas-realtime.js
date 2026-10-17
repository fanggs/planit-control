import {atlasSummaries} from './crew-atlas-data.js';

// Bulk adapter events update the existing map without another API request.
// A custom provider may supply only an invalidation; coalesce those refetches.
export function watchAtlasScores({api,roster,onSites,onConnection,onError=()=>{}}){
  let alive=true,unsubscribe,version=0,working=false,pending=false;
  async function refresh(){
    if(working){pending=true;return;}
    working=true;
    do{
      pending=false;const current=++version;
      try{const sites=await api.listSites();if(alive&&current===version)onSites(atlasSummaries(roster,sites));}
      catch(error){if(alive&&current===version){onConnection(false);onError(error);}}
    }while(alive&&pending);
    working=false;
  }
  void Promise.resolve().then(()=>{
    if(!alive)return;
    return api.subscribeEvents(null,event=>{
      if(!alive||!['site','alert','report'].includes(event?.type))return;
      if(Array.isArray(event.sites)){version++;pending=false;onSites(atlasSummaries(roster,event.sites));}
      else void refresh();
    },connected=>{if(alive)onConnection(connected===true);});
  }).then(close=>{if(!alive){close?.();return;}unsubscribe=close;}).catch(error=>{if(alive){onConnection(false);onError(error);}});
  return()=>{alive=false;version++;pending=false;unsubscribe?.();unsubscribe=undefined;};
}
