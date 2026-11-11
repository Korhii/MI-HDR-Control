/* Restore fixed LDM attributes through the same OEM interface as the live worker. */
typedef unsigned long u64;typedef unsigned int u32;typedef unsigned char u8;
static long sc(long n,long a,long b,long c){register long x0 __asm__("x0")=a,x1 __asm__("x1")=b,x2 __asm__("x2")=c,x8 __asm__("x8")=n;__asm__ volatile("svc 0":"+r"(x0):"r"(x1),"r"(x2),"r"(x8):"memory","cc");return x0;}
static void out(const char*s,long v){int n=0;while(s[n])n++;sc(64,1,(long)s,n);char b[24];n=0;if(v<0){sc(64,1,(long)"-",1);v=-v;}do{b[n++]='0'+v%10;v/=10;}while(v);while(n)sc(64,1,(long)&b[--n],1);sc(64,1,(long)"\n",1);}
static int eq(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static long number(const char*s){long n=0;int d=0;while(*s>='0'&&*s<='9'&&d++<4)n=n*10+*s++-'0';return d&&!*s?n:-1;}
static const u8 indices[]={7,8,9,10,11,20,22,21,23,24,25,26,27,28,29,30};
static const u8 limits[]={255,255,255,255,255,8,8,1,16,16,16,16,16,16,16,16};
struct __attribute__((packed)) Handle{u64 selector;u32 handle;};struct Attr{u64 type,input,output,handle;};
static long mik(long fd,u64 cmd,void*p){u64 env[2]={(cmd>>16)&0x3fff,(u64)p};return sc(29,fd,cmd,(long)env);}
__attribute__((used)) long entry(u64*st){
 char**av=(char**)(st+1);int restore=st[0]==18&&eq(av[1],"restore");u8 wanted[16];
 if(!restore)return 2;
 if(restore)for(int i=0;i<16;i++){long n=number(av[i+2]);if(n<0||n>limits[i])return 2;wanted[i]=n;}
 if(restore){
  long fd=sc(56,-100,(long)"/dev/mik!dispout",2);if(fd<0)return 4;struct Handle h={0,0};if(mik(fd,0xc00c3203UL,&h))return 5;
  u8 pip[2]={0,0};struct Attr a={0x46,(u64)pip,0,h.handle};if(mik(fd,0xc0203207UL,&a))return 6;
  for(int i=0;i<16;i++){u8 p[2]={wanted[i],indices[i]};a.type=0x43;a.input=(u64)p;if(mik(fd,0xc0203207UL,&a))return 7;out("written_index=",indices[i]);out("written_value=",wanted[i]);}sc(57,fd,0,0);
 }
 out("__ldm_written=",1);return 0;
}
__attribute__((naked,noreturn)) void _start(void){__asm__ volatile("mov x0,sp\nbl entry\nmov x8,#93\nsvc 0");}
