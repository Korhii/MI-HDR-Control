/* Vendor BSP probe in a dedicated child. Optional macro requests a diagnostic dump. */
extern void *dlopen(const char *,int);
extern void *dlsym(void *,const char *);
extern char *dlerror(void);
static long call3(long n,long a,long b,long c) {
    register long x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c;
    register long x8 __asm__("x8")=n;
    __asm__ volatile("svc 0":"+r"(x0):"r"(x1),"r"(x2),"r"(x8):"memory","cc");
    return x0;
}
static void text(const char *s) { long n=0;if(!s)s="(null)";while(s[n])++n;call3(64,1,(long)s,n);call3(64,1,(long)"\n",1); }
static void value(const char *key,long n) {
    char b[24];int k=0;text(key);
    if(n<0){call3(64,1,(long)"-",1);n=-n;}
    do{b[k++]='0'+n%10;n/=10;}while(n);
    for(int i=0;i<k/2;++i){char t=b[i];b[i]=b[k-i-1];b[k-i-1]=t;}
    b[k++]='\n';call3(64,1,(long)b,k);
}
static void finish(long code) { value("__exit",code);text("__complete=1");call3(94,code,0,0); }
__attribute__((constructor)) static void probe(void) {
    value("uid",call3(174,0,0,0));
    void *library=dlopen("/vendor/lib64/libbspmserver.so",2);
    if(!library){text(dlerror());finish(1);return;}
    void *(*instance)(void)=dlsym(library,"_ZN7android16BspMServerClient11getInstanceEv");
    void *(*create)(void *)=dlsym(library,"_ZN7android16BspMServerClient18CreateConfigObjectEv");
    int (*get_env)(void *,const char *,char *,int)=dlsym(library,"_ZN7android16BspMServerConfig11GetUbootEnvEPKcPci");
    int (*read_file)(void *,const char *,char *,int)=dlsym(library,"_ZN7android16BspMServerConfig15ReadStrFromFileEPKcPci");
    if(!instance||!create||!get_env||!read_file){text(dlerror());finish(2);return;}
    void *client=instance();value("client_present",client!=0);
    void *config=client?create(client):0;value("config_present",config!=0);
    if(!config){finish(3);return;}
#ifdef MI_BSP_LDM_INFO
    char basic[1001]={0};
    value("ldm_read_return",read_file(config,"/sys/class/localdimming/localdimming/ldm_basic_info_get",basic,1000));
    text(basic);finish(0);return;
#endif
#ifdef MI_BSP_HDR50_FRAME
    int (*store)(void *,const char *,const char *)=dlsym(library,"_ZN7android16BspMServerConfig14WriteStrToFileEPKcS2_");
    const char *frame="/vendor/persist/MIResearch-hdr50-spi.txt";
    if(!store || store(config,frame,"")!=1 || store(config,"/sys/class/localdimming/localdimming/ldm_dump_data",
        "2 1 /vendor/persist/MIResearch-hdr50-spi.txt")!=1) { finish(4);return; }
    char sample[1001]={0};
    value("spi_file_bytes",read_file(config,frame,sample,1000));
    text(sample);finish(0);return;
#endif
    char buffer[1001]={0};
    value("get_devicestate_return",get_env(config,"devicestate",buffer,1000));text(buffer);
    const char *paths[]={"/proc/self/status","/proc/self/attr/current","/sys/fs/selinux/enforce","/proc/sys/kernel/modprobe","/proc/sys/kernel/core_pattern","/proc/sys/kernel/modules_disabled","/sys/module/kdrv_ldm_sys/sections/.text","/sys/class/localdimming/localdimming/ldm_basic_info_get","/vendor/persist/MIResearch20261106-spi.txt","/sys/class/udc/1c7a3e00.usb/state","/sys/class/udc/1c7a3e00.usb/current_speed","/sys/class/android_usb/android0/state","/sys/devices/platform/1c7a3e00.usb/mode","/sys/module/mtu3/parameters/mtu3_dev_en"};
    for(unsigned i=0;i<sizeof(paths)/sizeof(paths[0]);++i){for(int j=0;j<1001;++j)buffer[j]=0;text(paths[i]);value("read_return",read_file(config,paths[i],buffer,1000));text(buffer);}
#ifdef MI_BSP_DUMP_SPI
    int (*write_file)(void *,const char *,const char *)=dlsym(library,"_ZN7android16BspMServerConfig14WriteStrToFileEPKcS2_");
    if(!write_file){finish(4);return;}
    value("spi_diagnostic_return",write_file(config,"/sys/class/localdimming/localdimming/ldm_dump_data",
        "2 1 /vendor/persist/MIResearch20261106-spi.txt"));
#endif
    finish(0);
}
