import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Project-owned adapter for the monitor interfaces used by MI HDR Control. */
public final class MIHDRBridge {
    private static final String[] KEYS={
        "g_video__picture_mode","g_dovi_info__","g_disp__disp_back_light",
        "g_video__vid_local_dimming","g_video__vid_hdr_tone_mapping_mode",
        "g_video__clr_temp","g_video__clr_gain_r","g_video__clr_gain_g",
        "g_video__clr_gain_b","g_video__contrast","g_video__brightness"
    };
    private static ClassLoader loader;

    public static synchronized void prepareSession() throws Exception {
        if (loader!=null) return;
        String archives="/system/framework/mitvmiddlewareimpl.jar:/system_ext/priv-app/TvServices/TvServices.apk";
        String libraries="/system/lib64:/system_ext/lib64:/vendor/lib64";
        loader=(ClassLoader)Class.forName("dalvik.system.PathClassLoader")
            .getConstructor(String.class,String.class,ClassLoader.class)
            .newInstance(archives,libraries,ClassLoader.getSystemClassLoader());
        Class.forName("com.mediatek.twoworlds.tv.TVNative",true,loader);
    }

    private static Object call(String owner,Object instance,String method,Class<?>[] types,Object... args) throws Exception {
        Class<?> type=loader.loadClass(owner);
        Method function;
        try { function=type.getMethod(method,types); }
        catch (NoSuchMethodException error) { function=type.getDeclaredMethod(method,types); }
        function.setAccessible(true);
        try { return function.invoke(instance,args); }
        catch (InvocationTargetException error) {
            Throwable cause=error.getCause();
            if (cause instanceof Exception) throw (Exception)cause;
            throw error;
        }
    }

    private static int get(String key) throws Exception {
        return ((Number)call("com.mediatek.twoworlds.tv.TVNative",null,"getConfigValue_native",
            new Class<?>[]{int.class,String.class},-1,key)).intValue();
    }

    private static int set(String key,int value,int update) throws Exception {
        return ((Number)call("com.mediatek.twoworlds.tv.TVNative",null,"setConfigValue_native",
            new Class<?>[]{int.class,String.class,int.class,int.class},-1,key,value,update)).intValue();
    }

    private static boolean known(String key) {
        for (String name:KEYS) if (name.equals(key)) return true;
        return false;
    }

    private static void picture(Map<String,String> result) throws Exception {
        for (String key:KEYS) result.put(key,Integer.toString(get(key)));
    }

    private static void signal(Map<String,String> result) throws Exception {
        boolean lost=(Boolean)call("com.mediatek.twoworlds.tv.TVNative",null,"isSignalLoss_native",new Class<?>[0]);
        result.put("input.lost_before",lost?"1":"0");
        if (!lost) {
            String owner="com.mediatek.twoworlds.tv.MtkTvAVMode";
            Object mode=call(owner,null,"getInstance",new Class<?>[0]);
            List<?> videos=(List<?>)call(owner,mode,"getInputSourceVideoAvailableRecord",new Class<?>[0]);
            if (videos==null || videos.size()!=1) throw new IllegalStateException("Active input is not unique");
            Object video=videos.get(0);
            String[] fields={"width","height","hz","dolby"};
            String[] methods={"getVideoWidth","getVideoHeight","getVideoFrameRate","getVideoDolbyVision"};
            for (int i=0;i<fields.length;i++)
                result.put("input."+fields[i],String.valueOf(video.getClass().getMethod(methods[i]).invoke(video)));
        }
        lost=(Boolean)call("com.mediatek.twoworlds.tv.TVNative",null,"isSignalLoss_native",new Class<?>[0]);
        result.put("input.lost_after",lost?"1":"0");
        picture(result);
    }

