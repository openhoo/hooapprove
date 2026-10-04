const $ = id => document.getElementById(id);
let me, items = [], history = false, busy = false;
const labels = {pending:'Wartet auf dich',approved:'Freigegeben',executing:'Wird ausgeführt',completed:'Abgeschlossen',rejected:'Abgelehnt',expired:'Abgelaufen',cancelled:'Zurückgezogen',failed:'Fehlgeschlagen',uncertain:'Ergebnis unklar'};
const events = {requested:'Anfrage eingegangen',approved:'Von dir freigegeben',rejected:'Von dir abgelehnt',claimed:'Ausführung gestartet',completed:'Ausführung abgeschlossen',failed:'Ausführung fehlgeschlagen',uncertain:'Ergebnis muss geprüft werden',expired:'Freigabe abgelaufen',cancelled:'Anfrage zurückgezogen'};
const node = (tag, text, cls) => {const n=document.createElement(tag); if(text)n.textContent=text;if(cls)n.className=cls;return n;};
function message(text, error=false){$(error?'error':'notice').textContent=text;$(error?'error':'notice').hidden=false;}
async function api(path, body, method='POST'){
  const response=await fetch(path,{method:body===undefined?'GET':method,headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':me?.csrf||''},body:body===undefined?undefined:JSON.stringify(body)});
  if(response.status===401){$('workspace').hidden=true;$('login').hidden=false;throw Error('Bitte melde dich erneut an.');}
  if(!response.ok)throw Error(response.status===409?'Diese Anfrage hat sich geändert oder ist nicht mehr verfügbar. Bitte aktualisieren.':'Die Anfrage konnte nicht verarbeitet werden. Bitte versuche es erneut.');
  return response.json();
}
async function reload(){if(busy)return;try{items=await api('/api/requests');render();}catch(e){message(e.message,true);}}
function render(){
  $('count').textContent=items.filter(x=>x.status==='pending').length;
  $('pending-tab').classList.toggle('active',!history);$('history-tab').classList.toggle('active',history);
  const list=items.filter(x=>history?x.status!=='pending':x.status==='pending');const area=$('requests');area.replaceChildren();
  if(!list.length){const empty=node('div',null,'empty');empty.append(node('div','✓','symbol'),node('h2',history?'Noch keine Entscheidungen.':'Alles erledigt.'),node('p',history?'Deine Freigaben und ihre Ergebnisse erscheinen hier.':'Sobald ein Agent deine Freigabe braucht, findest du die Anfrage hier.'));area.append(empty);}
  for(const item of list){
    const card=node('article',null,'card');const top=node('div',null,'card-top');const service=node('div',null,'service');service.append(node('span','↗','service-icon'),node('span',item.service));top.append(service,node('span',labels[item.status],'badge'+(item.status!=='pending'?' finished':'')));
    card.append(top,node('h2',item.title),node('p',item.summary));const dl=node('dl',null,'details');
    for(const detail of item.details){const row=node('div',null,'detail');row.append(node('dt',detail.label),node('dd',detail.value));dl.append(row);}card.append(dl);
    const remaining=Math.max(0,Math.ceil((item.expires-Date.now()/1000)/60));const digest=node('div',null,'digest');digest.append(node('span','Aktion '+item.digest.slice(0,12)),node('span',item.status==='pending'?`Noch ${remaining} Min.`:labels[item.status]));card.append(digest);
    if(item.status==='pending'){
      const slide=node('div',null,'slide');const label=node('label','Zur Freigabe nach rechts schieben →');label.htmlFor='slide-'+item.id;const input=node('input');Object.assign(input,{type:'range',min:'0',max:'100',value:'0',id:label.htmlFor});input.setAttribute('aria-valuetext','Noch nicht freigegeben');
      input.addEventListener('input',()=>input.setAttribute('aria-valuetext',`${input.value} Prozent`));
      input.addEventListener('change',()=>{if(Number(input.value)>=96)decide(item,'approve');else input.value=0;});
      slide.append(label,input,node('small','Du gibst ausschließlich die oben gezeigte Aktion frei.'));
      const reject=node('button','Anfrage ablehnen','reject');reject.onclick=()=>decide(item,'reject');card.append(slide,reject);
    } else {const toggle=node('button','Entscheidungsverlauf anzeigen ↓','event-toggle');toggle.onclick=async()=>{try{const list=await api(`/api/requests/${item.id}/events`);const ul=node('ul',null,'timeline');for(const event of list)ul.append(node('li',`${new Date(event.occurred*1000).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'})} · ${events[event.event]||event.event}`));toggle.replaceWith(ul);}catch(e){message(e.message,true);}};card.append(toggle);}
    area.append(card);
  }
}
async function decide(item,decision){
  if(busy)return;busy=true;document.querySelectorAll('input,button').forEach(n=>n.disabled=true);
  try{await api(`/api/requests/${item.id}/decision`,{decision,digest:item.digest});message(decision==='approve'?'Freigegeben. Der Dienst darf diese Aktion jetzt einmal ausführen.':'Anfrage abgelehnt.');}
  catch(e){message(e.message,true);}finally{busy=false;document.querySelectorAll('input,button').forEach(n=>n.disabled=false);await reload();}
}
$('pending-tab').onclick=()=>{history=false;render();};$('history-tab').onclick=()=>{history=true;render();};$('refresh').onclick=reload;
$('demo').onclick=async()=>{try{await api('/api/demo/request',{});history=false;await reload();}catch(e){message(e.message,true);}};
$('logout').onclick=async()=>{try{await api('/api/logout',{});location.reload();}catch(e){message(e.message,true);}};
$('push').onclick=async()=>{try{const permission=await Notification.requestPermission();if(permission!=='granted')return message('Benachrichtigungen sind nicht erlaubt. Du kannst Anfragen hier jederzeit öffnen.');const reg=await navigator.serviceWorker.register('/sw.js');await navigator.serviceWorker.ready;const raw=atob(me.push_public_key.replace(/-/g,'+').replace(/_/g,'/'));const key=Uint8Array.from(raw,c=>c.charCodeAt(0));const subscription=await reg.pushManager.getSubscription()||await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});await api('/api/push-subscriptions',subscription.toJSON());message('Benachrichtigungen sind aktiviert.');}catch(e){message(e.message,true);}};
(async()=>{try{me=await api('/api/me');$('identity').textContent=me.name;$('workspace').hidden=false;$('logout').hidden=false;$('demo').hidden=!me.demo;$('demo-banner').hidden=!me.demo;$('push').hidden=!(me.push_public_key&&'PushManager' in window);await reload();}catch(e){if(!$('login').hidden) return;message(e.message,true);}})();
setInterval(()=>{if(me&&!document.hidden)reload();},10000);
