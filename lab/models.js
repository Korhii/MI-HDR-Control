/* Model first: do not silently enter the 32-inch controller for an unknown monitor. */
let modelDialogTask=null,modelSelectionDismissed=false;
function showModelSelection(force=false){
 if(!state||(!force&&(state.model_confirmed||modelSelectionDismissed)))return Promise.resolve(!!state?.model_confirmed);
 if(modelDialogTask)return modelDialogTask;
 modelDialogTask=dialogQueue.then(()=>new Promise(resolve=>{
  const dialog=document.createElement('dialog');dialog.className='risk-dialog app-dialog model-choice';
  dialog.innerHTML='<div class="caution-stripe"></div><div class="instrument-code">DEVICE IDENTITY / FIRST STEP</div><h2>识别显示器型号</h2><p>先按本机EDID型号与物理尺寸分流；连接ADB后，再核对原厂活动屏型与固件。未知设备不会默认进入32寸写入路径。</p><a href="/model-guide" target="_blank" rel="noopener">机型、曲线与推算来源说明 ↗</a><div class="model-results"></div><div class="flex"><button class="model-cancel">取消</button><button class="model-refresh">重新侦测</button><button class="model-enter primary">进入对应工作台</button></div><details><summary>未接入目标显示器？仅离线查看</summary><p class="muted">离线选择不是识别成功。后续写入仍需实际ADB屏型与固件校验；旧27寸107号屏型不作为2026版。</p><div class="flex"><button data-offline-model="27u-2026">查看27寸2026</button><button data-offline-model="32u-2026">查看32寸2026</button></div></details><p class="model-error" role="status"></p>';
  const results=dialog.querySelector('.model-results'),enter=dialog.querySelector('.model-enter'),status=dialog.querySelector('.model-error');
  function paint(){results.replaceChildren();const rows=state.model_detection?.monitors||[];let supported=0;
   for(const row of rows){const label=document.createElement('label');label.className='model-result';const input=document.createElement('input');input.type='radio';input.name='detected-model';input.value=row.instance;input.disabled=!row.model_id;input.dataset.model=row.model_id||'';if(row.model_id&&supported++===0)input.checked=true;const text=document.createElement('span');text.textContent=row.name+' · '+(row.diagonal_estimate||'未知')+' 英寸\n'+(row.model_id==='27u-2026'?'27寸2026分支':row.model_id==='32u-2026'?'32寸2026分支':'未识别')+'\n'+row.basis;label.append(input,text);results.append(label)}
   if(!rows.length)results.textContent=state.model_detection?.error||'未检测到活动显示器。请检查显示连接后重试，或仅离线查看。';enter.disabled=!supported;
  }
  const cancel=dialog.querySelector('.model-cancel'),dismiss=()=>{if(cancel.disabled)return;modelSelectionDismissed=true;dialog.close();dialog.remove();resolve(false)};cancel.onclick=dismiss;
  const choose=async(model,monitor,offline=false)=>{enter.disabled=cancel.disabled=true;status.textContent='正在载入独立的机型配置…';try{await api('model-select',{model_id:model,monitor,offline,_field:'model'});await waitOperation();if(!state.model_confirmed||state.model_id!==model)throw Error(state.error||'机型未载入');dialog.close();dialog.remove();resolve(true)}catch(e){cancel.disabled=false;status.textContent=e.message;paint()}};
  enter.onclick=()=>{const selected=dialog.querySelector('input:checked');if(selected)choose(selected.dataset.model,selected.value)};
  dialog.querySelector('.model-refresh').onclick=async()=>{try{await api('model-detect');await waitOperation();paint()}catch(e){status.textContent=e.message}};
  for(const b of dialog.querySelectorAll('[data-offline-model]'))b.onclick=()=>choose(b.dataset.offlineModel,null,true);
  dialog.oncancel=e=>{e.preventDefault();dismiss()};paint();document.body.append(dialog);dialog.showModal();
 }));dialogQueue=modelDialogTask.then(()=>{});return modelDialogTask.finally(()=>{modelDialogTask=null});
}
function renderModelIdentity(){
 if(!state)return;let box=$('modelIdentity');
 if(!box){box=document.createElement('div');box.id='modelIdentity';box.className='model-identity';box.innerHTML='<strong></strong><span></span><button type="button">重新识别机型</button>';document.querySelector('.connection-strip').prepend(box);box.querySelector('button').onclick=()=>showModelSelection(true)}
 box.querySelector('strong').textContent=state.model_spec?.title||'等待识别显示器';
 box.querySelector('span').textContent=state.device_model?.verified?'ADB屏型已复核 · '+state.device_model.variant:state.model_confirmed?'EDID/离线分支已选择 · 等待ADB屏型复核':'尚未完成型号识别';
 box.querySelector('button').disabled=state.connected||state.busy;
 let note=$('modelPredictionNote');if(!note){note=document.createElement('small');note.id='modelPredictionNote';note.className='model-prediction-note';box.after(note)}
 note.textContent=(state.model_id==='27u-2026'?'27寸：标准=HGiG，10000 nit PQ表直接锚点；SF/Alpha、光场与其他输入响应借用32寸。截图的游戏/电影列尚未唯一对应亮暗选项。':'32寸：保留原有HGiG标定与独立配置。')+(+$('tone').value===5?'':' 当前亮暗模式为原厂ARM64 TMO等效输入预测，固定元数据/纯窗/静态；不是该模式的光学实测。');
}