    private static void tone(String[] args,Map<String,String> result) throws Exception {
        if (args.length!=5) throw new IllegalArgumentException("Tone request needs value, update, expected picture bank and receipt");
        int value=Integer.parseInt(args[1]),update=Integer.parseInt(args[2]),expected=Integer.parseInt(args[3]);
        if (value!=0 && value!=1 && value!=2 && value!=5) throw new IllegalArgumentException("Unsupported HDR mapping mode");
        int bank=get(KEYS[0]),dolby=get(KEYS[1]);
        result.put("bank_before",Integer.toString(bank));result.put("dovi_before",Integer.toString(dolby));
        if (bank!=expected || !(bank==15||bank==16||bank==17||bank==18||bank==19||bank==35||bank==55||bank==76||(bank>=25&&bank<=34)) || dolby!=0) throw new IllegalStateException("Supported HDR / non-Dolby picture bank required");
        int status=set(KEYS[4],value,update);result.put("native_return",Integer.toString(status));
        if (status!=0) throw new IllegalStateException("Native tone setter failed: "+status);
        String owner="xiaomi.hardware.mitv.provider.V1_0.IMiTVProvider";
        Object provider=call(owner,null,"getService",new Class<?>[]{boolean.class},false);
        if (provider==null) throw new IllegalStateException("HDR provider unavailable");
        status=((Number)call(owner,provider,"setHdrAttr",new Class<?>[]{int.class,int.class},4,value)).intValue();
        result.put("provider_return",Integer.toString(status));
        int after=get(KEYS[4]);result.put(KEYS[4],Integer.toString(after));result.put(KEYS[4]+"_after",Integer.toString(after));
        if (status!=0 || after!=value || get(KEYS[0])!=bank || get(KEYS[1])!=dolby)
            throw new IllegalStateException("HDR mapping readback did not match");
    }

    public static synchronized String executeSession(String[] args) throws Exception {
        if (args.length==0) throw new IllegalArgumentException("Missing bridge action");
        String action=args[0];
        if (action.equals("getBatch") || action.equals("getPictureState") || action.equals("getInputSignal") || action.equals("setHdrToneMappingChecked")) {
            if (args.length<2) throw new IllegalArgumentException("Missing receipt path");
        }
        Map<String,String> result=new LinkedHashMap<String,String>();
        result.put("__version","1");result.put("__action",action);
        try {
            prepareSession();
            if (action.equals("getBatch")) {
                if (args.length<3) throw new IllegalArgumentException("Missing keys");
                for (int i=1;i<args.length-1;i++) {
                    if (!known(args[i])) throw new IllegalArgumentException("Unsupported native key");
                    result.put(args[i],Integer.toString(get(args[i])));
                }
            } else if (action.equals("getPictureState")) picture(result);
            else if (action.equals("getInputSignal")) signal(result);
            else if (action.equals("setHdrToneMappingChecked")) tone(args,result);
            else if (action.equals("set")) {
                if (args.length!=4 || !args[1].equals(KEYS[3])) throw new IllegalArgumentException("Only local-dimming profile selection is exposed");
                int value=Integer.parseInt(args[2]);
                if (value<0 || value>3) throw new IllegalArgumentException("Local-dimming level must be 0..3");
                int status=set(args[1],value,Integer.parseInt(args[3]));
                if (status!=0 || get(args[1])!=value) throw new IllegalStateException("Local-dimming setter/readback failed");
                result.put("result","RESULT: SET "+args[1]+" to "+value+" native return: 0");
            } else throw new IllegalArgumentException("Unsupported bridge action: "+action);
        } catch (Exception error) {
            result.put("fatal",error.getClass().getSimpleName()+": "+String.valueOf(error.getMessage()).replace('\n',' '));
        }
        result.put("__complete","1");StringBuilder output=new StringBuilder();
        for (Map.Entry<String,String> field:result.entrySet()) output.append(field.getKey()).append('=').append(field.getValue()).append('\n');
        String text=output.toString();
        return text;
    }

    public static void main(String[] args) throws Exception {
        String result=executeSession(args);
        if (args.length>1 && (args[0].equals("getBatch") || args[0].equals("getPictureState") || args[0].equals("getInputSignal") || args[0].equals("setHdrToneMappingChecked")))
            Files.write(Paths.get(args[args.length-1]),result.getBytes(StandardCharsets.UTF_8));
        System.out.print(result);
        System.out.flush();
        // Vendor native bindings can leave non-daemon Binder threads after main returns.
        System.exit(result.contains("\nfatal=")?1:0);
    }
}
