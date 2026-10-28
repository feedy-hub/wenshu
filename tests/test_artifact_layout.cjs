const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','static','app.js'),'utf8');
const layout=vm.runInNewContext(source.slice(0,source.indexOf('/* END READING LAYOUT */'))+'\nReadingLayout');
const make=(page,id,text,bbox,extra={})=>({page,id,text,bbox,source_bbox:bbox.map(n=>n*800),kind:'paragraph',column:'left',...extra});
const doc={pages:[4,5].map(page=>({blocks:[
 make(page,`run-${page}`,'1 2 3 4 5 6 7 8',[.047,.24,.062,.55]),
 make(page,`single-${page}`,'9',[.047,.57,.062,.58]),
 make(page,`folio-${page}`,String(page-3),[.914,.071,.920,.080]),
 make(page,`body-${page}`,'1 2 3 4 5 6 7 8',[.2,.24,.6,.55]),
 make(page,`eq-${page}`,'(9)',[.95,.57,.97,.58],{source_only:true,kind:'equation'}),
]}))};
const original=JSON.stringify(doc);
assert.deepEqual(Array.from(layout.plan(doc,false),u=>u.id),['body-4','eq-4','body-5','eq-5']);
assert.equal(layout.plan(doc,false,true).length,10);
assert.equal(JSON.stringify(doc),original);
const title={pages:[{blocks:[
 make(4,'title-a','Holistic Facial Context-Augmented Spatio-Temporal Correlation',[.113,.112,.887,.133],{kind:'heading'}),
 make(4,'title-b','Learning for Lip Reading',[.345,.145,.655,.167],{kind:'heading'}),
 make(4,'authors','Ruoyao Xue and Wei He',[.179,.180,.802,.193],{kind:'heading'}),
]}]};
assert.equal(layout.plan(title,true)[0].blocks.length,2);
assert.equal(layout.plan(title,true).length,2);
console.log('Merged review numbers and offset folios hidden; body numbers, equations and anchors retained; title joined.');
