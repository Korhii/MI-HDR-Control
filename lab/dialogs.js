/* App-owned, theme-inheriting confirmations. Never delegate to browser chrome. */
let dialogQueue=Promise.resolve(),backupNoticeShown='';
function uiDialog(message,{title='确认操作',confirmText='确认',cancelText='取消',notice=false,severity='warning'}={}){
 const show=()=>new Promise(resolve=>{
  const dialog=document.createElement('dialog');dialog.className='risk-dialog app-dialog';dialog.dataset.severity=severity;
  dialog.innerHTML='<div class="caution-stripe"></div><div class="instrument-code">MI HDR / DEVICE CONTROL</div><h2></h2><p></p><div class="flex"><button class="dialog-cancel"></button><button class="dialog-confirm"></button></div>';
  dialog.querySelector('h2').textContent=title;dialog.querySelector('p').textContent=message;
  const cancel=dialog.querySelector('.dialog-cancel'),ok=dialog.querySelector('.dialog-confirm');
  cancel.textContent=cancelText;cancel.hidden=notice;ok.textContent=confirmText;
  const finish=value=>{dialog.close();dialog.remove();resolve(value)};
  cancel.onclick=()=>finish(false);ok.onclick=()=>finish(true);dialog.oncancel=e=>{e.preventDefault();finish(notice)};
  document.body.append(dialog);dialog.showModal();(notice?ok:cancel).focus();
 });
 const result=dialogQueue.then(show);dialogQueue=result.then(()=>{});return result;
}
let startupNoticeShown=false,startupNoticeTask=null;
function showStartupNotice(){
 if(new URLSearchParams(location.search).has('module'))return true;
 if(startupNoticeShown)return true;
 const key='mi-hdr-start:'+state.token;
 try{if(sessionStorage.getItem(key)){startupNoticeShown=true;return true}}catch(e){}
 if(!startupNoticeTask)startupNoticeTask=uiDialog(
  '个人借助 AI 工具制作的实验工具，仅适配 REDMI G Pro 32U 2026 / 27U 2026（27为推算）。\n\n错误参数可能导致黑屏、无法启动或设备损坏。参数的电流、温升和寿命安全未经测试，保修影响未确认；固件更新后可能失效。\n\n请保管好初始备份。退出时点击右上角“退出控制器”，等待窗口关闭后再拔线；不要直接结束进程。',
  {title:'开始使用前',confirmText:'知道了',notice:true}
 ).then(()=>{startupNoticeShown=true;try{sessionStorage.setItem(key,'1')}catch(e){}showBackupNotice()});
 return false;
}
let backupChoiceTask=null,backupChoiceDismissed=false;
function chooseBackupLocation(force=false){
 if(!state||new URLSearchParams(location.search).has('module'))return Promise.resolve(false);
 if(!force&&(state.backup_policy?.confirmed||backupChoiceDismissed))return Promise.resolve(!!state.backup_policy?.confirmed);
 if(backupChoiceTask)return backupChoiceTask;
 backupChoiceTask=dialogQueue.then(()=>new Promise(resolve=>{
  const d=document.createElement('dialog');d.className='risk-dialog app-dialog backup-choice';
  d.innerHTML='<div class="caution-stripe"></div><div class="instrument-code">INITIAL BACKUP / BEFORE DEVICE EDIT</div><h2>选择初始备份保存位置</h2><p>电脑备份是必选项，所有文件留在便携目录内。显示器副本可选；按设备序列号复用已有备份，不因IP、档位或配置改变重复创建。</p><label><input type="checkbox" checked disabled> 电脑 · 必选</label><label><input id="backupDeviceChoice" type="checkbox"> 同时保存到显示器</label><p class="backup-existing"></p><p class="muted">删除便携目录会删除电脑备份。若选择显示器副本，下次可从中恢复；否则首次状态快照丢失后不能找回。只读固件默认表仍可用于重建原厂调光依据，不意味着必须重置整机。已有显示器副本不会因改选“仅电脑”而删除。</p><div class="flex"><button class="backup-cancel">取消</button><button class="backup-confirm primary">保存选择</button></div>';
  d.querySelector('#backupDeviceChoice').checked=state.backup_policy?.device===true;
  d.querySelector('.backup-existing').textContent='电脑已检测到 '+(state.backup_inventory?.length||0)+' 台设备的初始备份；接入后核对稳定身份与完整性。';
  const cancel=d.querySelector('.backup-cancel'),dismiss=()=>{if(cancel.disabled)return;backupChoiceDismissed=true;d.close();d.remove();resolve(false)};
  cancel.onclick=dismiss;d.oncancel=e=>{e.preventDefault();dismiss()};d.querySelector('.backup-confirm').onclick=async()=>{
   const button=d.querySelector('.backup-confirm');button.disabled=cancel.disabled=true;
   try{await rawApi('backup-policy',{policy:{pc:true,device:d.querySelector('#backupDeviceChoice').checked,confirmed:true}});await waitOperation();d.close();d.remove();resolve(true)}catch(e){button.disabled=cancel.disabled=false;error(e.message)}
  };
  document.body.append(d);d.showModal();
 }));dialogQueue=backupChoiceTask.then(()=>{});return backupChoiceTask.finally(()=>{backupChoiceTask=null});
}
function showBackupNotice(){
 if(!showStartupNotice())return;
 if(!state?.model_confirmed){showModelSelection();return}
 if(!state?.backup_policy?.confirmed){chooseBackupLocation();return}
 const b=state?.initial_backup;if(!b?.ready||!b.notice_pending||backupNoticeShown===b.id||new URLSearchParams(location.search).has('module'))return;
 backupNoticeShown=b.id;
 const destination=b.device_selected?'电脑与显示器副本均已验证。':'仅电脑备份已验证。'+(b.device_copy_exists?'检测到已有显示器副本，保留但不重复写入。':'未创建显示器副本。');
 uiDialog(destination+'\n电脑：'+b.pc_path+(b.device_path?'\n已有显示器副本：'+b.device_path:'')+'\n\n备份记录本次首次连接时的设备状态，请另存一份。删除便携目录会同时删除电脑备份。调光恢复保留账号、ADB和桌面设置。',{title:'初始设备备份已就绪',confirmText:'知道了',notice:true}).then(confirmed=>confirmed&&rawApi('backup-ack').catch(e=>error(e.message)));
}

async function exportConfiguration(){
 const button=$('export');button.disabled=true;
 try{
  document.activeElement?.blur();await flushAblDraft();await operationQueue;
  await api('config-save',{pattern:pattern(),native_abl:ablValues()});await waitOperation();
  const result=await rawApi('config-export'),text=JSON.stringify(result.config,null,2);
  if(window.miNativeHost&&window.chrome?.webview){
   const status=await new Promise(resolve=>{window.miConfigExported=resolve;window.chrome.webview.postMessage('save-config:'+result.filename+'\n'+text)});
   if(status==='error')throw Error('配置导出未完成，请检查保存位置');
   if(status==='saved')localFeedback('configuration','applied','配置已导出');
  }else{
   const url=URL.createObjectURL(new Blob([text],{type:'application/json'})),link=document.createElement('a');
   link.href=url;link.download=result.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
 }finally{button.disabled=false;window.miConfigExported=null}
}
