/* JNI bridge to the same fixed BSP module parameters used by the portable controller. */
#include <jni.h>
extern void *dlopen(const char*,int);
extern void *dlsym(void*,const char*);
extern int snprintf(char*,unsigned long,const char*,...);
#include "../hdr_mapping_packet.h"
static void *cfg;
static int (*get)(void*,const char*,char*,int);
static int (*put)(void*,const char*,const char*);
static int initialize(void){
 if(cfg)return 1;
 void *lib=dlopen("/vendor/lib64/libbspmserver.so",2);if(!lib)return 0;
 void *(*instance)(void)=dlsym(lib,"_ZN7android16BspMServerClient11getInstanceEv");
 void *(*create)(void*)=dlsym(lib,"_ZN7android16BspMServerClient18CreateConfigObjectEv");
 get=dlsym(lib,"_ZN7android16BspMServerConfig15ReadStrFromFileEPKcPci");
 put=dlsym(lib,"_ZN7android16BspMServerConfig14WriteStrToFileEPKcS2_");
 if(!instance||!create||!get||!put)return 0;
 cfg=create(instance());return cfg!=0;
}
static int write_value(const char *name,unsigned value){
 char p[160],v[40];snprintf(p,sizeof(p),"/sys/module/mi_oemabl/parameters/%s",name);snprintf(v,sizeof(v),"%u",value);
 return put(cfg,p,v)==1;
}
static int read_value(const char *name,unsigned *value){
 char p[160],v[1001]={0};snprintf(p,sizeof(p),"/sys/module/mi_oemabl/parameters/%s",name);
 if(get(cfg,p,v,1000)<=0)return 0;
 unsigned n=0,i=0;while(v[i]>='0'&&v[i]<='9'&&i<10){n=n*10+(unsigned)(v[i++]-'0');}
 if(!i)return 0;*value=n;return 1;
}
static int policy(const char *s){
 const char *names[]={"enabled","l_th","e0","divisor","r_reset","generation"};unsigned v[6];
 for(unsigned i=0;i<6;i++){
  unsigned long long n=0;unsigned d=0;while(*s>='0'&&*s<='9'&&d<10){n=n*10+(unsigned)(*s++-'0');d++;}
  unsigned long long max=i==0?1:i==1||i==3?65535:i==4?82800:4294967295ULL;
  if(!d||n>max||(i<5?*s!=',':*s!=0))return 0;v[i]=(unsigned)n;if(i<5)s++;
 }
 if(!write_value("lease_end",0))return 0;
 for(unsigned i=0;i<6;i++)if(!write_value(names[i],v[i]))return 0;
 return 1;
}
JNIEXPORT jintArray JNICALL Java_MIHDRRuntime_budget(JNIEnv *e,jclass cls,jint value,jint running,jstring packet){
 (void)cls;
 if(value < -1||value>86||running < -1||running>1||!initialize())goto fail;
 if(packet){
  const char *s=(*e)->GetStringUTFChars(e,packet,0);if(!s)return 0;
  int ok=policy(s);(*e)->ReleaseStringUTFChars(e,packet,s);if(!ok)goto fail;
 }
 if(value>=0&&!write_value("budget",(unsigned)value))goto fail;
 if(running>=0){unsigned tick=0;if(running&&!read_value("tick",&tick))goto fail;if(!write_value("lease_end",running?tick+2500:0))goto fail;}
 const char *names[]={"budget","budget_used","raw_apl","window","frames","tick","lease_end","level","raw_spi","gain_used","hdr_revision","hdr_active","hdr_p0","hdr_gain"};
 jint data[14];
 for(unsigned i=0;i<14;i++){unsigned n;if(!read_value(names[i],&n))goto fail;data[i]=(jint)n;}
 jintArray out=(*e)->NewIntArray(e,14);if(out)(*e)->SetIntArrayRegion(e,out,0,14,data);return out;
fail:
 (*e)->ThrowNew(e,(*e)->FindClass(e,"java/lang/IllegalStateException"),"Owned budget module read/write failed; lease will expire");return 0;
}

JNIEXPORT void JNICALL Java_MIHDRRuntime_mapping(JNIEnv *e,jclass cls,jstring packet){
 (void)cls;unsigned revision;
 if(!packet||!initialize()||!read_value("hdr_revision",&revision)||revision!=2)goto fail;
 const char*s=(*e)->GetStringUTFChars(e,packet,0);if(!s)return;
 int ok=write_mapping(s,cfg,put);(*e)->ReleaseStringUTFChars(e,packet,s);if(ok)return;
fail:
 (*e)->ThrowNew(e,(*e)->FindClass(e,"java/lang/IllegalStateException"),"HDR mapping not committed; custom budget not started");
}
