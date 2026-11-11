/* UI explanations and reference arithmetic only. Never calls a device setter. */
const themeGlyphs={
 light:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
 dark:'<path d="M20.5 13A8.5 8.5 0 0 1 11 3.5 8.5 8.5 0 1 0 20.5 13Z"/>',
 system:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>'};
function glyph(choice){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+themeGlyphs[choice]+'</svg>'}
function syncThemeButton(choice){
 const button=document.getElementById('themeButton');if(!button)return;
 const name={light:'浅色',dark:'深色',system:'跟随系统'}[choice]||'深色';
 button.innerHTML=glyph(choice in themeGlyphs?choice:'dark');button.title='主题：'+name;button.setAttribute('aria-label','切换主题，当前'+name);
 for(const item of document.querySelectorAll('[data-theme-choice]'))item.setAttribute('aria-checked',String(item.dataset.themeChoice===choice));
}
function referenceEstimate(value,area,level,tone){if(!state||!Number.isFinite(+value)||value==='')return null;return responseForConfig(value,area,level,tone)}
function nitText(value,area){
 if(+area===0)return '黑场节点 · 无亮窗 nit';
 const e=referenceEstimate(value,area,$('level').value,$('tone').value);
 return e?(e.exact?'≈ '+e.nits+' nit':'≈ '+e.nits+' nit 等效'):'待建立参考';
}
function parameterDescription(kind,index){
 if(kind==='sf')return '第 '+(index+1)+' 圈分区邻域；255 不外扩，降低数值增加该圈扩散。不是单颗 LED 圈数。';
 if(kind==='alpha'){
  const a=config.alpha[index],weight=config.dynamic?a*config.dc/128*100:null;
  return '局部平均统计为 '+(index*32)+'–'+(index*32+31)+' 时选用 Alpha'+index+'。统计范围为0–255，与整屏窗口面积和nit分开。调高通常更偏向该区域的最亮像素；最终还受DC/Blend、SF及预算影响。'+(weight===null?' 动态 Alpha 关闭，本项不参与。':' 当前基础 Max 权重 '+weight.toFixed(1)+'%（不含 STD 修正）。');
 }
 return {dc:'最大值统计权重上限，0–8；不是亮度百分比。',blend:'局部统计混合强度，0–8；不是统一亮度倍率。',dynamic:'1：按均值选择 Alpha 桶；0：固定权重路径。'}[kind]||'';
}
function renderUx(){
 if(!state)return;
 const area=+($('nitWindow')?.value||100),value=$('budgetValue').value;
 const e=referenceEstimate(value,area,$('level').value,$('tone').value);
 $('setNit').textContent=nitText(value,area);
 $('settingBasis').textContent=e?e.basis+'；'+e.note:'正在计算当前SF/Alpha；非HGiG模式需独立标定';requestConfigPrediction();
 $('budgetInlineNit').textContent=nitText(value,area);
 $('budgetRange').disabled=$('budgetValue').disabled=false;
 $('uniformRelation').textContent=state.factory_budget?'当前设备仍为原厂预算路径；自定义草稿按应用后才接管。':'统一预算作用于所有窗口；原厂APL分配后再由SF/Alpha压暗，累计ABL在下方单独预测。';
 for(const button of document.querySelectorAll('[data-budget]')){
  button.disabled=false;let hint=button.querySelector('.button-nit');
  if(!hint){hint=document.createElement('small');hint.className='button-nit';button.append(hint)}
  hint.textContent=nitText(button.dataset.budget,area);
 }
 for(const row of document.querySelectorAll('[data-param-kind]')){
  let hint=row.querySelector('.parameter-hint');if(!hint){hint=document.createElement('small');hint.className='parameter-hint';row.append(hint)}
  const description=parameterDescription(row.dataset.paramKind,+row.dataset.paramIndex);
  hint.textContent=description;
 }

 if(typeof renderTuning==='function')renderTuning();
 if(typeof scheduleAblPrediction==='function')scheduleAblPrediction();
 if(typeof renderAuto==='function'&&!$('page-auto').hidden)renderAuto();
 explainControls();
}
function bindUx(){
 $('themeButton').onclick=()=>{const open=$('themeMenu').hidden;$('themeMenu').hidden=!open;$('themeButton').setAttribute('aria-expanded',String(open))};
 for(const item of document.querySelectorAll('[data-theme-choice]')){
  item.innerHTML=glyph(item.dataset.themeChoice)+'<span>'+({light:'浅色',dark:'深色',system:'跟随系统'}[item.dataset.themeChoice])+'</span>';
  item.onclick=()=>{$('themeChoice').value=item.dataset.themeChoice;$('themeChoice').dispatchEvent(new Event('change'));$('themeMenu').hidden=true;$('themeButton').setAttribute('aria-expanded','false')};
 }
 document.addEventListener('click',event=>{if(!event.target.closest('.theme-switcher')){$('themeMenu').hidden=true;$('themeButton').setAttribute('aria-expanded','false')}});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'){$('themeMenu').hidden=true;$('themeButton').setAttribute('aria-expanded','false')}});
 $('nitWindow').onchange=renderUx;
 for(const id of ['level','tone','sfControls','alphaControls','otherControls'])$(id).addEventListener('input',renderUx);
 syncThemeButton($('themeChoice').value);
}
