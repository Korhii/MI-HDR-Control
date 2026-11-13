/* Private fixed schema: enabled,level,tone,generation,11 Q16 window gains. */
static int write_mapping(const char*s,void*cfg,int(*put)(void*,const char*,const char*)){
 unsigned v[15];
 for(unsigned i=0;i<15;i++){
  unsigned long long n=0;unsigned digits=0;
  while(*s>='0'&&*s<='9'&&digits<10){n=n*10+(unsigned)(*s++-'0');digits++;}
  unsigned long long max=i==0?1:i==1?3:i==2?5:i==3?4294967295ULL:4194240;
  if(!digits||n>max||(i<14?*s!=',':*s!=0))return 0;
  v[i]=(unsigned)n;if(i<14)s++;
 }
 if(!v[1]||!(v[2]==0||v[2]==1||v[2]==2||v[2]==5))return 0;
 if(put(cfg,"/sys/module/mi_oemabl/parameters/lease_end","0")!=1)return 0;
 for(unsigned i=0;i<15;i++){
  unsigned j=i==14?3:i>=3?i+1:i;char name[40],path[160],number[40];
  if(j==0)snprintf(name,sizeof(name),"hdr_sync");
  else if(j==1)snprintf(name,sizeof(name),"hdr_level");
  else if(j==2)snprintf(name,sizeof(name),"hdr_tone");
  else if(j==3)snprintf(name,sizeof(name),"hdr_generation");
  else snprintf(name,sizeof(name),"hdr_scale%u",j-4);
  snprintf(path,sizeof(path),"/sys/module/mi_oemabl/parameters/%s",name);snprintf(number,sizeof(number),"%u",v[j]);
  if(put(cfg,path,number)!=1)return 0;
 }
 return 1;
}
