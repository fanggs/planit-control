import {safeURL} from './crew-ui.js';

const EXAMPLES = [
  'Which plants have the highest heat index forecast tomorrow?',
  'What is the strongest wind forecast in the next 24 hours, and where?',
  'Which 3 plants have the highest prototype screening score right now?',
  'Are there any active lightning alerts?'
];

export const shouldSubmitAskOnKey = event => event.key === 'Enter' && !event.shiftKey
  && !event.isComposing && !event.repeat;

// Mounts inside the existing authenticated crew workspace. No question, SQL,
// or answer is treated as HTML; the API is the only source of live answers.
export function mountAsk(root, ask, {sample = false} = {}) {
  root.innerHTML = `<section class="crew-card crew-ask" aria-labelledby="crew-ask-title">
    <p class="crew-eyebrow">ASK THE AVAILABLE DATA</p><h2 id="crew-ask-title">What would you like to know?</h2>
    <p class="crew-muted">Questions use the monitored-site database. Answers are not safety clearance; verify site alerts and source times before field decisions.</p>
    <form id="crew-ask-form"><label for="crew-ask-question">Your question</label>
      <textarea id="crew-ask-question" rows="3" minlength="3" maxlength="500" placeholder="Which sites have active lightning alerts?"></textarea>
      <small>Press Enter to ask; Shift+Enter adds a new line.</small>
      <button class="crew-button" type="submit">Ask data</button></form>
    <p id="crew-ask-status" role="status" aria-live="polite"></p>
    <div id="crew-ask-examples" class="crew-ask-examples"><strong>Try a question</strong></div>
    <div id="crew-ask-result" aria-live="polite"></div></section>`;
  const doc=root.ownerDocument,form=root.querySelector('#crew-ask-form'),question=root.querySelector('#crew-ask-question');
  const status=root.querySelector('#crew-ask-status'),result=root.querySelector('#crew-ask-result');
  const examples=root.querySelector('#crew-ask-examples'),submit=form.querySelector('button');
  let alive=true,busy=false;
  function element(tag,text){const node=doc.createElement(tag);if(text!=null)node.textContent=text;return node;}
  function setBusy(value){busy=value;question.disabled=value||sample;submit.disabled=value||sample;
    for(const button of examples.querySelectorAll('button'))button.disabled=value||sample;
    form.setAttribute('aria-busy',String(value));}
  for(const value of EXAMPLES){const button=element('button',value);button.type='button';button.className='crew-link';
    button.addEventListener('click',()=>{question.value=value;question.focus();});examples.append(button);}
  setBusy(false);
  if(sample){status.textContent='Questions require live data. Sample mode does not call Gemini.';return ()=>{alive=false;};}
  status.textContent='Ready for a question about monitored plants, forecasts, alerts, or prototype screening.';
  question.addEventListener('keydown',event=>{
    if(shouldSubmitAskOnKey(event)){
      event.preventDefault();form.requestSubmit();
    }
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!alive||busy)return;
    const value=question.value.trim();result.replaceChildren();
    if(value.length<3||value.length>500){status.textContent='Enter a question between 3 and 500 characters.';question.focus();return;}
    setBusy(true);status.textContent='Checking the available records…';
    try{
      const answer=await ask(value);if(!alive)return;
      if(answer?.answer===null&&answer.reason==='cannot_answer'){
        result.append(element('p','That question cannot be answered from the available data. Try a question about sites, weather, alerts, or screening.'));
        status.textContent='No answer from the available data.';return;
      }
      if(typeof answer?.answer!=='string'||typeof answer.sql!=='string'||!Array.isArray(answer.sources))throw new Error('The question service returned an invalid answer.');
      result.append(element('h3','Answer'),element('p',answer.answer));
      const sources=element('div');sources.className='crew-ask-sources';sources.append(element('h4','Sources'));
      for(const source of answer.sources){const url=safeURL(source?.url);const label=String(source?.label||'Source');
        if(url){const link=element('a',label+' ↗');link.href=url;link.target='_blank';link.rel='noopener noreferrer';sources.append(link);}
        else sources.append(element('span',label));}
      result.append(sources);
      const query=element('details'),summary=element('summary','How we got this'),sql=element('pre',answer.sql);
      query.append(summary,sql);result.append(query);status.textContent='Answer loaded. Review its sources and query.';
    }catch(error){if(alive)status.textContent=error?.status===503?'Questions are unavailable right now. Try again later.':error?.message||'Questions are unavailable right now.';}
    finally{if(alive)setBusy(false);}
  });
  return ()=>{alive=false;};
}
