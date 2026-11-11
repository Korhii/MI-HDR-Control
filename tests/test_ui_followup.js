/* Current dialog/hover/ABL UI regression, with real functions and no device I/O. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),rows=[];
function context(){
 const fields=new Map(),dialogs=[];
 const field=id=>{if(!fields.has(id))fields.set(id,{value:'3',hidden:true,disabled:false,events:{},style:{},dataset:{},classList:{toggle(){}},addEventListener(n,f){this.events[n]=f},getBoundingClientRect:()=>({left:0,top:0,width:900,height:360}),focus(){}});return fields.get(id)};
 const c=vm.createContext({console,Promise,Map,Set,JSON,Array,Object,Number,Math,String,URLSearchParams,location:{search:''},window:{},
  setTimeout:()=>1,clearTimeout(){},queueMicrotask(){},fetch:()=>new Promise(()=>{}),cancelAnimationFrame(){},requestAnimationFrame(){},
  $:field,installFeedback(){},inputNits:()=>4000,opticalFactory:()=>500,activeProfileKey:()=> '3:5',selectedProfileKey:()=> '3:5',copy:v=>JSON.parse(JSON.stringify(v)),
  config:{dynamic:1},state:{native_abl:{enabled:false},busy:false,local_assets:{ready:true},model_confirmed:true,connected:false,tuning_context:{}},ablValues:()=>({enabled:false}),feedbackLocal:new Map(),requireSelectedProfile:()=>true,
  document:{addEventListener(){},body:{append(d){dialogs.push(d)}},createElement(){const nodes={};return {dataset:{},querySelector(k){return nodes[k]||(nodes[k]={hidden:false,focus(){}})},showModal(){},close(){},remove(){}}}}});
 vm.runInContext(fs.readFileSync(path.join(root,'lab/dialogs.js'),'utf8'),c);
 vm.runInContext(fs.readFileSync(path.join(root,'lab/auto.js'),'utf8'),c);
 return {c,field,dialogs};
}
async function test(name,fn){try{await fn();rows.push({name,passed:true})}catch(e){rows.push({name,passed:false,error:e.message})}}
(async()=>{
 await test('acknowledgement notice has no Cancel and Escape acknowledges',async()=>{
  const {c,dialogs}=context(),p=vm.runInContext("uiDialog('已完成',{notice:true,confirmText:'知道了'})",c);await Promise.resolve();
  const d=dialogs[0];assert.equal(d.querySelector('.dialog-cancel').hidden,true);d.oncancel({preventDefault(){}});assert.equal(await p,true);
 });
 await test('choice confirmation retains Cancel and Escape cancels',async()=>{
  const {c,dialogs}=context(),p=vm.runInContext("uiDialog('是否应用？')",c);await Promise.resolve();
  const d=dialogs[0];assert.equal(d.querySelector('.dialog-cancel').hidden,false);d.oncancel({preventDefault(){}});assert.equal(await p,false);
 });
 await test('tooltip disappears on moving from a node onto empty chart',()=>{
  const {c,field}=context();vm.runInContext('autoFit={peak:Array(13).fill(100),long:Array(13).fill(100),peakBudgets:Array(13).fill(24),longBudgets:Array(13).fill(24)};autoTargets=[Array(13).fill(100),Array(13).fill(100)];bindAuto()',c);
  const move=field('autoChart').events.pointermove;move({target:{closest:()=>({dataset:{autoPoint:'3'}})},clientX:100,clientY:100});assert.equal(field('autoChartTip').hidden,false);
  move({target:{closest:()=>null},clientX:110,clientY:110});assert.equal(field('autoChartTip').hidden,true);
 });
 await test('ABL draft disables the whole auto module and chart',()=>{
  const {c,field}=context();c.ablValues=()=>({enabled:true});vm.runInContext('syncAutoAvailability()',c);
  assert.equal(field('autoControls').disabled,true);assert.equal(field('autoChartHost').inert,true);assert.equal(field('autoChartTip').hidden,true);
 });
 await test('device ABL keeps module disabled until its off draft is applied',()=>{
  const {c,field}=context();c.state.native_abl.enabled=true;vm.runInContext('syncAutoAvailability()',c);assert.equal(field('autoControls').disabled,true);
  c.state.native_abl.enabled=false;vm.runInContext('syncAutoAvailability()',c);assert.equal(field('autoControls').disabled,false);assert.equal(field('autoChartHost').inert,false);
 });
 await test('entering auto after ABL import greys controls even without a fit result',()=>{
  const {c,field}=context();c.ablValues=()=>({enabled:true});c.nitText=()=>'';c.requestConfigPrediction=()=>{};c.explainControls=()=>{};c.document.querySelectorAll=()=>[];field('page-auto').hidden=false;
  vm.runInContext(fs.readFileSync(path.join(root,'lab/ux.js'),'utf8'),c);c.referenceEstimate=()=>null;vm.runInContext('renderUx()',c);
  assert.equal(field('autoControls').disabled,true);assert.equal(field('autoChartHost').inert,true);assert.ok(field('autoAblSupport').textContent.includes('累计ABL已开启'));
 });
 await test('redundant Save UI and historical defensive sentence removed',()=>{
  const html=fs.readFileSync(path.join(root,'lab/portable.html'),'utf8'),modules=fs.readFileSync(path.join(root,'lab/modules.js'),'utf8');
  assert.ok(!html.includes('id="save"'));assert.ok(!modules.includes('此项目以前已进行过调参'));assert.ok(!modules.includes('不冒充未修改原厂状态'));
 });
 await test('normal exit and concise risks are in the startup dialog, not a page footer',()=>{
  const html=fs.readFileSync(path.join(root,'lab/portable.html'),'utf8'),dialogs=fs.readFileSync(path.join(root,'lab/dialogs.js'),'utf8');
  assert.ok(!html.includes('class="exit-help"'));assert.ok(dialogs.includes('showStartupNotice'));assert.ok(dialogs.includes('退出控制器'));assert.ok(dialogs.includes('设备损坏'));assert.ok(dialogs.includes('AI 工具'));
 });
 await test('native export uses a Save As picker',()=>{
  const native=fs.readFileSync(path.join(root,'scripts/windows-launcher/desktop.cpp'),'utf8');assert.ok(native.includes('GetSaveFileNameW'));assert.ok(native.includes('save-config:'));
 });
 console.log(JSON.stringify({tests:rows.length,passed:rows.filter(r=>r.passed).length,results:rows},null,2));process.exitCode=rows.every(r=>r.passed)?0:1;
})();
