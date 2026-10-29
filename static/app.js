const ReadingLayout=(()=>{
 const rect=b=>b.source_bbox;
 const overlap=(a,b)=>Math.max(0,Math.min(rect(a)[2],rect(b)[2])-Math.max(rect(a)[0],rect(b)[0]))/Math.min(rect(a)[2]-rect(a)[0],rect(b)[2]-rect(b)[0]);
 const heading=b=>b.kind==='heading'||/^(?:[A-Z]\.\s+[A-Z]|[IVX]+\.\s|REFERENCES\b)/.test(b.text);
 const prose=b=>!b.source_only&&!heading(b)&&['paragraph','caption'].includes(b.kind)&&!/^\s*(?:[•●]|\[\d+\]|\([a-z]\))/.test(b.text);
 const referenceHeading=b=>b.kind==='heading'&&/^(?:references|bibliography|参考文献)\s*$/i.test(b.text.trim());
 function referenceUnits(units){
  const result=[];
  for(let i=0;i<units.length;i++){
   const unit=units[i],head=unit.type==='text'&&unit.blocks.length===1?unit.blocks[0]:null;
   if(!head||!referenceHeading(head)){result.push(unit);continue}
   const sources=[];
   let j=i+1;
   while(j<units.length&&units[j].type==='text'&&units[j].blocks.every(b=>b.kind!=='heading'&&!b.source_only&&!/^(?:APPENDIX|ACKNOWLEDGMENTS|SUPPLEMENTARY)\b/i.test(b.text))){
    sources.push(...units[j].blocks);j++;
   }
   const entries=[],labels=/(^|\s)\[(\d{1,3})\]\s*/g;
   let current=null;
   const append=(part,b)=>{
    if(!current||!part.trim())return;
    const value=part.trim(),previous=current.text;
    current.text=previous&&/[A-Za-z]-$/.test(previous)&&/^[a-z]/.test(value)?previous.slice(0,-1)+value:previous?previous+' '+value:value;
    if(!current.blocks.includes(b))current.blocks.push(b);
   };
   for(const b of sources){
    const text=b.text;labels.lastIndex=0;let offset=0,match;
    while((match=labels.exec(text))){
     const number=Number(match[2]);
     if(!current||number===current.number+1){
      append(text.slice(offset,match.index),b);
      current={number,text:'',blocks:[b]};entries.push(current);offset=labels.lastIndex;
     }
    }
    append(text.slice(offset),b);
   }
   if(entries.length){result.push({type:'references',id:head.id,heading:head,entries});i=j-1}
   else result.push(unit);
  }
  return result;
 }
 function continuation(a,b){return prose(a)&&prose(b)&&((b.page===a.page&&a.column==='left'&&b.column==='right')||b.page===a.page+1)&&!/[.!?。！？:;]["'”’\])]*\s*$/.test(a.text)&&/^[a-z]/.test(b.text)&&a.text.length>35}
 function headingContinuation(a,b){if(!heading(a)||!heading(b)||a.page!==b.page)return false;const x=rect(a),y=rect(b),ha=x[3]-x[1],hb=y[3]-y[1];return ha>0&&Math.abs(ha-hb)<ha*.15&&y[1]-x[3]>=-1&&y[1]-x[3]<ha*.8&&Math.abs((x[0]+x[2]-y[0]-y[2])/2)<5}
 function artifacts(doc){
  const hidden=new Set(),folios=new Map();
  for(const p of doc.pages){
   const columns=new Map();
   for(const b of p.blocks){
    const box=b.bbox,text=b.text?.trim();
    if(b.source_only||!box||!/^\d{1,5}(?:\s+\d{1,5})*$/.test(text))continue;
    const numbers=text.split(/\s+/).map(Number),center=(box[0]+box[2])/2;
    if(box[2]<.09||box[0]>.93){const key=Math.round(center/.02);if(!columns.has(key))columns.set(key,[]);columns.get(key).push(b)}
    if(numbers.length===1&&(box[3]<.10||box[1]>.90)){
     const key=[Math.round(center/.02),box[1].toFixed(2),numbers[0]-b.page].join(':');
     if(!folios.has(key))folios.set(key,[]);folios.get(key).push(b);
    }
   }
   for(const group of columns.values()){
    group.sort((a,b)=>a.bbox[1]-b.bbox[1]);
    const numbers=group.flatMap(b=>b.text.trim().split(/\s+/).map(Number));
    if(numbers.length<6||group.at(-1).bbox[3]-group[0].bbox[1]<.18)continue;
    const steps=numbers.slice(1).map((n,i)=>n-numbers[i]);
    if(steps.filter(n=>n>=1&&n<=5).length/steps.length>=.75)group.forEach(b=>hidden.add(b.id));
   }
  }
  for(const group of folios.values())if(new Set(group.map(b=>b.page)).size>=2)group.forEach(b=>hidden.add(b.id));
  return hidden;
 }
 function plan(doc,smooth=true,showArtifacts=false){
  const ignored=showArtifacts?new Set():artifacts(doc);
  const visible=b=>!b.excluded&&(showArtifacts||!b.layout_ignored&&!ignored.has(b.id));
  const flat=doc.pages.flatMap(p=>p.blocks.filter(visible)),claimed=new Set(),floats=[];
  for(const p of doc.pages){
   const bs=p.blocks.filter(visible),visuals=bs.filter(b=>b.source_only&&['figure','table'].includes(b.kind));
   const captions=bs.filter(b=>!b.source_only&&/^(?:Fig(?:ure)?\.?\s*\d+|TABLE\s+[IVX\d]+|Table\s+\d+|图\s*\d+|表\s*\d+)/.test(b.text));
   for(const c of captions){
    if(claimed.has(c.id))continue;
    const kind=/^(?:TABLE|Table|表)/.test(c.text)?'table':'figure';
    let imgs=visuals.filter(v=>!claimed.has(v.id)&&v.kind===kind&&overlap(v,c)>.4&&(kind==='figure'?rect(c)[1]-rect(v)[3]>=-3&&rect(c)[1]-rect(v)[3]<90:rect(v)[1]-rect(c)[3]>=-3&&rect(v)[1]-rect(c)[3]<170));
    if(!imgs.length)continue;
    if(kind==='table')imgs=[imgs.sort((a,b)=>rect(a)[1]-rect(b)[1])[0]];
    else {const nearest=Math.min(...imgs.map(v=>rect(c)[1]-rect(v)[3]));imgs=imgs.filter(v=>rect(c)[1]-rect(v)[3]<nearest+24).sort((a,b)=>rect(a)[0]-rect(b)[0])}
    const captionsFor=[c],subcaptions=[],notes=[];
    if(kind==='table'){
     let bottom=rect(c)[3];
     for(const b of bs.filter(b=>b.id!==c.id&&!b.source_only&&!claimed.has(b.id)&&overlap(b,c)>.45&&rect(b)[1]>=rect(c)[3]-1&&rect(b)[3]<rect(imgs[0])[1]+1).sort((a,b)=>rect(a)[1]-rect(b)[1])){
      if(rect(b)[1]-bottom>15)break;captionsFor.push(b);bottom=rect(b)[3];
     }
     for(const b of bs){const gap=rect(b)[1]-rect(imgs[0])[3];if(!b.source_only&&!claimed.has(b.id)&&overlap(b,imgs[0])>.6&&gap>=-7&&gap<14&&rect(b)[3]-rect(b)[1]<45&&!heading(b)&&!captionsFor.includes(b))notes.push(b)}
    }else{
     for(const b of bs)if(!b.source_only&&!claimed.has(b.id)&&/^\([a-z]\)\s/.test(b.text)&&rect(b)[1]<rect(c)[1]&&imgs.some(v=>overlap(v,b)>.45&&rect(b)[1]-rect(v)[3]>=-2&&rect(b)[1]-rect(v)[3]<30))subcaptions.push(b);
    }
    const members=[...imgs,...captionsFor,...subcaptions,...notes];members.forEach(b=>claimed.add(b.id));
    floats.push({type:'float',kind,id:imgs[0].id,images:imgs,captions:captionsFor,subcaptions,notes,members,label:(c.text.match(/^(?:Fig(?:ure)?\.?\s*\d+[a-z]?|TABLE\s+[IVX\d]+|Table\s+\d+|[图表]\s*\d+)/)||[])[0]||''});
   }
   for(const b of visuals)if(!claimed.has(b.id)){claimed.add(b.id);floats.push({type:'float',kind:b.kind,id:b.id,images:[b],captions:[],subcaptions:[],notes:[],members:[b],label:''})}
  }
  const leaders=new Map();for(const f of floats){const first=f.members.reduce((a,b)=>flat.indexOf(a)<flat.indexOf(b)?a:b);leaders.set(first.id,f)}
  const units=[];for(const b of flat){if(leaders.has(b.id))units.push(leaders.get(b.id));else if(!claimed.has(b.id))units.push({type:b.source_only?'equation':'text',id:b.id,blocks:[b]})}
  const organized=referenceUnits(units);
  if(!smooth)return organized;
  const result=[];
  for(let i=0;i<organized.length;i++){
   const u=organized[i];result.push(u);if(u.type!=='text')continue;
   const deferred=[];
   while(true){let j=i+1;while(j<organized.length&&organized[j].type==='float')j++;
    const next=organized[j];if(!next||next.type!=='text'||!(continuation(u.blocks.at(-1),next.blocks[0])||(j===i+1&&headingContinuation(u.blocks.at(-1),next.blocks[0]))))break;
    deferred.push(...organized.slice(i+1,j));u.blocks.push(...next.blocks);i=j;
   }
   result.push(...deferred);
  }
  return result;
 }
 return {plan,continuation,heading};
})();
/* END READING LAYOUT */
'use strict';
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let token='',doc=null,selected=null,page=0,project=null,settings={},translationLanguages=[];
function translationAttributes(translation){const language=translationLanguages.find(l=>l.value===(translation?.target||'简体中文'));return `lang="${esc(language?.tag||'')}" dir="${language?.direction==='rtl'?'rtl':'auto'}"`}
const translationPair=()=>`${settings.source||'英语'} → ${settings.target||'简体中文'}`;
const status=t=>$('#status').textContent=t;
async function api(path,data,retry=true){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),path==='/api/rewrite'?120000:20000);try{const r=await fetch(path,{...(data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(data)}),signal:controller.signal});if(r.status===403&&retry&&path!=='/api/bootstrap'){const boot=await api('/api/bootstrap');token=boot.token;return api(path,data,false)}const v=await r.json();if(!r.ok)throw Error(v.error||'操作失败');return v}catch(e){if(e.name==='AbortError')throw Error('请求超时，请重试。若正在编译，请等编译完成后再操作。');throw e}finally{clearTimeout(timer)}}
function showError(error){status(error.message);if($('#modal').open){let box=$('#modal-error');if(!box){box=document.createElement('p');box.id='modal-error';box.className='warning';box.setAttribute('role','alert');$('#modal-content').prepend(box)}box.textContent=error.message;$('#modal').scrollTop=0}}
function action(fn){return async()=>{try{await fn()}catch(e){showError(e)}}}
function modal(html){$('#modal-content').innerHTML=html;if(!$('#modal').open)$('#modal').showModal();renderTex($('#modal-content'))}
$('#close').onclick=()=>$('#modal').close();
const blocks=()=>doc?.pages.flatMap(p=>p.blocks)||[];
const target=()=>{if(!selected)throw Error('请先点击一句原文或选中整段。');return {document_id:doc.id,...selected}};
async function library(){const rows=await api('/api/documents');$('#library').innerHTML='<option value="">选择文献</option>'+rows.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join('');if(doc)$('#library').value=doc.id}
async function openDoc(id){for(let n=0;n<120;n++){const d=await api('/api/documents/'+id);if(d.status==='error')throw Error(d.error);if(d.status==='ready'){doc=d;selected=null;page=0;project=d.project_id?{id:d.project_id}:null;$('#selection').textContent='尚未选择正文';$('#mapping').textContent='';render();await library();status(`已打开 ${d.name} · ${d.page_count} 页`);return}status('正在本地解析页面与阅读顺序…');await new Promise(r=>setTimeout(r,500))}throw Error('解析仍在进行，请稍后从文献库打开。')}
function sourceLabel(t){return (t?.source==='demo'?'人工示例译文':t?.source==='api'?'API 译文 · '+t.model:'人工译文')+' · '+(t?.target||'简体中文')}
function mathImage(b,r,index,translation=false){const size=Math.max(6,r.size),scale=1.1,align=(Number.isFinite(r.baseline_offset)?r.baseline_offset/size:-.28)*scale;return `<img class="inline-formula" src="/api/documents/${doc.id}/math/${b.id}/${index}${translation?'?variant=translation':''}" alt="${esc(r.text)}" title="原 PDF 公式" style="width:${r.width/size*scale}em;height:${r.height/size*scale}em;vertical-align:${align}em">`}
function sourceText(b,s){
 const chars=Array.from(b.text);
 const runs=(b.math_runs||[]).map((r,i)=>({...r,index:i})).filter(r=>r.start>=s.start&&r.end<=s.end);let at=s.start,html='';
 for(const r of runs){html+=esc(chars.slice(at,r.start).join(''));html+=mathImage(b,r,r.index);at=r.end}
 return html+esc(chars.slice(at,s.end).join(''));
}
function translatedText(b,text){return esc(text).replace(/\[\[MATH_(\d+)\]\]/g,(token,index)=>{const r=(b.translation?.math_runs||b.math_runs)?.[Number(index)];return r?mathImage(b,r,index,true):token})}
function renderTex(scope){if(!window.renderMathInElement)return;scope.querySelectorAll('.chinese,.math-content').forEach(el=>renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false},{left:'$',right:'$',display:false}],throwOnError:false,trust:false,strict:'ignore',maxExpand:1000,maxSize:10}))}
function sentenceHTML(b,s){const notes=doc.annotations.some(n=>n.status==='open'&&n.block_id===b.id&&n.start<s.end&&n.end>s.start);return `<span class="sentence${notes?' annotated':''}" data-b="${b.id}" data-s="${s.id}" tabindex="0">${sourceText(b,s)}</span>`}
let viewUnits=[],visualZoom=100,visualFitWidth=900;
const viewSettings=(()=>{try{return JSON.parse(localStorage.getItem('shore-reading-layout')||'{}')}catch{return {}}})();
const saveView=()=>{try{localStorage.setItem('shore-reading-layout',JSON.stringify(viewSettings))}catch{}};
function fragment(b){return `<span id="b-${b.id}" class="source-fragment" title="第 ${b.page+1} 页">${b.sentences.map(s=>sentenceHTML(b,s)).join(' ')}</span>`}
function textGroup(bs,caption=false){
 const allAligned=bs.every(b=>b.translation?.segments?.length===b.sentences.length&&b.translation.segments.every((r,i)=>r.id===b.sentences[i].id));
 let html='';
 if(!caption&&!ReadingLayout.heading(bs[0])&&$('#granularity').value==='sentence'&&allAligned){
  const pairs=[];
  bs.forEach((b,bi)=>b.sentences.forEach((s,si)=>{const row={en:`<span${si===0?` id="b-${b.id}"`:''} class="source-fragment">${sentenceHTML(b,s)}</span>`,zh:`<span class="sentence" data-b="${b.id}" data-s="${s.id}">${translatedText(b,b.translation.segments[si].text)}</span>`,attributes:translationAttributes(b.translation)};if(bi&&si===0&&ReadingLayout.continuation(bs[bi-1],b)&&pairs.length&&pairs.at(-1).attributes===row.attributes){pairs.at(-1).en+=' '+row.en;pairs.at(-1).zh+=' '+row.zh}else pairs.push(row)}));
  html=pairs.map(r=>`<div class="english" dir="auto">${r.en}</div><div class="chinese" ${r.attributes}>${r.zh}</div>`).join('');
 }else{
  html=`<div class="english" dir="auto">${bs.map(fragment).join(' ')}</div>`;
  if(bs.some(b=>b.translation))html+=`<div class="chinese" dir="auto">${bs.map(b=>b.translation?`<span class="translated-fragment" ${translationAttributes(b.translation)}>${translatedText(b,b.translation.text)}</span>`:'<span class="missing-translation">〔此段暂无译文〕</span>').join(' ')}</div>`;
 }
 const pages=[...new Set(bs.map(b=>b.page+1))],label=pages.length>1?`第 ${pages[0]}–${pages.at(-1)} 页`:`第 ${pages[0]} 页`;
 return `<${caption?'div':'article'} class="paper-block ${caption?'caption-fragment':ReadingLayout.heading(bs[0])?'paper-heading':''} ${bs.length>1&&!caption?'joined-paragraph':''}" data-members="${bs.map(b=>b.id).join(' ')}">${html}<span class="reading-provenance" title="${esc(bs.map(b=>b.translation?sourceLabel(b.translation):'暂无译文').join(' / '))}">${label}${bs.length>1?' · 续段':''}</span></${caption?'div':'article'}>`;
}
function visualWidth(u){return viewSettings[doc.id+':'+u.id]|| (u.kind==='table'?(u.images[0].column==='wide'?90:70):u.images.length>1||u.images[0].column==='wide'?100:75)}
function visualImage(b,u,lazy=true){const [x0,y0,x1,y1]=b.source_bbox;const trim=u.kind==='table'&&u.notes.some(n=>n.source_bbox[1]<y1)?1.5:0;return `<span class="visual-clip" style="aspect-ratio:${x1-x0}/${y1-y0-trim}"><img alt="${esc(u.label||(u.kind==='table'?'表格':'插图'))}" src="/api/documents/${doc.id}/crop/${b.id}" width="${Math.round((x1-x0)*3)}" height="${Math.round((y1-y0)*3)}" ${lazy?'loading="lazy"':''}></span>`}
function floatHTML(u){
 const caption=u.captions.length?`<figcaption>${textGroup(u.captions,true)}</figcaption>`:'';
 const gallery=`<div class="figure-panels ${u.images.length>1?'multiple':''}">${u.images.map(b=>{const sub=u.subcaptions.filter(s=>{const cx=(s.source_bbox[0]+s.source_bbox[2])/2;return cx>=b.source_bbox[0]&&cx<=b.source_bbox[2]});return `<div class="figure-panel" style="flex:${b.source_bbox[2]-b.source_bbox[0]} 1 0" id="b-${b.id}"><button class="visual-image" data-enlarge="${u.id}" aria-label="放大${esc(u.label||'图表')}">${visualImage(b,u)}</button>${sub.map(s=>textGroup([s],true)).join('')}</div>`}).join('')}</div>`;
 return `<figure class="paper-visual ${u.kind}" data-visual="${u.id}" style="--visual-width:${visualWidth(u)}%">${u.kind==='table'?caption:''}${gallery}${u.kind==='figure'?caption:''}${u.notes.map(b=>`<div class="table-note">${textGroup([b],true)}</div>`).join('')}<div class="visual-tools"><label>大小 <input type="range" min="40" max="100" step="5" value="${visualWidth(u)}" data-size="${u.id}" aria-label="${esc(u.label||'图表')}显示大小"></label><output>${visualWidth(u)}%</output><button data-enlarge="${u.id}">放大</button><button data-original="${u.images[0].id}">原页</button></div></figure>`;
}
function referenceHTML(u){
 const anchors=new Set();
 const rows=u.entries.map(entry=>{
  const anchor=entry.blocks.find(b=>!anchors.has(b.id));if(anchor)anchors.add(anchor.id);
  const pages=[...new Set(entry.blocks.map(b=>b.page+1))];
  return `<li class="reference-entry" ${anchor?`id="b-${anchor.id}"`:''} data-members="${entry.blocks.map(b=>b.id).join(' ')}" title="第 ${pages.join('、')} 页"><span class="reference-number">[${entry.number}]</span><span class="reference-text">${esc(entry.text)}</span></li>`;
 }).join('');
 return `<section class="references-section" data-members="${[u.heading,...u.entries.flatMap(e=>e.blocks)].map(b=>b.id).join(' ')}"><h2 id="b-${u.heading.id}">${esc(u.heading.text)}</h2><ol class="reference-list">${rows}</ol></section>`;
}
function openVisual(id){const u=viewUnits.find(u=>u.type==='float'&&u.id===id);if(!u)return;visualZoom=100;const dialog=$('#visual-dialog');$('#visual-title').textContent=u.label|| (u.kind==='table'?'表格':'插图');$('#visual-stage').innerHTML=`<div class="large-panels ${u.images.length>1?'multiple':''}">${u.images.map(b=>`<div class="large-image" style="flex:${b.source_bbox[2]-b.source_bbox[0]} 1 0">${visualImage(b,u,false)}</div>`).join('')}</div>`;$('#visual-caption').textContent=[...u.subcaptions,...u.captions,...u.notes].map(b=>b.text).join('\n');dialog.showModal();const stage=$('#visual-stage'),aspect=u.images.reduce((w,b)=>w+b.source_bbox[2]-b.source_bbox[0],0)/Math.max(...u.images.map(b=>b.source_bbox[3]-b.source_bbox[1]));visualFitWidth=Math.max(240,Math.min(stage.clientWidth-48,(stage.clientHeight-88)*aspect+40));setVisualZoom(100);$('#visual-original').onclick=()=>{dialog.close();revealSource(u.images[0].id)}}
function setVisualZoom(value){visualZoom=Math.max(50,Math.min(300,value));$('#visual-stage .large-panels').style.width=(visualFitWidth*visualZoom/100)+'px';$('#visual-zoom').textContent=visualZoom+'%'}
function revealSource(id){const b=blocks().find(b=>b.id===id);page=b.page;$('#pdf').hidden=false;document.body.classList.add('pdf-open');renderPdf();$('#page-canvas').querySelectorAll('.active').forEach(e=>e.classList.remove('active'));const box=$('#page-canvas').querySelector(`[data-block="${id}"]`);box?.classList.add('active');box?.scrollIntoView({block:'center'})}
function render(){
 if(!doc)return;viewUnits=ReadingLayout.plan(doc,$('#smooth-reading').checked,$('#show-artifacts')?.checked);
 $('#reading').classList.toggle('show-boundaries',!$('#smooth-reading').checked);
 $('#reading').innerHTML=`<div class="manuscript-sheet"><div class="document-bar"><h1 class="doc-title">${esc(doc.name)}</h1><span class="hint">${doc.page_count} 页${doc.project_id?' · 源稿版本 '+doc.project_revision:''}</span></div>`+viewUnits.map(u=>{
  if(u.type==='float')return floatHTML(u);
  if(u.type==='references')return referenceHTML(u);
  if(u.type==='text')return textGroup(u.blocks);
  const b=u.blocks[0],p=doc.pages[b.page],width=(b.bbox[2]-b.bbox[0])*p.width*1.98;
  return `<article class="paper-block equation-block" id="b-${b.id}"><button class="equation-image" data-original="${b.id}" title="核对原 PDF"><img alt="原文公式" loading="lazy" src="/api/documents/${doc.id}/crop/${b.id}" style="width:${width}px"></button></article>`;
 }).join('')+'</div>';
 $('#reading').querySelectorAll('[data-s]').forEach(el=>{const select=()=>{const b=blocks().find(b=>b.id===el.dataset.b),s=b.sentences.find(s=>s.id===el.dataset.s);choose(b,s)};el.onclick=select;el.onkeydown=e=>{if(e.key==='Enter')select()}});
 $('#reading').querySelectorAll('[data-original]').forEach(el=>el.onclick=()=>revealSource(el.dataset.original));
 $('#reading').querySelectorAll('[data-enlarge]').forEach(el=>el.onclick=()=>openVisual(el.dataset.enlarge));
 $('#reading').querySelectorAll('[data-size]').forEach(el=>el.oninput=()=>{const fig=el.closest('figure');fig.style.setProperty('--visual-width',el.value+'%');fig.querySelector('output').textContent=el.value+'%';viewSettings[doc.id+':'+el.dataset.size]=Number(el.value);saveView()});
 renderNotes();renderPdf();if(selected)highlight();renderTex($('#reading'));
}

