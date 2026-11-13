/* A conservative, tested joint recipe domain. No arbitrary freehand output is presented as attainable. */
let jointModel=null,jointRows=new Map(),autoFit=null,autoTargets=null,autoDragging=null,autoFrame=0,autoLastProjection='';
let factoryModel=null,autoPreviewTimer,autoManualAnchor=null;
function autoManualKey(){return JSON.stringify({model:state?.model_id,profile:activeProfileKey(),config,budget:+$('budgetValue').value,input:inputNits()})}
function autoUnavailable(){return !!(ablValues().enabled||state?.native_abl?.enabled)}
function syncAutoAvailability(){
 const blocked=autoUnavailable(),controls=$('autoControls');
 if(blocked&&!controls.disabled){fitWanted='';fitConfirmed='';fitBusy=false;if(autoFit)autoFit.fit_id=null;autoDragging=null}
 controls.disabled=blocked;controls.classList.toggle('auto-disabled',blocked);
 $('autoChartHost').inert=blocked;
 $('autoChartHost').setAttribute('aria-disabled',String(blocked));
 if(blocked)$('autoChartTip').hidden=true;
 return blocked;
}
function syncAutoRefresh(){
 const changed=autoManualAnchor!==null&&autoManualKey()!==autoManualAnchor;
 $('autoReset').disabled=autoUnavailable()||!changed||!!state?.busy;
 $('autoReset').title=changed?'用当前已手动修改的SF/Alpha、预算及PQ输入替换目标预览；不写入设备':'没有曲线之外的手动改动；只拖动目标不会启用此按钮';
}

