/* MIK getters, statistic trials and a fixed 12-second software PIP trial. */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned char u8;

static long call3(long number, long a, long b, long c) {
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x8 __asm__("x8") = number;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x8) : "memory", "cc");
    return x0;
}
static void value(const char *key, long number) {
    char digits[24];
    int length = 0, key_length = 0;
    while (key[key_length]) ++key_length;
    call3(64, 1, (long)key, key_length);
    if (number < 0) { call3(64, 1, (long)"-", 1); number = -number; }
    do { digits[length++] = '0' + number % 10; number /= 10; } while (number);
    for (int left=0, right=length-1; left<right; ++left, --right) {
        char digit=digits[left]; digits[left]=digits[right]; digits[right]=digit;
    }
    digits[length++]='\n';
    call3(64, 1, (long)digits, length);
}
struct __attribute__((packed)) Handle { u64 selector; u32 handle; };
struct Attr { u64 type, input, output, handle; };
static u8 ldf_data[0x5100];
_Static_assert(sizeof(struct Handle) == 12, "Handle ABI");
_Static_assert(sizeof(struct Attr) == 32, "Attr ABI");
static long mik_ioctl(long fd, u64 command, void *payload) {
    u64 envelope[2] = {(command >> 16) & 0x3fff, (u64)payload};
    return call3(29, fd, command, (long)envelope);
}
static void moment(const char *key) {
    long stamp[2] = {0};
    if (!call3(113, 0, (long)stamp, 0)) value(key, stamp[0]);
}

struct __attribute__((packed)) ScalerByte { u32 index; u8 byte; };
_Static_assert(sizeof(struct ScalerByte) == 5, "Scaler byte read ABI");

static int read_pwm_status(void) {
    const u32 indices[] = {0x4050, 0x40a0, 0x40a1, 0x40a2, 0x40a3, 0x40a8};
    long fd = call3(56, -100, (long)"/dev/scaler", 0);
    value("scaler_open=", fd);
    if (fd < 0) return 1;
    long status = 0;
    for (unsigned i = 0; i < sizeof(indices) / sizeof(indices[0]); ++i) {
        struct ScalerByte item = {indices[i], 0};
        status = call3(29, fd, 0xc0057847UL, (long)&item);
        value("index=", item.index);
        value("read_status=", status);
        if (status) break;
        value("byte=", item.byte);
    }
    call3(57, fd, 0, 0);
    return status != 0;
}

static int pulse_scaler_bit(int capture) {
    const unsigned short mask = capture ? 1 : 0x80;
    struct ScalerByte control = {capture ? 0x4050 : 0x40a8, 0};
    long fd = call3(56, -100, (long)"/dev/scaler", 2);
    if (fd < 0) { value("scaler_open=",fd); return 1; }
    long status = call3(29, fd, 0xc0057847UL, (long)&control);
    if (status || (control.byte & mask)) { call3(57,fd,0,0); return 1; }
    value("original=",control.byte);
    struct { u32 index; unsigned short mask, data; } change = {control.index, mask, mask};
    status = call3(29, fd, 0xc008784cUL, (long)&change);
    value("set_status=",status);
    if (status) { call3(57,fd,0,0); return 1; }
    long hold[2] = {0, 250000000};
    call3(101, (long)hold, 0, 0);
    status = call3(29, fd, 0xc0057847UL, (long)&control);
    value("active=",control.byte);
    if (!(control.byte & mask)) status = -1;
    if (!capture && !status) {
        struct ScalerByte computed = {0x40a2, 0};
        status = call3(29, fd, 0xc0057847UL, (long)&computed);
        if (!status) value("computed_duty=",computed.byte);
    }
    change.data = 0;
    long restored = call3(29, fd, 0xc008784cUL, (long)&change);
    value("restore_status=",restored);
    long checked = call3(29, fd, 0xc0057847UL, (long)&control);
    value("after=",control.byte);
    call3(57, fd, 0, 0);
    return status || restored || checked || (control.byte & mask);
}

