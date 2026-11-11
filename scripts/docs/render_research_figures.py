"""Render reproducible, data-driven SVG figures. Rasterize the SVGs with a standard SVG renderer."""
from pathlib import Path
import argparse,html,json,math
ROOT=Path(__file__).resolve().parents[2]
COLORS=['#36d6b5','#9d8aff','#ffb86b','#61b5ff','#f27c9c','#b6cf62','#d4a1ff','#cdd8e6']
BG='#0d1420';PANEL='#152131';FG='#eaf2fa';MUTED='#b1c2d4';GRID='#34465c'

class SVG:
 def __init__(self,w,h,title,subtitle):
  self.w=w;self.h=h;self.items=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">',f'<rect width="{w}" height="{h}" rx="20" fill="{BG}"/>']
  self.text(52,55,title,32,FG,600);self.text(52,92,subtitle,21,MUTED)
 def text(self,x,y,s,size=21,color=FG,weight=400,anchor='start'):
  self.items.append(f'<text x="{x:.2f}" y="{y:.2f}" fill="{color}" font-family="Microsoft YaHei,Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{html.escape(str(s))}</text>')
 def rect(self,x,y,w,h,fill,stroke=None,sw=1,rx=0):self.items.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" rx="{rx}"'+(f' stroke="{stroke}" stroke-width="{sw}"' if stroke else '')+'/>')
 def line(self,x1,y1,x2,y2,color=GRID,width=1,dash=None):self.items.append(f'<path d="M{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f}" fill="none" stroke="{color}" stroke-width="{width}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
 def path(self,points,color,width=3,dash=None):
  self.items.append('<path d="'+' '.join(('M' if i==0 else 'L')+f'{x:.2f},{y:.2f}' for i,(x,y) in enumerate(points))+'" fill="none" stroke="'+color+'" stroke-width="'+str(width)+'"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
 def save(self,p):p.write_text('\n'.join(self.items+['</svg>']),encoding='utf-8',newline='\n')

def heat(v,maximum):
 t=max(0,min(1,v/max(1,maximum)));a=(12,20,31);b=(197,255,236)
 return '#'+''.join(f'{round(x+(y-x)*t):02x}' for x,y in zip(a,b))
def map_grid(s,values,x,y,cell=12,cols=48,rows=24,maximum=65535,crop=None,bins=False):
 x0,y0,cw,ch=crop or (0,0,cols,rows)
 for yy in range(ch):
  for xx in range(cw):
   v=values[(yy+y0)*cols+xx+x0];color=(COLORS[v] if v>=0 else '#0b1019') if bins else heat(v,maximum)
   s.rect(x+xx*cell,y+yy*cell,cell-.5,cell-.5,color)
 s.rect(x,y,cw*cell,ch*cell,'none',GRID)
def legend(s,entries,x,y,step=230):
 for i,(name,color) in enumerate(entries):s.line(x+i*step,y-6,x+34+i*step,y-6,color,4);s.text(x+44+i*step,y,name,20)
def plot(s,box,series,xticks,yticks,xmin,xmax,ymin,ymax,xlog=False,xlabel='',ylabel='',shade=None):
 x,y,w,h=box
 def X(v):return x+(math.log10(v/xmin)/math.log10(xmax/xmin) if xlog else (v-xmin)/(xmax-xmin))*w
 def Y(v):return y+h-(v-ymin)/(ymax-ymin)*h
 s.rect(x,y,w,h,PANEL)
 if shade:
  a,b=shade;s.rect(X(a),y,X(b)-X(a),h,'#1d2d41')
 for v in yticks:
  if ymin<=v<=ymax:s.line(x,Y(v),x+w,Y(v));s.text(x-12,Y(v)+7,f'{v:g}',18,MUTED,anchor='end')
 for v in xticks:
  if xmin<=v<=xmax:s.line(X(v),y,X(v),y+h,GRID,1,'3 5');s.text(X(v),y+h+29,f'{v:g}',18,MUTED,anchor='middle')
 for values,color,dash in series:
  points=[(X(a),Y(b)) for a,b in values if xmin<=a<=xmax]
  s.path(points,color,3.5,dash)
 s.text(x+w/2,y+h+61,xlabel,20,MUTED,anchor='middle');s.text(x,y-15,ylabel,20,MUTED)
 return X,Y

def render(data,folder,lang):
 zh=lang=='zh';L=lambda a,b:a if zh else b
 # 1. A point stimulus makes the non-Gaussian ring topology visible.
 s=SVG(1500,940,L('SF 改的是哪些邻格？','Which neighbours does SF affect?'),L('单个逻辑格输入 65280；仅一个 SF=0，其余为 255。原厂 ARM64 空间函数离线执行。','One logical input cell = 65280; one SF=0, the others=255. Offline ARM64 execution.'))
 for i,r in enumerate(data['sf_rings']['cases']):
  x=70+(i%3)*490;y=168+(i//3)*350
  s.text(x,y,r['label'],25,FG,600);map_grid(s,r['output'],x,y+22,cell=20,crop=(18,6,13,13),maximum=65280)
  s.rect(x+6*20,y+22+6*20,20,20,'none','#ffb86b',2)
  s.text(x+285,y+66,L('亮格数','Lit cells'),18,MUTED);s.text(x+285,y+106,r['lit_cells'],35,COLORS[0],600)
 s.text(52,905,L('橙框＝原输入；亮格＝数字输出非零。逻辑网格不代表 LED 物理形状，图中没有光学散射。','Orange outline: original input. Bright cells: nonzero digital output. This is not an optical halo photograph.'),20,MUTED)
 s.save(folder/f'sf-rings.{lang}.svg')
 # 2. Same footprint, different digital intensity; the centerline provides exact magnitudes.
 s=SVG(1500,1000,L('SF1 的数值如何改变扩散强度？','How SF1 changes spread intensity'),L('3×3 亮格；SF2–SF5=255。上方共用线性色标，下方为中央行的实际数字剖面。','3×3 bright input; SF2–SF5=255. Shared linear scale above; exact digital centerline below.'))
 selected=[r for r in data['sf_strength']['cases'] if r['sf1'] in (0,128,240,255)]
 for i,r in enumerate(selected):
  x=58+i*365;s.text(x,160,'SF1 = '+str(r['sf1']),25,FG,600);map_grid(s,r['output'],x,186,cell=23,crop=(18,7,13,11),maximum=65280)
  s.rect(x+5*23,186+4*23,69,69,'none','#ffb86b',2)
  s.text(x,477,L('外一格 raw = ','One cell outside: raw = ')+str(r['edge_raw']),20,MUTED)
 legend(s,[(str(r['sf1']),COLORS[i]) for i,r in enumerate(selected)],120,543,250)
 series=[([(i-24,v/65280*100) for i,v in enumerate(r['centerline'])],COLORS[k],None) for k,r in enumerate(selected)]
 plot(s,(120,592,1290,257),series,[-6,-4,-2,0,2,4,6],[0,25,50,75,100],-6,6,0,105,xlabel=L('离中心的逻辑格偏移','Logical-cell offset from center'),ylabel=L('输入峰值归一化 / %','Relative to input peak / %'))
 s.text(52,963,L('这里改变的是非线性邻域的取大包络，不能把 SF 当成高斯模糊半径或亮度百分比。','The filter uses a nonlinear neighbourhood maximum envelope, not a Gaussian radius or a brightness percentage.'),20,MUTED)
 s.save(folder/f'sf-strength.{lang}.svg')
 # 3. Alpha index follows local mean, not global window size.
 s=SVG(1500,1100,L('Alpha0–7：由局部均值选择的 8 个桶','Alpha0–7: eight bins selected by local mean'),L('固定局部 Max=255、DC=8、Blend=8、Dynamic=1；横轴遍历全部 256 个局部均值。','Local Max=255, DC=8, Blend=8, Dynamic=1; all 256 local-mean inputs are evaluated.'))
 sweep=data['alpha_sweep'];first=sweep['cases'][:3]
 legend(s,[(L('原配置','Factory') if r['label']=='factory' else r['label'],COLORS[i]) for i,r in enumerate(first)],115,142,360)
 series=[([(x,y) for x,y in zip(sweep['mean'],r['output'])],COLORS[i],None) for i,r in enumerate(first)]
 plot(s,(115,240,1280,275),series,[0,32,64,96,128,160,192,224,255],[0,16384,32768,49152,65535],0,255,0,65535,xlabel=L('局部 Mean（不是整屏白窗面积）','Local Mean — not whole-screen window area'),ylabel=L('统计混合阶段输出 / raw','Scaling-stage output / raw'))
 for k in range(8):s.text(115+(k*32+15.5)/255*1280,189,'α'+str(k),19,COLORS[k],600,anchor='middle')
 base=first[0]['output'];changes=sweep['cases'][3:];legend(s,[('Alpha'+str(k)+L(' 改动',' changed'),COLORS[i]) for i,k in enumerate((0,3,7))],115,611,400)
 ds=[([(x,y-z) for x,y,z in zip(sweep['mean'],r['output'],base)],COLORS[i],None) for i,r in enumerate(changes)]
 lo=min(y for v,c,d in ds for x,y in v);hi=max(y for v,c,d in ds for x,y in v);limit=math.ceil(max(abs(lo),abs(hi))/10000)*10000
 plot(s,(115,668,1280,263),ds,[0,31,64,96,127,160,192,224,255],[-limit,-limit/2,0,limit/2,limit],0,255,-limit,limit,xlabel=L('只改变对应 Alpha 后，差异局限于相应均值桶','Changing one Alpha affects its corresponding local-mean bin'),ylabel=L('相对原配置的输出差 / raw','Output difference from factory / raw'))
 s.text(52,1050,L('Alpha0 改为16，Alpha3 改为16，Alpha7 改为0；其他项保持原配置。这里只展示统计混合阶段。','Alpha0→16, Alpha3→16, Alpha7→0; all other values stay unchanged. Scaling stage only.'),20,MUTED)
 s.save(folder/f'alpha-bins.{lang}.svg')
 # 4. Equal global area: show the actual classes and their before/after values.
 cases=data['same_area_geometry']
 used=sorted({v for r in cases for v in r['bins'] if v>=0})
 groups=[]
 for r in cases:
  row=[]
  for k in sorted(set(r['bins'])):
   idx=[i for i,v in enumerate(r['bins']) if v==k]
   before=sorted({r['factory_output'][i] for i in idx});after=sorted({r['alpha0_16_output'][i] for i in idx})
   assert len(before)==len(after)==1
   row.append(dict(bin=k,count=len(idx),mean=sorted({r['mean'][i] for i in idx}),maximum=sorted({r['maximum'][i] for i in idx}),before=before[0],after=after[0]))
  groups.append(row)
 s=SVG(1500,1450,L('同样 10% 白色：亮点分散后，Alpha0 才在本例起作用','Same 10% white: scattered highlights activate Alpha0 here'),L('只把 Alpha0 从3改为16；SF全255，DC=8，Blend=8，Dynamic=1。比较预算之前的数字请求。','Only Alpha0 changes 3→16; all SF=255, DC=8, Blend=8, Dynamic=1. Digital requests before budgeting.'))
 s.items.append('<metadata id="alpha-geometry-data">'+html.escape(json.dumps(dict(legend_bins=used,groups=groups),ensure_ascii=False))+'</metadata>')
 legend(s,[(('α'+str(k)),COLORS[k]) for k in used]+[(L('纯黑 / Max=0','Black / Max=0'),'#758192')],58,145,275)
 s.text(58,178,L('颜色只区分 Alpha 桶，不表示亮度；只列本例实际出现的桶。','Colours identify bins, not brightness. Only bins present in these inputs are listed.'),20,MUTED)
 for x,t in [(58,L('① 白色放在哪里','① Where the white pixels are')),(550,L('② 每个小格用哪个 Alpha','② Which Alpha each cell uses')),(1040,L('③ 每格请求：原值 → 改后','③ Per-cell request: before → after'))]:s.text(x,220,t,22,FG,600)
 for ri,r in enumerate(cases):
  y=275+ri*425
  s.text(58,y-19,L('集中成一个白窗','One solid central window') if ri==0 else L('分散成 1152 个小亮块','1152 scattered highlights'),25,FG,600)
  scale=430/3840;s.rect(58,y,430,2160*scale,'#000',GRID)
  for x,t,w,h in r['rectangles']:s.rect(58+x*scale,y+t*scale,w*scale,h*scale,'#fff')
  map_grid(s,r['bins'],550,y,cell=9,bins=True)
  s.text(58,y+282,L('总白色面积 ','Total white area ')+f"{r['white_area_percent']:.2f}%",22,MUTED)
  s.text(550,y+253,L('48×24 = 1152 个逻辑格','48×24 = 1152 logical cells'),21,MUTED)
  row=groups[ri]
  # Put bright classes first, then the pure-black background.
  row=sorted(row,key=lambda g:(g['bin']<0,g['bin']))
  for gi,g in enumerate(row):
   yy=y+gi*91;color=COLORS[g['bin']] if g['bin']>=0 else '#758192'
   label='α'+str(g['bin']) if g['bin']>=0 else L('纯黑','Black')
   s.text(1040,yy+1,label+' · '+str(g['count'])+L(' 格',' cells'),21,color,600)
   s.text(1437,yy+1,f"{g['before']} → {g['after']}",20,FG,anchor='end')
   s.rect(1040,yy+16,396,10,'#253344');s.rect(1040,yy+16,396*g['before']/65280,10,'#758192')
   s.rect(1040,yy+34,396,10,'#253344');s.rect(1040,yy+34,396*g['after']/65280,10,color)
  if ri==1:
   s.text(1040,y+100,L('每格增加 47872 raw','Each cell increases by 47872 raw'),23,COLORS[0],600)
   s.text(1040,y+141,L('1152 / 1152 格发生变化','1152 / 1152 cells change'),22)
  else:s.text(550,y+292,L('α4：边缘32格；α7：内部96格','α4: 32 edge cells; α7: 96 inner cells'),21)
  s.text(58,y+325,L('只改α0：本例亮格用α4/7，输出不变。','Only α0 changes; these bright cells use α4/7.') if ri==0 else L('每格大多是黑色，少量白色；都落在α0。','Mostly black plus a small white patch in every cell: all α0.'),22,FG,600)
 s.line(58,1080,1440,1080)
 s.text(58,1120,L('放大一个局部小格：黑白像素怎样混成 Mean？','Zoom into one local cell: how black and white form Mean'),25,FG,600)
 samples=[(0,-1,L('纯黑背景','Black background')),(1,0,L('分散小亮块','Small white patch')),(0,4,L('白窗边缘','Window edge')),(0,7,L('白窗内部','Window interior'))]
 for si,(ri,k,label) in enumerate(samples):
  r=cases[ri];j=r['bins'].index(k);x=58+si*353;y=1150;cx=(j%48)*80;cy=(j//48)*90;scale=1.2
  s.rect(x,y,96,108,'#000',GRID)
  for rx,ry,rw,rh in r['rectangles']:
   ax=max(cx,rx);ay=max(cy,ry);bx=min(cx+80,rx+rw);by=min(cy+90,ry+rh)
   if bx>ax and by>ay:s.rect(x+(ax-cx)*scale,y+(ay-cy)*scale,(bx-ax)*scale,(by-ay)*scale,'#fff')
  s.text(x+111,y+23,label,20,FG,600)
  s.text(x+111,y+55,'Mean '+str(r['mean'][j]),20,MUTED)
  s.text(x+111,y+87,'Max '+str(r['maximum'][j]),20,MUTED)
  s.text(x,y+142,L('无亮输入，保持0','No bright input; stays 0') if k<0 else 'α'+str(k)+L(' · 局部白色 ',' · local white ')+{0:'10%',4:'60%',7:'100%'}[k],20,COLORS[k] if k>=0 else MUTED)
 s.text(58,1348,L('灰条＝改前；彩条＝改后；所有条共用 0–65280 的线性 raw 标尺。','Grey bar = before; coloured bar = after. All bars use the same linear raw scale: 0–65280.'),21,MUTED)
 s.text(58,1388,L('逻辑格与实际 LED 外形无对应承诺；数字请求变化不等于屏幕亮度倍率。换位置或形状会改变结果。','Logical cells are not physical LED shapes. Request changes are not luminance ratios; alignment and geometry matter.'),20,MUTED)
 s.save(folder/f'alpha-geometry.{lang}.svg')
 # 5. The actual current model, including the reference-nit proxy, at selected budgets.
 s=SVG(1500,1190,L('统一预算怎样改变窗口曲线？','How the uniform budget changes window curves'),L('32U 2026 · 高控光 · HGiG · 10000 nit PQ 输入 · 累计 ABL 关闭。亮度为当前软件模型参考估算。','32U 2026 · High · HGiG · 10000-nit PQ input · cumulative ABL off. Nits are current model estimates.'))
 budgets=data['budget_curves']['budgets'];legend(s,[(L('预算 ','Budget ')+str(b),COLORS[i]) for i,b in enumerate(budgets)],115,145,380)
 ymax=math.ceil(max(v['reference_nits'] for c in data['budget_curves']['cases'] for r in c['rows'] for v in r['values'])/500)*500
 for ci,c in enumerate(data['budget_curves']['cases']):
  y=246+ci*445;s.text(55,y-63,L('原厂 SF / Alpha','Factory SF / Alpha') if ci==0 else L('只把 SF1 改为0，其他不变','Only SF1→0; all other values unchanged'),25,FG,600)
  series=[]
  for j,b in enumerate(budgets):series.append(([(r['area'],next(v['reference_nits'] for v in r['values'] if v['budget']==b)) for r in c['rows']],COLORS[j],None))
  plot(s,(110,y,580,285),series,[.001,.01,.1,1,10,100],list(range(0,ymax+1,500)),.001,100,0,ymax,True,xlabel=L('白窗面积 / % · 对数轴','Window area / % · log scale'),ylabel=L('参考亮度 / nit（估算）','Reference luminance / nit (estimate)'),shade=(10,100))
  plot(s,(850,y,565,285),series,[10,25,50,75,100],list(range(0,ymax+1,500)),10,100,0,ymax,False,xlabel=L('10%–100% 局部放大','10%–100% enlarged'),ylabel=L('同一组数据 · 线性面积轴','Same data · linear area axis'))
 s.text(52,1132,L('10% 是阅读分段，不是固件固定开关。SF/Alpha 会改变负载分布，预算开始影响曲线的位置也会变化。','10% is a reading split, not a fixed firmware switch. SF/Alpha alter load distribution and the onset of limiting.'),20,MUTED)
 s.text(52,1168,L('这是离线对照，不是新一轮亮度计测量，也不是参数安全性或推荐值。','Offline comparison, not a new luminance measurement or a parameter-safety recommendation.'),19,MUTED)
 s.save(folder/f'budget-curves.{lang}.svg')
 # 6. The different numeric domains must not be confused with a live readout or measured nits.
 st=data['signal_stages'];s=SVG(1500,1170,L('从输入统计到 MCU 返回缓存：同一窗口的四张数值图','From input statistics to the MCU-returned buffer'),L('10% 白窗，预算24；历史 LDF 输入统计与离线函数输出。此图不是此刻设备分区帧的直播。','10% window, budget 24; historical LDF statistics and offline outputs, not live hardware frame capture.'))
 panels=[('LDF Mean · 96×48',st['ldf_mean'],96,48,255),('LDF Max · 96×48',st['ldf_max'],96,48,255),(L('空间滤波输出 · 48×24','Spatial-filter output · 48×24'),st['spatial_raw'],48,24,65535),(L('MCU 返回缓存 · 48×24','MCU-returned buffer · 48×24'),st['mcu_output_raw'],48,24,65535)]
 for i,(label,values,cols,rows,maximum) in enumerate(panels):
  x=60+(i%2)*750;y=187+(i//2)*455;s.text(x,y-22,label,25,FG,600);cell=640/cols;map_grid(s,values,x,y,cell,cols,rows,maximum)
  s.text(x,y+cols/2*cell+40,f"max {max(values):,.0f}   |   mean {sum(values)/len(values):,.2f}   |   scale 0–{maximum}",21,MUTED)
 s.text(52,1100,L('上排是0–255的输入统计，下排是16位算法数值。不同数值域不能直接比大小，更不能直接称作屏幕 nit。','Top: 0–255 input statistics. Bottom: 16-bit algorithm values. Different numeric domains are not screen nits.'),20,MUTED)
 s.text(52,1138,L('APP 的 raw/raw_apl 是全局 AW 读回；不等同于这里的分区峰值，也不等同于 SPI 电流。','APP raw/raw_apl is a global AW readback, not the zone peak shown here and not SPI electrical current.'),20,MUTED)
 s.save(folder/f'driver-stages.{lang}.svg')

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,default=ROOT/'docs/assets/research/model-experiments.json');p.add_argument('--output',type=Path,default=ROOT/'docs/assets/research');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);data=json.loads(a.data.read_text('utf-8'))
 for lang in ('zh','en'):render(data,a.output,lang)
 print('Rendered 6 data-driven figures in Chinese and English (12 SVGs)')
