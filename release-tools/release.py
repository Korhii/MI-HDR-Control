"""Curated personal-to-public export. No Git, network, ADB or original-directory writes."""
from pathlib import Path
import argparse,ast,hashlib,json,os,re,shutil,sys,zipfile

ROOT=Path(__file__).resolve().parents[1]
POLICY=Path(__file__).with_name('policy.json')
RUNTIME={'state','profiles','logs','tmp','captures','experiments','.git','private-audit','__pycache__'}
TEXT={'.py','.js','.html','.css','.md','.json','.txt','.c','.cpp','.h','.java','.s','.sh','.cmd','.xml','.template'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def copy(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a,b)
def visible(p,root):return not any(x in RUNTIME for x in p.relative_to(root).parts) and p.suffix not in ('.pyc','.obj','.res')
def flexible(name,text):
    if name=='lab/portable.html':
        text,n=re.subn(r'<div><h3>桌面导航定制</h3>.*?</small></div>','',text,flags=re.S)
        if n!=1:raise ValueError('UI cleanup anchor changed: '+name)
        text=text.replace('桌面与 ADB 随开机','ADB 连接辅助').replace('卸载预算模块并回退桌面补丁','卸载预算模块')
        text=text.replace('const l=state.launcher,a=state.adb_boot;','const a=state.adb_boot;')
        text,n=re.subn(r"\$\('launcherState'\)\.textContent=.*?;",'',text)
        if n!=1:raise ValueError('UI state anchor changed: '+name)
        text=re.sub(r'<small class="font-disclosure">.*?</small>','<small class="font-disclosure">内置字体：Noto Serif SC、Roboto Condensed、Share Tech Mono。字体按各自许可分发，详见版权说明。</small>',text)
    if name=='lab/eva.css':
        text=re.sub(r'^@font-face\{font-family:"EVA Matisse Local".*?\}\n','',text,flags=re.M).replace('"EVA Matisse Local",','')
    for a,b in [('初号机 · 紫 / 绿','初·绿紫'),('零号机 / 绫波丽 · 蓝银','零·蓝银'),('贰号机 · 赤 / 橙','二·赤橙'),('八号机 · 桃 / 绿','八·桃绿'),('Mark.06 · 蓝 / 金','六·蓝金'),('无彩色 · MONO','素·黑白'),('EVA / UNIT-01','01 / GREEN · PURPLE'),('EVA / UNIT-00','00 / BLUE · SILVER'),('EVA / UNIT-02','02 / RED · ORANGE'),('EVA / UNIT-08','08 / PINK · GREEN'),('EVA / MARK.06','06 / BLUE · GOLD')]:text=text.replace(a,b)
    text=text.replace('外观与机体主题','外观与配色主题').replace('UNIT / 完整机体主题','PALETTE / 数字配色')
    if name=='lab/tuning.js':text=text.replace("'risk-unlock','risk-lock']);","'risk-unlock','risk-lock','model-select','model-detect']);")
    return text

def prepare(source,output,version):
    source=Path(source).resolve();output=Path(output).resolve();policy=json.loads(POLICY.read_text('utf-8'))
    if source==output or source in output.parents:raise ValueError('OUTPUT must be external to SOURCE')
    if output.exists():raise ValueError('Use a fresh output directory')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?',version):raise ValueError('Use a semantic version')
    is_public=(source/'release-meta.json').is_file();review=[];changed=[]
    # Stop BEFORE creating output. Never hide unknown core/asset updates behind an overlay.
    if is_public:
        for name,expected in policy['approved_files'].items():
            p=source/name
            if not p.is_file() or digest(p)!=expected:review.append('changed public file requires review: '+name)
    for name,expected in policy['source_files'].items():
        if is_public and name not in policy['public_files']:continue
        p=source/name
        if not p.is_file():review.append('missing: '+name);continue
        h=digest(p)
        if is_public:
            if h!=policy['approved_files'].get(name) and name not in policy['flexible']:review.append('changed public core: '+name)
        elif h!=expected and name not in policy['flexible']:review.append('changed core/dependency/asset: '+name)
        if h!=expected:changed.append(name)
    for p in source.rglob('*'):
        if not p.is_file() or not visible(p,source):continue
        name=p.relative_to(source).as_posix()
        known=policy['public_files']+['release-meta.json'] if is_public else policy['known_source_files']
        if name not in known and p.parts[len(source.parts)] not in ('docs',) and name not in ('README.md','README.en.md','package-manifest.json'):
            review.append('new file requires review: '+name)
    if review:raise ValueError('REVIEW_REQUIRED\n'+'\n'.join(review[:40]))
    output.mkdir(parents=True);portable=output/'portable';repo=output/'repository';portable.mkdir();repo.mkdir()
    for name in policy['public_files']:
        src=ROOT/name
        if name in policy['source_files'] and not is_public and name not in policy['overlays']:src=source/name
        elif is_public and (source/name).is_file():src=source/name
        target=portable/name
        if name in policy['flexible'] and not is_public:
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(flexible(name,src.read_text('utf-8')),encoding='utf-8')
        else:copy(src,target)
    # Versioned prose is generated, never inherited from a personal changelog.
    source_version=version.split('-')[0]
    for t in (ROOT/'release-tools/templates').rglob('*.template'):
        name=t.relative_to(ROOT/'release-tools/templates').as_posix().removesuffix('.template')
        text=t.read_text('utf-8').replace('{{SOURCE_VERSION}}',source_version).replace('{{PUBLIC_VERSION}}',version)
        p=portable/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    for n in ('使用说明.md','27与32寸机型与预测说明.md'):copy(portable/'docs/guide.zh-CN.md',portable/'docs'/n)
    # The inline-script contract follows actual transformed UI, not an old digest.
    ui=portable/'lab/portable.html';text=ui.read_text('utf-8')
    text=re.sub(r'PORTABLE \d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?(?=\s*·)','PORTABLE '+version,text)
    ui.write_text(text,encoding='utf-8')
    c=portable/'resources/ui/control-contract.json'
    contract=json.loads(c.read_text('utf-8'));html=(portable/'lab/portable.html').read_text('utf-8')
    scripts=re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',html,re.S)
    contract['controller_script_sha256']=hashlib.sha256(max(scripts,key=len).encode()).hexdigest()
    dump(c,contract)
    # Defaults are generated without importing code that touches ADB.
    sys.path[:0]=[str(portable/'lab'),str(portable/'scripts')]
    from features import PATTERN,CALIBRATION
    from native_abl import DEFAULT
    registry=json.loads((portable/'resources/models/registry.json').read_text('utf-8'))['models']['32u-2026']
    stock=registry['variants'][registry['default_variant']]['defaults']
    profiles={f'{level}:{tone}':dict(config=stock[str(level)],software_abl=True,budget=24,native_abl=dict(DEFAULT),factory_budget=True,pattern=PATTERN) for level in (1,2,3) for tone in (5,1,0,2)}
    dump(portable/'profiles/controller.json',dict(format='mi-hdr-controller-v1',model_id='32u-2026',model_confirmed=False,selected_level=3,selected_tone=5,profiles=profiles,pattern=PATTERN,calibration=CALIBRATION,ui=policy['default_ui'],nit_references=[CALIBRATION]))
    dump(portable/'state/connection.json',dict(serial='',port=5041))
    meta=dict(format='mi-public-candidate-v1',version=version,recipe=policy['recipe'],release_ready=False,publication_authorized=False,
              pending_decisions=[],automatic_upload=False,
              confirmed_decisions=dict(credit='MI HDR Control contributors',release_level='experimental-preview',palettes='retain numeric/color palettes and licensed fonts',readme_languages=['zh-CN','en'],english_gui_required=False,original_documentation_license='CC-BY-NC-SA-4.0',program_license='GPL-2.0-only',original_independent_artwork_license='CC-BY-NC-SA-4.0',commercial_boundary='GPL code retains commercial rights; original independent materials are noncommercial',privacy_capture_method='crop-and-opaque-mask; no generative editing',monitor_adb_route='Control → Settings → Account & security → ADB debugging'),
              documentation_gaps=[],
              inherited_test_suite='0.9.26 pristine: 128 tests, 13 failures and 48 errors; current maintained fixtures and regressions are reported separately in VALIDATION',
              updated_source_files=changed,device_evidence='component-scoped; resources/persistence/acceptance.json')
    acceptance=json.loads((portable/'resources/persistence/acceptance.json').read_text('utf-8'))
    meta['pending_gates']=['Separate GitHub publication authorization not granted']
    meta['known_limitations']=['27U inferred; no physical 27U acceptance','Factory-reset developer activation and RSA prompt not re-enacted; chassis button placement not photographed']
    if not acceptance['boot_verified']:meta['known_limitations'].append('Current component uninterrupted reboot acceptance incomplete')
    dump(portable/'release-meta.json',meta)
    # Bind deterministic rendered files after source review, for the next public rebuild.
    policy['approved_files']={name:digest(portable/name) for name in policy['approved_files']}
    dump(portable/'release-tools/policy.json',policy)
    for p in portable.rglob('*'):
        if not p.is_file() or not visible(p,portable):continue
        name=p.relative_to(portable).as_posix()
        if name.startswith(('tools/python/','tools/platform-tools/','tools/predict-libs/')):continue
        copy(p,repo/name)
    dump(output/'private-audit/source-fingerprints.json',dict(source=str(source),files={n:digest(source/n) for n in policy['source_files'] if (source/n).is_file()},version=version))
    report=check(portable);dump(output/'private-audit/export-report.json',report)
    if not report['ok']:raise ValueError('Export validation failed; inspect private-audit/export-report.json')
    dump(portable/'package-manifest.json',manifest(portable));dump(repo/'package-manifest.json',manifest(repo))
    return dict(output=str(output),portable=str(portable),repository=str(repo),release_ready=False,files=report['files'],ui_updates_preserved=[n for n in changed if n in policy['flexible']])

def manifest(root):
    return dict(files=[dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(root.rglob('*')) if p.is_file() and visible(p,root) and p.name!='package-manifest.json'])

def check(candidate):
    root=Path(candidate).resolve();errors=[];count=0
    required=['MI HDR Control.exe','tools/MIHDRBridge.jar','tools/MIHDRRuntime.jar','LICENSE','NOTICE.md','LICENSES/GPL-2.0-only.txt','LICENSES/CC-BY-NC-SA-4.0.txt','LICENSES/Unicorn-COPYING.txt','third_party/sources/unicorn-2.1.4.tar.gz','resources/preparation/inputs-v17.json','release-tools/policy.json']
    for n in required:
        if not (root/n).is_file():errors.append('missing required: '+n)
    if (root/'LICENSE').is_file() and (root/'LICENSES/GPL-2.0-only.txt').is_file():
        if (root/'LICENSE').read_text('utf-8')!=(root/'LICENSES/GPL-2.0-only.txt').read_text('utf-8'):errors.append('program license text differs from GPL-2.0-only')
    if (root/'release-meta.json').is_file():
        decisions=json.loads((root/'release-meta.json').read_text('utf-8')).get('confirmed_decisions',{})
        if decisions.get('program_license')!='GPL-2.0-only' or decisions.get('original_documentation_license')!='CC-BY-NC-SA-4.0':errors.append('confirmed license scope mismatch')
    for p in root.rglob('*'):
        if not p.is_file() or not visible(p,root):continue
        n=p.relative_to(root).as_posix();count+=1
        if (p.name.startswith('adbkey') or p.suffix.lower() in ('.pem','.p12','.pfx','.jks','.keystore','.ko') or n.startswith(('resources/model/','resources/firmware/','resources/launcher/')) or p.name in ('MtkDirectTool.jar','frida-inject','27u-reference.png') or (n.startswith('resources/models/') and p.suffix=='.ini') or (n.startswith('resources/persistence/') and p.suffix in ('.xml','.js'))):errors.append('excluded material: '+n)
        if n.startswith('tools/') and len(p.relative_to(root).parts)==2:
            binary=p.read_bytes()
            if binary.startswith(b'\x7fELF') and re.search(rb'[A-Z]:[\\/]+(?:Users|MI)[\\/]+',binary):errors.append('native debug build path: '+n)
        if p.suffix.lower() in TEXT and not n.startswith(('tools/python/','tools/predict-libs/','scripts/windows-launcher/webview2/','LICENSES/')):
            try:text=p.read_text('utf-8')
            except UnicodeDecodeError:errors.append('not UTF-8: '+n);continue
            if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}|[A-Z]:[\\/]+(?:Users|MI)[\\/]+|192\.168\.\d+\.\d+',text):errors.append('private data: '+n)
            if p.suffix=='.py':
                try:ast.parse(text,filename=n)
                except SyntaxError:errors.append('Python syntax: '+n)
            if p.suffix=='.md':
                for link in re.findall(r'\]\(([^)]+)\)',text):
                    if re.match(r'\w+://|mailto:|#',link):continue
                    path=link.split('#')[0].split('?')[0]
                    if path and not (p.parent/path).exists():errors.append('broken link: '+n+' -> '+path)
    for n in ('README.md','guide.zh-CN.md','SAFETY.zh-CN.md','LEGAL.zh-CN.md','THEME_REVIEW.zh-CN.md','RELEASING.zh-CN.md','VALIDATION.zh-CN.md'):
        zh=root/n if n=='README.md' else root/'docs'/n
        en=root/'README.en.md' if n=='README.md' else root/'docs'/n.replace('zh-CN','en')
        if not zh.exists() or not en.exists():errors.append('missing language pair: '+n)
    if (root/'state/connection.json').exists() and json.loads((root/'state/connection.json').read_text('utf-8')).get('serial'):errors.append('device serial default')
    if (root/'profiles/controller.json').exists():
        conf=json.loads((root/'profiles/controller.json').read_text('utf-8'))
        if conf['ui']['auto_connect'] or conf['ui']['unit']!='mono' or not all(x['factory_budget'] for x in conf['profiles'].values()):errors.append('non-factory/offline default')
    meta=json.loads((root/'release-meta.json').read_text('utf-8')) if (root/'release-meta.json').is_file() else {}
    if meta.get('release_ready') and not meta.get('publication_authorized'):errors.append('publication approval missing')
    return dict(ok=not errors,files=count,errors=errors,device_commands_executed=False,release_ready=meta.get('release_ready',False))

