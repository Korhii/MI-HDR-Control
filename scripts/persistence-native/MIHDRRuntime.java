import android.os.Process;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** One on-monitor owner. No sockets, ADB client, private host keys or permanent permissive mode. */
public class MIHDRRuntime {
    static final String BASE="/data/data/mitv.service/files/MIHDRControl";
    static final String RECEIPT="/sdcard/Download/Mimonitor_Toolbox/.mtk_action_11111111111111111111111111111111.txt";
    static final String[] KEYS={"g_video__picture_mode","g_dovi_info__","g_disp__disp_back_light","g_video__vid_local_dimming","g_video__vid_hdr_tone_mapping_mode"};
    static final String[] RAW={"budget","budget_used","raw","window","frames","tick","lease_end","level","raw_spi","gain_used"};
    static native int[] budget(int value,int running,String packet);
    static File file(String name){return new File(BASE,name);}
    static String read(File f)throws Exception{return new String(Files.readAllBytes(f.toPath()),StandardCharsets.UTF_8).trim();}
    static void write(File f,String s)throws Exception{
        File t=new File(f.getPath()+".tmp");Files.write(t.toPath(),s.getBytes(StandardCharsets.UTF_8));
        if(!t.renameTo(f))throw new IOException("Atomic write failed: "+f);
    }
    static String call(String... args)throws Exception{return MIHDRBridge.executeSession(args);}
    static Map<String,Integer> state()throws Exception{
        String[] a=new String[KEYS.length+2];a[0]="getBatch";System.arraycopy(KEYS,0,a,1,KEYS.length);a[a.length-1]=RECEIPT;
        Map<String,Integer> s=new HashMap<String,Integer>();
        for(String line:call(a).split("\n")){int n=line.indexOf('=');if(n>0){String key=line.substring(0,n);if(Arrays.asList(KEYS).contains(key))s.put(key,Integer.parseInt(line.substring(n+1).trim()));}}
        if(s.size()!=KEYS.length)throw new IOException("Incomplete native state");return s;
    }
    static int value(Map<String,Integer>s,int n){return s.get(KEYS[n]);}
    static boolean hdrInput(Map<String,Integer>s){
        int mode=value(s,0);return value(s,1)==0&&(mode==15||mode==16||mode==17||mode==18||mode==19||mode==35||mode==55||mode==76||(mode>=25&&mode<=34));
    }
    static void set(String key,int v)throws Exception{
        String result=call("set",key,""+v,"3");if(!result.trim().equals("0")&&!result.contains("return: 0"))throw new IOException(result);
    }
    static String packet(JSONObject c,int generation)throws Exception{
        return (c.getBoolean("enabled")?1:0)+","+c.getInt("l_th")+","+c.getLong("e0")+","+c.getInt("divisor")+","+c.getInt("r_reset")+","+generation;
    }

