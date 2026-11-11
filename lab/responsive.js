/* Discrete layout-first scaling. Below the comfort floor we scroll, never shrink text indefinitely. */
let appliedScale=1,scaleFrame=0;
function chooseUiScale(width,height,choice='auto'){
 if(choice!=='auto')return Math.max(.5,Math.min(1,+choice/100));
 if(width>=1000&&height>=760)return 1;
 if(width>=780&&height>=620)return .9;
 if(width>=620&&height>=480)return .75;
 if(width>=480&&height>=360)return .65;
 return .5;
}
function applyUiScale(){
 const width=window.innerWidth,height=window.innerHeight,choice=state?.ui_preferences.ui_scale||'auto';
 const layout=width>=1400?'wide':width>=1100?'compact':'stack';
 document.documentElement.dataset.layout=layout;
 // Layout breakpoint is selected from the physical viewport, before any scale step.
 const scale=chooseUiScale(width,height,choice);appliedScale=scale;
 document.documentElement.style.setProperty('--ui-scale',String(scale));document.body.style.zoom=String(scale);
 $('uiScale').value=choice;$('uiScaleState').textContent=(choice==='auto'?'自动 · ':'固定 · ')+Math.round(scale*100)+'%'+(scale===.5?' · 最小档，超出内容滚动':'');
 for(const chart of document.querySelectorAll('.brightness-chart')){
  const width=chart.getBoundingClientRect().width;if(!width)continue;
  const ratio=chart.viewBox.baseVal.width/width;
  chart.style.setProperty('--chart-font',Math.max(6,12*scale*ratio)+'px');
  chart.style.setProperty('--chart-handle',Math.max(3,5.5*scale*ratio)+'px');
 }
 sidebarMode();
}
function requireAdb(field='connection'){
 if(state?.connected)return true;
 const message='请先连接ADB，再调整显示器参数；本地HDR图样不需要ADB';
 error(message);localFeedback(field,'blocked',message);
 document.querySelector('.connection-strip').classList.add('needs-connection');
 return false;
}
function bindResponsive(){
 $('uiScale').onchange=()=>{state.ui_preferences.ui_scale=$('uiScale').value;applyUiScale();act(savePreferences)};
 addEventListener('resize',()=>{cancelAnimationFrame(scaleFrame);scaleFrame=requestAnimationFrame(applyUiScale)});
 const guard=event=>{
  if(state?.connected)return;
  const target=event.target.closest('input,select,[data-budget],[data-edit],[data-column]');
  if(!target||target.type==='file'||!target.closest('.workspace')||target.closest('#page-pattern')||target.closest('#page-auto')||['uiScale','nitWindow'].includes(target.id))return;
  if(event.type==='pointerdown'&&target.matches('input:not([type=range]):not([type=checkbox]):not([type=radio])'))return;
  if(!requireAdb('connection')){event.preventDefault();event.stopImmediatePropagation()}
 };
 for(const name of ['pointerdown','beforeinput','change'])document.addEventListener(name,guard,true);
 applyUiScale();
}
