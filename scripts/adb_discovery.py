"""Find the supported display through USB, ADB DNS-SD, remembered endpoints or LAN neighbors.

Only the configured local ADB server is used. There is no subnet/port-range scan,
authorization bypass, transport-mode change, or display-setting write here.
"""
from concurrent.futures import ThreadPoolExecutor
import ipaddress,json,re,socket,subprocess
from mi_probe import ADB,ENV,ROOT

CACHE=ROOT/'state/adb-discovery.json'

def endpoint(text):
    if not isinstance(text,str):return None
    match=re.fullmatch(r'([A-Za-z0-9_.-]+):(\d{1,5})',text or '')
    if not match or not 1<=int(match[2])<=65535:return None
    host=match[1]
    try:
        address=ipaddress.ip_address(host)
        if not address.is_private or address.is_loopback or address.is_multicast or address.is_unspecified:return None
    except ValueError:
        if not host.endswith('.local'):return None
    return text

def mdns_endpoints(raw):
    return list(dict.fromkeys(p for line in raw.splitlines() if re.search(r'_adb(?:-tls-connect)?\._tcp',line) for word in line.split() if (p:=endpoint(word))))

def neighbor_endpoints(raw):
    rows=[]
    for line in raw.splitlines():
        match=re.search(r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})',line)
        if not match:continue
        mac=match[2].replace('-',':').lower()
        if mac in ('ff:ff:ff:ff:ff:ff','00:00:00:00:00:00') or int(mac[:2],16)&1:continue
        if endpoint(match[1]+':5555'):rows.append(match[1]+':5555')
    return list(dict.fromkeys(rows))[:256]

def open_endpoint(value):
    host,port=value.rsplit(':',1)
    try:
        with socket.create_connection((host,int(port)),timeout=.25):return value
    except OSError:return None

class Discovery:
    def __init__(self,port,folder,progress=lambda _:None):
        self.port=port;self.folder=folder;folder.mkdir(parents=True,exist_ok=True);self.rows=[];self.progress=progress;self.pending=[]
        try:self.cache=json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
        except (OSError,ValueError):self.cache={}
        if not isinstance(self.cache,dict) or not isinstance(self.cache.get('endpoints',[]),list):self.cache={}

    def run(self,*args,timeout=5,system=False):
        command=list(args) if system else [str(ADB),'-P',str(self.port),*args]
        try:
            p=subprocess.run(command,env=ENV,capture_output=True,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
            row=dict(command=command,stdout=p.stdout.decode('utf-8',errors='replace'),stderr=p.stderr.decode('utf-8',errors='replace'),exit_status=p.returncode)
        except subprocess.TimeoutExpired as e:
            row=dict(command=command,stdout=(e.stdout or b'').decode(errors='replace'),stderr='timeout',exit_status=None)
        self.rows.append(row);(self.folder/'execution.json').write_text(json.dumps(self.rows,ensure_ascii=False,indent=2),encoding='utf-8');return row

    def identify(self,serial,source):
        result=self.run('-s',serial,'shell','getprop ro.product.device; getprop ro.serialno',timeout=3)
        if result['exit_status']!=0:
            if any(s in (result['stdout']+result['stderr']).lower() for s in ('unauthorized','offline','authentication')):self.pending.append(serial)
            return None
        values=result['stdout'].strip().splitlines()
        if not values or values[0].strip()!='beekeeper':return None
        return dict(serial=serial,port=self.port,source=source,device='beekeeper',device_serial=values[1].strip() if len(values)>1 else '')

    def remember(self,result):
        endpoints=[result['serial']] if endpoint(result['serial']) else []
        network=self.run('-s',result['serial'],'shell','ip -o -4 addr show; getprop service.adb.tcp.port',timeout=3)
        lines=network['stdout'].strip().splitlines();port=int(lines[-1]) if lines and lines[-1].isdigit() else 0
        if 1<=port<=65535:
            endpoints.extend(ip+':'+str(port) for ip in re.findall(r'\binet\s+(\d+\.\d+\.\d+\.\d+)/',network['stdout']) if endpoint(ip+':'+str(port)))
        endpoints=list(dict.fromkeys(endpoints+self.cache.get('endpoints',[])))[:8]
        CACHE.parent.mkdir(parents=True,exist_ok=True);CACHE.write_text(json.dumps(dict(endpoints=endpoints,device_serial=result['device_serial']),ensure_ascii=False,indent=2),encoding='utf-8')
        (self.folder/'selected.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return result

    def choose(self,matches):
        # USB and Wi-Fi can describe the same physical monitor. Keep the preferred transport order.
        unique={}
        for row in matches:unique.setdefault(row['device_serial'] or row['serial'],row)
        matches=list(unique.values())
        if len(matches)==1:return self.remember(matches[0])
        if len(matches)>1:
            saved=[r for r in matches if r['device_serial']==self.cache.get('device_serial')]
            if len(saved)==1:return self.remember(saved[0])
            raise ValueError('发现多台支持的显示器，请在高级连接中选择其中一台：'+', '.join(r['serial'] for r in matches))
        return None

    def find(self,preferred=''):
        self.progress('查找USB与已在线的ADB设备')
        raw=self.run('devices','-l')['stdout'];devices=[line.split()[:2] for line in raw.splitlines()[1:] if len(line.split())>=2]
        devices.sort(key=lambda r:(r[0]!=preferred,':' in r[0]))
        matches=[]
        for serial,status in devices:
            if status=='unauthorized':self.pending.append(serial);continue
            if status!='device':continue
            if found:=self.identify(serial,'USB' if ':' not in serial else '已在线的无线ADB'):matches.append(found)
        if found:=self.choose(matches):return found
        self.progress('查找局域网ADB广播与已记录地址')
        broadcast=self.run('mdns','services',timeout=5)['stdout']
        candidates=list(dict.fromkeys(mdns_endpoints(broadcast)+([preferred] if endpoint(preferred) else [])+[p for p in self.cache.get('endpoints',[]) if endpoint(p)]))
        tried=set()
        def connect(values,source):
            matches=[]
            for serial in values:
                if serial in tried:continue
                tried.add(serial);self.run('connect',serial,timeout=3)
                if found:=self.identify(serial,source):matches.append(found)
            return self.choose(matches)
        if found:=connect(candidates,'广播/已记录地址'):return found
        self.progress('检查本机已知局域网邻居的传统ADB端口')
        neighbors=neighbor_endpoints(self.run('arp','-a',system=True,timeout=3)['stdout'])
        with ThreadPoolExecutor(max_workers=8) as pool:available=[p for p in pool.map(open_endpoint,neighbors) if p]
        if found:=connect(available,'局域网邻居 · 5555'):return found
        if self.pending:raise ValueError('已发现ADB设备但尚未授权/在线。请在显示器上确认调试授权或重新开启ADB；无需手填IP。设备：'+', '.join(dict.fromkeys(self.pending)))
        raise ValueError('未发现已开启ADB的显示器。已检查USB、ADB广播、记录地址及本机已知局域网邻居；请确认显示器ADB已开启。未广播的自定义端口可在高级连接中指定。')

def discover(port,folder,preferred='',progress=lambda _:None):return Discovery(port,folder,progress).find(preferred)