function choose(b,s){selected={block_id:b.id,start:s?.start??0,end:s?.end??Array.from(b.text).length,quote:s?.text??b.text};page=b.page;$('#selection').innerHTML=sourceText(b,{start:selected.start,end:selected.end});highlight();renderPdf();const snapshot=selected;api('/api/source-map',target()).then(m=>{if(selected===snapshot)$('#mapping').textContent=m.available?`可回写：${m.file} 第 ${m.line} 行（唯一匹配）`:m.reason}).catch(e=>status(e.message))}
function highlight(){document.querySelectorAll('.paper-block.active,.sentence.selected').forEach(e=>e.classList.remove('active','selected'));$('#b-'+selected.block_id)?.closest('.paper-block')?.classList.add('active');document.querySelectorAll(`[data-b="${selected.block_id}"][data-s]`).forEach(e=>{const s=blocks().find(b=>b.id===selected.block_id).sentences.find(s=>s.id===e.dataset.s);if(s.start<selected.end&&s.end>selected.start)e.classList.add('selected')})}
function renderNotes(){ $('#notes').innerHTML=doc.annotations.map(n=>`<div class="note ${n.status}" data-note="${n.id}">${esc(n.body)}<small>第 ${n.page+1} 页 · ${n.status==='open'?'待处理':'已解决'}</small></div>`).join('')||'<p class="hint">暂无批注</p>';$('#notes').querySelectorAll('[data-note]').forEach(el=>el.onclick=()=>{const n=doc.annotations.find(n=>n.id===el.dataset.note);choose(blocks().find(b=>b.id===n.block_id),{start:n.start,end:n.end,text:n.quote});$('#b-'+n.block_id)?.scrollIntoView({block:'center'});modal(`<h2>批注</h2><blockquote>${esc(n.quote)}</blockquote><p>${esc(n.body)}</p><button id="resolve">标记已解决</button>`);$('#resolve').onclick=action(async()=>{await api('/api/annotation',{document_id:doc.id,resolve:n.id});$('#modal').close();await refresh()})});$('#proposals').innerHTML=doc.proposals.map(p=>`<div class="proposal" data-proposal="${p.id}">${esc(p.replacement.slice(0,120))}<div class="hint">${p.status==='applied'?'已写入源稿':'待审阅'} · ${esc(p.model)}</div></div>`).join('')||'<p class="hint">暂无改写建议</p>';$('#proposals').querySelectorAll('[data-proposal]').forEach(e=>e.onclick=action(()=>showProposal(doc.proposals.find(p=>p.id===e.dataset.proposal))))}
async function refresh(){doc=await api('/api/documents/'+doc.id);const top=$('#reading').scrollTop;render();$('#reading').scrollTo({top,behavior:'instant'})}
function renderPdf(){if(!doc||$('#pdf').hidden)return;$('#page-label').textContent=`${page+1} / ${doc.page_count}`;$('#page-canvas').innerHTML=`<img alt="原 PDF 第 ${page+1} 页" src="/api/documents/${doc.id}/page/${page}?scale=1.5">`+doc.pages[page].blocks.map(b=>`<button aria-label="定位原文段落" class="pdf-box ${selected?.block_id===b.id?'active':''}" data-block="${b.id}" style="left:${b.bbox[0]*100}%;top:${b.bbox[1]*100}%;width:${(b.bbox[2]-b.bbox[0])*100}%;height:${(b.bbox[3]-b.bbox[1])*100}%"></button>`).join('');$('#page-canvas').querySelectorAll('[data-block]').forEach(e=>e.onclick=()=>{const b=blocks().find(b=>b.id===e.dataset.block);if(!b.source_only)choose(b);$('#b-'+b.id)?.scrollIntoView({block:'center'})})}
async function upload(file,route){if(!file)return;status('正在导入 '+file.name);const r=await fetch(route+'?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-Local-Token':token},body:file});const v=await r.json();if(!r.ok)throw Error(v.error);return v}
async function uploadFolder(list){
 const allowed=new Set(['tex','bib','cls','sty','bst','bbl','png','jpg','jpeg','pdf','eps','svg','csv','dat','txt','pgf','tikz']);
 const files=[...list].filter(file=>allowed.has(file.name.split('.').at(-1).toLowerCase()));
 if(!files.length)throw Error('所选文件夹里没有可导入的 LaTeX 文件。');
 if(files.length>2000||files.reduce((size,file)=>size+file.size,0)>150*1024*1024)throw Error('项目超过 2000 个文件或 150 MB 限制。');
 const paths=files.map(file=>file.webkitRelativePath||file.name);
 const body=new FormData();body.append('paths',JSON.stringify(paths));files.forEach(file=>body.append('files',file,file.name));
 const name=paths[0].split('/')[0];status(`正在导入 ${name} · ${files.length} 个文件`);
 const response=await fetch('/api/project-folder-import?name='+encodeURIComponent(name),{method:'POST',headers:{'X-Local-Token':token},body});
 const result=await response.json();if(!response.ok)throw Error(result.error||'文件夹导入失败。');return result;
}
// Native labels open the file inputs directly; avoid forwarding clicks through other buttons.
document.querySelectorAll('.file-trigger').forEach(label=>label.addEventListener('keydown',event=>{
 if(event.key==='Enter'||event.key===' '){event.preventDefault();document.getElementById(label.htmlFor).click()}
}));
$('#pdf-input').onchange=action(async()=>{const v=await upload($('#pdf-input').files[0],'/api/import');if(v)await openDoc(v.id);$('#pdf-input').value=''});$('#tex-input').onchange=action(async()=>{project=await upload($('#tex-input').files[0],'/api/project-import');if(project)compileDialog();$('#tex-input').value=''});$('#folder-input').onchange=action(async()=>{try{project=await uploadFolder($('#folder-input').files);if(project)compileDialog()}finally{$('#folder-input').value=''}});
$('#empty-demo').onclick=()=>$('#demo').click();
async function poll(jid){while(true){const j=await api('/api/jobs/'+jid);status(j.kind==='compile'?'正在本地编译 LaTeX…':`对照处理中：${j.processed||0} / ${j.total}`);if(!['running','queued'].includes(j.status)){if(j.kind==='compile'){if(j.status!=='completed')throw Error(j.errors.map(e=>e.message).join('\n'));await openDoc(j.document_id)}else {await refresh();status(`对照任务 ${j.status} · 成功 ${j.done} 段${j.errors.length?' · '+j.errors[0].message:''}`)}if($('#cancel-job'))$('#modal').close();if(j.kind!=='compile'&&j.errors.length){const failed=[...new Set(j.errors.map(e=>e.block_id).filter(Boolean))];modal(`<h2>部分段落未完成</h2><p>成功 ${j.done} 段，失败 ${failed.length} 段。已完成的译文保留。</p><p class="warning">${esc(j.errors[0].message)}</p><button id="retry-translation" class="primary">重试失败段落</button>`);$('#retry-translation').onclick=action(()=>translateDialog(failed))}return}await new Promise(r=>setTimeout(r,900))}}
function compileDialog(){if(!project)throw Error('请先导入 LaTeX 源稿。');modal(`<h2>编译 LaTeX 副本</h2><p class="hint">${project.file_count?`已导入 ${project.file_count} 个项目文件。`:''} 原文件不会改变。每次编译保留独立 PDF。</p>${project.missing_files?.length?`<p class="warning">项目缺少：${esc(project.missing_files.slice(0,8).join('、'))}。请改用包含这些文件的完整文件夹或 ZIP。</p>`:''}${project.candidates?`<label>主文件</label><select id="main-file">${project.candidates.map(f=>`<option ${f===project.main_file?'selected':''}>${esc(f)}</option>`).join('')}</select>`:''}<label>编译器</label><select id="engine"><option ${project.preferred_engine==='pdflatex'?'selected':''}>pdflatex</option><option ${project.preferred_engine==='xelatex'?'selected':''}>xelatex</option><option>lualatex</option></select><button class="primary" id="run-compile">开始编译</button>`);$('#run-compile').onclick=action(async()=>{const data={project_id:project.id,engine:$('#engine').value};if($('#main-file'))data.main_file=$('#main-file').value;$('#modal').close();await poll((await api('/api/compile',data)).id)})}
$('#compile').onclick=action(compileDialog);
$('#demo').onclick=action(async()=>{const d=await api('/api/demo',{});await openDoc(d.id);await api('/api/demo-translations',{id:d.id});await refresh();status('示例已打开 · 译文为人工演示内容，可体验句子选择与批注')});
$('#library').onchange=action(async()=>{if($('#library').value)await openDoc($('#library').value)});$('#granularity').onchange=()=>render();$('#whole').onclick=action(()=>{const t=target();choose(blocks().find(b=>b.id===t.block_id))});
$('#save-note').onclick=action(async()=>{await api('/api/annotation',{...target(),body:$('#note').value});$('#note').value='';await refresh();status('批注已保存，已绑定所选原文')});
async function translateDialog(ids){settings=(await api('/api/bootstrap')).settings;const language={source:settings.source,target:settings.target};modal(`<h2>生成${$('#granularity').value==='sentence'?'逐句':'逐段'}双语对照</h2><p class="translation-summary">${esc(translationPair())}</p><p>将 ${ids.length} 个正文段落发送至你配置的 API。图表与已排除内容不会发送。</p><p class="hint">已有译文会被本次结果替换；逐句模式严格按原句配对。</p><div class="dialog-actions"><button id="run-translate" class="primary">开始生成</button><button id="change-translation-language">更改翻译语言</button></div>`);$('#change-translation-language').onclick=action(()=>openSettings(false,()=>translateDialog(ids)));$('#run-translate').onclick=action(async()=>{const jid=(await api('/api/translate',{document_id:doc.id,block_ids:ids,granularity:$('#granularity').value,...language})).id;$('#modal').close();status('对照任务已开始 · '+translationPair());modal('<h2>正在生成对照</h2><p>可关闭此窗口继续阅读，处理进度显示在顶部。</p><button id="cancel-job">停止生成</button>');$('#cancel-job').onclick=action(async()=>{await api('/api/cancel',{id:jid});$('#modal').close()});await poll(jid)})}
$('#translate').onclick=action(()=>{if(!doc)throw Error('请先导入论文。');translateDialog(blocks().filter(b=>!b.excluded&&!b.source_only&&!b.layout_ignored).map(b=>b.id))});$('#translate-one').onclick=action(()=>translateDialog([target().block_id]));
$('#rewrite').onclick=action(()=>{const a=target();modal(`<h2>仅改写当前选区</h2><blockquote>${esc(a.quote)}</blockquote><label>本次要求（自动带入重叠批注）</label><textarea id="instruction" placeholder="保留科学含义，压缩表达，避免过度断言"></textarea><label>人工草稿（可选；填写后无需 API）</label><textarea id="manual" placeholder="留空则由 API 按原文语言生成改写"></textarea><button id="generate-rewrite" class="primary">生成差异预览</button>`);$('#generate-rewrite').onclick=action(async()=>{const data={...a,instruction:$('#instruction').value};if($('#manual').value.trim())data.manual=$('#manual').value;$('#generate-rewrite').disabled=true;status('正在生成改写建议，原文保持不变…');try{const p=await api('/api/rewrite',data);await refresh();await showProposal(p);status('改写建议已保存，请核对差异')}finally{if($('#generate-rewrite'))$('#generate-rewrite').disabled=false}})});
async function showProposal(p){
 const did=doc.id;
 modal(`<div class="dialog-eyebrow">REVIEW CHANGES</div><h2>审阅这次改写</h2><div class="diff">${p.diff.map(d=>d.kind==='equal'?esc(d.text):`<${d.kind==='delete'?'del':'ins'}>${esc(d.text)}</${d.kind==='delete'?'del':'ins'}>`).join('')}</div><div class="chinese" ${translationAttributes({target:p.translation_target})}>${esc(p.translation||'人工草稿尚无译文')}</div><details class="rewrite-reason"><summary>改写说明</summary><p>${esc(p.rationale)}</p></details>${p.warnings.map(w=>`<p class="warning">${esc(w)}</p>`).join('')}<div class="source-status"><p id="proposal-map" class="hint">正在检查源稿位置…</p><button id="retry-map" hidden>重新检查</button></div><label><input id="reviewed" type="checkbox"> 已核对改写范围、数值与引用</label><div class="dialog-actions"><button id="apply" class="primary" disabled>写入源稿副本</button><button id="edit-from-proposal">直接编辑源稿</button><button id="download-proposal">导出建议</button></div>`);
 $('#download-proposal').onclick=()=>download('改写建议.json',JSON.stringify(p,null,2));
 $('#edit-from-proposal').onclick=action(()=>openSourceEditor());
 let mapping=null;
 const updateApply=()=>{if($('#apply'))$('#apply').disabled=!(mapping?.available&&$('#reviewed').checked&&p.status==='proposed')};
 $('#reviewed').onchange=updateApply;
 const locate=async()=>{const label=$('#proposal-map');label.textContent='正在检查源稿位置…';$('#retry-map').hidden=true;try{mapping=await api('/api/source-map',{document_id:did,block_id:p.block_id,start:p.start,end:p.end,quote:p.quote});if(!label.isConnected)return;label.textContent=p.status==='applied'?'已写入源稿，可重新编译查看。':mapping.available?`已定位到 ${mapping.file} · 第 ${mapping.line} 行。写入后重新编译即可查看。`:mapping.reason;$('#edit-from-proposal').hidden=!doc.project_id;updateApply()}catch(e){if(!label.isConnected)return;label.textContent='源稿定位失败：'+e.message;$('#retry-map').hidden=false;updateApply()}};
 $('#retry-map').onclick=action(locate);
 $('#apply').onclick=action(async()=>{const button=$('#apply');button.disabled=true;button.textContent='正在写入…';try{project=await api('/api/apply',{document_id:did,proposal_id:p.id,reviewed:$('#reviewed').checked});$('#modal').close();await refresh();status('已写入源稿副本。点击“编译预览”查看修改结果。')}finally{if(button.isConnected){button.textContent='写入源稿副本';updateApply()}}});
 await locate();
}
function download(name,text,type='application/json'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
$('#export').onclick=action(()=>{if(!doc)throw Error('请先打开文献。');download(doc.name+'-工作记录.json',JSON.stringify(doc,null,2))});$('#project-export').onclick=action(async()=>{if(!project)throw Error('请先导入 LaTeX 项目。');const r=await fetch(`/api/projects/${project.id}/export`);if(!r.ok)throw Error('导出失败');download('LaTeX-源稿副本.zip',await r.blob(),'application/zip')});
$('#pdf-toggle').onclick=()=>{$('#pdf').hidden=!$('#pdf').hidden;document.body.classList.toggle('pdf-open',!$('#pdf').hidden);renderPdf()};$('#prev').onclick=()=>{if(doc&&page>0){page--;renderPdf()}};$('#next').onclick=()=>{if(doc&&page<doc.page_count-1){page++;renderPdf()}};
async function openSettings(showService=true,onSave){
 const boot=await api('/api/bootstrap');settings=boot.settings;translationLanguages=boot.languages;
 const options=(value,source=false)=>(source?'<option value="自动识别">自动识别</option>':'')+translationLanguages.map(l=>`<option value="${esc(l.value)}" ${l.value===value?'selected':''}>${esc(l.label)}</option>`).join('');
 modal(`<h2>翻译与 AI 设置</h2><section class="translation-settings" aria-labelledby="translation-settings-title"><h3 id="translation-settings-title">翻译语言</h3><p class="hint">默认中英对照，可交换方向或选择其他语言。</p><div class="language-settings-grid"><div><label for="source-language">原文语言</label><select id="source-language">${options(settings.source,true)}</select></div><button id="swap-languages" class="quiet-button" aria-label="交换原文与译文语言">交换语言</button><div><label for="target-language">译文语言</label><select id="target-language">${options(settings.target)}</select></div></div><p id="translation-pair-preview" class="translation-summary" role="status" aria-live="polite"></p><p class="hint">语言设置用于之后生成的译文及改写建议中的译文，已有译文不会自动改变。实际翻译能力取决于所配置的模型。</p></section><details id="api-service-settings" class="api-service-settings" ${showService?'open':''}><summary>AI 服务</summary><p class="hint">兼容 OpenAI Chat Completions。密钥仅保存在本次运行内存中，重启需重填。</p><label for="base-url">API 地址</label><input id="base-url" value="${esc(settings.base_url)}"><label for="model">模型名称</label><input id="model" value="${esc(settings.model)}"><label for="key">API 密钥 ${settings.has_key?'（已配置，留空保留）':''}</label><input id="key" type="password" autocomplete="off"></details><button id="save-settings" class="primary">保存设置</button>`);
 $('#source-language').value=settings.source;
 const updatePair=()=>{const source=$('#source-language').value,target=$('#target-language').value,conflict=source===target;$('#translation-pair-preview').textContent=conflict?'请选择不同的原文与译文语言。':`${source} → ${target}`;$('#translation-pair-preview').classList.toggle('language-conflict',conflict);$('#save-settings').disabled=conflict;$('#swap-languages').disabled=source==='自动识别'};
 $('#source-language').onchange=updatePair;$('#target-language').onchange=updatePair;
 $('#swap-languages').onclick=()=>{const source=$('#source-language').value;$('#source-language').value=$('#target-language').value;$('#target-language').value=source;updatePair()};updatePair();
 $('#save-settings').onclick=action(async()=>{const button=$('#save-settings'),data={base_url:$('#base-url').value,model:$('#model').value,source:$('#source-language').value,target:$('#target-language').value};if($('#key').value)data.api_key=$('#key').value;button.disabled=true;try{await api('/api/settings',data);settings={...settings,...data};delete settings.api_key;$('#modal').close();status('设置已保存 · '+translationPair())}finally{if(button.isConnected)updatePair()}if(onSave)await onSave()});
}
$('#settings').onclick=action(()=>openSettings());
$('#translation-settings').onclick=action(()=>{document.querySelector('.reading-options').open=false;return openSettings(false)});
action(async()=>{const boot=await api('/api/bootstrap');token=boot.token;settings=boot.settings;translationLanguages=boot.languages;await library();let last='';try{last=localStorage.getItem('wenshu-last-document')||''}catch{}if(last&&Array.from($('#library').options).some(o=>o.value===last))await openDoc(last)})();

$('#smooth-reading').checked=viewSettings.smooth!==false;
$('#smooth-reading').onchange=()=>{viewSettings.smooth=$('#smooth-reading').checked;saveView();const focus=selected?.block_id;render();if(focus)$('#b-'+focus)?.scrollIntoView({block:'center'})};
$('#visual-close').onclick=()=>$('#visual-dialog').close();
$('#visual-minus').onclick=()=>setVisualZoom(visualZoom-25);
$('#visual-plus').onclick=()=>setVisualZoom(visualZoom+25);
$('#visual-fit').onclick=()=>setVisualZoom(100);
$('#visual-dialog').onclick=e=>{if(e.target===$('#visual-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close()}};

$('#show-artifacts').onchange=()=>render();

/* WORKSPACE INTERFACE */
/* Interface behavior only. Manuscript data and write-back stay in app.js. */
'use strict';
(()=>{
 const paths={
  book:'<path d="M12 5.5C9 3.5 5 3.5 2.5 4.5v14c3-1 6.5-1 9.5 1 3-2 6.5-2 9.5-1v-14c-2.5-1-6.5-1-9.5 1Z"/><path d="M12 5.5v14"/>',
  code:'<path d="m8 7-5 5 5 5m8-10 5 5-5 5M14 4l-4 16"/>',
  play:'<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m10 8 6 4-6 4Z"/>',
  'file-plus':'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z"/><path d="M14 3v6h6M8 14h8m-4-4v8"/>',
  'file-code':'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z"/><path d="M14 3v6h6m-10 3-3 3 3 3m4-6 3 3-3 3"/>',
  folder:'<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="M3 9h18"/>',
  spark:'<path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3Z"/>',
  sliders:'<path d="M4 7h4m4 0h8M4 17h8m4 0h4"/><circle cx="10" cy="7" r="2"/><circle cx="14" cy="17" r="2"/>',
  document:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z"/><path d="M14 3v6h6M8 13h8m-8 4h6"/>',
  download:'<path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
  languages:'<path d="M3 5h11M8 3v2m3 0c0 6-3 9-7 11m1-8c1 3 3 5 6 7m2 6 4-11 4 11m-6.7-4h5.4"/>',
  split:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M12 4v16M6.5 8h2m-2 4h2m7-4h2m-2 4h2"/>',
  focus:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><rect x="8" y="8" width="8" height="8" rx="1"/>',
  quote:'<path d="M10 6H4v7h5c0 3-2 4-4 5m15-12h-6v7h5c0 3-2 4-4 5"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  'chevron-left':'<path d="m14 6-6 6 6 6"/>',
  'chevron-right':'<path d="m10 6 6 6-6 6"/>'
 };
 document.querySelectorAll('[data-icon]').forEach(el=>{el.setAttribute('aria-hidden','true');el.innerHTML=`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[el.dataset.icon]||paths.document}</svg>`});
 document.querySelectorAll('.rail-item').forEach(el=>{el.title=el.title||el.textContent.trim()});
 const tabs=[$('#annotation-tab'),$('#revision-tab')];
 function selectTab(index,focus=false){tabs.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===index));tab.tabIndex=i===index?0:-1;$('#'+tab.getAttribute('aria-controls')).hidden=i!==index});if(focus)tabs[index].focus()}
 tabs.forEach((tab,index)=>{tab.addEventListener('click',()=>selectTab(index));tab.addEventListener('keydown',event=>{let next=index;if(event.key==='ArrowRight'||event.key==='ArrowLeft')next=1-index;else if(event.key==='Home')next=0;else if(event.key==='End')next=1;else return;event.preventDefault();selectTab(next,true)})});
 $('#focus-mode').addEventListener('click',()=>{const active=document.body.classList.toggle('focus-mode');$('#focus-mode').setAttribute('aria-pressed',String(active));$('#focus-mode').setAttribute('aria-label',active?'退出专注':'专注阅读');$('#focus-mode').lastElementChild.textContent=active?'退出专注':'专注阅读'});
 $('#nav-reader').addEventListener('click',event=>{event.preventDefault();$('#reading').focus({preventScroll:true})});
 document.addEventListener('click',event=>{document.querySelectorAll('.reading-options[open],.mobile-actions[open]').forEach(el=>{if(!el.contains(event.target))el.open=false})});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'){document.querySelectorAll('.reading-options[open],.mobile-actions[open]').forEach(el=>el.open=false);if(!document.querySelector('dialog[open]'))document.body.classList.remove('mobile-inspector-open')}});
 document.querySelectorAll('[data-trigger]').forEach(el=>el.addEventListener('click',()=>{$('#'+el.dataset.trigger).click();el.closest('details').open=false}));
 $('#mobile-inspector').addEventListener('click',()=>{document.body.classList.add('mobile-inspector-open');document.querySelector('.mobile-actions').open=false;$('#inspector-close').focus()});
 $('#inspector-close').addEventListener('click',()=>{document.body.classList.remove('mobile-inspector-open');$('#reading').focus({preventScroll:true})});
 $('#mobile-body').addEventListener('click',()=>{$('#document-outline a')?.click();document.querySelector('.mobile-actions').open=false});
 let outlineDoc=null;
 function outline(){
  if(!doc||outlineDoc===doc.id)return;
  outlineDoc=doc.id;
  const all=blocks().filter(b=>!b.source_only&&!b.excluded&&!b.layout_ignored),first=all.find(b=>b.kind==='heading')||all[0],items=first?[{id:first.id,label:'论文正文'}]:[];
  for(const b of all){
   const section=b.text.match(/^([IVX]+\.)\s+(INTRODUCTION|RELATED WORK|METHOD(?:S)?|EXPERIMENTS|DISCUSSION|CONCLUSION(?:S)?|RESULTS|BACKGROUND|APPENDIX)\b/);
   if(section)items.push({id:b.id,label:section[1]+' '+section[2].toLowerCase().replace(/\b\w/g,c=>c.toUpperCase())});
   else if(/^(?:REFERENCES|BIBLIOGRAPHY|参考文献)\s*$/i.test(b.text.trim()))items.push({id:b.id,label:'参考文献'});
  }
  $('#document-outline').innerHTML=items.map((item,i)=>`<a class="outline-link${i===0?' active':''}" href="#b-${esc(item.id)}" title="${esc(item.label)}">${esc(item.label)}</a>`).join('');
  document.querySelector('.contents-section').hidden=!items.length;
  $('#document-outline').querySelectorAll('a').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();const node=document.getElementById(link.hash.slice(1));if(!node)return;node.scrollIntoView({block:'start',behavior:'instant'});$('#document-outline').querySelectorAll('a').forEach(a=>a.classList.toggle('active',a===link));$('#reading').focus({preventScroll:true})}));
 }
 function sync(){
  $('#document-meta').textContent=doc?doc.page_count+' 页'+(doc.project_id?' / 源稿版本 '+doc.project_revision:''):'论文阅读与修订';
  $('#note-count').textContent=doc?.annotations?.filter(n=>n.status==='open').length||0;
  $('#proposal-count').textContent=doc?.proposals?.filter(p=>p.status!=='applied').length||0;
  $('#selection').classList.toggle('is-empty',!selected);
  if(!selected)$('#selection').textContent='点击一句正文，开始批注或改写。';
  for(const id of ['whole','save-note','rewrite','translate-one'])$('#'+id).disabled=!selected;
  for(const id of ['translate','export','pdf-toggle','batch-rewrite','context-manager'])$('#'+id).disabled=!doc;
  for(const id of ['source-editor','compile','project-export'])$('#'+id).disabled=!(project||doc?.project_id);
  document.querySelectorAll('[data-trigger]').forEach(el=>el.disabled=$('#'+el.dataset.trigger).disabled);
  $('#pdf-toggle').setAttribute('aria-pressed',String(!$('#pdf').hidden));
  $('#notes').querySelectorAll('.note').forEach(el=>{el.tabIndex=0;el.setAttribute('role','button');el.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();el.click()}}});
  $('#proposals').querySelectorAll('.proposal').forEach(el=>{el.tabIndex=0;el.setAttribute('role','button');el.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();el.click()}}});
  outline();
 }
 const originalRender=render;render=function(){originalRender();sync()};
 const originalChoose=choose;choose=function(...args){originalChoose(...args);sync();if(matchMedia('(max-width:640px)').matches)document.body.classList.add('mobile-inspector-open')};
 const originalOpen=openDoc;
 openDoc=async function(id){await originalOpen(id);try{localStorage.setItem('wenshu-last-document',id)}catch{};const first=$('#document-outline a');if(first){document.getElementById(first.hash.slice(1))?.scrollIntoView({block:'start',behavior:'instant'})}sync()};
 $('#pdf-toggle').addEventListener('click',()=>sync());
 $('#note').addEventListener('input',()=>{$('#save-note').classList.toggle('has-draft',!!$('#note').value.trim())});
 const modalObserver=new MutationObserver(()=>{if($('#modal').open){const h=$('#modal-content h2');if(h){if(!h.id)h.id='operation-title';$('#modal').setAttribute('aria-labelledby',h.id)}$('#modal-content').querySelectorAll('label').forEach((label,i)=>{if(label.querySelector('input,select,textarea'))return;const field=label.nextElementSibling;if(field?.matches('input,select,textarea')){if(!field.id)field.id='dialog-field-'+i;label.htmlFor=field.id}})}sync()});
 modalObserver.observe($('#modal'),{attributes:true,attributeFilter:['open']});
 modalObserver.observe($('#modal-content'),{childList:true,subtree:true});
 sync();
})();
