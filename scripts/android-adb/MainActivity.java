package local.mi.adbkeepalive;

import android.app.Activity;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {
    TextView status;
    void refresh() {
        boolean enabled=BootReceiver.prefs(this).getBoolean("enabled",true);
        status.setText("MI ADB 随屏开启\n\n开机自动开启："+(enabled?"开":"关")
            +"\n当前 adb_enabled："+Settings.Global.getInt(getContentResolver(),"adb_enabled",-1)
            +"\n\n最近执行：\n"+BootReceiver.prefs(this).getString("receipt","尚未执行")
            +"\n\n只操作原厂 ADB 开关；不改变 USB 角色、端口或认证。停用只影响以后开机，不会立即断开当前连接。");
    }
    public void onCreate(Bundle state) {
        super.onCreate(state);
        if(getIntent().getBooleanExtra("enable",false))BootReceiver.prefs(this).edit().putBoolean("enabled",true).apply();
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(40,24,40,24);
        status=new TextView(this);status.setTextSize(20);box.addView(status);
        Button on=new Button(this);on.setText("启用开机自动 ADB");box.addView(on);
        on.setOnClickListener(new View.OnClickListener(){public void onClick(View v){BootReceiver.prefs(MainActivity.this).edit().putBoolean("enabled",true).apply();BootReceiver.enable(MainActivity.this,"ENABLE");refresh();}});
        Button off=new Button(this);off.setText("停用开机自动 ADB");box.addView(off);
        off.setOnClickListener(new View.OnClickListener(){public void onClick(View v){BootReceiver.prefs(MainActivity.this).edit().putBoolean("enabled",false).apply();refresh();}});
        if(BootReceiver.prefs(this).getBoolean("enabled",true))BootReceiver.enable(this,"ACTIVITY");
        refresh();setContentView(box);
    }
}
