/* Frontend part 5
Commit: feat(crew): add photo reporting and next-day briefing flows
Why: Confirm stored report receipts and preserve retry IDs; show site-local delivery preferences without pretending that a browser schedules server jobs.
*/
import {config} from './crew-config.js';
import {services} from './crew-services.js';
import {esc,dateLabel,safeURL,makeMap} from './crew-ui.js';
export function mountReports(container,site,message){
  let disposed=false,map,marker,photoURL,photoURLs=[],feedVersion=0,reportVersion=0;
  container.innerHTML=`<div class="crew-section-heading"><div><p class="crew-eyebrow">SHARED SITE MEMORY</p><h1>Crew hazard reports</h1></div><button class="crew-button" id="crew-new-report">+ Report a hazard</button></div><p class="crew-muted">${config.dataMode==='mock'?'Sample reports and photos are saved on this browser. Other tabs on the same browser receive updates; other devices do not.':'Reports from the team are stored for current and future crews. Delivery confirmation is supplied by the report service.'}</p><div id="crew-report-editor"></div><section class="crew-card"><div class="crew-row"><h2>Reports at this site</h2><button id="crew-reload-reports" class="crew-link">Refresh</button></div><label for="crew-report-filter">Show</label><select id="crew-report-filter"><option value="open">Open hazards</option><option value="all">All reports / site history</option><option value="archived">Resolved or archived</option></select><div id="crew-report-feed" aria-live="polite">Loading reports…</div></section>`;
  const editor=container.querySelector('#crew-report-editor'),feed=container.querySelector('#crew-report-feed');
  function cleanMap(){map?.remove();map=null;}
  function releasePhotos(){photoURLs.forEach(URL.revokeObjectURL);photoURLs=[];}
  async function refresh(){
    const version=++feedVersion;
    try{const rows=await services.listReports(site.id);if(disposed||version!==feedVersion)return;if(!Array.isArray(rows))throw new Error('Report service did not return a list.');
      const filter=container.querySelector('#crew-report-filter').value,matching=rows.filter(r=>String(r.site_id)===String(site.id)),reports=matching.filter(r=>filter==='all'||filter==='open'&&!['archived','resolved'].includes(r.status)||filter==='archived'&&['archived','resolved'].includes(r.status));
      releasePhotos();
      feed.innerHTML=reports.length?reports.map(r=>{
        let photo=safeURL(r.photo_url);if(r.photo instanceof Blob){photo=URL.createObjectURL(r.photo);photoURLs.push(photo);}
        return `<article class="crew-report-record">${photo?`<a href="${esc(photo)}" target="_blank" rel="noopener noreferrer"><img src="${esc(photo)}" alt="Crew-reported ${esc(r.category)} hazard" loading="lazy"></a>`:'<p class="crew-muted">Photo unavailable</p>'}<div><div class="crew-row"><h3>${esc(r.category)}</h3><span class="crew-pill">${esc(r.status||'Status unavailable')}</span></div><p>${esc(r.description)}</p><small>${dateLabel(r.created_at)} · ${esc(r.latitude)}, ${esc(r.longitude)}<br>${r.demo?'Stored locally · sample':r.shared===true?'Team sharing confirmed':'Stored report · team notification not confirmed'} · ID ${esc(r.id)}</small></div></article>`;
      }).join(''):'<p class="crew-empty">No reports in this view. Add the first observation for the next crew.</p>';
      if(!editor.querySelector('form')&&matching.length){
        cleanMap();const mapBox=document.createElement('div');mapBox.id='crew-reports-map';mapBox.className='crew-map';mapBox.setAttribute('aria-label','Reported hazard locations');feed.prepend(mapBox);map=makeMap(mapBox.id,[site.latitude,site.longitude],14);
        const points=[];for(const r of reports){if(!Number.isFinite(r.latitude)||!Number.isFinite(r.longitude)||!map)continue;const point=[r.latitude,r.longitude];points.push(point);const popup=document.createElement('div');popup.textContent=`${r.category}: ${r.description}`;L.circleMarker(point,{radius:8,color:'#173f32',fillOpacity:.8}).bindPopup(popup).addTo(map);}if(points.length)map?.fitBounds(points,{padding:[30,30],maxZoom:15});
      }
    }catch(error){if(!disposed&&version===feedVersion)feed.innerHTML=`<p class="crew-error" role="alert">${esc(error.message)} Use Refresh to retry.</p>`;}
  }
  function newReport(){
    reportVersion++;cleanMap();if(photoURL)URL.revokeObjectURL(photoURL);photoURL=null;
    editor.innerHTML=`<section class="crew-card"><div class="crew-row"><h2>Report what you see</h2><button class="crew-link" id="crew-cancel-report">Cancel</button></div><form id="crew-report-form"><label for="crew-photo">Hazard photo</label><input id="crew-photo" name="photo" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" required><small>JPEG, PNG or WebP, up to 8 MB. Supported phones can open the rear camera.</small><img id="crew-photo-preview" alt="Your selected hazard photo" hidden><label for="crew-category">Hazard type</label><select id="crew-category" name="category">${['Wildlife','Flooding / standing water','Soil / access','Weather','Heat','Lightning','Wildfire / smoke','Other'].map(v=>`<option>${v}</option>`).join('')}</select><label for="crew-severity">How severe is the hazard?</label><select id="crew-severity" name="severity" required><option value="">Choose severity</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select><label for="crew-description">What should the next crew know?</label><textarea id="crew-description" name="description" rows="3" maxlength="1500" required placeholder="Describe the hazard and how to find it."></textarea><label>Pin the location</label><p class="crew-muted">Tap the map, drag the pin, or enter coordinates below.</p><div id="crew-pin-map" class="crew-map" aria-label="Hazard location map"></div><p id="crew-pin-map-status" role="status"></p><div class="crew-coordinate-row"><div><label for="crew-lat">Latitude</label><input id="crew-lat" name="latitude" type="number" min="-90" max="90" step="any" required value="${site.latitude}"></div><div><label for="crew-lng">Longitude</label><input id="crew-lng" name="longitude" type="number" min="-180" max="180" step="any" required value="${site.longitude}"></div></div><label class="crew-checkbox"><input type="checkbox" required><span>I checked the photo, description and map pin.</span></label><button class="crew-button" id="crew-submit" type="submit">${config.dataMode==='mock'?'Save sample report':'Submit to crew'}</button><p id="crew-upload-status" role="status"></p></form></section>`;
    const form=editor.querySelector('form'),file=editor.querySelector('#crew-photo'),preview=editor.querySelector('#crew-photo-preview');
    file.addEventListener('change',()=>{if(photoURL)URL.revokeObjectURL(photoURL);preview.hidden=true;const photo=file.files[0];if(!photo)return;if(!['image/jpeg','image/png','image/webp'].includes(photo.type)||photo.size>8*1024*1024){file.value='';message('Choose JPEG, PNG or WebP up to 8 MB.');return;}photoURL=URL.createObjectURL(photo);preview.src=photoURL;preview.hidden=false;});
    map=makeMap('crew-pin-map',[site.latitude,site.longitude]);
    if(map){const icon=L.divIcon({className:'crew-location-pin',html:'<span><b>!</b></span>',iconSize:[32,40],iconAnchor:[16,40]});marker=L.marker([site.latitude,site.longitude],{draggable:true,icon,title:'Hazard location; drag to move'}).addTo(map);map.on('click',e=>setPin(e.latlng.lat,e.latlng.lng));marker.on('dragend',()=>{const point=marker.getLatLng();setPin(point.lat,point.lng);});}
    else editor.querySelector('#crew-pin-map-status').textContent='Map unavailable. Use latitude and longitude to place the pin.';
    function setPin(lat,lng){marker?.setLatLng([lat,lng]);editor.querySelector('#crew-lat').value=lat.toFixed(6);editor.querySelector('#crew-lng').value=lng.toFixed(6);editor.querySelector('#crew-pin-map-status').textContent=`Pin: ${lat.toFixed(6)}, ${lng.toFixed(6)}`;}
    for(const id of ['crew-lat','crew-lng'])editor.querySelector('#'+id).addEventListener('change',()=>{const lat=Number(editor.querySelector('#crew-lat').value),lng=Number(editor.querySelector('#crew-lng').value);if(Number.isFinite(lat)&&Number.isFinite(lng)&&Math.abs(lat)<=90&&Math.abs(lng)<=180){setPin(lat,lng);map?.panTo([lat,lng]);}});
    editor.querySelector('#crew-cancel-report').addEventListener('click',()=>{reportVersion++;cleanMap();editor.innerHTML='';refresh();});
    const requestId=crypto.randomUUID(),version=reportVersion;
    form.addEventListener('submit',async event=>{
      event.preventDefault();const button=form.querySelector('#crew-submit');button.disabled=true;editor.querySelector('#crew-upload-status').textContent=config.dataMode==='mock'?'Saving photo and report locally…':'Uploading photo and saving report…';
      try{const data=new FormData(form),description=String(data.get('description')).trim(),latitude=Number(data.get('latitude')),longitude=Number(data.get('longitude')),photo=file.files[0];
        if(!description||!photo||!['image/jpeg','image/png','image/webp'].includes(photo.type)||photo.size>8*1024*1024||!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180)throw new Error('Check the photo, description and coordinates.');
        const receipt=await services.submitReport({site_id:site.id,category:data.get('category'),description,latitude,longitude,photo,severity:data.get('severity'),request_id:requestId});
        if(!receipt?.id||String(receipt.site_id)!==String(site.id))throw new Error('The service did not confirm a stored report for this site. Retry with this form.');
        if(disposed||version!==reportVersion){message('Report saved for '+site.name+'.');return;}
        cleanMap();if(photoURL)URL.revokeObjectURL(photoURL);photoURL=null;
        editor.innerHTML=`<section class="crew-card"><p class="crew-eyebrow">${config.dataMode==='mock'?'SAMPLE SAVED LOCALLY':'REPORT STORED'}</p><h2>${config.dataMode==='mock'?'Your photo and pin are saved on this browser.':'Your report was received.'}</h2><p>${config.dataMode==='mock'?'No upload to the team or other devices occurred.':receipt.shared===true?'The service confirmed team sharing.':'The report is stored. Team notification has not been confirmed.'}</p><small>Report ID: ${esc(receipt.id)}</small></section>`;await refresh();
      }catch(error){if(!disposed&&version===reportVersion){editor.querySelector('#crew-upload-status').textContent=error.message;button.disabled=false;}else message(error.message);}
    });
    file.focus();
  }
  container.querySelector('#crew-new-report').addEventListener('click',newReport);container.querySelector('#crew-reload-reports').addEventListener('click',refresh);container.querySelector('#crew-report-filter').addEventListener('change',refresh);refresh();
  return {refresh,destroy(){disposed=true;feedVersion++;reportVersion++;cleanMap();releasePhotos();if(photoURL)URL.revokeObjectURL(photoURL);}};
}
