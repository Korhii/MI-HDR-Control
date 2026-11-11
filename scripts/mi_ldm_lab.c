/* Local-dimming console with device heartbeat and restoration on exit. */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned char u8;
static long call3(long n,long a,long b,long c) {
    register long x0 __asm__("x0")=a, x1 __asm__("x1")=b, x2 __asm__("x2")=c;
    register long x8 __asm__("x8")=n;
    __asm__ volatile("svc 0":"+r"(x0):"r"(x1),"r"(x2),"r"(x8):"memory","cc");
    return x0;
}
static void value(const char *s,long n) {
    char b[24]; int k=0,l=0;
    while(s[l]) ++l;
    call3(64,1,(long)s,l);
    if(n<0) { call3(64,1,(long)"-",1); n=-n; }
    do { b[k++]='0'+n%10; n/=10; } while(n);
    for(int i=0;i<k/2;++i) { char t=b[i]; b[i]=b[k-i-1]; b[k-i-1]=t; }
    b[k++]='\n'; call3(64,1,(long)b,k);
}
static long number(const char *s) {
    long n=0; int i=0;
    while(s[i]>='0' && s[i]<='9' && i<10) { n=n*10+s[i++]-'0'; }
    return i && (s[i]==0 || s[i]=='\n') ? n : -1;
}
static long now(void) { long t[2]={0}; return call3(113,0,(long)t,0) ? 0 : t[0]; }
static int path(char *out,const char *base,const char *leaf) {
    int i=0,j=0; while(base[i] && i<180) { out[i]=base[i]; ++i; }
    if(base[i]) return 0;
    out[i++]='/'; while(leaf[j]) out[i++]=leaf[j++]; out[i]=0; return 1;
}
static long read_number(const char *p) {
    char b[24]={0}; long fd=call3(56,-100,(long)p,0);
    if(fd<0) return -1;
    long r=call3(63,fd,(long)b,23); call3(57,fd,0,0);
    return r>0 ? number(b) : -1;
}
struct __attribute__((packed)) Handle { u64 selector; u32 handle; };
struct Attr { u64 type,input,output,handle; };
static long ioctl_mik(long fd,u64 cmd,void *p) {
    u64 e[2]={(cmd>>16)&0x3fff,(u64)p}; return call3(29,fd,cmd,(long)e);
}
static const u8 indices[16]={7,8,9,10,11,20,22,21,23,24,25,26,27,28,29,30};
static const u8 stock[16]={255,255,255,255,255,8,8,1,3,5,7,9,11,13,15,16};
static const u8 maximum[16]={255,255,255,255,255,8,8,1,16,16,16,16,16,16,16,16};
static long configuration(const char *p,u8 *values,u8 *pip) {
    char b[256]={0}; long fd=call3(56,-100,(long)p,0);
    if(fd<0) return -1;
    long size=call3(63,fd,(long)b,255); call3(57,fd,0,0);
    if(size<=0 || size==255) return -1;
    char *s=b; long sequence=-1;
    *pip=0;
    for(int i=0;i<18;++i) {
        while(*s==' ' || *s=='\n' || *s=='\r') ++s;
        if(i==17 && !*s) break; /* Older packets have no PIP option. */
        long n=0; int digits=0;
        while(*s>='0' && *s<='9' && digits<10) { n=n*10+*s++-'0'; ++digits; }
        if(!digits || (*s && *s!=' ' && *s!='\n' && *s!='\r')) return -1;
        if(i==0) { if(n>2147483647) return -1; sequence=n; }
        else if(i==17) { if(n>1) return -1; *pip=(u8)n; }
        else { if(n>maximum[i-1]) return -1; values[i-1]=(u8)n; }
    }
    while(*s==' ' || *s=='\n' || *s=='\r') ++s;
    return *s ? -1 : sequence;
}
static long setting(long fd,u32 handle,u8 index,u8 v) {
    u8 data[2]={v,index}; struct Attr a={0x43,(u64)data,0,handle};
    return ioctl_mik(fd,0xc0203207UL,&a);
}
static long pip_setting(long fd,u32 handle,u8 v) {
    u8 data[2]={v,0}; struct Attr a={0x46,(u64)data,0,handle};
    return ioctl_mik(fd,0xc0203207UL,&a);
}
__attribute__((used)) long lab_main(u64 *stack) {
    char **av=(char **)(stack+1); u8 values[16]; char heartbeat[200],stop[200],config[200];
    if(stack[0]!=20 && stack[0]!=21) return 2;
    long duration=number(av[1]),apply=number(av[2]);
    long pip=stack[0]==21 ? number(av[20]) : 0;
    if(duration<0 || duration>180 || apply<0 || apply>1 || pip<0 || pip>1) return 2;
    if(!path(heartbeat,av[3],"heartbeat") || !path(stop,av[3],"stop") || !path(config,av[3],"config")) return 2;
    for(int i=0;i<16;++i) {
        long v=number(av[i+4]); if(v<0 || v>maximum[i]) return 2; values[i]=(u8)v;
    }
    long fd=call3(56,-100,(long)"/dev/mik!dispout",2); value("open=",fd);
    if(fd<0) return 1;
    struct Handle h={0,0}; long result=ioctl_mik(fd,0xc00c3203UL,&h);
    value("get_handle=",result);
    if(result) { call3(57,fd,0,0); return 1; }
    long first=now();
    result=pip_setting(fd,h.handle,apply ? (u8)pip : 0);
    value("set_pip_bypass=",apply ? pip : 0); value("set_pip_return=",result);
    if(apply && !result) for(int i=0;i<16;++i) {
        long r=setting(fd,h.handle,indices[i],values[i]);
        value("set_index=",indices[i]); value("set_value=",values[i]); value("set_return=",r);
        if(r) { result=r; break; }
    }
    if(!result) {
        value("__applied=",1); value("set_epoch_s=",now());
        long last_sequence=-1;
        while(duration==0 || now()-first<duration) {
            long stop_fd=call3(56,-100,(long)stop,0);
            if(stop_fd>=0) { call3(57,stop_fd,0,0); value("stop_reason=",1); break; }
            long beat=read_number(heartbeat), t=now();
            if(beat<0 || beat>t+2 || t-beat>12) { value("stop_reason=",2); break; }
            if(apply) {
                u8 next[16],next_pip; long sequence=configuration(config,next,&next_pip);
                if(sequence>=0 && sequence!=last_sequence) {
                    result=pip_setting(fd,h.handle,next_pip);
                    value("live_pip_bypass=",next_pip); value("live_pip_return=",result);
                    if(result) break;
                    /* A native mode change reloads its defaults: rewrite every index. */
                    for(int i=0;i<16;++i) {
                        long r=setting(fd,h.handle,indices[i],next[i]);
                        value("live_index=",indices[i]); value("live_value=",next[i]); value("live_return=",r);
                        if(r) { result=r; break; }
                        values[i]=next[i];
                    }
                    if(result) break;
                    last_sequence=sequence; value("applied_sequence=",sequence);
                }
            }
            long delay[2]={0,200000000};
            if(call3(101,(long)delay,0,0)) { value("stop_reason=",3); break; }
        }
    }
    long pip_restored=pip_setting(fd,h.handle,0);
    value("restore_pip_bypass=",0); value("restore_pip_return=",pip_restored);
    if(pip_restored) result=pip_restored;
    for(int i=0;i<16;++i) {
        long r=setting(fd,h.handle,indices[i],stock[i]);
        value("restore_index=",indices[i]); value("restore_return=",r);
        if(r) result=r;
    }
    value("__native_restored=",result==0); value("restore_epoch_s=",now());
    call3(57,fd,0,0); return result!=0;
}
__attribute__((naked,noreturn)) void _start(void) {
    __asm__ volatile("mov x0,sp\nbl lab_main\nmov x8,#93\nsvc 0");
}