__attribute__((used)) long probe_main(u64 *stack) {
    long alpha = -1;
    long dynamic = -1;
    long spatial = -1;
    long pip = -1;
    long buffers = 0;
    long ldf = 0;
    int format_trial = 0;
    char **argv = (char **)(stack + 1);
    if (stack[0] == 2) {
        if (argv[1][0]=='3' && argv[1][1]==0) alpha=3;
        else if (argv[1][0]=='1' && argv[1][1]=='2' && argv[1][2]==0) alpha=12;
        else if (argv[1][0]=='1' && argv[1][1]=='6' && argv[1][2]==0) alpha=16;
        else if (argv[1][0]=='m' && argv[1][1]=='a' && argv[1][2]=='x' && argv[1][3]==0) dynamic=0;
        else if (argv[1][0]=='d' && argv[1][1]=='y' && argv[1][2]=='n' && argv[1][3]=='1' && argv[1][4]==0) dynamic=1;
        else if (argv[1][0]=='s' && argv[1][1]=='f' && argv[1][2]==0) spatial=128;
        else if (argv[1][0]=='s' && argv[1][1]=='f' && argv[1][2]=='2' && argv[1][3]=='5' && argv[1][4]=='5' && argv[1][5]==0) spatial=255;
        else if (argv[1][0]=='v' && argv[1][1]=='r' && argv[1][2]==0) return read_pwm_status();
        else if (argv[1][0]=='v' && argv[1][1]=='c' && argv[1][2]==0) return pulse_scaler_bit(1);
        else if (argv[1][0]=='v' && argv[1][1]=='g' && argv[1][2]==0) return pulse_scaler_bit(0);
        else if (argv[1][0]=='p' && argv[1][1]=='i' && argv[1][2]=='p' && argv[1][3]==0) pip=1;
        else if (argv[1][0]=='p' && argv[1][1]=='i' && argv[1][2]=='p' && argv[1][3]=='0' && argv[1][4]==0) pip=0;
        else if (argv[1][0]=='b' && argv[1][1]=='u' && argv[1][2]=='f' && argv[1][3]==0) buffers=1;
        else if (argv[1][0]=='l' && argv[1][1]=='d' && argv[1][2]=='f' && argv[1][3]==0) ldf=1;
        else if (argv[1][0]=='f' && argv[1][1]=='0' && argv[1][2]==0) format_trial=1;
        else if (argv[1][0]=='f' && argv[1][1]=='1' && argv[1][2]==0) format_trial=2;
        else return 2;
    } else if (stack[0] != 1) return 2;
    value("uid=", call3(174, 0, 0, 0));
    long fd = call3(56, -100, (long)"/dev/mik!dispout", 2);
    value("open=", fd);
    if (fd < 0) return 1;
    struct Handle handle = {0, 0};
    long status = mik_ioctl(fd, 0xc00c3203UL, &handle);
    value("get_handle=", status);
    value("handle=", handle.handle);
    if (!status) {
        u8 dimensions[3] = {0};
        struct Attr attr = {0x40, 0, (u64)dimensions, handle.handle};
        status = mik_ioctl(fd, 0xc020320aUL, &attr);
        value("get_ldf_wh=", status);
        value("ldf_byte0=", dimensions[0]);
        value("ldf_byte1=", dimensions[1]);
        value("ldf_byte2=", dimensions[2]);
        if (!status && format_trial) {
            u8 format = 0;
            attr.type=0x50; attr.input=(u64)&format; attr.output=0;
            if (format_trial==1) {
                status=mik_ioctl(fd,0xc0203207UL,&attr);
                value("ldm_format_0=",status);
                if (!status) {
                    long hold[2]={12,0};
                    status=call3(101,(long)hold,0,0);
                }
            }
            format=1;
            long restored=mik_ioctl(fd,0xc0203207UL,&attr);
            value("ldm_format_1=",restored);
            if (restored) status=restored;
        }
        if (!status && ldf) {
            attr.type=0x42; attr.input=0; attr.output=(u64)ldf_data;
            status=mik_ioctl(fd,0xc020320aUL,&attr);
            value("get_ldf_data=",status);
            long size=(long)dimensions[1]*dimensions[2]*(dimensions[0]?dimensions[0]:1);
            value("ldf_bytes=",size);
            if(!status && size>0 && size<=(long)sizeof(ldf_data)) {
                long output=call3(56,-100,(long)"/sdcard/Download/MIResearch20261106/ldf-read.bin",513);
                value("open_ldf_output=",output);
                if(output<0) status=output;
                else {
                    long written=call3(64,output,(long)ldf_data,size);
                    value("ldf_bytes_written=",written);
                    call3(57,output,0,0);
                    if(written!=size) status=-1;
                }
            }
        }
        if (!status && buffers) {
            u64 addresses[3]={0};
            attr.type=10; attr.input=0; attr.output=(u64)addresses;
            status=mik_ioctl(fd,0xc020320aUL,&attr);
            value("get_buffers=",status);
            for(int i=0;i<3;++i) { value("buffer_index=",i+1); value("buffer_address=",addresses[i]); }
            long memory=call3(56,-100,(long)"/dev/malloc",0);
            value("open_malloc_readonly=",memory);
            if(memory>=0) call3(57,memory,0,0);
        }
        if (!status && pip >= 0) {
            // CusBoost=1 bypasses the MID/LOW software accumulator; 0 enables it.
            // This does not write the HIGH budget or any LED current register.
            u8 setting[2]={(u8)pip,0};
            attr.type=0x46; attr.input=(u64)setting; attr.output=0;
            status=mik_ioctl(fd,0xc0203207UL,&attr);
            value("set_pip_bypass=",pip); value("set_pip_return=",status);
            moment("set_epoch_s=");
            if (pip==1) {
                if (!status) {
                    long duration[2]={12,0};
                    value("hold_return=",call3(101,(long)duration,0,0));
                }
                setting[0]=0;
                long restored=mik_ioctl(fd,0xc0203207UL,&attr);
                value("restore_pip_bypass=",0); value("restore_pip_return=",restored);
                moment("restore_epoch_s=");
                if (restored) status=restored;
            }
        }
        if (!status && (alpha >= 0 || dynamic >= 0 || spatial >= 0)) {
            // SET layout is value,index; GET on /dev/localdimming uses index,value.
            // This byte order was verified through utpa2k and the LDM ioctl's ARM64 instructions.
            // Index 21 toggles dynamic weighting only; DCMaxAlpha stays at stock 8.
            const int is_dynamic = dynamic >= 0;
            const int is_spatial = spatial >= 0;
            const long requested = is_spatial ? spatial : is_dynamic ? dynamic : alpha;
            const long baseline = is_spatial ? 255 : is_dynamic ? 1 : 3;
            u8 setting[2] = {(u8)requested, is_spatial ? 7 : is_dynamic ? 21 : 23};
            attr.type=0x43; attr.input=(u64)setting; attr.output=0;
            status=mik_ioctl(fd, 0xc0203207UL, &attr);
            value(is_spatial ? "set_spatial_strength=" : is_dynamic ? "set_dynamic_en=" : "set_alpha0=", requested);
            value(is_spatial ? "set_spatial_return=" : is_dynamic ? "set_dynamic_return=" : "set_alpha_return=", status);
            moment("set_epoch_s=");
            if (requested != baseline) {
                if (!status) {
                    long duration[2] = {12, 0};
                    value("hold_return=", call3(101, (long)duration, 0, 0));
                }
                setting[0]=(u8)baseline;
                long restored=mik_ioctl(fd, 0xc0203207UL, &attr);
                value(is_spatial ? "restore_spatial_strength=" : is_dynamic ? "restore_dynamic_en=" : "restore_alpha0=", baseline);
                value(is_spatial ? "restore_spatial_return=" : is_dynamic ? "restore_dynamic_return=" : "restore_alpha_return=", restored);
                moment("restore_epoch_s=");
                if (restored) status=restored;
            }
        }
    }
    call3(57, fd, 0, 0);
    return status != 0;
}
__attribute__((naked, noreturn)) void _start(void) {
    __asm__ volatile("mov x0, sp\nbl probe_main\nmov x8, #93\nsvc 0");
}
