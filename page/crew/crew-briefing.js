/* Frontend part 5
Commit: feat(crew): add photo reporting and next-day briefing flows
Why: Confirm stored report receipts and preserve retry IDs; show site-local delivery preferences without pretending that a browser schedules server jobs.
*/
import {config} from './crew-config.js';
import {services} from './crew-services.js';
import {esc,dateLabel,sourceLink} from './crew-ui.js';
import {nextSixPM,timezoneValid} from './crew-domain.js';
export function mountBriefing(container,site,message){
  let disposed=false,detailVersion=0;
  container.innerHTML='<section class="crew-card"><h1>Next-day briefing</h1><p>Loading the latest briefing…</p></section>';
  async function start(){
    try{
      const preferencesEnabled=config.features.briefingPreferences;
      const [history,prefs]=await Promise.all([services.listBriefings(site.id),preferencesEnabled?services.readPreferences(site.id):Promise.resolve(null)]);if(disposed)return;
      if(!Array.isArray(history)||(preferencesEnabled&&String(prefs?.site_id)!==String(site.id)))throw new Error('Briefing data did not match the selected site.');
      const zones=[...new Set(['',prefs?.timezone||'',site.timezone||'','America/New_York','America/Chicago','America/Denver','America/Phoenix','America/Los_Angeles','America/Anchorage','Pacific/Honolulu','America/Puerto_Rico'])];
      container.innerHTML=`<div class="crew-section-heading crew-briefing-heading"><div><p class="crew-eyebrow">PLAN TOMORROW</p><h1>Next-day safety briefing</h1></div></div>
        ${preferencesEnabled?`<section class="crew-card"><h2>Every evening, 6 PM at this site</h2><p class="crew-muted">The report covers tomorrow’s hazards. Delivery is handled by the backend, even when this browser is closed.</p>
        <form id="crew-briefing-settings"><label class="crew-checkbox"><input id="crew-briefing-enabled" type="checkbox" ${prefs.enabled?'checked':''}><span>Receive the daily briefing</span></label>
        <label for="crew-timezone">Site timezone</label><select id="crew-timezone" required>${zones.map(z=>`<option value="${esc(z)}" ${z===prefs.timezone?'selected':''}>${esc(z||'Choose the site timezone')}</option>`).join('')}</select><small>Use the site’s timezone, which may differ from your phone’s. The backend must validate it.</small>
        <label class="crew-checkbox"><input id="crew-email-channel" type="checkbox" ${prefs.channels?.includes('email')?'checked':''}><span>Also deliver by email</span></label><label for="crew-email">Delivery email</label><input id="crew-email" type="email" maxlength="254" autocomplete="email" value="${esc(prefs.email||'')}" placeholder="you@example.com">
        <p id="crew-schedule-preview" class="crew-muted"></p><button class="crew-button" type="submit">Save delivery settings</button><p id="crew-schedule-receipt" role="status"></p></form>
        <small>${config.dataMode==='mock'?'Sample mode: saves preferences locally. No report is scheduled or sent.':'Delivery status comes from the server; saving settings does not confirm a sent report.'}</small></section>`:''}
        <section class="crew-card"><label for="crew-briefing-history">${config.features.briefingHistory?'Briefing history':'Latest briefing'}</label><select id="crew-briefing-history" ${config.features.briefingHistory?'':'hidden'}>${history.length?history.filter(b=>String(b.site_id)===String(site.id)).map(b=>`<option value="${esc(b.id)}">${esc(b.valid_date)} · ${esc(b.title)} · ${esc(b.delivery_status||'Delivery unavailable')}</option>`).join(''):'<option value="">No briefings yet</option>'}</select><div id="crew-briefing-detail"></div></section>`;
      const form=container.querySelector('form');
      if(form){const zone=container.querySelector('#crew-timezone'),enabled=container.querySelector('#crew-briefing-enabled'),emailChannel=container.querySelector('#crew-email-channel'),email=container.querySelector('#crew-email');
      const preview=()=>{email.disabled=!emailChannel.checked;email.required=emailChannel.checked;const next=enabled.checked?nextSixPM(zone.value):null;container.querySelector('#crew-schedule-preview').textContent=next?`Next 6 PM (preview): ${dateLabel(next,zone.value)} · ${zone.value}`:enabled.checked?'Choose a valid site timezone.':'Daily delivery is disabled.';};
      form.addEventListener('change',preview);preview();
      container.querySelector('#crew-schedule-receipt').textContent=`${config.dataMode==='mock'?'Local sample preference':'Server status'}: ${prefs.delivery_status||'unavailable'}. ${prefs.next_run_at?'Next run: '+dateLabel(prefs.next_run_at,prefs.timezone):''}`;
      form.addEventListener('submit',async event=>{
        event.preventDefault();const button=form.querySelector('button');button.disabled=true;
        try{
          if(!timezoneValid(zone.value))throw new Error('Choose a valid site timezone.');
          const result=await services.savePreferences(site.id,{enabled:enabled.checked,timezone:zone.value,local_time:'18:00',channels:emailChannel.checked?['in_app','email']:['in_app'],email:emailChannel.checked?email.value.trim():null});
          if(String(result?.site_id)!==String(site.id)||result.local_time!=='18:00')throw new Error('The server did not confirm the 6 PM settings for this site.');
          if(disposed)return;
          container.querySelector('#crew-schedule-receipt').textContent=config.dataMode==='mock'?'Sample preferences saved on this browser. No delivery job was created.':`Settings saved. Server delivery status: ${result.delivery_status||'unavailable'}. Next run: ${dateLabel(result.next_run_at,result.timezone)}.`;
        }catch(error){message(error.message);}finally{if(button.isConnected)button.disabled=false;}
      });
      }
      container.querySelector('#crew-briefing-history').addEventListener('change',event=>read(event.target.value));
      await read(container.querySelector('#crew-briefing-history').value);
    }catch(error){if(!disposed)container.innerHTML=`<section class="crew-card"><h1>Briefing unavailable</h1><p>${esc(error.message)}</p><button class="crew-button secondary" id="crew-retry-briefing">Try again</button></section>`;container.querySelector('#crew-retry-briefing')?.addEventListener('click',start);}
  }
  async function read(id){
    const version=++detailVersion,target=container.querySelector('#crew-briefing-detail');if(!id){target.textContent='No briefing has been generated for this site yet.';return;}
    target.innerHTML='<p>Loading briefing…</p>';
    try{const b=await services.readBriefing(site.id,id);if(disposed||version!==detailVersion)return;if(String(b?.site_id)!==String(site.id))throw new Error('This briefing belongs to a different site.');
      target.innerHTML=`<article><p class="crew-eyebrow">${esc(b.valid_date)}${b.delivery_status?' · '+esc(b.delivery_status):''}</p><h2>${esc(b.title)}</h2><p class="crew-briefing-text">${esc(b.body)}</p><div class="crew-hazard-grid">${(b.forecast||[]).map(f=>`<div class="crew-hazard"><h3>${esc(f.name)}</h3><strong>${esc(f.reading??'Unavailable')}</strong><p>${esc(f.advice)}</p></div>`).join('')}</div><h3>Evidence</h3>${b.sources?.length?b.sources.map(s=>`<p>${sourceLink(s)}</p>`).join(''):'<p>Source links were not included in this briefing.</p>'}${b.inputs?`<p class="crew-muted">Forecast valid from: ${dateLabel(b.inputs.forecast_valid_from,b.timezone||site.timezone)}<br>Score calculated: ${dateLabel(b.inputs.score_scored_at,b.timezone||site.timezone)}</p>`:''}<small>Generated: ${dateLabel(b.generated_at,b.timezone||site.timezone)} · ${esc(b.timezone||'Timezone unavailable')}</small><button class="crew-button secondary" id="crew-print-briefing">Print briefing</button></article>`;
      target.querySelector('button').addEventListener('click',()=>window.print());
    }catch(error){if(!disposed&&version===detailVersion)target.innerHTML=`<p class="crew-error" role="alert">${esc(error.message)}</p>`;}
  }
  start();return ()=>{disposed=true;detailVersion++;};
}
