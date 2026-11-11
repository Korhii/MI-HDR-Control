package com.example.autoreboot;
import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

public class MainActivity extends Activity {
    public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView text=new TextView(this);text.setTextSize(22);text.setPadding(40,40,40,40);
        text.setText("MI HDR 随屏启动\n\n"+BootReceiver.start()+"\n\n方案保存和重置请在PC控制器操作。");
        setContentView(text);
        if(getIntent().getBooleanExtra("background",false))finish();
    }
}
