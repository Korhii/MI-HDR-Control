/* Exact parameter bridge for the owned mi_oemabl module; no arbitrary paths. */
extern void *dlopen(const char*,int);
extern void *dlsym(void*,const char*);
extern int snprintf(char*,unsigned long,const char*,...);
extern char *getenv(const char*);
extern int usleep(unsigned int);
extern long write(int,const void*,unsigned long);
extern void _exit(int);
#include "hdr_mapping_packet.h"
static void text(const char*s){unsigned long n=0;while(s[n])++n;write(1,s,n);}
__attribute__((constructor)) static void run(void){
 void*lib=dlopen("/vendor/lib64/libbspmserver.so",2);
 if(!lib){_exit(1);return;}
 void*(*instance)(void)=dlsym(lib,"_ZN7android16BspMServerClient11getInstanceEv");
 void*(*create)(void*)=dlsym(lib,"_ZN7android16BspMServerClient18CreateConfigObjectEv");
 int(*read_file)(void*,const char*,char*,int)=dlsym(lib,"_ZN7android16BspMServerConfig15ReadStrFromFileEPKcPci");
 int(*put)(void*,const char*,const char*)=dlsym(lib,"_ZN7android16BspMServerConfig14WriteStrToFileEPKcS2_");
 if(!instance||!create||!read_file||!put){_exit(2);return;}
 void*c=instance();void*cfg=c?create(c):0;if(!cfg){_exit(3);return;}
 const char*fields[]={"budget","budget_used","frames","lease_end","tick","raw_apl","raw_spi","window","level","enabled","l_th","e0","divisor","r_reset","k","energy","r_prev","gain_next","load","recovery","charge","delta","triggered","threshold","generation","gain_used","active","k_min","k_max","c_max","g_base","native_gain","stat_floor","factory_l_th","factory_e0","factory_divisor","factory_r_reset","factory_g_base","original_cap","post_cap","native_k","native_energy","native_r_prev","budget_active","source_format","hdr_revision","hdr_active","hdr_p0","hdr_gain","hdr_mode_actual","hdr_picture","hdr_floor","hdr_peak_filter"};
 const char*mapping=getenv("MI_HDR_MAPPING_CONFIG");
 if(mapping){
  char revision[1001]={0};
  if(read_file(cfg,"/sys/module/mi_oemabl/parameters/hdr_revision",revision,1000)<=0||revision[0]!='2'||!write_mapping(mapping,cfg,put)){text("mapping_write_failed=1\n");_exit(9);return;}
  text("mapping_write_return=1\n");
 }
 const char*policy=getenv("MI_OEM_ABL_CONFIG");
 if(policy){
  const char*names[]={"enabled","l_th","e0","divisor","r_reset","generation"};
  unsigned values[6];const char*p=policy;
  for(int i=0;i<6;i++){
   unsigned long long n=0;unsigned digits=0;while(*p>='0'&&*p<='9'&&digits<10){n=n*10+(unsigned)(*p++-'0');digits++;}
   unsigned long long max=i==0?1:i==1||i==3?65535:i==4?82800:4294967295ULL;
   if(!digits||n>max||(i<5?*p!=',':*p!=0)){_exit(7);return;}
   values[i]=(unsigned)n;if(i<5)p++;
  }
  if(put(cfg,"/sys/module/mi_oemabl/parameters/lease_end","0")!=1){_exit(8);return;}
  for(int i=0;i<6;i++){
   char path[160],number[40];snprintf(path,sizeof(path),"/sys/module/mi_oemabl/parameters/%s",names[i]);snprintf(number,sizeof(number),"%u",values[i]);
   if(put(cfg,path,number)!=1){text("policy_write_failed=1\n");_exit(8);return;}
  }
  text("policy_write_return=1\n");
 }
 const char*setting=getenv("MI_BUDGET_SET");
 if(setting){unsigned n=0,i=0;while(setting[i]>='0'&&setting[i]<='9'&&i<3)n=n*10+setting[i++]-'0';if(!i||setting[i]||n>86){_exit(4);return;}char line[80];int rc=put(cfg,"/sys/module/mi_oemabl/parameters/budget",setting);snprintf(line,sizeof(line),"write_return=%d\n",rc);text(line);}
 const char*run=getenv("MI_BUDGET_RUN");
 if(run){
  if((run[0]!='0'&&run[0]!='1')||run[1]){_exit(5);return;}
  char b[1001]={0},value[40],line[80];unsigned deadline=0;
  if(run[0]=='1'){
   if(read_file(cfg,"/sys/module/mi_oemabl/parameters/tick",b,1000)<=0){text("tick_unavailable=1\n");_exit(6);return;}
   for(int i=0;b[i]>='0'&&b[i]<='9';++i)deadline=deadline*10+(unsigned)(b[i]-'0');
   deadline+=2500; /* This exact kernel CONFIG_HZ=250; ten-second lease. */
  }
  snprintf(value,sizeof(value),"%u",deadline);int rc=put(cfg,"/sys/module/mi_oemabl/parameters/lease_end",value);
  snprintf(line,sizeof(line),"lease_write_return=%d\n",rc);text(line);
 }
 if(setting||run||mapping)usleep(100000); /* Allow a fresh driver invocation before the sampled readback. */
 for(unsigned i=0;i<sizeof(fields)/sizeof(fields[0]);++i){char path[160],b[1001]={0},line[180];snprintf(path,sizeof(path),"/sys/module/mi_oemabl/parameters/%s",fields[i]);int rc=read_file(cfg,path,b,1000);b[1000]=0;snprintf(line,sizeof(line),"read_return.%s=%d\n%s=",fields[i],rc,fields[i]);text(line);text(b);text("\n");}
 if(mapping||getenv("MI_HDR_READ_ANCHORS"))for(unsigned i=0;i<11;i++){char path[160],b[1001]={0},line[180];snprintf(path,sizeof(path),"/sys/module/mi_oemabl/parameters/hdr_apl%u",i);int rc=read_file(cfg,path,b,1000);snprintf(line,sizeof(line),"hdr_apl%u=",i);text(line);if(rc>0)text(b);text("\n");}
 text("__complete=1\n");_exit(0);
}
