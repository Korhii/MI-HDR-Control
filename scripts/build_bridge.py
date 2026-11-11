"""Developer build only; portable users receive the project-owned DEX JARs."""
from pathlib import Path
import argparse
import json
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def build(jdk,android_jar,d8_jar,output_directory):
    jdk=Path(jdk);output_directory=Path(output_directory);output_directory.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mi-hdr-bridge-') as temporary:
        folder=Path(temporary);classes=folder/'classes';classes.mkdir()
        subprocess.run([str(jdk/'bin/javac.exe'),'--release','8','-Xlint:-options','-encoding','UTF-8','-cp',str(android_jar),'-d',str(classes),
                        str(ROOT/'scripts/android-bridge/MIHDRBridge.java'),str(ROOT/'scripts/persistence-native/MIHDRRuntime.java')],check=True)
        for jar,names in [('MIHDRBridge.jar',['MIHDRBridge.class']),('MIHDRRuntime.jar',['MIHDRBridge.class','MIHDRRuntime.class'])]:
            dex=folder/(Path(jar).stem+'-dex');dex.mkdir()
            subprocess.run([str(jdk/'bin/java.exe'),'-cp',str(d8_jar),'com.android.tools.r8.D8','--min-api','26','--lib',str(android_jar),'--output',str(dex),
                            *[str(classes/name) for name in names]],check=True)
            data=(dex/'classes.dex').read_bytes()
            if b'LMtkDirectTool;' in data:raise ValueError('Unexpected upstream helper in new DEX')
            with zipfile.ZipFile(output_directory/jar,'w',zipfile.ZIP_DEFLATED) as archive:
                info=zipfile.ZipInfo('classes.dex',(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,data)
    return {'jars':[str((output_directory/name).resolve()) for name in ('MIHDRBridge.jar','MIHDRRuntime.jar')]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('jdk','android-jar','d8-jar','output-directory'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();print(json.dumps(build(args.jdk,args.android_jar,args.d8_jar,args.output_directory)))
