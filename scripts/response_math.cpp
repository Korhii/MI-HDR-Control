#include <algorithm>
#include <cmath>
#include <cstdint>
extern "C" {
__declspec(dllexport) void spatial(const uint16_t* source,const uint8_t* sf,uint16_t* output){
 int radius=0;for(int i=0;i<5;i++)if(sf[i]!=255)radius=i+1;
 for(int y=0;y<24;y++)for(int x=0;x<48;x++){
  int best=source[y*48+x];
  for(int dy=-radius;dy<=radius;dy++)for(int dx=-radius;dx<=radius;dx++){
   int ring=std::max(std::abs(dx),std::abs(dy));if(!ring||x+dx<0||x+dx>=48||y+dy<0||y+dy>=24)continue;
   best=std::max(best,int(source[(y+dy)*48+x+dx])-(int(sf[ring-1])<<8));
  }output[y*48+x]=uint16_t(best);
 }
}
__declspec(dllexport) void metrics(const uint16_t* output,const double* roi,const double* nearw,const double* farw,double* result){
 double r=0,n=0,f=0;int m=0;for(int i=0;i<1152;i++){r+=output[i]*roi[i];n+=output[i]*nearw[i];f+=output[i]*farw[i];m=std::max(m,int(output[i]));}result[0]=r;result[1]=n;result[2]=f;result[3]=m;
}
// Grid: Alpha0 x Alpha1 x SF1 x budget-knot x (13 nits + halo + black).
__declspec(dllexport) void solve(const float* grid,const double* target,int ceiling,double* result){
 const int aa[]={0,2,4,6,8,10,12,14,16},ss[]={0,4,8,16,32,64,128,192,255},bb[]={0,1,4,8,16,24,41,62,86};
 auto at=[&](int a,int b,int s,int k,int i){return grid[((((a*9+b)*9+s)*9+k)*15+i)];};
 double best=1e99,chosen=1e99,scoreCut=0;double keep[21]={};
 for(int pass=0;pass<2;pass++)for(int a0=0;a0<=16;a0++)for(int a1=0;a1<=16;a1++)for(int sf=0;sf<=255;sf++){
  int al=std::min(7,a0/2),bl=std::min(7,a1/2),sl=0;while(sl<7&&ss[sl+1]<sf)sl++;
  double ta=(a0-aa[al])/2.,tb=(a1-aa[bl])/2.,ts=double(sf-ss[sl])/(ss[sl+1]-ss[sl]),values[9][15];
  for(int k=0;k<9;k++)for(int i=0;i<15;i++){double v=0;for(int da=0;da<2;da++)for(int db=0;db<2;db++)for(int ds=0;ds<2;ds++)v+=at(al+da,bl+db,sl+ds,k,i)*(da?ta:1-ta)*(db?tb:1-tb)*(ds?ts:1-ts);values[k][i]=v;}
  int j=0;for(int budget=0;budget<=ceiling;budget++){
   while(j<7&&bb[j+1]<budget)j++;double t=double(budget-bb[j])/(bb[j+1]-bb[j]),v[15],score=0;
   for(int i=0;i<15;i++)v[i]=values[j][i]+t*(values[j+1][i]-values[j][i]);
   for(int i=1;i<13;i++){double e=(v[i]-target[i])/std::max(100.,target[i]);score+=e*e/12;}
   if(!pass){best=std::min(best,score);continue;}
   double spill=v[13]+2*v[14];if(score<=scoreCut&&(spill<chosen-1e-9||(std::abs(spill-chosen)<1e-9&&score<keep[4]))){chosen=spill;keep[0]=a0;keep[1]=a1;keep[2]=sf;keep[3]=budget;keep[4]=score;keep[5]=spill;for(int i=0;i<15;i++)keep[6+i]=v[i];}
  }
  if(pass==0&&a0==16&&a1==16&&sf==255)scoreCut=std::pow(std::sqrt(best)+.005,2);
 }
 for(int i=0;i<21;i++)result[i]=keep[i];
}
}
