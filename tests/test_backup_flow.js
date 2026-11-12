/* Actual public dialog functions with synthetic state. No browser or ADB. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=process.env.MI_TEST_ROOT||path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'lab/dialogs.js'),'utf8');
function context(overrides={}){
 const dialogs=[],notices=[],choices=[];
 const c=vm.createContext({console,URLSearchParams,Promise,location:{search:''},state:{model_confirmed:true,connected:false,backup_policy:{confirmed:false,device:false},initial_backup:{ready:false,status:'not-checked'},...overrides},
  showModelSelection:()=>{},error:e=>{throw e},rawApi:async()=>({}),waitOperation:async()=>{},
  document:{body:{append:d=>dialogs.push(d)},createElement:()=>{const fields=new Map();return{querySelector:s=>{if(!fields.has(s))fields.set(s,{disabled:false,checked:false,textContent:'',focus(){}});return fields.get(s)},showModal(){this.opened=true},close(){this.opened=false},remove(){}}}}});
 vm.runInContext(source,c);c.showStartupNotice=()=>true;c.uiDialog=(message,opts)=>{notices.push({message,opts});return Promise.resolve(false)};
 return {c,dialogs,notices,choices};
}
const tick=()=>new Promise(r=>setImmediate(r));const results=[];
async function test(name,fn){try{await fn();results.push({name,passed:true})}catch(e){results.push({name,passed:false,error:e.message})}}
(async()=>{
 await test('offline startup does not ask for backup location',()=>{const x=context();x.c.chooseBackupLocation=()=>x.choices.push(1);x.c.showBackupNotice();assert.equal(x.choices.length,0);assert.equal(x.notices.length,0)});
 await test('existing recovered backup skips choice without saved policy',()=>{const x=context({connected:true,initial_backup:{ready:true,status:'ready',notice_pending:true,id:'test',pc_path:'PACKAGE/state/test',device_path:'/TEST_ONLY/initial-v1.json',device_copy_exists:true,recovered_from_device:true}});x.c.chooseBackupLocation=()=>x.choices.push(1);x.c.showBackupNotice();assert.equal(x.choices.length,0);assert.match(x.notices[0].message,/复用显示器/);assert.equal(x.notices[0].opts.notice,true);assert.equal(x.notices[0].opts.confirmText,'知道了')});
 await test('missing backup asks even when old global preference exists',()=>{const x=context({connected:true,backup_policy:{confirmed:true,device:true},initial_backup:{ready:false,status:'missing'}});x.c.chooseBackupLocation=()=>x.choices.push(1);x.c.showBackupNotice();assert.equal(x.choices.length,1)});
 await test('failed inspection never becomes a create-backup dialog',()=>{const x=context({connected:true,initial_backup:{ready:false,status:'error',message:'read failed'}});x.c.chooseBackupLocation=()=>x.choices.push(1);x.c.showBackupNotice();assert.equal(x.choices.length,0)});
 await test('manual settings before connection only explains discovery',async()=>{const x=context();assert.equal(await x.c.chooseBackupLocation(true),false);assert.equal(x.dialogs.length,0);assert.match(x.notices[0].message,/先连接 ADB/)});
 await test('connected missing choice states actual device result',async()=>{const x=context({connected:true,initial_backup:{ready:false,status:'missing'}});const p=x.c.chooseBackupLocation();await tick();assert.equal(x.dialogs.length,1);assert.match(x.dialogs[0].querySelector('.backup-existing').textContent,/已连接并完成检查/);x.dialogs[0].querySelector('.backup-cancel').onclick();assert.equal(await p,false)});
 await test('offline module says monitor backup has not been inspected',()=>{const x=context();const field={textContent:''};x.c.$=()=>field;const line=fs.readFileSync(path.join(root,'lab/modules.js'),'utf8').split(/\r?\n/).find(s=>s.startsWith(" const backup=$('initialBackupStatus')"));assert.ok(line);vm.runInContext(line,x.c);assert.match(field.textContent,/显示器备份尚未检测/);assert.ok(!field.textContent.includes('0'))});
 console.log(JSON.stringify({tests:results.length,passed:results.filter(x=>x.passed).length,results},null,2));process.exitCode=results.every(x=>x.passed)?0:1;
})();
