/* Draft-vs-device-default indication. Reset follows the field's existing event path. */
const parameterBindings=new WeakMap();
const resetGlyph='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M5 8a8 8 0 1 1-1 7M5 3v5h5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function parameterBadge(label,read,defaultValue,reset){
 if(!label)return;let binding=parameterBindings.get(label);
 if(!binding){
  const name=document.createElement('span');name.className='param-name';
  for(const node of [...label.childNodes])if(node.nodeType===Node.TEXT_NODE){name.append(node)}
  if(!name.textContent.trim())return;const heading=document.createElement('span');heading.className='param-heading';label.prepend(heading);heading.append(name);const checkbox=label.querySelector('input[type=checkbox]');if(checkbox){heading.prepend(checkbox);heading.classList.add('param-check-heading')}
  const star=document.createElement('span');star.className='param-star';star.textContent='*';name.append(star);
  const button=document.createElement('button');button.type='button';button.className='param-reset';button.innerHTML=resetGlyph;button.setAttribute('aria-label','此参数恢复默认');heading.append(button);
  button.onclick=e=>{e.preventDefault();e.stopPropagation();binding.reset();renderParameterChanges()};
  binding={name,star,button};parameterBindings.set(label,binding);
 }
 Object.assign(binding,{read,defaultValue,reset});const changed=JSON.stringify(read())!==JSON.stringify(defaultValue());
 binding.name.classList.toggle('modified',changed);binding.star.hidden=!changed;binding.button.disabled=!changed||!!label.closest(".abl-off .abl-body");
 binding.button.title='只将此参数恢复默认：'+String(defaultValue())+'；沿用本模块原有应用方式';binding.name.title=changed?'已修改（相对默认）；星号不代表已写入设备':'默认值';
}
function renderParameterChanges(){
 if(typeof state==='undefined'||!state||typeof config==='undefined'||!config)return;
 const level=+$('level').value,defaults=state.stock_by_level?.[level]||{sf:[255,255,255,255,255],alpha:[3,5,7,9,11,13,15,16],dc:{1:7,2:6,3:8}[level],blend:level===2?6:8,dynamic:1};
 for(const row of document.querySelectorAll('[data-param-kind]')){
  const k=row.dataset.paramKind,i=+row.dataset.paramIndex,number=row.querySelector('input[type=number]'),value=()=>Array.isArray(defaults[k])?defaults[k][i]:defaults[k];
  parameterBadge(row.querySelector('label'),()=>Array.isArray(config[k])?config[k][i]:config[k],value,()=>{number.value=value();number.dispatchEvent(new Event('input',{bubbles:true}))});
 }
 const fields=[['budgetValue',24],['autoCeiling',41],['ablThresholdValue',18288,'ablThresholdName'],['ablEnergy','37491600','ablEnergyName'],['ablSpeed',1,'ablSpeedName'],['ablRecovery',9760,'ablRecoveryName'],['input_nits',4000],['background_nits',0],['area_percent',50],['pixel_width',0],['pixel_height',0],['rows',1],['cols',1],['seconds',0],['monitor',0],['mode','windowed'],['geometry','area'],['calArea',100],['calRaw',31245],['calNit',1236],['calBudget',41]];
 for(const [id,def,labelId] of fields){const input=$(id);if(!input)continue;const label=labelId?$(labelId):input.labels?.[0]||input.closest('label');
  parameterBadge(label,()=>typeof def==='number'?+input.value:String(input.value),()=>def,()=>{input.value=def;input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}))});
 }
 for(const [id,def] of [['nativeAblEnabled',false],['label',true]]){const input=$(id);if(input)parameterBadge(input.labels?.[0]||input.closest('label'),()=>input.checked,()=>def,()=>{input.checked=def;input.dispatchEvent(new Event('change',{bubbles:true}))})}
}
document.addEventListener('input',()=>queueMicrotask(renderParameterChanges));document.addEventListener('change',()=>queueMicrotask(renderParameterChanges));
