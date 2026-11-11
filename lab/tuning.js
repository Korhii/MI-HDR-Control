/* Offline response curves and explicitly gated live controls. No screen test is started here. */
let outputModel=null,outputIndex=new Map(),operationQueue=Promise.resolve(),requestCounter=0;
let liveDebugPending=false,lastDisplayedAdbPort=null;
let riskConsent=null,pendingUniform=null,patternEditTimer,haloEditTimer,dragPoint=null,topFeedbackField=null;
const haloEdits=new Set();
const feedbackLocal=new Map();
const unitNames={unit01:'初·绿紫',unit00:'零·蓝银',unit02:'二·赤橙',unit08:'八·桃绿',mark06:'六·蓝金',mono:'素·黑白'};
const fieldForOperation={'profile-defaults':'profile-defaults','software-defaults':'software-defaults','all-defaults':'factory','auto-apply':'auto','module-defaults':'module-defaults','quick-budget':'uniform','runtime-draft':'uniform','runtime-set':'uniform','native-abl-draft':'native-abl','abl':'abl','profile-select':'profile','live-debug':'live','connect':'connection','auto-connect':'connection','permanent-write':'permanent','permanent-remove':'permanent','apply-profile':'profile','pattern-config':'pattern','pattern-draft':'pattern','pattern-start':'pattern','close-pattern':'pattern','restore':'restore','config-load':'configuration'};
const noFeedback=new Set(['backup-ack','heartbeat','sensors','permanent-status','preferences','risk-unlock','risk-lock','model-select','model-detect']);
function modelRaw(budget,area,level){
 if(!outputModel||!Number.isFinite(+budget)||!Number.isFinite(+area))return null;
 budget=Math.max(0,Math.min(86,Math.round(+budget)));area=Math.max(0,Math.min(100,+area));
 if(area>0&&area<.1)area=.1;
 const windows=outputModel.windows,hi=windows.findIndex(x=>x>=area),right=hi<0?windows.length-1:hi,left=Math.max(0,right-1);
 const a=outputIndex.get(level+':'+windows[left]+':'+budget),b=outputIndex.get(level+':'+windows[right]+':'+budget);
 if(!a||!b)return null;
 const t=windows[left]===windows[right]?0:(area-windows[left])/(windows[right]-windows[left]);
 return {raw:a.raw+(b.raw-a.raw)*t,actual:a.actual_zone_percent+(b.actual_zone_percent-a.actual_zone_percent)*t,sampled:windows.includes(area),budget};
}
function windowEstimate(value,area,level,tone){return responseForConfig(value,area,level,tone)}
function operationRisk(op,data){
 let values=[];
 if(op==='auto-apply')values=[data.budget];
 else if(['quick-budget','runtime-set','runtime-draft'].includes(op))values=[data.budget];
 else if(op==='live-debug'&&data.enabled||op==='apply-profile'){
  const p=state.configuration.profiles[state.selected_backlight_level+':'+state.tone];values=[p.budget];
 }else if(op==='profile-select'){
  const p=state.configuration.profiles[data.level+':'+data.tone];values=[p.budget];
 }else if(['config-load','permanent-write'].includes(op))values=Object.values(op==='config-load'?data.config.profiles:state.configuration.profiles).flatMap(p=>[p.budget]);
 return values.length&&Math.max(...values)>(state.risk_budget||41);
}
function localFeedback(field,status,message){feedbackLocal.set(field,{status,message});topFeedbackField=field;renderFeedback()}
async function ensureRisk(op,data){
 const dangerous=operationRisk(op,data),permanent=op==='permanent-write'&&dangerous;
 if(!dangerous||!permanent&&state.risk_unlocked)return;
 if(!riskConsent){
  $('riskPermanentNote').hidden=!permanent;$('riskSessionNote').hidden=permanent;
  $('riskTitle').textContent=permanent?'⚠ 危险值永久写入确认':'⚠ 超范围调节警告';
  $('riskAccept').checked=false;$('riskConfirm').disabled=true;
  $('riskDialog').showModal();
  riskConsent=new Promise(resolve=>{
   $('riskCancel').onclick=()=>{$('riskDialog').close();resolve(false)};
   $('riskDialog').oncancel=event=>{event.preventDefault();$('riskDialog').close();resolve(false)};
   $('riskConfirm').onclick=()=>{$('riskDialog').close();resolve(true)};
  });
 }
 const accepted=await riskConsent;riskConsent=null;
 if(!accepted)throw Error('未确认风险：此修改未应用');
 if(permanent){data.permanent_risk_ack=true;return}
 if(state.busy)await waitOperation();
 await rawApi('risk-unlock',{acknowledged:true});
 // risk-unlock is asynchronous like every device operation; wait for its completed state.
 await waitOperation();if(!state.risk_unlocked)throw Error('风险解锁未完成，未应用');
}
function dispatchOperation(op,data={}){
 data={_profile:activeProfileKey(),...data};
 if(['pattern-config','pattern-draft','pattern-start','close-pattern'].includes(op))return rawApi(op,{...data,_field:'pattern',_request_id:'local-'+(++requestCounter)}).then(result=>{state.pattern_config=data.config||state.pattern_config;if(result.result){state.operation_results.pattern=result.result;state.last_operation=result.result;feedbackLocal.delete('pattern');renderFeedback()}return result.result});
 const deviceEdit=['auto-apply','quick-budget','runtime-draft','runtime-set','quick-halo','draft','update','native-abl-draft','abl','profile-select','calibration'].includes(op)||op==='module-defaults'&&!['pattern','sensors'].includes(data.module);
 if(deviceEdit&&op!=='profile-select'&&!requireSelectedProfile())return Promise.reject(Error('请先点击选择配置'));
 if(deviceEdit&&!requireAdb(data._field||fieldForOperation[op]||op))return Promise.reject(Error('请先连接ADB，再调整显示器参数'));
 if(noFeedback.has(op))return rawApi(op,data);
 const field=data._field||fieldForOperation[op]||op;
 localFeedback(field,'queued','等待提交…');
 const work=async()=>{
  try{
   await ensureRisk(op,data);if(state.busy)await waitOperation();
   const id='ui-'+(++requestCounter);localFeedback(field,'running','正在执行…');
   await rawApi(op,{...data,_field:field,_request_id:id});
   await waitOperation();
   const result=state.operation_results?.[field];
   if(result?.id===id){feedbackLocal.delete(field);for(const f of data._fields||[])feedbackLocal.delete(f);if(result.status==='error')throw Error(result.message)}
   if(field==='uniform'&&pendingUniform===data.budget)pendingUniform=null;
   renderFeedback();return result;
  }catch(e){const status=e.message.includes('未确认风险')?'blocked':'error';for(const f of [field,...(data._fields||[])])localFeedback(f,status,e.message);throw e}
 };
 const next=operationQueue.then(work,work);operationQueue=next.catch(()=>{});return next;
}
function hasPendingUniform(){return pendingUniform!==null}
function markUniform(value){pendingUniform=value;localFeedback('uniform','draft','草稿已编辑，按应用才写入')}
function installFeedback(parent,field){
 let label=parent.querySelector('.field-feedback[data-field="'+field+'"]');
 if(!label){label=document.createElement('small');label.className='field-feedback';label.dataset.field=field;label.setAttribute('aria-live','polite');parent.append(label)}
}
function renderFeedback(){
 if(typeof state==='undefined'||!state)return;
 for(const label of document.querySelectorAll('.field-feedback')){
  const entry=feedbackLocal.get(label.dataset.field)||state.operation_results?.[label.dataset.field];
  label.dataset.status=entry?.status||'';label.textContent=entry?.message||'尚未调整';
 }
 const local=feedbackLocal.get(topFeedbackField),last=local||state.last_operation;
 $('topOperation').textContent=last?(state.last_operation?.operation||'参数')+' · '+last.message:'未下发调整';
 if(state.error&&!state.connected)$('topOperation').textContent='ADB异常 / 未确认：'+state.error;
 $('topOperation').className=last?.status==='error'||state.error&&!state.connected?'danger-note':'';
}
function warningValues(){
 const limit=state?.risk_budget||41;
 for(const input of [$('budgetValue')]){
  const dangerous=input.value!==''&&+input.value>limit;input.classList.toggle('danger-value',dangerous);
  let note=input.parentElement.querySelector('.danger-note[data-for="'+input.id+'"]');
  if(dangerous&&!note){note=document.createElement('small');note.className='danger-note';note.dataset.for=input.id;input.after(note)}
  if(note){note.hidden=!dangerous;note.textContent='⚠ '+input.value+'/86 超出验证范围'+(state?.risk_unlocked?' · 本次已解锁':' · 未解锁，禁止应用')}
 }
 $('riskLock').hidden=!state?.risk_unlocked;
}
function applyUnit(unit){
 unit=unit in unitNames?unit:'mono';document.documentElement.dataset.unit=unit;
 const mark=document.querySelector('.eva-unit-mark');if(mark)mark.textContent=({unit01:'01',unit00:'00',unit02:'02',unit08:'08',mark06:'06',mono:'MI'})[unit];
 $('unitCode').textContent=({unit01:'01 / GREEN · PURPLE',unit00:'00 / BLUE · SILVER',unit02:'02 / RED · ORANGE',unit08:'08 / PINK · GREEN',mark06:'06 / BLUE · GOLD',mono:'DISPLAY / MONO'})[unit];
 for(const button of document.querySelectorAll('[data-unit-choice]'))button.setAttribute('aria-checked',String(button.dataset.unitChoice===unit));
 try{localStorage.setItem('mi-hdr-unit',unit)}catch(e){}
}
function sidebarMode(){
 const auto=window.innerWidth<1100,manual=!!state?.ui_preferences.sidebar_collapsed;
 document.documentElement.classList.toggle('sidebar-collapsed',auto||manual);
 $('sidebarHide').textContent=auto?'窄窗自动隐藏 · 移至左侧唤出':manual?'固定展开侧栏':'隐藏侧栏 · 左侧悬停唤出';
}
function queueHalo(field){
 if(!requireAdb(field))return;
 enableModuleLive('halo');haloEdits.add(field);localFeedback(field,'queued','已编辑，等待提交…');clearTimeout(haloEditTimer);
 haloEditTimer=setTimeout(()=>{const fields=[...haloEdits];haloEdits.clear();act(()=>api(state.live_debug&&moduleRealtime.halo?'quick-halo':'draft',{config:copy(config),_field:'halo',_fields:fields}))},180);
}
let patternWanted=null,patternSending=false;
async function flushPattern(){
 if(patternSending)return;patternSending=true;
 try{while(patternWanted){const value=patternWanted;patternWanted=null;await api(state.pattern?'pattern-config':'pattern-draft',{config:value})}}
 catch(e){error(e.message)}finally{patternSending=false}
}
function schedulePattern(){
 enableModuleLive('pattern');clearTimeout(patternEditTimer);patternWanted=pattern();localFeedback('pattern','queued','本地图样更新…');
 patternEditTimer=setTimeout(flushPattern,40);
}
async function writePermanent(){
 document.activeElement?.blur();
 // Let the input debounces enqueue before taking the permanent configuration snapshot.
 await new Promise(resolve=>setTimeout(resolve,260));await flushBudget();await operationQueue;await refresh();
 const sameHalo=Object.keys(config).every(k=>JSON.stringify(config[k])===JSON.stringify(state.draft[k]));
 if(pendingUniform!==null||!sameHalo||+$('level').value!==state.selected_backlight_level||+$('tone').value!==state.tone)
  throw Error('仍有未提交或被拦住的参数；尚未永久保存。请先处理参数旁的提示。');
 if(!await uiDialog('将把当前机型的12组配置保存到显示器，并由显示器开机后自行加载、持续续租。关闭PC不会恢复默认。'+(state.permanent_boot_verified?'':'此机型的当前适配器尚未完成重启验收，可能需要手动移除或恢复。')+'初始备份已保存，请勿删除。是否继续？',{title:'永久写入显示器 · '+(state.model_spec?.title||''),confirmText:'确认保存并启用本机方案',severity:'danger'}))return;
 await api('permanent-write',{experimental_ack:true});
}
function featureWarning(key,anchor,message){
 let note=$('availability-'+key);if(!note){note=document.createElement('p');note.id='availability-'+key;note.className='availability-warning';note.setAttribute('role','status');$(anchor).parentElement.after(note)}
 note.hidden=!message;note.textContent=message?'⚠ '+message:'';
}
function renderAvailability(){
 if(!state)return;
 const selected=selectedProfileKey()===activeProfileKey(),online=state.connected,live=state.live_debug;
 featureWarning('profile','selectProfile',selected?'':'尚未载入此分区档位 × 亮暗模式：当前为预览，先点击“选择配置”才能修改和写入该组合。');
 const inputReason=state.tuning_context?.hdr_input===false?'实际HDR输入尚未就绪：控光写入暂不可用，先等待输入稳定。':state.tuning_context?.backlight&&+state.tuning_context.backlight!==100?'系统背光不是100：当前nit参考以100为基准，请先恢复系统背光100。':'';
 const reason=!online?'ADB未连接：设备调节不可用，本地图样和曲线预览仍可用。':inputReason?inputReason:!selected?'先选择当前调光组合，再开始调节。':!live?'实时调试未开启：控光和模块启动不可用；开启顶栏实时调试后再操作。':'';
 featureWarning('halo','apply',reason);
 featureWarning('runtime','runtimeLoad',reason||(!state.runtime.loaded?'读取模块尚未加载：先初始化模块，再应用统一设置。':''));
 featureWarning('permanent','permanentWrite',!online?'永久写入需要先连接ADB。':!state.device_model?.verified?'机型尚未复核：永久写入暂不可用。':!state.initial_backup?.ready?'初始备份未就绪：永久写入暂不可用。':pendingUniform!==null?'统一设置还有未应用的草稿：先点击应用，再永久保存。':!state.permanent_boot_verified?'永久写入已开放，但本机型尚未完成重启验收。保存后显示器自行续租，关闭PC不会回默认；点击后必须确认。':'');
 featureWarning('abl-level','nativeAblEnabled',+$('level').value===1?'低档不执行计时ABL：本组不能启用累计机制；中/高档才支持。':'');
 $('nativeAblEnabled').disabled=+$('level').value===1;
 featureWarning('alpha-dynamic','otherControls',config.dynamic?'':'动态Alpha关闭：所有Alpha值暂不参与输出和拟合，只能由SF与预算塑形；开启动态Alpha后再调整。');
 featureWarning('abl-off','nativeAblEnabled',ablValues().enabled?'':'计时ABL草稿未启用：整区灰化，参数与预测不可用；勾选后可编辑，按统一设置应用才改变设备。');
}
/* Display-only budget chart is implemented in abl.js. */
function renderTuning(){
 const discovery=state.adb_discovery;$('autoDeviceStatus').textContent=discovery?.message||'先点自动寻找；未找到时可展开高级连接';$('autoDeviceStatus').title=$('autoDeviceStatus').textContent;$('connect').disabled=state.busy;
 if(state.connected&&state.connection&&state.connection.port!==lastDisplayedAdbPort){lastDisplayedAdbPort=state.connection.port;$('port').value=lastDisplayedAdbPort}
 $('liveDebug').setAttribute('aria-pressed',String(state.live_debug));$('liveDebug').textContent=['restore-error','disconnect-error'].includes(state.debug_phase)?'恢复/断开未确认 · 重试关闭':state.live_debug?'● 关闭调试 · 恢复默认并断开':'○ 开启实时调试 · 自动连接ADB';$('liveDebug').disabled=liveDebugPending||['connecting','applying','restoring','disconnecting'].includes(state.debug_phase);
 $('topAdb').textContent=state.adb_discovery?.searching?'ADB · '+state.adb_discovery.message:state.connected?'ADB 在线'+(state.adb_age_seconds>12?' · 读数待刷新':' · '+(state.adb_age_seconds??0)+'s前读回'):'ADB 未连接';
 $('topMode').textContent=state.live_debug?'LIVE / 预算与自动方案需按应用':state.persistence?.running&&!state.persistence.paused?'LOCAL / 显示器永久方案自行运行':state.connected?'DRAFT / 已连接，调试未开启':'OFFLINE / 调参前请连接ADB';
 for(const id of ['runtimeLoad','runtimeStart','apply'])$(id).disabled=state.busy||!state.live_debug;
 $('uniformPreviewState').textContent=pendingUniform!==null?'DRAFT / 当前编辑值尚未确认执行':state.live_debug?'LIVE / 已提交的统一设置':'SAVED / 控制器草稿';
 renderProfileSelection();
 if(!state.connected)$('runtimeStatus').textContent='ADB已断开 · 当前模块状态未读取';
 document.querySelector('.connection-strip').classList.toggle('needs-connection',!state.connected);renderResetScope();syncModuleRealtime();warningValues();renderFeedback();renderCharts();renderAvailability();
}
function bindTuning(){
 try{applyUnit(localStorage.getItem('mi-hdr-unit')||'mono')}catch(e){applyUnit('mono')}
 $('riskAccept').onchange=()=>{$('riskConfirm').disabled=!$('riskAccept').checked};
 $('liveDebug').onclick=()=>{if(liveDebugPending)return;liveDebugPending=true;renderTuning();act(async()=>{try{await api('live-debug',{enabled:!['restore-error','disconnect-error'].includes(state.debug_phase)&&!state.live_debug})}finally{liveDebugPending=false;renderTuning()}})};
 $('permanentWrite').onclick=()=>act(writePermanent);
 $('riskLock').onclick=()=>act(()=>rawApi('risk-lock'));
 for(const button of document.querySelectorAll('[data-unit-choice]'))button.onclick=()=>{state.ui_preferences.unit=button.dataset.unitChoice;applyUnit(button.dataset.unitChoice);act(savePreferences)};
 $('sidebarHide').onclick=()=>{state.ui_preferences.sidebar_collapsed=!state.ui_preferences.sidebar_collapsed;sidebarMode();act(savePreferences)};
 $('sidebarEdge').onpointerenter=()=>document.documentElement.classList.add('sidebar-peek');
 $('sidebarEdge').onfocus=()=>document.documentElement.classList.add('sidebar-peek');
 document.querySelector('.sidebar').addEventListener('pointerleave',()=>document.documentElement.classList.remove('sidebar-peek'));
 document.querySelector('.sidebar').addEventListener('focusout',event=>{if(!event.currentTarget.contains(event.relatedTarget))document.documentElement.classList.remove('sidebar-peek')});
 matchMedia('(max-width:1000px)').addEventListener('change',sidebarMode);
 for(const id of ['pixel_width','pixel_height','rows','cols','area_percent','input_nits','background_nits','label','geometry','mode','seconds','monitor']){$(id).addEventListener('input',schedulePattern);installFeedback($(id).parentElement,'pattern')}
 for(const id of ['level','tone'])$(id).addEventListener('change',()=>{renderProfileSelection();localFeedback('profile','queued','尚未切换；点击选择配置后才切换设备与参数')});
 installFeedback(document.querySelector('.budget-editor'),'uniform');installFeedback($('selectProfile').parentElement,'profile');installFeedback($('patternStart').parentElement,'pattern');
 bindUniformChart();
 fetch('/window-output.json').then(r=>{if(!r.ok)throw Error('离线曲线数据未加载');return r.json()}).then(data=>{outputModel=data;for(const row of data.rows)outputIndex.set(row.level+':'+row.window_percent+':'+row.budget,row);if(state)renderUx()}).catch(e=>{$('uniformChartScope').textContent=e.message});
 sidebarMode();
}