const autoKnots=[0,.001,.01,.1,.5,1,2,5,10,25,50,75,100];
function axisPosition(area,mode){
 if(mode!=='log')return Math.max(0,Math.min(1,area/100));
 return area<=0?0:Math.max(.08,Math.min(1,.08+.92*(Math.log10(Math.max(area,.00001))+5)/7));
}
function axisArea(position,mode){
 position=Math.max(0,Math.min(1,position));
 return mode==='log'?(position<.08?0:10**(((position-.08)/.92)*7-5)):position*100;
}
function axisTicks(mode){return mode==='log'?[0,.001,.01,.1,1,10,100]:[0,10,25,50,75,100]}
function setChartAxis(value){for(const id of ['uniformChartAxis','autoChartAxis','ablVolumeAxis'])$(id).value=value}
function jointRecipe(config,level){
 if(!jointModel)return null;
 return jointModel.recipes.find(r=>Object.keys(config).every(k=>JSON.stringify(config[k])===JSON.stringify(r.configs[level][k])))||null;
}
function jointRaw(recipe,level,area,budget){
 if(!jointModel)return null;
 const row=jointRow(recipe,level),areas=jointModel.areas;if(!row)return null;
 budget=Math.max(0,Math.min(86,Math.round(budget)));area=Math.max(0,Math.min(100,area));
 const right=areas.findIndex(x=>x>=area),hi=right<0?areas.length-1:right,lo=Math.max(0,hi-1);
 const t=areas[hi]===areas[lo]?0:(area-areas[lo])/(areas[hi]-areas[lo]);
 return row.raw[lo][budget]+(row.raw[hi][budget]-row.raw[lo][budget])*t;
}
function jointEstimate(recipe,level,area,budget){const row=jointRow(recipe,level);return calibratedEstimate(jointRaw(recipe,level,area,budget),level,area,inputNits(),apertureAt(row,area),row)}
function jointEstimateForConfig(value,area){return responseForConfig(value,area,$('level').value,$('tone').value)}
function nearestJointBudget(nits,area,level,tone,previous){
 const recipe=jointRecipe(config,level);if(!recipe)return previous;
 let best=previous,distance=Infinity;
 for(let b=0;b<=86;b++){const d=Math.abs(jointEstimate(recipe.id,level,area,b).nits-nits);if(d<distance-.01||Math.abs(d-distance)<.01&&Math.abs(b-previous)<Math.abs(best-previous)){best=b;distance=d}}
 return best;
}
function candidateVectors(recipe,level,budget){
 return autoKnots.map(area=>jointEstimate(recipe,level,area,budget).nits);
}
function factoryNit(area,level){return opticalFactory(level,area)}
function saveAutoPreview(){
 clearTimeout(autoPreviewTimer);
 if(!autoTargets||selectedProfileKey()!==activeProfileKey())return;
 const preview={targets:autoTargets.map(r=>r.map(v=>Math.max(0,Math.min(10000,v)))),mode:$('autoMode').value,ceiling:+$('autoCeiling').value};
 const key=activeProfileKey();
 autoPreviewTimer=setTimeout(()=>rawApi('auto-preview',{preview,_profile:key}).catch(e=>error(e.message)),140);
}
let fitTimer,fitWanted='',fitConfirmed='',fitTask=null,fitBusy=false,fitError='';
function requestAutoFit(){
 if(!autoTargets||!state||!config||!state.model_confirmed||autoUnavailable()||$('page-auto').hidden)return;
 const input={config:copy(config),level:+$('level').value,input_nits:inputNits(),tone:+$('tone').value,_model:state.model_id,targets:autoTargets[0].slice(),ceiling:+$('autoCeiling').value,_profile:activeProfileKey()};
 const key=JSON.stringify(input);if(key===fitWanted)return;fitWanted=key;fitBusy=true;fitError='';clearTimeout(fitTimer);renderAuto();
 fitTimer=setTimeout(runAutoFit,180);
}
async function runAutoFit(){
 if(autoUnavailable())return;
 if(fitTask)return fitTask;
 fitTask=(async()=>{while(!autoUnavailable()&&fitWanted!==fitConfirmed){const key=fitWanted;
  try{const result=await rawApi('auto-fit',JSON.parse(key));if(key!==fitWanted)continue;autoFit=result.fit;autoFit.peakBudgets=autoKnots.map(()=>autoFit.budget);autoFit.longBudgets=autoKnots.map(()=>autoFit.budget);fitConfirmed=key;fitBusy=false;renderAuto()}
  catch(e){if(key===fitWanted){fitConfirmed=key;fitBusy=false;if(autoFit)autoFit.fit_id=null;fitError='拟合未完成：'+e.message;renderAuto()}break}
 }})().finally(()=>{fitTask=null;if(!autoUnavailable()&&fitWanted!==fitConfirmed)runAutoFit()});return fitTask;
}
function autoEnvelope(){return autoKnots.map(a=>a?10000:0)}
function resistTarget(requested,minimum,maximum){
 const span=Math.max(100,maximum-minimum);
 if(requested>maximum)return maximum+Math.tanh((requested-maximum)/span)*span*.07;
 if(requested<minimum)return minimum-Math.tanh((minimum-requested)/span)*span*.07;
 return requested;
}
function planFromFit(fit,mode,ceiling){
 return {fit_id:fit.fit_id,mode:'global',ceiling,budget:fit.budget,input_nits:inputNits()};
}
function resetAutoFromState(fromCurrent=false){
 if(!jointModel||!factoryModel||!opticalModel||!state||jointModel.format!=='mi-joint-response-v2')return;
 if(!fromCurrent&&autoTargets&&autoManualAnchor!==null){requestAutoFit();return}
 const row=configRow();if(!row){requestConfigPrediction();return}
 const preview=fromCurrent?null:state.auto_preview,saved=fromCurrent?null:state.auto_plan,level=+$('level').value,recipe=jointRecipe(config,level),cap=preview?.ceiling??saved?.ceiling??Math.max(24,state.runtime.budget);
 $('autoCeiling').value=cap;$('autoMode').value='global';
 const budget=fromCurrent?+$('budgetValue').value:state.runtime.budget;
 const value=area=>interpolate(jointModel.areas.map((a,i)=>[a,row.nits?.[i]?.[budget]??0]),area,true);
 autoTargets=[autoKnots.map(value),autoKnots.map(value)];if(preview)autoTargets=copy(preview.targets);
 autoFit={recipe:'preview-current',config:copy(config),budget,peak:autoKnots.map(value),long:autoKnots.map(value),peakBudgets:autoKnots.map(()=>budget),longBudgets:autoKnots.map(()=>budget)};
 autoManualAnchor=autoManualKey();autoLastProjection='';fitWanted='';fitConfirmed='';renderAuto();requestAutoFit();
}
async function commitAuto(){
 if(!autoFit?.fit_id||fitBusy)throw Error('请等待当前目标的拟合完成');
 if(autoUnavailable())throw Error('请先关闭并应用计时ABL，再使用自动拟合');
 if(!requireAdb('auto')||!requireSelectedProfile())return;
 if(!state.live_debug)throw Error('先开启实时调试，再按应用可达方案；图形编辑始终只是预览');
 const plan=planFromFit(autoFit,$('autoMode').value,+$('autoCeiling').value);
 await api('auto-apply',{...plan,_field:'auto',_fields:['uniform','sf-0',...Array.from({length:8},(_,i)=>'alpha-'+i)]});
 config=copy(state.draft);controls();$('budgetValue').value=$('budgetRange').value=state.runtime.budget;pendingUniform=null;autoManualAnchor=autoManualKey();localFeedback('auto','applied','方案已一次性写入；后续手动参数独立，不自动重放方案');renderUx();
}
function resolveAuto(){
 if(autoUnavailable())return;
 if(!jointModel||!factoryModel||!opticalModel||!autoTargets)return;
 const cap=+$('autoCeiling').value;if(!Number.isInteger(cap)||cap<0||cap>86)return;
 requestAutoFit();
 renderAuto();saveAutoPreview();
}
function autoTooltip(index,event){
 if(!autoFit)return;const tip=$('autoChartTip'),host=$('autoChartHost').getBoundingClientRect();
 tip.textContent=autoKnots[index]+'% 窗口\n目标 ≈ '+autoTargets[0][index].toFixed(1)+' nit / 默认 ≈ '+(factoryNit(autoKnots[index],+$('level').value)?.toFixed(1)||'待加载')+' nit\n拟合峰值 ≈ '+autoFit.peak[index].toFixed(1)+' nit 等效 · '+autoFit.peakBudgets[index]+'/86\n持续 ≈ '+autoFit.long[index].toFixed(1)+' nit 等效 · '+autoFit.longBudgets[index]+'/86\n同一组Alpha/SF共同作用；共用统计占比的点绑定预算；非光学实测';tip.hidden=false;
 tip.style.left=Math.max(0,Math.min(host.width-250,event.clientX-host.left+12))+'px';tip.style.top=Math.max(0,event.clientY-host.top-100)+'px';
}
function renderAuto(){
 syncAutoAvailability();
 if(state?.local_assets?.ready===false){$('autoModelScope').textContent=state.local_assets.message;$('autoApply').disabled=true;return}
 syncAutoRefresh();
 if(state){
  const abl=ablValues().enabled,ablPending=!abl&&state.native_abl.enabled;let reason=abl?'累计ABL已开启：自动联合拟合和应用不可用。先关闭计时ABL，或保留ABL并手动调节。':ablPending?'关闭ABL的草稿尚未应用：先在APL与ABL控制点击应用，再应用自动拟合。':state.tuning_context?.hdr_input===false?'实际HDR输入尚未就绪：可以预览，但不能应用调光。':state.tuning_context?.backlight&&+state.tuning_context.backlight!==100?'系统背光不是100：当前nit参考以100为基准，先恢复系统背光100再应用。':!config.dynamic?'动态Alpha关闭：Alpha0–7不会影响输出；本次只能用SF1和预算拟合。开启动态Alpha可使用全部Alpha。':selectedProfileKey()!==activeProfileKey()?'当前调光组合尚未载入：点击“选择配置”后才可应用。':!state.connected?'当前仅离线计算预览；连接ADB并开启实时调试后，才可写入拟合方案。':!state.live_debug?'实时调试关闭：仍可编辑目标曲线，但不能将拟合参数写入显示器。':'';
  $('autoAblSupport').textContent=(reason?'⚠ '+reason:'统一预算自动拟合已就绪；累计ABL不参与拟合。');$('autoAblSupport').classList.toggle('blocking-warning',!!reason);
  $('autoApply').disabled=state.busy||fitBusy||!autoFit?.fit_id||!state.model_confirmed||abl||ablPending||!state.connected||!state.live_debug||selectedProfileKey()!==activeProfileKey()||state.tuning_context?.hdr_input===false||!!(state.tuning_context?.backlight&&+state.tuning_context.backlight!==100);
 }
 if(!jointModel||!state||!autoFit||!opticalModel||!factoryModel)return;
 if(!$('page-auto').hidden)requestAutoFit();
 const mode=$('autoMode').value,axis=$('autoChartAxis').value,style=$('autoChartStyle').value,cap=+$('autoCeiling').value,column=0;
 const level=+$('level').value,settings=autoFit.config,upper=autoEnvelope();
 const W=900,H=360,L=68,R=24,T=28,B=52,PW=W-L-R,PH=H-T-B,ymax=autoDragging?.ymax||Math.ceil(Math.max(200,...autoTargets[column],...autoFit.peak,...jointModel.areas.map(a=>factoryNit(a,level)))/250)*250;
 const x=a=>L+axisPosition(a,axis)*PW,y=n=>H-B-n/ymax*PH,svg=$('autoChart');svg.dataset.ymax=ymax;
 let content=barGradient('auto');for(let i=0;i<=4;i++){const v=ymax*i/4;content+='<path class="grid" d="M'+L+' '+y(v)+'H'+(W-R)+'"/><text class="axis" x="'+(L-10)+'" y="'+(y(v)+4)+'" text-anchor="end">'+v+'</text>'}
 for(const a of axisTicks(axis))content+='<text class="axis" x="'+x(a)+'" y="'+(H-B+23)+'" text-anchor="middle">'+a+'%</text>';
 const defaults=jointModel.areas.map(a=>[x(a),y(factoryNit(a,level))]),fitted=autoKnots.map((a,i)=>[x(a),y(autoFit.peak[i])]);
 content+='<path class="factory-fill" d="'+smoothPath(defaults)+' L'+(W-R)+','+y(0)+' L'+L+','+y(0)+' Z"/><path class="factory-curve" d="'+smoothPath(defaults)+'"/><path class="peak" d="'+smoothPath(fitted)+'"/><path class="requested-curve" d="'+smoothPath(autoTargets[column].map((v,i)=>[x(autoKnots[i]),y(v)]))+'"/>';
 for(let i=0;i<autoKnots.length;i++){
  if(style==='bar'){const n=(column?autoFit.long:autoFit.peak)[i];content+='<rect data-auto-point="'+i+'" x="'+(x(autoKnots[i])-3)+'" y="'+y(n)+'" width="6" height="'+Math.max(0,y(0)-y(n))+'" class="opaque-bar" fill="url(#auto-gradient)"/>'}
  content+='<circle class="handle requested-handle" data-auto-point="'+i+'" data-column="'+column+'" cx="'+x(autoKnots[i])+'" cy="'+y(autoTargets[column][i])+'" r="6" tabindex="'+(i?'0':'-1')+'" role="slider" aria-label="'+autoKnots[i]+'% '+(column?'持续':'峰值')+'目标" aria-valuemin="0" aria-valuemax="'+Math.max(1000,Math.round(upper[i]))+'" aria-valuenow="'+Math.round(autoTargets[column][i])+'"/>';
 }
 content+='<text class="axis" x="'+L+'" y="14">'+inputNits()+' nit PQ输入 · '+(column?'持续目标/预测':'峰值目标/预测')+' · 截图校准近似</text>';
 if(svg.dataset.markup!==content){svg.innerHTML=content;svg.dataset.markup=content}
 $('autoRecipe').textContent='联合搜索 · SF1 '+settings.sf[0]+' / Alpha0 '+settings.alpha[0]+' / Alpha1 '+settings.alpha[1]+' · 预算 '+autoFit.budget+'/86'+(autoFit.rmse!==undefined?' · RMS '+autoFit.rmse+'%':'')+(autoFit.worst_error!==undefined?' · 最差窗口误差 '+autoFit.worst_error+'%':'');
 $('autoParameters').textContent='允许SF1、全部Alpha0–7与统一预算；SF2–5、DC、Blend及Dynamic保持当前组合原值。Alpha2–7以强正则趋向16，Alpha1次之；通常Alpha按序不下降。仅小窗先升后降再回升时允许Alpha1低于Alpha0；大窗极低亮目标放松高Alpha偏好。仍保留真实拟合误差，再兼顾光晕和黑场。SF ['+settings.sf.join(', ')+'] Alpha ['+settings.alpha.join(', ')+']';
 $('autoConstraint').textContent='一个全局预算与同一组局部统计参数共同拟合，不能独立控制每个窗口。不支持累计ABL自动拟合。'+autoLastProjection;
 const progress=state.fit_progress,building=fitBusy&&progress&&progress.done<progress.total;
 $('autoModelScope').textContent=(configRow()?.scope||'正在计算当前机型预测')+'。'+(autoFit.report?.note||'联合搜索全部Alpha；原厂函数计算，未采样组合仍为估算。')+' 只有按应用才写一次，累计ABL不参与拟合。';
 $('autoCurrentState').textContent=fitError?fitError:ablValues().enabled?'累计ABL已开启：这里只显示当前参数预览，不进行自动拟合':!fitBusy&&!autoFit.fit_id?'当前参数预览 · 尚无可应用的拟合结果':fitBusy?(building?(progress.message||'正在计算')+' '+progress.done+'/'+progress.total+(progress.workers?' · '+progress.workers+'个计算进程':''):'正在拟合最新目标；旧预测线为上一轮结果，不可应用'):autoDragging?'预览拖动中 · 不写设备':feedbackLocal.get('auto')?.message||'最新拟合已就绪；按应用可达方案才一次写入';

}
function autoMove(index,column,requested){
 if(autoUnavailable())return;
 if(!requireSelectedProfile())return;
 const upper=autoEnvelope(+$('autoCeiling').value,+$('level').value),bounded=Math.max(0,Math.min(10000,resistTarget(requested,0,Math.max(1000,upper[index]))));
 autoTargets[column][index]=bounded;
 if($('autoMode').value==='global')autoTargets[1]=autoTargets[0].slice();
 requestAutoFit();
 const actual=(column?autoFit.long:autoFit.peak)[index],delta=Math.abs(requested-actual);
 autoLastProjection=delta>1?' 目标与模型拟合相差约 '+delta.toFixed(1)+' nit；目标保留，应用的是拟合参数，不把预测或目标当作实测结果。':'';
 renderAuto();saveAutoPreview();
}
async function rebuildAutoPreview(){
 if($('autoReset').disabled)return;
 clearTimeout(autoPreviewTimer);await operationQueue;
 const key=autoManualKey();localFeedback('auto','running','正在按已手动修改的本地值刷新预览…');
 do{await requestConfigPrediction()}while(!configRow()&&predictionPending&&key===autoManualKey());
 if(key!==autoManualKey())throw Error('计算期间手动参数又有变化，请按最新值重新刷新');
 if(!configRow())throw Error('当前参数预测未就绪，未覆盖目标；请等预测完成后重试');
 resetAutoFromState(true);saveAutoPreview();
 localFeedback('auto','draft','已用手动值刷新目标；未写设备');
}
function bindAuto(){
 for(const event of ['input','change'])document.addEventListener(event,()=>queueMicrotask(syncAutoRefresh));
 const svg=$('autoChart');
 svg.addEventListener('pointerdown',event=>{const p=event.target.closest('[data-column]');if(autoUnavailable()||!p||!+p.dataset.autoPoint||!autoFit||!requireSelectedProfile())return;event.preventDefault();autoDragging={index:+p.dataset.autoPoint,column:+p.dataset.column,ymax:+svg.dataset.ymax};svg.setPointerCapture(event.pointerId);$('autoChartTip').hidden=true});
 svg.addEventListener('pointermove',event=>{
  if(autoDragging){const box=svg.getBoundingClientRect(),requested=(360-52-(event.clientY-box.top)/box.height*360)/(360-28-52)*autoDragging.ymax;cancelAnimationFrame(autoFrame);autoFrame=requestAnimationFrame(()=>autoMove(autoDragging.index,autoDragging.column,requested));return}
  const p=event.target.closest('[data-auto-point]');if(p&&!autoUnavailable())autoTooltip(+p.dataset.autoPoint,event);else $('autoChartTip').hidden=true;
 });
 svg.addEventListener('pointerup',event=>{if(!autoDragging)return;cancelAnimationFrame(autoFrame);autoDragging=null;if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);renderAuto();saveAutoPreview()});
 svg.addEventListener('pointercancel',()=>{cancelAnimationFrame(autoFrame);autoDragging=null;resetAutoFromState()});
 svg.addEventListener('pointerout',event=>{if(event.target.closest('[data-auto-point]'))$('autoChartTip').hidden=true});
 svg.addEventListener('pointerleave',()=>{$('autoChartTip').hidden=true});
 svg.addEventListener('keydown',event=>{const p=event.target.closest('[data-column]');if(autoUnavailable()||!p||!+p.dataset.autoPoint||!['ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();const i=+p.dataset.autoPoint,j=+p.dataset.column,old=(j?autoFit.long:autoFit.peak)[i];autoMove(i,j,old+(event.key==='ArrowUp'?10:-10));saveAutoPreview();svg.querySelector('[data-auto-point="'+i+'"][data-column="'+j+'"]')?.focus()});
 for(const kind of ['uniform','auto'])$(kind+'ChartAxis').onchange=()=>{state.ui_preferences.chart_axis=$(kind+'ChartAxis').value;setChartAxis(state.ui_preferences.chart_axis);act(savePreferences);renderCharts();renderAuto();if(ablForecast)renderAblVolume(ablForecast)};
 $('autoCeiling').onchange=resolveAuto;
 $('autoChartStyle').onchange=renderAuto;$('autoApply').onclick=()=>act(commitAuto);$('autoReset').onclick=()=>act(rebuildAutoPreview);
 installFeedback($('autoApply').parentElement,'auto');
 fetch('/factory-output.json').then(r=>r.json()).then(data=>{factoryModel=data;nitScaleCache.clear();if(jointModel&&opticalModel&&state){autoFit=null;resetAutoFromState()}});
 fetch('/joint-output.json').then(r=>{if(!r.ok)throw Error('联合模型未加载');return r.json()}).then(data=>{jointModel=data;for(const row of data.rows)jointRows.set(row.recipe+':'+row.level,row);if(state&&factoryModel&&opticalModel)resetAutoFromState()}).catch(e=>{$('autoModelScope').textContent=e.message});
}
