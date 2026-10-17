// Compatibility entry for old bookmarks and the Auth0 supervisor handoff.
// Keep this document alive so the authenticated SDK retains its memory-only token.
async function openPrimaryMap(){
  const response=await fetch(new URL('crew-atlas.html',import.meta.url));
  if(!response.ok)throw new Error('The site map could not be loaded. Please reload.');
  const page=new DOMParser().parseFromString(await response.text(),'text/html');
  const css=document.createElement('link');css.rel='stylesheet';css.href=new URL('crew-atlas.css',import.meta.url).href;
  await new Promise((resolve,reject)=>{css.onload=resolve;css.onerror=()=>reject(new Error('Map styles could not be loaded.'));document.head.append(css);});
  document.title=page.title;document.body.className=page.body.className;
  document.body.replaceChildren(...page.body.childNodes);
  const url=new URL('crew-atlas.html',location.href);url.search=location.search;
  history.replaceState({},document.title,url);
  await import('./crew-atlas.js');
}
openPrimaryMap().catch(error=>{const message=document.createElement('p');message.textContent=error.message;message.setAttribute('role','alert');document.body.append(message);});