def approve(candidate,repository,tag):
    root=Path(candidate).resolve();report=check(root)
    if not report['ok']:raise ValueError('Candidate check failed')
    meta=json.loads((root/'release-meta.json').read_text('utf-8'))
    if not re.fullmatch(r'https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('Use the intended GitHub repository URL')
    if tag!='v'+meta['version']:raise ValueError('Tag must match candidate version')
    meta.update(publication_authorized=True,release_ready=True,automatic_upload=False,pending_gates=[],publication=dict(repository=repository,tag=tag,channel='experimental-preview',ai_assisted=True))
    dump(root/'release-meta.json',meta);dump(root/'package-manifest.json',manifest(root))
    return dict(repository=repository,tag=tag,publication_authorized=True,release_ready=True,network_commands_executed=False)

def package(candidate):
    root=Path(candidate).resolve();report=check(root)
    if not report['ok']:raise ValueError(json.dumps(report,ensure_ascii=False))
    version=json.loads((root/'release-meta.json').read_text('utf-8'))['version']
    out=root.parent/('MI-HDR-Control-'+version+'-Windows.zip')
    if out.exists():raise ValueError('Archive already exists; use a new output')
    dump(root/'package-manifest.json',manifest(root))
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(root.rglob('*')):
            if not p.is_file():continue
            n=p.relative_to(root)
            if not visible(p,root) and n.as_posix() not in ('state/connection.json','profiles/controller.json'):continue
            z.write(p,'MI-HDR-Control-'+version+'/'+n.as_posix())
    with zipfile.ZipFile(out) as z:
        if z.testzip() is not None:raise ValueError('ZIP integrity failure')
        names=z.namelist()
        if any('/state/' in n and not n.endswith('/state/connection.json') for n in names):raise ValueError('Private runtime material in ZIP')
    return dict(archive=str(out),bytes=out.stat().st_size,sha256=digest(out),release_ready=json.loads((root/'release-meta.json').read_text('utf-8'))['release_ready'],zip_reopened=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('--source',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--version',required=True)
    for name in ('check','package'):a=s.add_parser(name);a.add_argument('--candidate',type=Path,required=True)
    a=s.add_parser('approve');a.add_argument('--candidate',type=Path,required=True);a.add_argument('--repository',required=True);a.add_argument('--tag',required=True)
    args=p.parse_args()
    try:
        value=prepare(args.source,args.output,args.version) if args.action=='prepare' else approve(args.candidate,args.repository,args.tag) if args.action=='approve' else globals()[args.action](args.candidate)
        print(json.dumps(value,ensure_ascii=False,indent=2));return 0 if value.get('ok',True) else 1
    except (ValueError,FileNotFoundError) as e:print(str(e),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
