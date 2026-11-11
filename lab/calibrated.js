/* Window/input-specific optical anchors; original ARM64 SF/Alpha responses, never universal raw/nit. */
let opticalModel=null,manualResponse=null,manualResponseKey='',predictionPending='',predictionTask=null;
const rowCache=new Map(),nitScaleCache=new Map(),opticalCache=new Map();
function inputNits(){return +($('input_nits')?.value??state?.pattern_config.input_nits??4000)}
function pqValue(n){const p=(Math.max(0,n)/10000)**(2610/16384);return ((3424/4096+2413/128*p)/(1+2392/128*p))**(2523/32)}
function interpolate(points,x,log=false){
 if(x<=points[0][0])return points[0][1];if(x>=points.at(-1)[0])return points.at(-1)[1];
 for(let i=1;i<points.length;i++)if(x<=points[i][0]){const[a,u]=points[i-1],[b,v]=points[i],t=log&&a>0?(Math.log10(x)-Math.log10(a))/(Math.log10(b)-Math.log10(a)):(x-a)/(b-a);return u+(v-u)*t}
}
function inputRow(row,q){
 if(!row?.input_rows)return row;
 if(row.input_rows[String(q)])return row.input_rows[String(q)];
 const inputs=jointModel.inputs,right=inputs.findIndex(x=>x>=q),hi=right<0?inputs.length-1:right,lo=Math.max(0,hi-1),a=row.input_rows[String(inputs[lo])],b=row.input_rows[String(inputs[hi])],t=hi===lo?0:(pqValue(q)-pqValue(inputs[lo]))/(pqValue(inputs[hi])-pqValue(inputs[lo]));
 return {raw:a.raw.map((r,i)=>r.map((v,j)=>v+(b.raw[i][j]-v)*t)),native:a.native.map((v,i)=>v+(b.native[i]-v)*t),metrics:a.metrics.map((m,i)=>{const out={...m,aperture_fraction:m.aperture_fraction+(b.metrics[i].aperture_fraction-m.aperture_fraction)*t,driver_window_percent:m.driver_window_percent+(b.metrics[i].driver_window_percent-m.driver_window_percent)*t};for(const k of ['driver_ratio24','driver_aw24','driver_peak24','driver_power'])if(Number.isFinite(m[k])&&Number.isFinite(b.metrics[i][k]))out[k]=m[k]+(b.metrics[i][k]-m[k])*t;else delete out[k];return out}),interpolated:true};
}
function jointRow(recipe,level,q=inputNits()){
 const key=recipe+':'+level+':'+q;if(rowCache.has(key))return rowCache.get(key);
 const result=inputRow(jointRows.get(recipe+':'+level),q);if(result)rowCache.set(key,result);return result;
}
function opticalFactory(level,area,q=inputNits()){
 const actual=state&&config?configRow():null;if(actual?.factory_nits)return interpolate(jointModel.areas.map((a,i)=>[a,actual.factory_nits[i]]),area,true);
 if(!opticalModel||area<=0||q<=0)return 0;
 if(state?.model_confirmed)return null; // Wait for the current native model; never flash a stale PQ-linear curve.
 const cacheKey=level+":"+area+":"+q;if(opticalCache.has(cacheKey))return opticalCache.get(cacheKey);
 const table=opticalModel.high,a=Math.max(.01,Math.min(100,area));
 const interpolateArea=row=>interpolate(table.areas.map((x,i)=>[x,row[i]]).sort((a,b)=>a[0]-b[0]),a,true);
 let n=interpolate(table.inputs.map((p,i)=>[pqValue(p),interpolateArea(table.nits[i])]),pqValue(q));
 if(+level!==3){const peak=interpolate(opticalModel.bars.areas.map((x,i)=>[x,opticalModel.bars.peak_nits[level][i]]),a,true);n*=peak/interpolateArea(table.nits.at(-1))}
 if(area<.01){const base=factoryRaw(level,.01,q)*factoryAperture(level,.01,q);n*=base?factoryRaw(level,area,q)*factoryAperture(level,area,q)/base:0}
 const value=Math.max(0,n);opticalCache.set(cacheKey,value);return value;
}
function factoryRaw(level,area,q=inputNits()){
 const source=factoryModel?.rows.find(r=>r.level===+level);if(!source?.input_rows)return null;
 const row=inputRow(source,q);return interpolate(factoryModel.areas.map((a,i)=>[a,row.native[i]]),area,true);
}
function apertureAt(row,area){return interpolate(jointModel.areas.map((a,i)=>[a,row.metrics[i].aperture_fraction]),area,true)}
function factoryAperture(level,area,q=inputNits()){return apertureAt(inputRow(factoryModel.rows.find(r=>r.level===+level),q),area)}
function nitScale(level,area,q=inputNits()){
 const key=level+':'+area+':'+q;if(nitScaleCache.has(key))return nitScaleCache.get(key);
 const raw=factoryRaw(level,area,q)*factoryAperture(level,area,q),value=raw?opticalFactory(level,area,q)/raw:0;nitScaleCache.set(key,value);return value;
}
function measuredCurveNit(raw,row,level,area,q=inputNits()){
 if(!row||area<=0)return area<=0?0:null;
 const at=field=>interpolate(jointModel.areas.map((a,i)=>[a,row.metrics[i][field]]),area,true);
 if(!row.metrics.every((m,i)=>jointModel.areas[i]===0||Number.isFinite(m.driver_ratio24)))return null;
 const base=interpolate(jointModel.areas.map((a,i)=>[a,row.raw[i][24]]),area,true);
 return base?opticalFactory(level,area,q)*at('driver_ratio24')*(Math.max(0,raw)/base)**at('driver_power'):0;
}
function calibratedEstimate(raw,level,area,q=inputNits(),fraction=1,row=null){
 if(raw===null||!opticalModel||!factoryModel)return null;
 const measured=measuredCurveNit(raw,row,level,area,q);
 if(measured!==null)return {raw:Math.round(raw),nits:measured,actual:area,exact:false,basis:'实机末级DMA逐区输出 × 光学代理；非nit实测',note:'窗口/参数插值；非24预算沿用原厂算法的相对增益，不能认证1000nit',joint:true,driverBacked:true};
 return {raw:Math.round(raw),nits:+(raw*fraction*nitScale(level,area,q)).toFixed(1),actual:area,sampled:jointModel.areas.includes(area)&&jointModel.inputs.includes(q),exact:false,basis:'截图逐窗参考 × raw比值 × 当前SF/Alpha邻区光场',note:(+level===3?'高HGiG表':'中/低条图峰值，输入形状近似')+(area<.01?'；低于0.01%外推':'')+'；空间核为经验拟合，非实测',base:state.calibration,joint:true};
}
function configKey(c,level=+$('level').value,q=inputNits()){return JSON.stringify([state?.model_id,+$('tone').value,level,q,c.sf,c.alpha,c.dc,c.blend,c.dynamic])}
function configRow(){
 return manualResponseKey===configKey(config)?manualResponse:null;
}
function responseForConfig(value,area,level,tone){
 const row=configRow();if(!row)return null;
 const b=Math.max(0,Math.min(86,Math.round(value))),raw=interpolate(jointModel.areas.map((a,i)=>[a,row.raw[i][b]]),area,true),nits=interpolate(jointModel.areas.map((a,i)=>[a,row.nits[i][b]]),area,true);return {raw:Math.round(raw),nits,actual:area,basis:'96×48原厂ARM64 · '+(state.model_id==='27u-2026'?'27寸峰值锚点':'32寸DMA校正'),note:row.scope};
}
function driverMetricAt(area){const row=configRow();return row?interpolate(jointModel.areas.map((a,i)=>[a,row.metrics[i].driver_window_percent]),area,true):null}
function geometryForMetric(metric){const row=configRow();if(!row)return null;const points=new Map();jointModel.areas.forEach((a,i)=>{const x=row.metrics[i].driver_window_percent;if(!points.has(x))points.set(x,a)});return interpolate([...points].sort((a,b)=>a[0]-b[0]),metric)}
async function requestConfigPrediction(){
 if(state?.local_assets?.ready===false){$('settingBasis').textContent=state.local_assets.message;return}
 if(!jointModel||!opticalModel||!state||!state.model_confirmed)return;
 const key=configKey(config);if(key===manualResponseKey)return;if(predictionTask)return predictionTask;
 predictionPending=key;
 predictionTask=(async()=>{
  try{const result=await rawApi('predict-response',{config:copy(config),level:+$('level').value,input_nits:inputNits(),tone:+$('tone').value});if(key===configKey(config)){manualResponse=result.response;manualResponseKey=key;if(!autoFit)resetAutoFromState();else requestAutoFit();renderUx();renderCharts()}}
  catch(e){$('settingBasis').textContent='参数预测失败：'+e.message}
  finally{predictionPending='';predictionTask=null;if(key!==configKey(config))requestConfigPrediction()}
 })();
 return predictionTask;
}

function lockPatternGeometry(){const pixels=$('geometry').value==='pixels';for(const id of ['pixel_width','pixel_height'])$(id).disabled=!pixels;$('area_percent').disabled=pixels}
function bindCalibration(){
 fetch('/optical-reference.json').then(r=>r.json()).then(data=>{opticalModel=data;nitScaleCache.clear();opticalCache.clear();if(jointModel&&factoryModel&&state){autoFit=null;renderUx();renderCharts()}});
 $('geometry').addEventListener('change',lockPatternGeometry);lockPatternGeometry();
 for(const id of ['input_nits','background_nits'])$(id).addEventListener('input',()=>{rowCache.clear();nitScaleCache.clear();if(autoTargets&&jointModel&&opticalModel&&factoryModel)resolveAuto();requestConfigPrediction();renderUx();renderCharts()});
}
