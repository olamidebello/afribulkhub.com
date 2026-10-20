'use strict';
/** Static UI localization. Business records and legal text are never machine-translated. */
window.HubI18n=(()=>{
 let catalog=null,dictionary={},language='pcm',rendered='pcm',observer=null,scheduled=false,user=null,csrf='';
 const originals=new WeakMap(),attributes=new WeakMap();
 const storage={get(){try{return localStorage.getItem('abh-language');}catch{return null;}},set(code){try{localStorage.setItem('abh-language',code);}catch{}}};
 const safe=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const protectedSelector='script,style,textarea,pre,[data-no-i18n],[translate="no"],.rowcard h3,.rowcard p,.productbody h3,.meta,.detailsgrid div,.brand,.footbrand,.sidebar>p,.price,.badge';
 function text(value){if(rendered!=='pcm')return value;const trim=value.trim();const mapped=dictionary[trim];return mapped?value.replace(trim,mapped):value;}
 function apply(root=document.body){
  if(!root)return;
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;
  while((node=walker.nextNode())){
   const parent=node.parentElement;if(!parent||parent.closest(protectedSelector)||(parent.tagName==='OPTION'&&!parent.hasAttribute('value')))continue;
   let source=originals.get(node);if(source===undefined){source=node.nodeValue;originals.set(node,source);}
   const value=text(source);if(node.nodeValue!==value)node.nodeValue=value;
  }
  for(const el of root.querySelectorAll('[placeholder],[aria-label],[title]')){
   if(el.closest('[data-no-i18n],[translate="no"]'))continue;
   let original=attributes.get(el);if(!original){original={};for(const key of ['placeholder','aria-label','title'])if(el.hasAttribute(key))original[key]=el.getAttribute(key);attributes.set(el,original);}
   for(const [key,value] of Object.entries(original)){const translated=text(value);if(el.getAttribute(key)!==translated)el.setAttribute(key,translated);}
  }
 }
 function schedule(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;observer?.disconnect();apply();watch();});}
 function watch(){observer?.observe(document.body,{subtree:true,childList:true,characterData:true});}
 function entry(){return catalog?.languages.find(r=>r.code===language);}
 function updateIndicator(){
  const button=document.querySelector('#languageButton'),note=document.querySelector('#languageNotice');
  if(button)button.textContent=(entry()?.native||language)+' ▾';
  if(note){note.hidden=['pcm','en'].includes(language);note.textContent=note.hidden?'':`${entry()?.name||language} selected. Interface currently uses English; this language is not yet translated. Listings and messages retain their original language.`;}
  document.documentElement.lang=rendered;document.documentElement.dir='ltr';
 }
 async function choose(code,persist=true){
  if(!catalog.languages.some(r=>r.code===code))throw Error('Language is not in the catalog');
  language=code;rendered=code==='pcm'?'pcm':'en';storage.set(code);
  observer?.disconnect();apply();updateIndicator();watch();
  if(user&&persist){const response=await fetch('/api/language',{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({language:code})});const result=await response.json();if(!response.ok)throw Error(result.error||'Language preference was not saved to your account.');}
 }
 async function syncAccount(account,token){user=account;csrf=token||'';if(account?.language)await choose(account.language,false);}
 function picker(){
  const modal=document.querySelector('#modal'),content=document.querySelector('#dialogContent');if(!catalog)return;
  content.innerHTML=`<section data-no-i18n><h2>${rendered==='pcm'?'Choose your language':'Choose your language'}</h2><p class="caption">${catalog.languages.length.toLocaleString()} documented language/dialect entries. Pidgin and English interfaces are available; other choices use English until translated.</p><label>Search by name, code or country<input id="languageSearch" type="search" autocomplete="off" placeholder="Yoruba, Hausa, Swahili, Nigeria…"></label><div id="languageResults" class="language-results" role="list" aria-label="Languages"></div><p class="subtle">Catalog: Glottolog (CC BY 4.0), supplemented by Unicode CLDR. A listed language is not a translation claim. Historical entries are included.</p></section>`;
  const input=content.querySelector('#languageSearch'),results=content.querySelector('#languageResults');
  const filter=()=>{const q=input.value.trim().toLocaleLowerCase();const all=catalog.languages.filter(r=>!q||[r.name,r.native,r.code,r.glottocode,...r.countries,...r.country_names].filter(Boolean).join(' ').toLocaleLowerCase().includes(q));const shown=all.slice(0,80);results.innerHTML=shown.map(r=>`<button type="button" role="listitem" data-language="${safe(r.code)}" aria-pressed="${r.code===language}"><span><strong>${safe(r.name)}</strong>${r.native!==r.name?' · '+safe(r.native):''}<small>${safe(r.code)} · ${safe(r.country_names.join(', ')||r.level)}</small></span><span class="pill">${r.ui==='available'?'UI available':'English fallback'}</span></button>`).join('')+`<p class="subtle">Showing ${shown.length} of ${all.length.toLocaleString()} matches. Narrow your search to find another entry.</p>`;};
  input.addEventListener('input',filter);results.addEventListener('click',async event=>{const button=event.target.closest('[data-language]');if(!button)return;try{await choose(button.dataset.language);modal.close();}catch(error){const message=document.createElement('p');message.className='error';message.textContent=error.message;content.appendChild(message);}});filter();if(!modal.open)modal.showModal();input.focus();
 }
 async function init(){
  const [c,d]=await Promise.all([fetch('/i18n/languages.json').then(r=>{if(!r.ok)throw Error('Language catalog unavailable');return r.json();}),fetch('/i18n/pcm.json').then(r=>{if(!r.ok)throw Error('Pidgin translations unavailable');return r.json();})]);catalog=c;dictionary=d;
  observer=new MutationObserver(schedule);await choose(storage.get()&&catalog.languages.some(r=>r.code===storage.get())?storage.get():'pcm',false);
  document.querySelector('#languageButton')?.addEventListener('click',picker);watch();
 }
 const ready=new Promise(resolve=>{const start=()=>init().then(resolve).catch(error=>{document.documentElement.lang='en';const note=document.querySelector('#languageNotice');if(note){note.hidden=false;note.textContent='Language files could not load. English is shown. Reload to try again.';}console.error(error);resolve();});if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();});
 return {ready,choose,picker,syncAccount,apply,text,get language(){return language;},get rendered(){return rendered;}};
})();
