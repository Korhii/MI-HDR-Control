/* File-only preparation. Caller verifies MODULE_SHA256 with sha256sum before use. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#ifdef _WIN32
#include <io.h>
#else
#include <unistd.h>
#define O_BINARY 0
#endif
struct slot {unsigned offset,region;uint64_t addend,expected;};
#include "budget_relocation.h"

int main(int argc,char**argv){
    if(argc!=6){fprintf(stderr,"usage: mi-budget-prepare SOURCE OUTPUT TEXT BSS DATA\n");return 2;}
    uint64_t bases[3];
    for(unsigned i=0;i<3;i++){
        char*end; bases[i]=strtoull(argv[3+i],&end,0);
        if(!argv[3+i][0]||*end){fprintf(stderr,"invalid section address\n");return 3;}
    }
    if((bases[0]&0xffffffff00000fffULL)!=0xffffffc000000000ULL||bases[1]!=bases[0]+0x3c000||bases[2]!=bases[0]+0x98060){
        fprintf(stderr,"driver section layout mismatch\n");return 4;
    }
    FILE*in=fopen(argv[1],"rb");if(!in){perror("source");return 5;}
    unsigned char*image=malloc(MODULE_BYTES+1);if(!image){fclose(in);return 5;}
    size_t size=fread(image,1,MODULE_BYTES+1,in);int read_error=ferror(in);fclose(in);
    if(read_error||size!=MODULE_BYTES||memcmp(image,"\177ELF\2\1",6)||image[18]!=183||image[19]){
        fprintf(stderr,"module template size or ELF mismatch\n");free(image);return 6;
    }
    for(unsigned i=0;i<sizeof(slots)/sizeof(slots[0]);i++){
        uint64_t value;memcpy(&value,image+slots[i].offset,8);
        if(value!=slots[i].expected){fprintf(stderr,"address slot mismatch: %u\n",i);free(image);return 7;}
        value=bases[slots[i].region]+slots[i].addend;memcpy(image+slots[i].offset,&value,8);
    }
    int fd=open(argv[2],O_WRONLY|O_CREAT|O_EXCL|O_BINARY,0600);
    if(fd<0){perror("fresh output");free(image);return 8;}
    FILE*out=fdopen(fd,"wb");
    if(!out){close(fd);unlink(argv[2]);free(image);return 9;}
    size_t written=fwrite(image,1,size,out);int close_error=fclose(out);free(image);
    if(written!=size||close_error){unlink(argv[2]);fprintf(stderr,"output write failed\n");return 9;}
    printf("prepared=1\ntext=0x%llx\nbss=0x%llx\ndata=0x%llx\nslots=%u\noutput=%s\n",
        (unsigned long long)bases[0],(unsigned long long)bases[1],(unsigned long long)bases[2],
        (unsigned)(sizeof(slots)/sizeof(slots[0])),argv[2]);
    return 0;
}