    static ArrayList<String> haloArgs(JSONObject p)throws Exception{
        JSONObject c=p.getJSONObject("config");ArrayList<String>a=new ArrayList<String>();
        a.add(BASE+"/mi-ldm-lab");a.add("0");a.add("1");a.add(BASE+"/halo-live");
        JSONArray sf=c.getJSONArray("sf"),alpha=c.getJSONArray("alpha");for(int i=0;i<5;i++)a.add(""+sf.getInt(i));
        for(String k:new String[]{"dc","blend","dynamic"})a.add(""+c.getInt(k));for(int i=0;i<8;i++)a.add(""+alpha.getInt(i));a.add(p.getBoolean("software_abl")?"0":"1");return a;
    }
    static java.lang.Process halo;
    static void stopHalo()throws Exception{
        if(halo==null)return;write(file("halo-live/stop"),"1");
        if(!halo.waitFor(4,TimeUnit.SECONDS))throw new IOException("Halo worker did not confirm restoration");
        if(halo.exitValue()!=0)throw new IOException("Halo restoration failed");halo=null;
    }
    public static void main(String[] args)throws Exception{
        System.load(BASE+"/libmi-persistence.so");
        MIHDRBridge.prepareSession();
        final String boot=read(new File("/proc/sys/kernel/random/boot_id"));
        write(file("runtime.pid"),""+Process.myPid());file("daemon-stopped.txt").delete();
        String lastProfile="",lastError="";long stamp=-1;int generation=1,lastBank=-1;JSONObject config=null;boolean select=true;String configHash="";
        try{
            while(file("enabled").exists()&&!file("stop").exists()){
                JSONObject status=new JSONObject().put("boot_id",boot).put("pid",Process.myPid()).put("heartbeat_ms",System.currentTimeMillis()).put("owner","monitor");
                try{
                    if(stamp!=file("controller.json").lastModified()){
                        String text=read(file("controller.json"));config=new JSONObject(text);
                        byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));StringBuilder hex=new StringBuilder();for(byte x:digest)hex.append(String.format(java.util.Locale.US,"%02x",x&255));configHash=hex.toString();stamp=file("controller.json").lastModified();lastProfile="";select=true;
                    }
                    status.put("config_sha256",configHash);
                    boolean paused=file("pause-boot").exists()&&read(file("pause-boot")).equals(boot);
                    Map<String,Integer>s=state();
                    for(String k:KEYS)status.put(k,s.get(k));
                    if(paused||!hdrInput(s)||value(s,2)!=100){
                        if(!lastProfile.isEmpty()||halo!=null){stopHalo();budget(-1,0,null);}lastProfile="";status.put("state",paused?"paused-this-boot":"waiting-HDR-input");
                    }else{
                        if(select){
                            set(KEYS[3],config.getInt("selected_level"));
                            String r=call("setHdrToneMappingChecked",""+config.getInt("selected_tone"),"3",""+value(s,0),RECEIPT);
                            if(r.contains("fatal="))throw new IOException(r);s=state();if(value(s,3)!=config.getInt("selected_level")||value(s,4)!=config.getInt("selected_tone"))throw new IOException("Saved mode readback mismatch");select=false;
                        }
                        String key=value(s,3)+":"+value(s,4);JSONObject p=config.getJSONObject("profiles").optJSONObject(key);
                        if(p==null){stopHalo();budget(-1,0,null);status.put("state","unsupported-mode");lastProfile="";}
                        else{
                            boolean changed=!key.equals(lastProfile)||lastBank!=value(s,0);String policy=changed?packet(p.getJSONObject("native_abl"),generation++):null;
                            if(changed){
                                File h=file("halo-live");h.mkdirs();new File(h,"stop").delete();
                                ArrayList<String>a=haloArgs(p);write(new File(h,"heartbeat"),""+(System.currentTimeMillis()/1000));
                                if(halo==null)halo=new ProcessBuilder(a).redirectErrorStream(true).redirectOutput(file("halo-worker.log")).start();
                                StringBuilder packet=new StringBuilder(""+generation);for(int i=4;i<a.size();i++)packet.append(' ').append(a.get(i));write(new File(h,"config"),packet.toString()+"\n");
                                lastProfile=key;lastBank=value(s,0);
                            }
                            if(!halo.isAlive())throw new IOException("Halo worker exited; do not keep a custom budget without owner");
                            write(file("halo-live/heartbeat"),""+(System.currentTimeMillis()/1000));
                            boolean factory=p.optBoolean("factory_budget",false);
                            int[] data=budget(factory?-1:p.getInt("budget"),factory?0:1,factory?null:policy);for(int i=0;i<RAW.length;i++)status.put(RAW[i],data[i]);
                            status.put("state","applied").put("profile",key).put("generation",generation);
                        }
                    }
                    lastError="";
                }catch(Exception e){
                    status.put("state","error").put("error",e.toString());if(!e.toString().equals(lastError))System.err.println(e);lastError=e.toString();
                    stopHalo();try{budget(-1,0,null);}catch(Exception ignored){}lastProfile="";
                }
                write(file("runtime-state.json"),status.toString());Thread.sleep(1000);
            }
        }finally{
            try{budget(-1,0,null);}finally{stopHalo();write(file("daemon-stopped.txt"),boot);}
        }
        System.exit(0);
    }
}
