/* Read-only OEM BSP file API. No policy changes, module load or device writes. */
extern void *dlopen(const char*,int);extern void *dlsym(void*,const char*);
extern long write(int,const void*,unsigned long);extern void _exit(int);
static unsigned long length(const char*s){unsigned long n=0;while(s[n])n++;return n;}
__attribute__((constructor)) static void snapshot(void){
 void*lib=dlopen("/vendor/lib64/libbspmserver.so",2);if(!lib)_exit(2);
 void*(*instance)(void)=dlsym(lib,"_ZN7android16BspMServerClient11getInstanceEv");
 void*(*create)(void*)=dlsym(lib,"_ZN7android16BspMServerClient18CreateConfigObjectEv");
 int(*readfile)(void*,const char*,char*,int)=dlsym(lib,"_ZN7android16BspMServerConfig15ReadStrFromFileEPKcPci");
 if(!instance||!create||!readfile)_exit(3);void*client=instance();void*config=client?create(client):0;if(!config)_exit(4);
 char raw[4097]={0};int result=readfile(config,"/sys/class/localdimming/localdimming/ldm_basic_info_get",raw,4096);
 if(result<=0)_exit(5);write(1,raw,length(raw));write(1,"\n__info_verified=1\n",19);_exit(0);
}
