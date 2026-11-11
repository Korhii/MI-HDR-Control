"""Reproduce documentation figures with the prepared 0.9.17 PC model. Never opens ADB."""
from pathlib import Path
import argparse,copy,hashlib,json,struct,sys,time

def collect(runtime,output):
 runtime=Path(runtime).resolve();output=Path(output);sys.path[:0]=[str(runtime/'lab'),str(runtime/'scripts'),str(runtime/'tools/predict-libs')]
 from local_asset_paths import require_ready
 require_ready()
 from firmware_scaling import Driver
 from firmware_model import Driver as ConfigDriver
 import device_models as dm,ldf_response as ldf
 from firmware_budget import BUFFER
 dm.activate('32u-2026',5);stock=dm.defaults(3);driver=Driver();start=time.monotonic()
 data=dict(format='mi-hdr-documentation-research-v1',kind='offline firmware execution and reference estimates; no new screen-luminance measurement',model='32u-2026',local_dimming=3,tone=5,input_nits=10000,
  grid=[48,24],grid_note='algorithm coordinates, not a physical LED-count claim',stock=stock,
  source_sha256={n:hashlib.sha256((runtime/n).read_bytes()).hexdigest() for n in ('lab/firmware_scaling.py','lab/firmware_model.py','lab/ldf_response.py','tools/response-math.dll','resources/ui/ldf-samples.json')})
 def spatial(source,sf):
  radius=max((i+1 for i,v in enumerate(sf) if v!=255),default=0)
  if not radius:return list(source)
  coefficients=[0]*176
  for y in range(radius*2+1):
   for x in range(radius*2+1):
    ring=max(abs(x-radius),abs(y-radius));coefficients[y*16+x]=(sf[ring-1]<<8) if ring else 0
  driver.u.mem_write(0x60100000,struct.pack('<1152H',*source));driver.u.mem_write(0x60130000,struct.pack('<176H',*coefficients))
  name='MDrv_Alg_LD_SpatialFilter_NonLinearMode_'+('One' if radius<4 else 'Two')+'_Array_NEON'
  driver.call(name,0x60100000,0x60110000,24,48,0x60130000,radius,radius)
  return list(struct.unpack('<1152H',driver.u.mem_read(0x60110000,2304)))
 point=[65280 if x==24 and y==12 else 0 for y in range(24) for x in range(48)]
 block=[65280 if abs(x-24)<=1 and abs(y-12)<=1 else 0 for y in range(24) for x in range(48)]
 rings=[dict(label='all 255',sf=[255]*5)]
 for k in range(1,6):sf=[255]*5;sf[k-1]=0;rings.append(dict(label='SF'+str(k)+' = 0',sf=sf))
 for row in rings:row['output']=spatial(point,row['sf']);row['lit_cells']=sum(v>0 for v in row['output'])
 data['sf_rings']=dict(input=point,cases=rings)
 strengths=[]
 for value in (0,64,128,192,240,255):
  sf=[value,255,255,255,255];out=spatial(block,sf)
  strengths.append(dict(sf1=value,output=out,centerline=out[12*48:13*48],outside_sum=sum(v for v,s in zip(out,block) if not s),edge_raw=out[12*48+26]))
 data['sf_strength']=dict(input=block,cases=strengths)
 print('SF ring and strength experiments complete',flush=True)
 vectors=[('factory',stock['alpha']),('all 0',[0]*8),('all 16',[16]*8)]
 for k in (0,3,7):a=list(stock['alpha']);a[k]=16 if k<7 else 0;vectors.append(('only Alpha'+str(k)+' changed',a))
 data['alpha_sweep']=dict(mean=list(range(256)),maximum=255,dc=8,blend=8,dynamic=1,cases=[dict(label=label,alpha=a,output=[driver.scaling(m,255,a) for m in range(256)]) for label,a in vectors])
 def cells(rectangles):
  out=[]
  for y in range(24):
   for x in range(48):
    count=sum(max(0,min((x+1)*80,r+width)-max(x*80,r))*max(0,min((y+1)*90,t+height)-max(y*90,t)) for r,t,width,height in rectangles)
    out.append((min(255,count*255//7200),255 if count else 0))
  return out
 center=[(1280,756,1280,648)]
 dots=[(x*80+28,y*90+30,24,30) for y in range(24) for x in range(48)]
 geometry=[]
 for label,rectangles in [('center window',center),('fine highlights',dots)]:
  inp=cells(rectangles);changed=copy.deepcopy(stock);changed['sf']=[255]*5;changed['alpha'][0]=16;base=copy.deepcopy(stock);base['sf']=[255]*5
  a,ma=ConfigDriver(base).process(inp);b,mb=ConfigDriver(changed).process(inp)
  geometry.append(dict(label=label,rectangles=rectangles,white_area_percent=sum(w*h for x,y,w,h in rectangles)/8294400*100,
   mean=[x[0] for x in inp],maximum=[x[1] for x in inp],bins=[x[0]//32 if x[1] else -1 for x in inp],factory_output=list(a),alpha0_16_output=list(b),delta=[y-x for x,y in zip(a,b)],metrics_before=ma,metrics_after=mb))
 data['same_area_geometry']=geometry
 print('Alpha sweep and equal-area geometry experiments complete',flush=True)
 areas=[.001,.003,.01,.03,.1,.3,1,2,5,10,15,20,25,30,40,50,60,75,100];budgets=[16,24,41];curves=[]
 for name,config in [('factory SF/Alpha',stock),('SF1=0; Alpha unchanged',{**stock,'sf':[0,255,255,255,255]})]:
  e=ldf.Engine(config,3,10000);rows=[]
  for area in areas:
   s=e.spatial(area);sp=list(struct.unpack('<1152H',s));values=[]
   for budget in budgets:
    metrics=list(e.run(s,area,budget));out=list(struct.unpack('<1152H',e.alg.u.mem_read(BUFFER,2304)))
    values.append(dict(budget=budget,roi_raw=metrics[0],near_dark_raw=metrics[1],far_dark_raw=metrics[2],peak_raw=metrics[3],reference_nits=ldf.scale_nit(metrics,config,3,area,10000),output_mean=sum(out)/1152))
   rows.append(dict(area=area,spatial_peak=max(sp),spatial_mean=sum(sp)/1152,driver_window_percent=sum(sp)/max(1,max(sp))/1152*100,values=values))
  curves.append(dict(label=name,config=config,rows=rows));print('Budget curves complete: '+name,flush=True)
 data['budget_curves']=dict(areas=areas,budgets=budgets,cases=curves)
 e=ldf.Engine(stock,3,10000);area=10;s=e.spatial(area);m=e.run(s,area,24);inp=ldf.ldf(area,10000)[0]
 data['signal_stages']=dict(area=area,input_nits=10000,budget=24,ldf_shape=[96,48],ldf_mean=list(inp[0::2]),ldf_max=list(inp[1::2]),spatial_raw=list(struct.unpack('<1152H',s)),mcu_output_raw=list(struct.unpack('<1152H',e.alg.u.mem_read(BUFFER,2304))),metric=list(m),reference_nits=ldf.scale_nit(m,stock,3,area,10000),note='Historical 96x48 statistics; no live-driver readback or optical measurement performed in this documentation step')
 data['elapsed_seconds']=round(time.monotonic()-start,3);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8',newline='\n')
 print(json.dumps(dict(output=str(output),seconds=data['elapsed_seconds'],device_writes=False)),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();collect(a.runtime,a.output)
