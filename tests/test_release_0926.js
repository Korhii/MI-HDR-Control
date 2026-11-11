/* Regression tests for real 0.9.26 functions; no browser, ADB or monitor writes. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
function context(){
 const fields=new Map();
 const c=vm.createContext({console,Map,Set,WeakMap,Promise,JSON,Math,Number,String,Array,Object,Infinity,URLSearchParams,
  setTimeout:()=>1,clearTimeout:()=>{},queueMicrotask:()=>{},window:{},document:{addEventListener:()=>{}},location:{search:''},
  $:id=>{if(!fields.has(id))fields.set(id,{value:({level:'3',tone:'5',budgetValue:'24'})[id]||'',textContent:'',dataset:{}});return fields.get(id)},
  copy:v=>JSON.parse(JSON.stringify(v)),state:{model_id:'32u-2026',model_confirmed:true,connected:true,live_debug:true,profile_key:'3:5',local_assets:{ready:true},telemetry:{}},
  config:{sf:[255,255,255,255,255],alpha:[3,5,7,9,11,13,15,16],dc:8,blend:8,dynamic:1},
  operationQueue:Promise.resolve(),pendingUniform:null,requireAdb:()=>true,requireSelectedProfile:()=>true,
  saveAutoPreview:()=>{},renderUx:()=>{},calls:[],api:async function(op,data){c.calls.push({op,data});},
  flushAblDraft:async()=>{},renderParameterChanges:()=>{},rawApi:async()=>({}),placeholders:[]});
 vm.runInContext(fs.readFileSync(path.join(root,'lab/abl.js'),'utf8'),c);
 vm.runInContext(fs.readFileSync(path.join(root,'lab/modules.js'),'utf8'),c);
 vm.runInContext(`ablDraft={enabled:true,l_th:18288,e0:100,divisor:600,r_reset:9760};renderAbl=()=>{};ablPlaceholder=(m,p)=>placeholders.push(p);`,c);
 return c;
}
const tick=()=>new Promise(r=>setImmediate(r));
const rows=[];
async function test(name,fn){try{await fn();rows.push({name,passed:true});}catch(e){rows.push({name,passed:false,error:e.message});}}
(async()=>{
 await test('new forecast input immediately invalidates old coupled charts',()=>{
  const c=context();vm.runInContext(`ablForecast={old:true};ablForecastKey='old';ablWantedKey='old';config.alpha[0]=4;scheduleAblPrediction();`,c);
  assert.equal(vm.runInContext('ablForecast',c),null);
  assert.ok(c.placeholders.includes('pending'));
 });
 await test('disabled ABL wins over missing local assets',()=>{
  const c=context();vm.runInContext(`ablDraft.enabled=false;state.local_assets.ready=false;let rendered=false;renderAbl=()=>{rendered=true};scheduleAblPrediction();if(!rendered)throw Error('disabled state was bypassed');`,c);
 });
 await test('Apply captures one budget/ABL snapshot at click time',async()=>{
  const c=context();let release;c.flushAblDraft=()=>new Promise(r=>{release=r});
  const promise=vm.runInContext('applyUniform()',c);
  vm.runInContext(`$('budgetValue').value='31';ablDraft.e0=200;`,c);release();await promise;
  assert.equal(c.calls[0].data.budget,24);assert.equal(c.calls[0].data.native_abl.e0,100);
  assert.equal(c.calls[0].data._profile,'3:5');
 });
 await test('Apply does not discard a newer budget draft while waiting',async()=>{
  const c=context();let release;c.api=(op,data)=>{c.calls.push({op,data});return new Promise(r=>{release=r})};
  vm.runInContext('pendingUniform=24',c);const promise=vm.runInContext('applyUniform()',c);await tick();
  vm.runInContext(`$('budgetValue').value='31';pendingUniform=31`,c);release();await promise;
  assert.equal(vm.runInContext('pendingUniform',c),31);
 });
 await test('profile change during Apply prevents submission to a different profile',async()=>{
  const c=context();let release;c.flushAblDraft=()=>new Promise(r=>{release=r});const promise=vm.runInContext('applyUniform()',c);
  vm.runInContext(`state.profile_key='2:1';$('level').value='2';$('tone').value='1'`,c);release();
  await assert.rejects(promise,/组合/);assert.equal(c.calls.length,0);
 });
 await test('late ABL reply cannot replace a newer generation',async()=>{
  const c=context(),replies=[];c.rawApi=(op,p)=>new Promise(r=>replies.push({p,r}));c.accepted=[];
  vm.runInContext(`renderAblForecast=()=>accepted.push(ablForecast.generation);ablWantedKey=JSON.stringify({revision:1});ablGeneration=1`,c);
  const promise=vm.runInContext('runAblPrediction()',c);await tick();
  vm.runInContext(`ablWantedKey=JSON.stringify({revision:2});ablGeneration=2`,c);
  replies[0].r({forecast:{generation:1}});await tick();assert.equal(replies.length,2);
  replies[1].r({forecast:{generation:2}});await promise;assert.deepEqual(c.accepted,[2]);
 });
 await test('slice spacing preserves selected seconds when observation range changes',()=>{
  const c=context();vm.runInContext(`ablSliceSeconds=2;ablSliceScaleFor(10);const second=ablSliceScaleFor(25);if(ablSliceSeconds!==2||second.mid!==2.5)throw Error('spacing changed');for(const p of [-1,-.5,0,.5,1])if(Math.abs(ablSlicePosition(second,ablSliceAt(second,p))-p)>.00001)throw Error('mapping mismatch')`,c);
 });
 await test('offline file import is a PC operation and is not blocked by the input guard',()=>{
  const c=context(),listeners={};c.document.addEventListener=(name,fn)=>{listeners[name]=fn};c.addEventListener=()=>{};
  c.error=()=>{};c.localFeedback=()=>{};c.document.querySelector=()=>({classList:{add:()=>{}}});
  vm.runInContext(fs.readFileSync(path.join(root,'lab/responsive.js'),'utf8'),c);vm.runInContext('applyUiScale=()=>{};state.connected=false;bindResponsive()',c);
  let blocked=false;const target={type:'file',id:'file',closest:s=>s==='.workspace'?{}:s.startsWith('input,')?target:null,matches:()=>true};
  listeners.change({type:'change',target,preventDefault:()=>{blocked=true},stopImmediatePropagation:()=>{blocked=true}});assert.equal(blocked,false);
 });
 await test('offline display parameter changes remain blocked by the same guard',()=>{
  const c=context(),listeners={};c.document.addEventListener=(name,fn)=>{listeners[name]=fn};c.addEventListener=()=>{};
  c.error=()=>{};c.localFeedback=()=>{};c.document.querySelector=()=>({classList:{add:()=>{}}});
  vm.runInContext(fs.readFileSync(path.join(root,'lab/responsive.js'),'utf8'),c);vm.runInContext('applyUiScale=()=>{};state.connected=false;bindResponsive()',c);
  let blocked=false;const target={type:'range',id:'sf1',closest:s=>s==='.workspace'?{}:s.startsWith('input,')?target:null,matches:()=>false};
  listeners.change({type:'change',target,preventDefault:()=>{blocked=true},stopImmediatePropagation:()=>{blocked=true}});assert.equal(blocked,true);
 });
 await test('HDR annotation remains contrasted on black and full-white inputs',()=>{
  const cpp=fs.readFileSync(path.join(root,'scripts/hdr_pattern_control.cpp'),'utf8');
  const m=cpp.match(/fg=bg>=([0-9.]+)\?([0-9.]+):([0-9.]+);/);assert.ok(m,'annotation color selector changed; review readability');
  const code=n=>{const p=(n/10000)**(2610/16384);return Math.round(((3424/4096+(2413/128)*p)/(1+(2392/128)*p))**(2523/32)*1023)};
  for(const bg of [0,.1,1,9.9,10,100,1000,10000]){
   const fg=bg>=Number(m[1])?Number(m[2]):Number(m[3]);
   assert.ok(Math.abs(code(fg)-code(bg))>=200,`insufficient annotation code contrast at ${bg} nit`);
  }
 });
 console.log(JSON.stringify({tests:rows.length,passed:rows.filter(r=>r.passed).length,results:rows},null,2));process.exitCode=rows.every(r=>r.passed)?0:1;
})();
