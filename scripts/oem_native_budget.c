/* Exact-device uniform budget plus the OEM cumulative policy, no window knots/timers. */
typedef unsigned int u32;typedef unsigned short u16;typedef unsigned char u8;
typedef unsigned long u64;typedef long s64;
#define INLINE static __attribute__((always_inline)) inline
#define KMAX 31243U
#define KMIN 18288U
#define GBASE 65535U
#define E0 37491600U
#define PATCH 0xffffffc00910011cUL
#define RCU 0xffffffc008173cecUL
INLINE u32 min(u32 a,u32 b){return a<b?a:b;}
INLINE u64 data(volatile u32*c){return ((volatile u64*)(c+48))[0];}
INLINE u64 bss(volatile u32*c){return ((volatile u64*)(c+48))[1];}
INLINE int live(volatile u32*c){return c[4]&&(int)(c[4]-*(volatile u32*)0xffffffc009bc6980UL)>0;}
INLINE void reset(volatile u32*c){c[13]=KMAX;c[14]=c[10];c[15]=0;c[16]=GBASE;c[21]=0;}
/* Owned mapping uses the same frame/lease as budget; no PC frame loop. */
INLINE volatile u32* hdr(volatile u32*c){return (volatile u32*)((volatile u64*)(c+54))[0];}
INLINE void mapping(volatile u32*c,int active,u32 gain){
 if(c[60]!=2)return;
 volatile u32*p=hdr(c);int was=c[58];
 /* Capture factory initialization when the lease starts, not early at boot. */
 if(!was){
  for(u32 i=0;i<11;i++)c[64+i]=p[50+i];
  c[75]=p[47];c[76]=((volatile u8*)p)[176];
 }
 if(c[57]!=c[59]||(!was&&active)){
  u32 valid=c[62]>=1&&c[62]<=3&&(c[61]==0||c[61]==1||c[61]==2||c[61]==5);
  for(u32 i=0;i<11;i++){u32 n=c[80+i];if(n>64U*GBASE)valid=0;c[96+i]=min((u32)((u64)c[64+i]*n/GBASE),10000);}
  c[110]=c[62];c[111]=c[61];c[107]=valid;c[59]=c[57];
 }
 int apply=active&&c[56]&&c[107]&&c[25]==c[110]&&p[85]==c[111];
 if(apply&&(!was||c[63]!=p[85]||c[78]!=p[84])){c[75]=p[47];c[63]=p[85];c[78]=p[84];}
 c[58]=apply;c[108]=apply?gain:GBASE;
 if(!apply&&!was)return;
 /* ABL already defines the time curve. Avoid a second P0-only low-pass lag. */
 if(apply&&(c[27]||gain!=GBASE||c[77])){((volatile u8*)p)[176]=0;c[77]=1;}
 else if(c[77]){((volatile u8*)p)[176]=(u8)c[76];c[77]=0;}
 for(u32 i=0;i<11;i++){
  u32 value=apply?(u32)((u64)c[96+i]*gain/GBASE):c[64+i];
  if(apply&&value&&value<100)value=100;
  p[50+i]=min(value,10000);
 }
 u32 floors=c[75];
 if(apply){
  u32 limit=p[c[25]==3?60:55];if(limit<100)limit=100;
  floors=min(floors&65535,limit)|(min(floors>>16,limit)<<16);
 }
 if(apply||p[85]==c[63])p[47]=floors;
}
u32 mi_budget_high(volatile u32*c){u32 n=live(c)?min(c[0],86):24;c[1]=n;return n;}
u32 mi_budget_post(volatile u32*c,u16*buffer,u32 count,u32 cap,u32 mean,u32 window,u32 level){
 c[2]++;c[25]=level;c[45]=*(volatile u32*)(bss(c)+323976);c[46]=*(volatile u32*)(bss(c)+323992);c[47]=*(volatile u32*)(bss(c)+323984);c[41]=*(volatile u8*)(bss(c)+0x104);
 if(!count||count>16384||level<1||level>3)return cap;
 int active=live(c)&&c[41]==1;c[40]=active;
 u32 desired=cap;
 if(active&&level<3){c[1]=min(c[0],86);u32 budget=min(c[0],86)*65535U/86;desired=mean>budget?(u32)((u64)budget*65535/mean):65535;if(!c[0])desired=0;}
 c[42]=cap;c[43]=desired;
 int timed=active&&c[8]&&level>=2;
 if(c[24]!=c[23]||c[44]!=level){reset(c);c[24]=c[23];c[44]=level;}
 if(!timed)reset(c);
 u32 gain=timed?c[16]:(level<3?c[32]:GBASE);c[26]=gain;c[27]=timed;
 /* The OEM load statistic is taken BEFORE demura, not from the final SPI/PWM mean. */
 volatile u16*temp=(volatile u16*)(bss(c)+366348);
 u32 floor=*(volatile u16*)(bss(c)+0x4f100);c[33]=floor;
 u64 sum=0;u32 bright=0;
 for(u32 i=0;i<count;i++){
  u32 value=temp[i];
  if(active&&level<3){value=cap?(u32)((u64)value*desired/cap):0;buffer[i]=(u16)min(cap?(u32)((u64)buffer[i]*desired/cap):0,65535);}
  if(timed){value=(u32)((u64)value*gain/GBASE);buffer[i]=(u16)((u64)buffer[i]*gain/GBASE);}
  value=min(value,65535);sum+=value;if((value>>4)>floor)bright++;
 }
 u32 load=(u32)(sum/count),r=bright?(u32)(sum/bright):0;c[17]=load;c[18]=r;
 mapping(c,active,gain);
 c[19]=min(load,KMAX);c[20]=(c[11]?(KMAX-KMIN)/c[11]:0)+1;c[22]=load>c[9];
 if(timed){
  if(c[15]<c[12]){c[13]=KMAX;c[14]=c[10];}
  if(load>c[9]){
   if(c[14]<=c[19]){u32 step=c[20];c[13]=c[13]<=KMAX&&c[13]>KMIN+step?c[13]-step:KMIN;}
   else c[14]-=c[19];
  }
  c[15]=r;c[16]=(u32)((u64)GBASE*c[13]/KMAX);c[21]=gain<GBASE;
 }
 return desired;
}
INLINE u32 branch(u64 site,u64 hook){s64 d=(s64)(hook-site);return (d&3)||d<-(1L<<27)||d>=(1L<<27)?0:0x14000000U|((u32)(d>>2)&0x3ffffff);}
int mi_install(volatile u32*c,u32*high,u32*post,u32*native,u64 h,u64 p,u64 n){
 if(*high!=0x79400509||*post!=0x12003e88||(*native&0x9f00001f)!=0x90000008)return -22;
 c[3]=branch((u64)high,h);c[5]=branch((u64)post,p);c[6]=branch((u64)native,n);if(!c[3]||!c[5]||!c[6])return -22;
 c[7]=*native;u64 insn=*native,imm=(((insn>>5)&0x7ffff)<<2)|((insn>>29)&3);s64 pages=(s64)(imm<<43)>>43;
 ((volatile u64*)(c+48))[2]=((u64)native&~4095UL)+(u64)(pages*4096);
 u64 base=bss(c);c[35]=*(volatile u16*)(base+0x4f16a);c[36]=*(volatile u32*)(base+0x4f17c);c[37]=*(volatile u16*)(base+0x4f170);c[38]=*(volatile u16*)(base+0x4f16c);c[39]=*(volatile u16*)(base+0x4f166);
 if(c[35]!=KMIN||*(volatile u16*)(base+0x4f168)!=KMAX||c[36]!=E0||c[39]!=GBASE)return -22;
 u64 hp=(u64)hdr(c);
 if((hp&0xffffffff00000003UL)!=0xffffffc000000000UL)return -22;
 volatile u32*tp=hdr(c);
 for(u32 i=0;i<11;i++){if(tp[50+i]>10000)return -22;c[64+i]=tp[50+i];}
 c[75]=tp[47];c[76]=((volatile u8*)tp)[176];c[60]=2;
 int(*patch)(void*,u32)=(void*)PATCH;
 int rc=patch(high,c[3]);if(rc)return rc;
 rc=patch(post,c[5]);if(rc){patch(high,0x79400509);return rc;}
 rc=patch(native,c[6]);if(rc){patch(post,0x12003e88);patch(high,0x79400509);}return rc;
}
void mi_remove(volatile u32*c,u32*high,u32*post,u32*native){
 mapping(c,0,GBASE);c[60]=0;
 int(*patch)(void*,u32)=(void*)PATCH;
 if(*high==c[3])patch(high,0x79400509);
 if(*post==c[5])patch(post,0x12003e88);
 if(*native==c[6])patch(native,c[7]);
 ((void(*)(void))RCU)();
}
