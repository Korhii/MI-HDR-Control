/* Module windows share one local backend, but every device edit is bound to its loaded profile. */
let sharedControlsSeen=null;
const moduleRealtime={halo:true,pattern:true};
function syncModuleRealtime(){
 const module=currentModule(),manual=['auto','budget'].includes(module),halo=!!state?.halo_realtime;
 const status=$('moduleLiveStatus');status.textContent=manual?'编辑预览 · 按应用一次写入':module==='halo'?(state?.live_debug&&halo?'实时下发中 · 改动即生效':'参数自动下发已关闭'):'本地实时更新';
 status.title=manual?'本页没有自动应用开关；预算与ABL使用同一个应用按钮':'顶栏控制连接和总体调试；光晕页的实时按钮控制自动下发';
 $('apply').textContent=state?.live_debug&&halo?'实时调节中 · 点击关闭':'开始实时调节';
 $('apply').setAttribute('aria-pressed',String(!!state?.live_debug&&halo));
 $('apply').title='开启后SF/Alpha等改动自动下发；关闭只暂停自动下发，已写参数保持。再次编辑参数会自动开启；顶栏关闭实时调试才恢复默认并断开ADB。';
 $('haloLiveState').textContent=state?.live_debug&&halo?'实时写入 · 参数旁显示执行回执':'自动下发关闭 · 已写参数保持';
}
async function toggleHaloRealtime(){
 if(state.halo_realtime){clearTimeout(haloEditTimer);haloEdits.clear();await operationQueue;await api('halo-stop',{_field:'halo'});moduleRealtime.halo=false}
 else{if(!requireAdb('halo')||!requireSelectedProfile())return;if(!state.live_debug)throw Error('请先开启顶栏实时调试');await api('apply-profile',{_field:'halo'});moduleRealtime.halo=true}
 syncModuleRealtime();
}
function enableModuleLive(module){moduleRealtime[module]=true;syncModuleRealtime()}
async function applyUniform(){
 if(!requireAdb('uniform')||!requireSelectedProfile())return;
 if(!state.live_debug)throw Error('请先开启实时调试，再点击应用统一亮度设置');
 const budget=+$('budgetValue').value,nativeAbl=ablValues(),profile=activeProfileKey();
 await flushAblDraft();await operationQueue;
 if(activeProfileKey()!==profile||selectedProfileKey()!==profile)throw Error('调光组合已变化，本次统一设置未应用；请在目标组合重新确认');
 await api('quick-budget',{budget,native_abl:nativeAbl,_profile:profile,_field:'uniform',_fields:['native-abl']});
 saveAutoPreview();if(pendingUniform===budget)pendingUniform=null;renderUx();
}
function renderResetScope(){
 const button=$('allDeviceDefaults');if(!button)return;const module=currentModule(),all=module==='save',profile=module==='auto';
 button.dataset.scope=all?'device':profile?'profile':module;
 const names={budget:'统一亮度设置',halo:'光晕与控光',pattern:'HDR图样',sensors:'传感器采样'};
 const title=all?'恢复设备出厂调光':profile?'取消当前调光组合的profile的所有修改':'重置当前控制区参数 · '+names[module];
 const detail=all?'依据首次备份与原厂固件默认表恢复；移除本工具永久调光，保留账号、ADB及桌面':profile?`当前 ${activeProfileKey()} · 控光、预算、ABL、图样及自动预览；其他11组不动`:(defaultDescriptions[module]||'只重置本区；同组合其他控制区及其他11组不变');
 const markup='<small>'+(all?'DEVICE / INITIAL BACKUP':profile?'CURRENT PROFILE / 1 OF 12':'CURRENT CONTROL SECTION')+'</small><strong>'+title+'</strong><span>'+detail+'</span>';
 if(button.dataset.markup!==markup){button.innerHTML=markup;button.dataset.markup=markup;installFeedback(button,all?'factory':profile?'profile-defaults':'module-defaults')}
 button.disabled=all&&(!state?.connected||!state?.initial_backup?.ready);
 const backup=$('initialBackupStatus');if(backup){const b=state?.initial_backup;backup.textContent=b?.ready?'电脑初始备份已验证：'+b.pc_path+'\n'+(b.device_copy_exists?'显示器已有同一备份：'+b.device_path:'未创建显示器副本')+'\n不按IP、档位或配置另存初始备份。':b?.status==='error'?'备份检查未完成：'+b.message:!state?.connected?'显示器备份尚未检测。点击“自动寻找并连接”后先检查已有备份。':b?.status==='missing'?'已连接并检查，未找到当前设备可复用的初始备份。请选择保存位置；完成前不允许调光写入。':'正在核验已有备份，尚未允许调光写入。'}
}
function renderProfileSelection(){
 const native=state.native||{},same=selectedProfileKey()===activeProfileKey()&&String(native.g_video__vid_local_dimming)===$('level').value&&String(native.g_video__vid_hdr_tone_mapping_mode)===$('tone').value;
 $('selectProfile').disabled=!state.connected||same||state.busy;
 $('selectProfile').title=!state.connected?'先连接ADB，再选择调光组合':same?'设备与软件已经选用此调光组合':'切换显示器档位/模式并载入这一组独立参数';
}
async function resetCurrentProfile(){
 if(!requireSelectedProfile()||!await uiDialog('取消当前分区档位 × 亮暗模式的所有参数；其他11组不动。已连接时立即应用临时默认，不改写显示器保存的永久配置。继续？'))return;
 clearTimeout(budgetTimer);clearTimeout(haloEditTimer);clearTimeout(patternEditTimer);clearTimeout(autoPreviewTimer);clearTimeout(ablDraftTimer);ablDirty=false;
 budgetWanted=null;patternWanted=null;pendingUniform=null;haloEdits.clear();await operationQueue;
 await api('profile-defaults',{confirmed:true,_field:'profile-defaults'});feedbackLocal.clear();loadedProfile=null;autoFit=null;await refresh();
}
function syncSharedControls(){
 const next={draft:JSON.stringify(state.draft),nativeAbl:JSON.stringify(state.native_abl),pattern:JSON.stringify(state.pattern_config),budget:state.runtime.budget};
 if(sharedControlsSeen){
  const pending=prefix=>[...feedbackLocal].some(([k,v])=>prefix.test(k)&&['queued','running','error','blocked'].includes(v.status));
  if(next.draft!==sharedControlsSeen.draft&&!haloEdits.size&&!pending(/^(sf-|alpha-|dc-|blend-|dynamic-|halo)/)){config=copy(state.draft);controls();autoFit=null}
  if(next.pattern!==sharedControlsSeen.pattern&&!patternSending&&!patternWanted&&!pending(/^pattern/)){fillPattern(state.pattern_config);rowCache.clear();nitScaleCache.clear();autoFit=null}
  if(next.budget!==sharedControlsSeen.budget&&!hasPendingUniform())autoFit=null;
 }
 if(next.nativeAbl!==sharedControlsSeen?.nativeAbl&&!ablDirty)fillAbl(state.native_abl);
 sharedControlsSeen=next;
}
let overlayInput=null;
window.miRestoreInputFocus=()=>{if(overlayInput?.isConnected)overlayInput.focus({preventScroll:true})};
document.addEventListener('pointerdown',event=>{
 const field=event.target.closest('input,textarea,select,[contenteditable="true"]');
 if(!field||field.disabled||['range','checkbox','radio','button','submit','reset','color'].includes(field.type)||document.documentElement.dataset.overlay!=='true')return;
 overlayInput=field;window.chrome?.webview?.postMessage('keyboard-focus');
},true);
document.addEventListener('pointerup',()=>{
 if(document.documentElement.dataset.overlay!=='true'||!String(getSelection()))return;
 overlayInput=null;window.chrome?.webview?.postMessage('keyboard-focus');
});
window.miOverlayState=(enabled,editing=false)=>{
 document.documentElement.dataset.overlay=String(enabled);
 let hint=$('overlayHint');if(!hint){hint=document.createElement('small');hint.id='overlayHint';hint.className='overlay-hint';document.querySelector('.page-head').after(hint)}
 hint.textContent=enabled?(editing?'悬浮置顶 · 正在键盘输入；点击HDR图样后恢复不抢焦点的悬浮调参':'悬浮鼠标调参 · 不抢全屏焦点；点击数字/文字输入框即可键入，无需取消置顶'):'普通交互 · 可键盘输入；标题栏置顶图标可开启悬浮调参';
};
function activeProfileKey(){return typeof state==='undefined'||!state?'':state.profile_key||state.selected_backlight_level+':'+state.tone}
function selectedProfileKey(){return $('level').value+':'+$('tone').value}
function requireSelectedProfile(){if(selectedProfileKey()===activeProfileKey())return true;error('档位/模式尚未载入，请先点击“选择配置”');localFeedback('profile','blocked','先点击选择配置，再修改本组合');return false}
function detachModule(module){
 if(!uiPages[module])return;
 if(window.chrome?.webview)window.chrome.webview.postMessage('detach:'+module);
 else error('独立自绘窗口请从便携包EXE打开；浏览器调试模式不创建系统窗口');
}
function bindModules(){
 const advanced=document.querySelector('.connection-advanced');advanced.querySelector('.connection-cancel').onclick=()=>{advanced.open=false};advanced.addEventListener('keydown',event=>{if(event.key==='Escape'){advanced.open=false;advanced.querySelector('summary').focus()}});
 const guide=document.querySelector('a[href="/guide"]');if(guide)guide.onclick=event=>{event.preventDefault();act(async()=>{const response=await fetch('/guide');await uiDialog(await response.text(),{title:'参数与使用说明',confirmText:'关闭',notice:true})})};
 const global=document.createElement('button');global.id='allDeviceDefaults';global.className='factory-reset';global.innerHTML='<small>FACTORY DIMMING / ALL 12 PROFILES</small><strong>恢复设备出厂调光</strong><span>全部档位 × 亮暗模式 · 不清空账号、ADB或桌面</span>';
 document.querySelector('.page-head').after(global);
 global.onclick=()=>act(async()=>{
  if(!requireAdb('factory'))return;
  if(!await uiDialog('将按首次备份中的原厂固件依据恢复本工具涉及的调光参数，停止并清除本工具永久调光及其自定义模块。账号、ADB、桌面不变；不是整机系统重置。继续？',{title:'恢复设备出厂调光',confirmText:'恢复初始原厂调光',severity:'danger'}))return;
  clearTimeout(budgetTimer);clearTimeout(haloEditTimer);clearTimeout(patternEditTimer);clearTimeout(autoPreviewTimer);clearTimeout(ablDraftTimer);ablDirty=false;
  budgetWanted=null;patternWanted=null;pendingUniform=null;haloEdits.clear();await operationQueue;
  await api('all-defaults',{confirmed:true,_field:'factory'});await refresh();loadedProfile=null;autoFit=null;await refresh();
 });
 const restoreAll=global.onclick;global.onclick=()=>currentModule()==='save'?restoreAll():act(async()=>{if(currentModule()==='auto')return resetCurrentProfile();if(await uiDialog(defaultDescriptions[currentModule()]+'。同组合其他控制区与其他11组不变。继续？',{title:'仅重置当前控制区'}))await resetCurrentModule()});
 const backup=document.createElement('section');backup.className='card';backup.innerHTML='<h2>初始设备备份 <small>ORIGINAL DEVICE BASELINE</small></h2><p id="initialBackupStatus" style="white-space:pre-line;overflow-wrap:anywhere"></p><p class="muted">备份保存首次连接时的状态。恢复调光时结合这份备份与匹配固件的默认值，保留账号、ADB和桌面。Alpha/Blend/Dynamic 使用写入回执核对。</p>';
 $('page-save').prepend(backup);const choice=document.createElement('button');choice.id='backupLocations';choice.textContent='选择备份保存位置';choice.onclick=()=>chooseBackupLocation(true);backup.append(choice);
 const software=document.createElement('section');software.className='card';software.innerHTML='<h2>软件配置重置 <small>PC ONLY / 12 PROFILES</small></h2><p>恢复12组控制器配置为设备默认参考值，仅保存到PC；不改写当前屏幕、显示器永久配置或启动策略。当前活动会话保持不变；重新选择配置后载入默认值。</p><button id="softwareDefaults">恢复12个 profiles 的软件设置为默认</button><p class="muted">上方“恢复设备出厂调光”会按初始备份恢复原厂调光并清除本项目常驻调光；不是刷写原厂固件；“永久保存”才把自定义配置保存到显示器。普通软件调节由临时会话运行。</p>';
 $('page-save').prepend(software);$('softwareDefaults').onclick=()=>act(async()=>{if(!await uiDialog('仅重置PC内12组软件配置，当前显示器输出和已保存的永久方案不变。继续？'))return;clearTimeout(autoPreviewTimer);clearTimeout(haloEditTimer);clearTimeout(budgetTimer);haloEdits.clear();pendingUniform=null;budgetWanted=null;await operationQueue;await api('software-defaults',{confirmed:true,_field:'software-defaults'});feedbackLocal.clear();loadedProfile=null;autoFit=null;await refresh()});
 $('uniformApply').onclick=()=>act(applyUniform);
 renderResetScope();
 const button=document.createElement('button');button.id='detachModule';button.className='detach-module';button.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 5H5v14h14v-8M14 3h7v7M21 3l-9 9"/></svg><span>独立窗口</span>';
 const updateButton=()=>{renderResetScope();button.dataset.detach=currentModule();button.title='将'+uiPages[currentModule()].title+'弹出为独立窗口';button.setAttribute('aria-label',button.title)};
 button.onclick=()=>detachModule(currentModule());document.querySelector('.connection').append(button);
 for(const nav of document.querySelectorAll('[data-page]'))nav.addEventListener('click',updateButton);updateButton();
 const module=new URLSearchParams(location.search).get('module');
 if(module&&uiPages[module]){
  document.documentElement.dataset.moduleWindow=module;
  document.querySelector('[data-page="'+module+'"]').click();
  document.title=uiPages[module].title+' · MI HDR Control';
 }
}
window.miCloseModule=async()=>{
 try{document.activeElement?.blur();saveAutoPreview();await new Promise(r=>setTimeout(r,240));await flushPattern();await flushBudget();await operationQueue}
 finally{window.chrome?.webview?.postMessage('close-module-ready')}
};
