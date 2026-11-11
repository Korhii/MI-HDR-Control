let ablDraft=null,ablDirty=false,ablForecast=null,ablForecastKey='',ablWantedKey='',ablGeneration=0,ablTimer,ablDraftTimer,ablTask=null,ablParamRevision=0;
function ablValues(){return copy(ablDraft||state?.native_abl||{enabled:false,l_th:18288,e0:37491600,divisor:600,r_reset:9760})}
function fillAbl(p){
 ablDraft=copy(p);ablDirty=false;
 $('nativeAblEnabled').checked=p.enabled;$('ablEnergy').value=p.e0;$('ablEnergyRange').max=Math.max(149966400,Number(p.e0)||0);$('ablEnergyRange').value=p.e0;
 const speed=p.divisor?600/p.divisor:600;$('ablSpeed').value=+speed.toFixed(3);$('ablSpeedRange').value=Math.log2(speed);
 $('ablRecovery').value=$('ablRecoveryRange').value=p.r_reset;$('ablThresholdValue').value=$('ablThresholdRange').value=p.l_th;renderAbl();
}
function ablAvailable(){return !!ablDraft?.enabled&&+$('level').value!==1}
function ablPlaceholder(message,phase){
 const body=$('nativeAblCard').querySelector('.abl-body');if(body.dataset.ablDisplay===phase)return;body.dataset.ablDisplay=phase;
 for(const id of ['ablStableBars','ablDurationBars'])$(id).innerHTML='<svg class="abl-placeholder" viewBox="0 0 900 330" role="img" aria-label="'+message+'"><text x="450" y="165" text-anchor="middle">'+message+'</text></svg>';
 $('ablVolume').classList.add('abl-placeholder');$('ablVolume').innerHTML='<text x="550" y="330" text-anchor="middle">'+message+'</text>';
}
function renderAbl(){
 if(!ablDraft)return;
 const card=$('nativeAblCard'),off=!ablAvailable(),wasOff=card.classList.contains('abl-off');card.classList.toggle('abl-off',off);card.querySelector('.abl-body').setAttribute('aria-disabled',String(off));
 for(const field of $('nativeAblCard').querySelectorAll('.abl-body input,.abl-body select')){
  if(field.tagName==='INPUT'&&field.type!=='range'){field.readOnly=off;field.tabIndex=off?-1:0}else field.disabled=off;
 }
 $('ablThresholdRaw').textContent='raw '+ablDraft.l_th;$('ablSpeedRaw').textContent='分母 '+ablDraft.divisor+' · ΔK '+(Math.floor((31243-18288)/(ablDraft.divisor||Infinity))+1);
 $('ablRecoveryRaw').textContent='raw '+ablDraft.r_reset;
 if(off){
  clearTimeout(ablTimer);if(ablWantedKey){ablWantedKey='';ablGeneration++}ablForecast=null;ablForecastKey='';
  for(const button of card.querySelectorAll('.abl-body button'))button.disabled=true;
  const reason=+$('level').value===1?'低档不支持计时ABL · 本区不可用':'计时ABL草稿未启用 · 本区不可用';
  for(const [id,text] of [['ablLiveState',reason],['ablApplyState','本区已停用：参数、读回与预测不可用。启停设备端机制仍须点击“应用统一亮度设置”。'],['ablLoadValue','—'],['ablThresholdLive','未启用 · 不显示ABL负载判定'],['ablHz','— · 不可用'],['ablModelStatus','未启用 · 不计算ABL图表']])if($(id).textContent!==text)$(id).textContent=text;
  $('ablLiveState').classList.remove('abl-triggered');ablPlaceholder('未启用计时ABL · 预测不可用','off');return;
 }
 if(wasOff)renderParameterChanges();
 if(!ablForecast)ablPlaceholder('等待最新ABL预测…','pending');
 $('ablApplyState').textContent=ablDirty?'草稿已改 · 全部耦合预测重算；按统一设置应用才下发':'与控制器已保存参数一致；预算/ABL按应用才下发';
 const t=state?.telemetry,live=t?.status==='live-driver'&&state.connected&&(state.runtime.loaded||state.runtime.active);
 $('ablHz').textContent=live&&t.driver_hz?t.driver_hz+' Hz · 驱动读回':'60 Hz · 待读回，暂估';$('ablLoadValue').textContent=live?String(t.load):'—';
 $('ablThresholdLive').textContent=live?'草稿门槛 '+ablDraft.l_th+'：'+(t.load>ablDraft.l_th?'已达到（严格大于）':'未达到')+'；设备已应用门槛 '+t.l_th:'负载门槛状态：等待当前驱动读回';
 const triggered=live&&t.gain_used<65535;
 const nativeBypass=live&&!t.active&&(t.level??state.selected_backlight_level)===3;
 $('ablLiveState').textContent=nativeBypass?'高档原厂路径 · 本累计机制未接管':live?(triggered?(t.active?'实验ABL 正在限亮':'原厂ABL 正在限亮'):'ABL 未限亮')+' · K '+(t.active?t.k:t.native_k)+' · E '+(t.active?t.energy:t.native_energy)+' · 本轮G '+t.gain_used+'/65535':state?.connected?'ABL 状态未读取':'ABL 状态：ADB未连接';
 $('ablLiveState').classList.toggle('abl-triggered',!!triggered);
}
function markAbl(){ablParamRevision++;ablDirty=true;renderAbl();renderParameterChanges();scheduleAblPrediction();clearTimeout(ablDraftTimer);ablDraftTimer=setTimeout(()=>act(flushAblDraft),240);autoFit=null;renderCharts()}
async function flushAblDraft(){clearTimeout(ablDraftTimer);if(!ablDirty)return;if(!requireAdb('native-abl')||!requireSelectedProfile())return;const p=ablValues();await api('native-abl-draft',{config:p,_field:'native-abl'});if(JSON.stringify(p)===JSON.stringify(ablValues())){ablDirty=false;renderAbl()}}
function scheduleAblPrediction(){
 if(!ablAvailable()){renderAbl();return}
 if(state?.local_assets?.ready===false){$('ablModelStatus').textContent=state.local_assets.message;return}
 if(!state?.model_confirmed||!config||!ablDraft)return;
 const input={_model:state.model_id,revision:ablParamRevision,tone:+$('tone').value,config:copy(config),level:+$('level').value,budget:+$('budgetValue').value,native_abl:ablValues(),factory:false,hz:state.telemetry?.driver_hz||60};
 const key=JSON.stringify(input);if(key===ablWantedKey)return;ablWantedKey=key;ablGeneration++;clearTimeout(ablTimer);
 ablForecast=null;ablForecastKey='';ablPlaceholder('等待最新ABL预测…','pending');
 $('ablModelStatus').textContent='正在按最新完整快照重算：持续时间 / 稳态 / 时间曲面…';
 ablTimer=setTimeout(()=>runAblPrediction(),100);
}
async function runAblPrediction(){
 if(ablTask)return ablTask;
 ablTask=(async()=>{while(ablAvailable()&&ablWantedKey&&ablWantedKey!==ablForecastKey){const key=ablWantedKey,generation=ablGeneration;
  try{const result=await rawApi('abl-predict',{...JSON.parse(key),generation});if(!ablAvailable()||key!==ablWantedKey||generation!==ablGeneration)continue;ablForecast=result.forecast;ablForecastKey=key;renderAblForecast()}
  catch(e){if(ablAvailable()&&key===ablWantedKey&&generation===ablGeneration){ablForecastKey=key;$('ablModelStatus').textContent='模拟未完成：'+e.message}break}
 }})().finally(()=>{ablTask=null});return ablTask;
}
function finiteLabel(v,unit){return v===null?'∞':v===0?'0 '+unit:(v<1?v.toFixed(3):v<100?v.toFixed(1):Math.round(v).toLocaleString('zh-CN'))+' '+unit}
function renderAblForecast(){
 if(!ablAvailable()){renderAbl();return}
 const f=ablForecast;if(!f)return;$('nativeAblCard').querySelector('.abl-body').dataset.ablDisplay='ready';$('ablVolume').classList.remove('abl-placeholder');const rows=f.rows.filter(r=>r.area>0),ceilings=rows.map(r=>budgetCeilingNit(f.snapshot.budget,r.area,f.snapshot.level)),maxDuration=Math.max(1,...rows.filter(r=>r.duration!==null).map(r=>r.duration)),maxNit=Math.max(1,...rows.map(r=>r.peak_nits),...ceilings.map(n=>n??0));
 for(const [id,field,max,unit] of [['ablDurationBars','duration',maxDuration,'s'],['ablStableBars','stable_nits',maxNit,'nit']]){
  const width=900,height=330,left=62,bottom=280,top=28,step=810/rows.length,y=v=>bottom-v/max*(bottom-top);
  let markup='<svg viewBox="0 0 900 330" role="img" aria-label="横轴APL，纵轴'+(unit==='nit'?'亮度nit':'持续时间秒')+'">'+barGradient(id);
  for(let i=0;i<=4;i++){const v=max*i/4;markup+='<path d="M62 '+y(v)+'H875" stroke="currentColor" opacity=".12"/><text x="53" y="'+(y(v)+4)+'" text-anchor="end">'+Math.round(v)+'</text>'}
  if(unit==='nit'&&ceilings.every(n=>n!==null))markup+='<path class="abl-budget-limit" data-values="'+JSON.stringify(ceilings)+'" d="'+smoothPath(ceilings.map((n,i)=>[left+step*(i+.5),y(n)]))+'"><title>统一预算最大亮度上限 · 不含SF/Alpha与计时ABL · 同一模拟快照</title></path>';
  rows.forEach((r,i)=>{const cycle=unit==='nit'&&r.cycle,unknown=unit==='nit'&&r.stable_nits===null&&!cycle,value=cycle?cycle.max_nits:unknown?0:r[field],x=left+step*(i+.5),h=value===null?bottom-top:Math.max(0,value/max*(bottom-top)),dash=field==='stable_nits'&&r.stop==='threshold'&&r.k>18288;
   const text=cycle?'循环 ≈'+cycle.min_nits+'–'+cycle.max_nits+' nit · 周期 '+finiteLabel(cycle.period_s,'s')+'；没有单值稳态':unknown?'模拟尚未收敛，不能认定最终亮度':(dash?'— ≈':'≈')+finiteLabel(value,unit),label=cycle?'↕ '+Math.round(cycle.min_nits)+'–'+Math.round(cycle.max_nits):unknown?'未收敛':value===null?'∞':(dash?'—':'')+Math.round(value);
   markup+='<g'+(cycle?' class="abl-cycle-column"':'')+'><title>'+r.area+'% APL · '+text+' · 瞬时≈'+r.peak_nits+' nit · 初始负载 '+r.load_peak+' · K '+r.k+' · '+r.stop+'</title><rect x="'+(x-step*.29)+'" y="'+(bottom-h)+'" width="'+step*.58+'" height="'+h+'" rx="2" class="opaque-bar" fill="url(#'+id+'-gradient)"/>';
   if(cycle)markup+='<rect class="abl-cycle-band" x="'+(x-step*.29)+'" y="'+y(cycle.max_nits)+'" width="'+step*.58+'" height="'+((cycle.max_nits-cycle.min_nits)/max*(bottom-top))+'" fill="url(#'+id+'-cycle-range)"/><path d="M'+(x-step*.29)+','+y(cycle.min_nits)+'h'+(step*.58)+'" stroke="currentColor" stroke-dasharray="2 2"/>';
   markup+='<text x="'+x+'" y="'+Math.max(top-4,bottom-h-8)+'" text-anchor="middle">'+label+'</text><text x="'+x+'" y="300" text-anchor="middle">'+r.area+'%</text></g>';
  });markup+='<text x="62" y="15">Y '+(unit==='nit'?'亮度 ≈ nit':'峰值持续时间 ≈ s')+'</text><text x="700" y="325">X 窗口面积 APL（分类）</text></svg>';$(id).innerHTML=markup;$(id).style.opacity='1';
 }
 $('ablRecoveryRange').max=Math.max(1,f.r_max);$('ablRecoveryRange').value=ablValues().r_reset;
 $('ablRecoveryRange').title='当前模型最大R '+f.r_max+'；已有值不因滑杆范围变化而被偷偷更改';
 $('ablModelStatus').textContent='快照 #'+f.generation+' · '+f.hz+' Hz · '+f.scope+(!f.supported?'；低档不移植本实验，显示未额外限亮预测':'')+(rows.some(r=>r.stop==='cycle')?'；含反复复位窗口：显示循环范围/周期，不是单值稳态':'')+(rows.some(r=>r.stop==='limit')?'；部分窗口尚未收敛，不宣称最终稳态':'');
 
 $('ablVolume').style.opacity='1';renderAblVolume(f);renderAbl();
}
function ablNitAt(row,time){
 const cycle=row.cycle,trace=cycle&&time>=cycle.start_s?cycle.trace:row.trace;
 if(cycle&&time>=cycle.start_s)time=(time-cycle.start_s)%cycle.period_s;
 if(!trace.length)return row.peak_nits;
 for(let i=1;i<trace.length;i++)if(trace[i][0]>=time){const [a,u]=trace[i-1],[b,v]=trace[i];return u+(v-u)*(time-a)/(b-a||1)}
 return trace.at(-1)[1];
}
let ablSliceSeconds=1,ablSliceScale=null,ablSliceDrag=null,ablSliceFrame=0;
function ablSliceScaleFor(extent){
 if(!ablSliceScale||ablSliceScale.extent!==extent){
  const mid=extent/10,span=Math.max(2,Math.ceil(Math.abs(Math.log10(ablSliceSeconds/mid))+.25));
  ablSliceScale={extent,mid,span,min:mid*10**-span,max:mid*10**span};
 }
 return ablSliceScale;
}
// Log-rate accelerates symmetrically away from the middle, without changing the chosen seconds on rescale.
function ablSliceAt(scale,position){
 position=Math.max(-1,Math.min(1,position));if(Math.abs(position)<.005)position=0;
 return scale.mid*10**(Math.sign(position)*scale.span*Math.expm1(3*Math.abs(position))/Math.expm1(3));
}
function ablSlicePosition(scale,seconds){
 const offset=Math.log10(seconds/scale.mid);
 return Math.max(-1,Math.min(1,Math.sign(offset)*Math.log1p(Math.abs(offset)/scale.span*Math.expm1(3))/3));
}
function ablSliceLabel(seconds){
 if(seconds>=10000||seconds<.001){const [m,e]=seconds.toExponential(3).split('e');return Number(m)+'e'+Number(e)+' s'}
 return Number(seconds.toPrecision(4))+' s';
}
function setAblSliceSeconds(seconds){
 if(!Number.isFinite(seconds)||seconds<=0)return;
 ablSliceSeconds=seconds;if(ablForecast&&ablAvailable())renderAblVolume(ablForecast);
}
function bindAblSliceScale(){
 const svg=$('ablVolume');
 const valueAt=event=>{const point=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());return ablSliceAt(ablSliceDrag.scale,(150-point.y)/75)};
 const drawLater=event=>{const value=valueAt(event);cancelAnimationFrame(ablSliceFrame);ablSliceFrame=requestAnimationFrame(()=>setAblSliceSeconds(value))};
 svg.onpointerdown=event=>{
  if(!event.target.closest('[data-abl-slice-slider]')||!ablAvailable()||!ablForecast)return;
  event.preventDefault();ablSliceDrag={scale:ablSliceScale};svg.setPointerCapture(event.pointerId);drawLater(event);
 };
 svg.onpointermove=event=>{if(ablSliceDrag){event.preventDefault();drawLater(event)}};
 const finish=(event,commit)=>{
  if(!ablSliceDrag)return;cancelAnimationFrame(ablSliceFrame);const value=commit?valueAt(event):ablSliceSeconds;ablSliceDrag=null;
  if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);setAblSliceSeconds(value);svg.querySelector('[data-abl-slice-slider]')?.focus({preventScroll:true});
 };
 svg.onpointerup=event=>finish(event,true);svg.onpointercancel=event=>finish(event,false);
 svg.onkeydown=event=>{
  if(!event.target.closest('[data-abl-slice-slider]')||!ablAvailable()||!ablForecast)return;
  let position=ablSlicePosition(ablSliceScale,ablSliceSeconds);
  if(event.key==='ArrowUp'||event.key==='ArrowRight')position+=.02;
  else if(event.key==='ArrowDown'||event.key==='ArrowLeft')position-=.02;
  else if(event.key==='PageUp')position+=.2;
  else if(event.key==='PageDown')position-=.2;
  else if(event.key==='Home')position=-1;
  else if(event.key==='End')position=1;
  else return;
  event.preventDefault();setAblSliceSeconds(ablSliceAt(ablSliceScale,position));svg.querySelector('[data-abl-slice-slider]')?.focus({preventScroll:true});
 };
}
// Fixed-time cross-sections; the onset contour is an annotation, not another sample.
function renderAblVolume(f){
 if(!ablAvailable()){renderAbl();return}
 const sliderFocused=document.activeElement?.matches?.('[data-abl-slice-slider]')&&$('ablVolume').contains(document.activeElement);
 const rows=f.rows.filter(r=>r.area>0),axis=$('ablVolumeAxis').value,svg=$('ablVolume');if(!rows.length)return;
 const maxN=Math.ceil(Math.max(250,...rows.map(r=>r.peak_nits))/250)*250;
 const ends=rows.map(r=>r.cycle?r.cycle.start_s+2*r.cycle.period_s:r.trace.at(-1)?.[0]||0),end=Math.max(0,...ends),extent=Math.max(1,end),interval=ablSliceSeconds,steps=Math.max(1,Math.ceil(extent/interval-1e-9)),horizon=steps*interval,scale=ablSliceDrag?.scale||ablSliceScaleFor(extent);
 const starts=rows.filter(r=>r.peak_nits>0&&Number.isFinite(r.duration)).map(r=>r.duration),onset=starts.length?Math.min(...starts):null;
 const cyclic=rows.some(r=>r.cycle),unresolved=rows.some(r=>r.stop==='limit'),position=a=>axisPosition(a,axis),light=document.documentElement.dataset.theme==='light';
 const project=(a,n,t)=>[235+560*position(a)-150*t/horizon,345-260*n/maxN+180*t/horizon];
 const points=(values,t)=>[[0,0],...rows.map((r,i)=>[r.area,values[i]])].map(([a,n])=>project(a,n,t));
 const area=(ps,t)=>smoothPath(ps)+' L'+project(100,0,t).join(',')+' L'+project(0,0,t).join(',')+' Z';
 const hue=t=>onset===null||t<=onset?0:240*Math.min(1,(t-onset)/Math.max(1e-9,end-onset));
 const color=t=>'hsl('+hue(t)+' 100% '+(light?30:64)+'%)',seconds=t=>Number(t.toFixed(3))+' s';
 const segment=(a,b,cls)=>'<path class="'+cls+'" d="M'+a.join(',')+' L'+b.join(',')+'"/>';
 const regular=[]; // Refuse an impractically large preview rather than silently changing Δt or hanging the UI.
 const tooLarge=steps>5000;
 if(!tooLarge)for(let i=0;i<=steps;i++){const t=i*interval;regular.push({t,values:rows.map(r=>ablNitAt(r,t))})}
 svg.dataset.sliceInterval=String(interval);svg.dataset.horizon=String(horizon);svg.dataset.onset=onset===null?'':String(onset);
 let s='<title>可调等时间隔的透明ABL瀑布图：X为APL，Y为nit，Z向左下方为时间；白色闭合虚线标记最早降亮时刻。右侧为XY及ZY正投影。</title><g class="volume-grid-layer">';
 for(const a of axisTicks(axis))s+=segment(project(a,0,0),project(a,0,horizon),'volume-grid');
 for(let i=0;i<=4;i++){
  const n=maxN*i/4,t=horizon*i/4;
  s+=segment(project(0,n,0),project(100,n,0),'volume-grid')+segment(project(0,0,t),project(100,0,t),'volume-grid');
 }
 s+='</g><g class="volume-slices">';
 for(const frame of regular){
  const ps=points(frame.values,frame.t),outline=area(ps,frame.t);
  s+='<g class="volume-slice" data-time="'+frame.t+'" data-hue="'+hue(frame.t)+'" style="--slice-color:'+color(frame.t)+'"><title>'+seconds(frame.t)+' · '+rows.map((r,j)=>r.area+'% ≈ '+frame.values[j].toFixed(1)+' nit').join(' / ')+'</title><path class="volume-area" d="'+outline+'"/><path class="volume-trace" d="'+smoothPath(ps)+'"/></g>';
 }
 s+='</g>';
 if(tooLarge)s+='<text class="volume-label" x="110" y="220">超过5000片；请用右侧时间滑块调稀。</text><text class="volume-key" x="110" y="246">仅调绘图间隔，不必改预算或ABL参数。</text>';
 if(onset!==null){
  const outline=area(points(rows.map(r=>ablNitAt(r,onset)),onset),onset);
  s+='<path class="volume-onset-halo" d="'+outline+'"/><path class="volume-onset" data-time="'+onset+'" d="'+outline+'"><title>最早开始降亮：'+seconds(onset)+'；整片曲线与XY基线的闭合边界</title></path>';
 }
 // Axes and their labels are drawn after every data/annotation plane, so no slice can cover a number.
 s+='<g class="volume-axis-layer">';
 for(const [t,plane] of [[0,'start'],[horizon,'end']]){
  const right=plane==='end',edge=right?100:0;
  s+=segment(project(edge,0,t),project(edge,maxN,t),'volume-axis volume-y-axis').replace('<path ','<path data-plane="'+plane+'" ')+segment(project(0,0,t),project(100,0,t),'volume-axis');
  for(let i=0;i<=4;i++){
   const n=maxN*i/4,p=project(edge,n,t);s+=segment([p[0]+(right?4:-4),p[1]],p,'volume-axis');
   s+='<text class="volume-tick volume-y-tick" data-plane="'+plane+'" x="'+(p[0]+(right?12:-12))+'" y="'+(p[1]+4)+'" text-anchor="'+(right?'start':'end')+'">'+Math.round(n)+'</text>';
  }
 }
 s+=segment(project(0,0,0),project(0,0,horizon),'volume-axis volume-depth-axis volume-depth-left')+segment(project(100,0,0),project(100,0,horizon),'volume-axis volume-depth-axis volume-depth-right');
 for(let i=0;i<=4;i++){
  const t=horizon*i/4,left=project(0,0,t),right=project(100,0,t);
  s+=segment([left[0]-4,left[1]],left,'volume-axis volume-z-mark-left')+segment(right,[right[0]+4,right[1]],'volume-axis volume-z-mark-right');
  s+='<text class="volume-tick volume-z-tick" data-side="right" x="'+(right[0]+28)+'" y="'+(right[1]+21)+'" text-anchor="start">'+(t===0?'0 s':ablSliceLabel(t))+'</text>';
 }
 for(const a of axisTicks(axis)){const p=project(a,0,horizon);s+='<text class="volume-tick" x="'+p[0]+'" y="'+(p[1]+25)+'" text-anchor="middle">'+a+'%</text>'}
 s+='<text class="volume-label" x="215" y="57">Y / 亮度 ≈ nit</text><text class="volume-label" x="365" y="589" text-anchor="middle">X / 窗口面积 APL（'+(axis==='log'?'对数':'线性')+'）</text><text class="volume-label" x="700" y="599">Z / 时间 s ↙</text></g>';
 // Keep the XY projection, including its peak outline and steady/cycle response area.
 const upper=rows.map(r=>r.peak_nits),ix=a=>906+174*position(a),iy=n=>220-135*n/maxN,xy=values=>[[ix(0),iy(0)],...rows.map((r,i)=>[ix(r.area),iy(values[i])])];
 s+='<g class="volume-projection"><rect x="865" y="30" width="232" height="249" rx="6"/><text class="volume-label" x="877" y="52">XY 正投影 · 面积</text>';
 for(let i=0;i<=2;i++){const n=maxN*i/2;s+='<path class="volume-grid" d="M906 '+iy(n)+'H1080"/><text class="volume-tick" x="900" y="'+(iy(n)+4)+'" text-anchor="end">'+Math.round(n)+'</text>'}
 s+='<path class="projection-peak" d="'+smoothPath(xy(upper))+' L1080,220 L906,220 Z"/>';
 if(!unresolved){
  const low=rows.map(r=>r.cycle?.min_nits??r.stable_nits),high=rows.map(r=>r.cycle?.max_nits??r.stable_nits);
  s+='<path class="projection-steady" d="'+smoothPath(xy(low))+' L1080,220 L906,220 Z"/>';
  if(cyclic)s+='<path class="projection-steady projection-cycle-range" d="'+smoothPath(xy(high))+' '+smoothPath(xy(low).reverse()).replace(/^M/,'L')+' Z"><title>长期循环亮度范围，不是单值稳态</title></path>';
 }else s+='<text class="volume-tick" x="877" y="90">尚未收敛：无稳态投影</text>';
 for(const a of axis==='log'?[.001,.1,10,100]:[0,25,50,75,100])s+='<text class="volume-tick" x="'+ix(a)+'" y="239" text-anchor="middle">'+a+'</text>';
 s+='<text class="volume-tick" x="908" y="72">nit</text><text class="volume-tick" x="1050" y="257">APL %</text><text class="volume-key" x="877" y="273">红：峰值　绿：稳态/循环</text></g>';
 // ZY projection: every APL trajectory uses the same time colours and onset position.
 const zx=t=>906+174*t/horizon,zy=n=>525-165*n/maxN,zt=new Set(regular.map(r=>r.t));zt.add(0);zt.add(horizon);if(onset!==null)zt.add(onset);
 for(const r of rows){
  for(const [t] of r.trace)if(t>=0&&t<=horizon)zt.add(t);
  if(r.cycle)for(let i=0;i<2;i++)for(const [t] of r.cycle.trace){const time=r.cycle.start_s+i*r.cycle.period_s+t;if(time<=horizon)zt.add(time)}
 }
 const times=[...zt].sort((a,b)=>a-b),stops=onset===null?[[0,0],[1,0]]:[[0,0],[onset/horizon,0],...Array.from({length:6},(_,i)=>[(onset+(end-onset)*(i+1)/6)/horizon,(i+1)/6]),[1,1]];
 s+='<defs><linearGradient id="abl-time-gradient" x1="0" x2="1" y1="0" y2="0">'+stops.map(([offset,p])=>'<stop offset="'+offset+'" stop-color="'+(onset===null?color(0):color(onset+(end-onset)*p))+'"/>').join('')+'</linearGradient></defs>';
 s+='<g class="volume-zy-projection"><title>各APL窗口的亮度—时间轨迹</title><rect x="865" y="306" width="232" height="273" rx="6"/><text class="volume-label" x="877" y="330">ZY 正投影 · 时间轨迹</text>';
 for(let i=0;i<=2;i++){const n=maxN*i/2;s+='<path class="volume-grid" d="M906 '+zy(n)+'H1080"/><text class="volume-tick" x="900" y="'+(zy(n)+4)+'" text-anchor="end">'+Math.round(n)+'</text>'}
 for(const r of rows)s+='<path class="zy-trace" stroke="url(#abl-time-gradient)" d="'+smoothPath(times.map(t=>[zx(t),zy(ablNitAt(r,t))]))+'"><title>'+r.area+'% APL · 亮度随时间变化</title></path>';
 if(onset!==null)s+='<path class="zy-onset" data-time="'+onset+'" d="M'+zx(onset)+',360V525"><title>最早开始降亮：'+seconds(onset)+'</title></path>';
 for(const t of [0,horizon/2,horizon])s+='<text class="volume-tick" x="'+zx(t)+'" y="547" text-anchor="'+(t===0?'start':t===horizon?'end':'middle')+'">'+seconds(t)+'</text>';
 s+='<text class="volume-tick" x="906" y="349">Y / nit</text><text class="volume-tick" x="1080" y="568" text-anchor="end">Z / 时间 s</text></g>';
 const meaning=onset===null?'当前预测无回落：全部时间切片为红色':cyclic?'存在循环，无单值稳态；红→蓝只表示当前观察时间':unresolved?'尚未收敛；红→蓝仅表示当前观察时间':'红→蓝：从开始降亮到最终稳态';
 s+='<text class="volume-key volume-time-legend" x="70" y="618">等时切片 Δt = '+ablSliceLabel(interval)+' · '+(onset===null?'无降亮标记':'白色闭合虚线：最早降亮 '+seconds(onset))+'<tspan x="70" y="643">'+meaning+'</tspan></text>';
 const thumb=ablSlicePosition(scale,interval),railY=p=>150-75*p,ticks=new Set([scale.min,scale.mid,scale.max]);
 for(let e=Math.floor(Math.log10(scale.min));e<=Math.ceil(Math.log10(scale.max));e++)for(const m of [1,2,5]){const value=m*10**e;if(value>scale.min&&value<scale.max)ticks.add(value)}
 svg.dataset.sliceReference=String(scale.mid);svg.dataset.slicePosition=String(thumb);
 s+='<text class="slice-scale-label" x="812" y="48" text-anchor="middle">切片 Δt '+ablSliceLabel(interval)+'</text><g class="slice-scale-control" data-abl-slice-slider tabindex="0" role="slider" aria-orientation="vertical" aria-label="图表切片时间间隔；中点约11片，仅影响绘图" aria-valuemin="'+scale.min+'" aria-valuemax="'+scale.max+'" aria-valuenow="'+interval+'" aria-valuetext="'+interval+'秒；中点'+scale.mid+'秒约11片"><title>仅调图表切片间隔，不改ABL和设备。中点约11片，中间细调，两端按倍率加速。</title><rect class="slice-scale-hit" x="798" y="63" width="28" height="174"/><line class="slice-scale-track" x1="812" x2="812" y1="75" y2="225"/>';
 for(const value of [...ticks].sort((a,b)=>a-b)){const p=ablSlicePosition(scale,value),y=railY(p),major=value===scale.mid||value===scale.min||value===scale.max;s+='<line class="slice-scale-tick" data-value="'+value+'" data-y="'+y+'" x1="'+(major?806:809)+'" x2="'+(major?818:815)+'" y1="'+y+'" y2="'+y+'"/>'}
 s+='<rect class="slice-scale-thumb" data-y="'+railY(thumb)+'" x="804" y="'+(railY(thumb)-5)+'" width="16" height="10" rx="5"/></g>';
 const tickLabel=value=>{let text=String(Number(value.toPrecision(2)));if(text.length>5)text=value.toExponential(0).replace('e+','e');return text+'s'};
 for(const [value,y] of [[scale.max,79],[scale.mid,148],[scale.min,229]])s+='<text class="slice-scale-label slice-scale-value" x="826" y="'+y+'">'+tickLabel(value)+'</text>';
 s+='<text class="slice-scale-label slice-scale-value" x="826" y="162">11片</text>';
 svg.innerHTML=s;if(sliderFocused)svg.querySelector('[data-abl-slice-slider]')?.focus({preventScroll:true});
}

