import {siteParameter,workspaceURL} from './crew-routing.js';

// Mount either crew-owned workspace in this document. This preserves the
// verified Auth0 client and its memory-only token across the callback handoff.
export async function mountWorkspace(workspace,{baseURL,siteId,document,history,load=path=>import(path)}){
  const url=workspaceURL(workspace,baseURL),id=siteParameter(siteId);
  const filename=workspace==='supervisor'?'crew-supervisor':'crew';
  if(id)url.searchParams.set('site',id);
  document.title='PlanIT Control · '+(workspace==='supervisor'?'Supervisor':'Crew');
  document.getElementById('crew-access-root').id=filename+'-root';
  history.replaceState({},document.title,url);
  const app=await load('./'+filename+'.js');
  await app.ready;
}
