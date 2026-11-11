/* Exercise only this process's newly allocated shared page. */
typedef unsigned long u64;
typedef unsigned int u32;
static long syscall6(long n,long a,long b,long c,long d,long e,long f) {
    register long x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c;
    register long x3 __asm__("x3")=d,x4 __asm__("x4")=e,x5 __asm__("x5")=f;
    register long x8 __asm__("x8")=n;
    __asm__ volatile("svc 0":"+r"(x0):"r"(x1),"r"(x2),"r"(x3),"r"(x4),"r"(x5),"r"(x8):"memory","cc");
    return x0;
}
static long call3(long n,long a,long b,long c) { return syscall6(n,a,b,c,0,0,0); }
static void value(const char *label,long number) {
    char digits[24];int n=0,len=0;while(label[len])++len;
    call3(64,1,(long)label,len);
    if(number<0){call3(64,1,(long)"-",1);number=-number;}
    do {digits[n++]='0'+number%10;number/=10;} while(number);
    for(int a=0,b=n-1;a<b;++a,--b){char t=digits[a];digits[a]=digits[b];digits[b]=t;}
    digits[n++]='\n';call3(64,1,(long)digits,n);
}
__attribute__((used)) long scratch_main(void) {
    long fd=call3(56,-100,(long)"/dev/mtal_system",2);
    value("device_open=",fd);if(fd<0)return 1;
    long address=syscall6(222,0,4096,3,0x21,-1,0);
    value("shared_page_allocated=",address>0);
    if(address<=0){call3(57,fd,0,0);return 2;}
    volatile u32 *page=(volatile u32 *)address;
    page[0]=0x11223344;page[1]=0xa55a5aa5;
    u64 destination=(u64)address;
    long result=call3(29,fd,0xc0042206UL,(long)&destination);
    value("user_get_status=",result);value("user_result=",page[0]);
    value("user_guard_intact=",page[1]==0xa55a5aa5);
    int ok=result==0 && page[0]==0 && page[1]==0xa55a5aa5;
    if(ok){
        u64 mapping[2]={(u64)address,4096};
        result=call3(29,fd,0xc010220dUL,(long)mapping);
        value("map_status=",result);
        if(result==0){
            u64 owned_alias=mapping[0];
            int valid=(owned_alias>>39)==0x1ffffffUL && !(owned_alias&4095);
            value("owned_alias_shape_valid=",valid);
            if(valid){
                page[8]=0x12345678;
                value("owned_value_log_status=",call3(29,fd,0x40042205UL,owned_alias+32));
                value("owned_value_unchanged=",page[8]==0x12345678);
                page[4]=0x11223344;page[5]=0xa55a5aa5;
                destination=owned_alias+16;
                result=call3(29,fd,0xc0042206UL,(long)&destination);
                value("alias_get_status=",result);value("alias_result=",page[4]);
                value("alias_guard_intact=",page[5]==0xa55a5aa5);
                value("alias_update_observed=",result==0 && page[4]==0 && page[5]==0xa55a5aa5);
                volatile unsigned char *bytes=(volatile unsigned char *)page;
                for(int i=64;i<70;++i)bytes[i]=0x5a;
                destination=owned_alias+65;
                result=call3(29,fd,0xc0042206UL,(long)&destination);
                int unaligned=result==0 && bytes[64]==0x5a && bytes[69]==0x5a;
                for(int i=65;i<69;++i)unaligned=unaligned && bytes[i]==0;
                value("unaligned_four_byte_boundary_verified=",unaligned);
                ok=ok && unaligned;
            }
            mapping[0]=owned_alias;mapping[1]=4096;
            value("driver_unmap_status=",call3(29,fd,0x4010220eUL,(long)mapping));
        }
    }
    value("process_unmap_status=",call3(215,address,4096,0));
    call3(57,fd,0,0);value("__complete=",1);return ok?0:3;
}

static int same(const char *a,const char *b) {while(*a&&*a==*b){++a;++b;}return *a==*b;}
static int has(const char *s,const char *needle) {for(;*s;++s){const char *a=s,*b=needle;while(*b&&*a==*b){++a;++b;}if(!*b)return 1;}return 0;}
static long readfile(const char *path,char *out,long size) {
    long fd=call3(56,-100,(long)path,0);if(fd<0)return fd;
    long n=call3(63,fd,(long)out,size-1);call3(57,fd,0,0);if(n>=0)out[n]=0;return n;
}
__attribute__((used)) long probe_main(long *stack) {
    int apply=stack[0]==2 && same(((char **)stack)[2],"--apply");
    long rc=scratch_main();if(rc||!apply)return rc;
    char uts[390],cmdline[8192],enforce[8];
    if(call3(160,(long)uts,0,0)||!same(uts+130,"5.15.148-android14-11-g37010446f523"))return 11;
    if(readfile("/proc/cmdline",cmdline,sizeof(cmdline))<=0||!has(cmdline,"nokaslr"))return 12;
    if(readfile("/sys/fs/selinux/enforce",enforce,sizeof(enforce))<=0||enforce[0]!='1')return 13;
    long fd=call3(56,-100,(long)"/dev/mtal_system",2);if(fd<0)return 14;
    /* Exact firmware: enforcing is the first byte at selinux_state.
       The preceding three bytes belong to an unused lock-class key/padding;
       DEBUG_LOCK_ALLOC is disabled and __mutex_init ignores that key.
       Offset -3 prevents overwriting checkreqprot/initialized/policycap. */
    u64 destination=0xffffffc00a2c9365UL;
    long result=call3(29,fd,0xc0042206UL,(long)&destination);
    call3(57,fd,0,0);value("temporary_write_status=",result);
    if(readfile("/sys/fs/selinux/enforce",enforce,sizeof(enforce))<=0)return 15;
    value("enforcing_after=",enforce[0]-'0');
    return result==0&&enforce[0]=='0'?0:16;
}
__attribute__((naked,noreturn)) void _start(void) {
    __asm__ volatile("mov x0,sp\nbl probe_main\nmov x8,#93\nsvc 0");
}