// Shape-preserving cubic interpolation: continuous tangents, no invented overshoot.
function smoothPath(points){
 if(!points.length)return '';if(points.length===1)return 'M'+points[0].join(',');
 const h=points.slice(1).map((p,i)=>p[0]-points[i][0]),d=h.map((v,i)=>(points[i+1][1]-points[i][1])/(v||1)),m=[d[0]];
 for(let i=1;i<points.length-1;i++){const a=d[i-1],b=d[i],w1=2*h[i]+h[i-1],w2=h[i]+2*h[i-1];m.push(a*b<=0?0:(w1+w2)/(w1/a+w2/b))}m.push(d.at(-1));
 let path='M'+points[0].join(',');for(let i=0;i<h.length;i++){const [x,y]=points[i],[u,v]=points[i+1],dx=h[i]/3;path+=' C'+(x+dx)+','+(y+dx*m[i])+' '+(u-dx)+','+(v-dx*m[i+1])+' '+u+','+v}return path;
}
function barGradient(id){return '<defs><linearGradient id="'+id+'-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#474b52"/></linearGradient><pattern id="'+id+'-cycle-range" width="6" height="6" patternUnits="userSpaceOnUse"><path d="M0 6L6 0" stroke="currentColor" stroke-width=".6" opacity=".5"/></pattern></defs>'}
function budgetCeilingNit(budget,area,level){const sample=modelRaw(budget,area,level);return sample?sample.raw*1236/31243:null}
function renderUniformChart(){
 const svg=$('uniformChart');if(!outputModel||!jointModel||!factoryModel||!state||!configRow())return;

 const level=+$('level').value,b=+$('budgetValue').value,areas=jointModel.areas,rows=areas.map(area=>({area,ceiling:budgetCeilingNit(b,area,level)||0,predicted:windowEstimate(b,area,level,5)?.nits||0,factory:factoryNit(area,level)})),max=Math.ceil(Math.max(250,...rows.flatMap(r=>[r.ceiling,r.predicted,r.factory]))/250)*250,x=a=>68+axisPosition(a,$('uniformChartAxis').value)*808,y=n=>268-n/max*244;
 let s=barGradient('uniform');for(let i=0;i<=4;i++){const n=max*i/4;s+='<path class="grid" d="M68 '+y(n)+'H876"/><text class="axis" x="58" y="'+(y(n)+4)+'" text-anchor="end">'+n+'</text>'}
 const fp=rows.map(r=>[x(r.area),y(r.factory)]);s+='<path class="factory-fill" d="'+smoothPath(fp)+' L876,268 L68,268 Z"/><path class="factory-curve" d="'+smoothPath(fp)+'"/><path class="peak" d="'+smoothPath(rows.map(r=>[x(r.area),y(r.predicted)]))+'"/><path class="requested-curve" d="'+smoothPath(rows.map(r=>[x(r.area),y(r.ceiling)]))+'"/>';
 if($('uniformChartStyle').value==='bar')for(const r of rows)s+='<rect x="'+(x(r.area)-3)+'" y="'+y(r.predicted)+'" width="6" height="'+(268-y(r.predicted))+'" class="opaque-bar" fill="url(#uniform-gradient)"/>';
 for(const a of axisTicks($('uniformChartAxis').value))s+='<text class="axis" x="'+x(a)+'" y="293" text-anchor="middle">'+a+'%</text>';
 for(let i=0;i<rows.length;i++)s+='<rect data-uniform="'+i+'" x="'+(x(rows[i].area)-5)+'" y="24" width="10" height="244" fill="transparent"/>';
 s+='<text class="axis" x="68" y="14">预算raw等效上限 / 当前 '+inputNits()+' nit PQ输入预测</text>';
 if(svg.dataset.markup!==s){svg.innerHTML=s;svg.dataset.markup=s}svg._rows=rows;
 $('uniformChartScope').textContent='展示图，不可操作。主题色：理想预算分配raw×1236/31243，未含SF/Alpha/ABL；白线：当前SF/Alpha与PQ输入估算；灰线：设备默认参考。不是逐窗独立设置，也不是实测nit。';
}
function renderCharts(){renderUniformChart();if(jointModel&&state&&!autoFit){if(autoTargets&&autoManualAnchor!==null)requestAutoFit();else resetAutoFromState()}else if(jointModel&&state&&!$('page-auto').hidden)renderAuto();renderAbl()}
function bindUniformChart(){
 $('uniformChartStyle').onchange=renderUniformChart;
 $('uniformChart').addEventListener('pointermove',event=>{const hit=event.target.closest('[data-uniform]'),r=hit&&$('uniformChart')._rows?.[+hit.dataset.uniform];if(!r){$('uniformChartTip').hidden=true;return}const tip=$('uniformChartTip'),box=$('uniformChartHost').getBoundingClientRect();tip.textContent=r.area+'% · APL预算等效上限 ≈'+r.ceiling.toFixed(1)+' nit\n当前SF/Alpha预测 ≈'+r.predicted.toFixed(1)+' nit\n设备默认 ≈'+r.factory.toFixed(1)+' nit；均为估算，不可拖动';tip.style.left=Math.max(0,Math.min(box.width-260,event.clientX-box.left+12))+'px';tip.style.top=Math.max(0,event.clientY-box.top-90)+'px';tip.hidden=false});
 $('uniformChart').addEventListener('pointerout',event=>{if(event.target.closest('[data-uniform]'))$('uniformChartTip').hidden=true});
 $('uniformChart').addEventListener('pointerleave',()=>{$('uniformChartTip').hidden=true});
}
function explainControls(){
 for(const el of document.querySelectorAll('button,input,select,summary,[role=slider]')){
  if(el.title)continue;
  const row=el.closest('[data-param-kind]');if(row){el.title=parameterDescription(row.dataset.paramKind,+row.dataset.paramIndex);continue}
  const label=el.labels?.[0]?.textContent?.trim()||el.getAttribute('aria-label')||el.closest('label')?.textContent?.trim()||el.textContent.trim();
  const detail=el.closest('.abl-group')?.querySelector('p')?.textContent||'';el.title=(label+' '+detail).trim()||'操作当前选中的档位 × 亮暗模式配置';
 }
}
function bindAbl(){
 bindAblSliceScale();
 $('ablVolumeAxis').onchange=()=>{setChartAxis($('ablVolumeAxis').value);state.ui_preferences.chart_axis=$('ablVolumeAxis').value;act(savePreferences);if(ablForecast)renderAblVolume(ablForecast);renderCharts()};
 fillAbl(state?.native_abl||{enabled:false,l_th:18288,e0:37491600,divisor:600,r_reset:9760});
 $('nativeAblEnabled').onchange=async()=>{if(!requireAdb('native-abl')){$('nativeAblEnabled').checked=ablValues().enabled;return}if($('nativeAblEnabled').checked&&!await uiDialog('实验累计ABL移植仅支持HDR中/高；K上下限固定，但持续亮度和温升未经长时验证。编辑只预览，统一设置按应用才下发。继续？')){$('nativeAblEnabled').checked=false;return}ablDraft.enabled=$('nativeAblEnabled').checked;markAbl()};
 for(const [range,number,key,transform] of [['ablThresholdRange','ablThresholdValue','l_th',v=>Number.isInteger(+v)&&+v>=0&&+v<=65535?+v:null],['ablEnergyRange','ablEnergy','e0',v=>/^\d+$/.test(v)?v:null],['ablSpeedRange','ablSpeed','divisor',v=>Number.isFinite(+v)&&+v>0?Math.max(1,Math.min(65535,Math.round(600/+v))):null],['ablRecoveryRange','ablRecovery','r_reset',v=>Number.isInteger(+v)&&+v>=0&&+v<=82800?+v:null]]){
  for(const id of [range,number])$(id).oninput=()=>{if(!requireAdb('native-abl')){const saved=ablValues(),dirty=ablDirty;fillAbl(saved);ablDirty=dirty;renderAbl();renderParameterChanges();return}const value=transform(key==='divisor'&&id===range?2**+$(id).value:$(id).value);if(value===null)return;ablDraft[key]=value;if(id===range)$(number).value=key==='divisor'?+(2**+$(id).value).toFixed(4):$(id).value;else if(key==='e0'){$(range).max=Math.max(149966400,Number(value));$(range).value=value}else $(range).value=key==='divisor'?Math.log2(+$(id).value):$(id).value;markAbl()};
 }
 installFeedback($('nativeAblEnabled').parentElement,'native-abl');explainControls();scheduleAblPrediction();
}
