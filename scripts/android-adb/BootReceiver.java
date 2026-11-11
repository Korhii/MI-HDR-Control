package local.mi.adbkeepalive;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {
    static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("adb-autostart", Context.MODE_PRIVATE);
    }
    static String enable(Context context, String reason) {
        try {
            int before=Settings.Global.getInt(context.getContentResolver(), "adb_enabled", -1);
            boolean ok=Settings.Global.putInt(context.getContentResolver(), "adb_enabled", 1);
            int after=Settings.Global.getInt(context.getContentResolver(), "adb_enabled", -1);
            int boot=Settings.Global.getInt(context.getContentResolver(), "boot_count", -1);
            String receipt="reason="+reason+" boot_count="+boot+" uptime_ms="+SystemClock.elapsedRealtime()
                +" before="+before+" after="+after+" write_ok="+ok;
            prefs(context).edit().putString("receipt",receipt).apply();
            Log.i("MIADBKeepalive",receipt);
            return receipt;
        } catch(Exception error) {
            String receipt="reason="+reason+" error="+error;
            prefs(context).edit().putString("receipt",receipt).apply();
            Log.e("MIADBKeepalive",receipt);
            return receipt;
        }
    }
    public void onReceive(Context context, Intent intent) {
        if(Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()) && prefs(context).getBoolean("enabled",true)) {
            enable(context,"BOOT_COMPLETED");
        }
    }
}