const defaultDescriptions={auto:'当前组合整组控光设备默认：原厂SF/Alpha、官方预算路径及ABL；其他11组不变',budget:'恢复官方预算路径并关闭实验累计ABL；光晕不变',halo:'当前档位原厂SF/Alpha/DC/Blend/Dynamic；预算不变',pattern:'50%单窗、4000nit PQ输入等默认图样；离线时不显示图样',sensors:'关闭自动采样；保留历史读数'};
function currentModule(){return [...document.querySelectorAll('[data-panel]')].find(p=>!p.hidden)?.dataset.panel||'auto'}
async function resetCurrentModule(){
 const module=currentModule();if(module==='save')return;
 if(module==='sensors'){$('sensorAuto').checked=false;localFeedback('module-defaults','applied','自动采样已关闭；保留历史读数');return}
 const haloFields=[...Array.from({length:5},(_,i)=>'sf-'+i),...Array.from({length:8},(_,i)=>'alpha-'+i),'dc-0','blend-0','dynamic-0'];
 let fields=[];
 if(['auto','budget'].includes(module)){clearTimeout(budgetTimer);clearTimeout(ablDraftTimer);ablDirty=false;budgetWanted=null;pendingUniform=null;fields.push('uniform')}
 if(['auto','halo'].includes(module)){clearTimeout(haloEditTimer);haloEdits.clear();fields.push(...haloFields)}
 if(module==='pattern'){clearTimeout(patternEditTimer);fields.push('pattern')}
 for(const field of fields)feedbackLocal.delete(field);
 await operationQueue;
 await api('module-defaults',{module,_field:'module-defaults',_fields:fields});
 if(['auto','budget'].includes(module))fillAbl(state.native_abl);
 config=copy(state.draft);controls();fillPattern(state.pattern_config);$('budgetValue').value=$('budgetRange').value=state.runtime.budget;
 pendingUniform=null;autoFit=null;renderUx();
}
