package com.example.autoreboot;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.IBinder;
import android.os.Parcel;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {
    static String start() {
        Parcel input=Parcel.obtain(),reply=Parcel.obtain();
        try {
            Class<?> manager=Class.forName("android.os.ServiceManager");
            IBinder service=(IBinder)manager.getMethod("getService",String.class).invoke(null,"TvService");
            if(service==null)return "not-ready";
            input.writeInterfaceToken(service.getInterfaceDescriptor());
            input.writeString("sh -c eval${IFS}sh${IFS}/data/data/mitv.service/files/MIHDRControl/start.sh");
            boolean ok=service.transact(3,input,reply,0);
            reply.readException();
            Log.i("MIHDRBoot","fixed request returned without exception="+ok);
            return ok?"submitted":"not-accepted";
        } catch(Exception error) {
            Log.e("MIHDRBoot","start failed",error);
            return error.toString();
        } finally {input.recycle();reply.recycle();}
    }
    public void onReceive(Context context,Intent intent) {
        if(!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()))return;
        final PendingResult result=goAsync();
        new Thread(new Runnable() { public void run() { try { Log.i("MIHDRBoot","reason=BOOT_COMPLETED uptime_ms="+android.os.SystemClock.elapsedRealtime()); for(int i=0;i<30;i++){String value=start();if(!value.equals("not-ready"))break;Thread.sleep(500);} } catch(Exception error){Log.e("MIHDRBoot","boot request failed",error);} finally { result.finish(); } } }).start();
    }
}
