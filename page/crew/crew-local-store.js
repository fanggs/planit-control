/* Why: Allow reproducible local demos while keeping browser-only storage and synthetic conditions clearly distinct from the real backend. */
// Browser-only demonstration storage. This is not DeepSpace or the team's shared database.
let connection;
async function db(){
  if(!connection)connection=new Promise((resolve,reject)=>{
    const request=indexedDB.open('planit-crew-demo-v2',1);
    request.onupgradeneeded=()=>{request.result.createObjectStore('reports',{keyPath:'id'});request.result.createObjectStore('preferences',{keyPath:'site_id'});};
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(new Error('Local demo storage is unavailable. Enable browser storage to retain photos.'));
  });return connection;
}
export async function localRead(store,key){const database=await db();return new Promise((resolve,reject)=>{const request=database.transaction(store).objectStore(store)[key===undefined?'getAll':'get'](key);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});}
export async function localWrite(store,value){const database=await db();return new Promise((resolve,reject)=>{const transaction=database.transaction(store,'readwrite');transaction.objectStore(store).put(value);transaction.oncomplete=()=>resolve(value);transaction.onerror=()=>reject(new Error('Could not save locally. The browser may be out of storage.'));transaction.onabort=()=>reject(new Error('Local save was interrupted.'));});}
