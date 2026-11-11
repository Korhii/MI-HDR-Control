/* Emit one local research event through the original client library. */
extern void *dlopen(const char *,int);
extern void *dlsym(void *,const char *);
extern char *dlerror(void);
extern long write(int,const void *,unsigned long);
extern void _exit(int);
static void output(const char *s) { unsigned long n=0;while(s[n])++n;write(1,s,n);write(1,"\n",1); }
__attribute__((constructor)) static void probe(void) {
    void *library=dlopen("/system_ext/lib64/libmisight.so",2);
    if(!library){output(dlerror());_exit(1);}
    int (*send)(unsigned int,const char *)=dlsym(library,"sendEventMisight");
    if(!send){output(dlerror());_exit(2);}
    int result=send(967099999,"{\"Research\":\"MIResearch20261106\"}");
    output(result<0?"event_failed=1":"event_written=1");
    _exit(result<0?3:0);
}
