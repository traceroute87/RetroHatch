package app.retrohatch.testfixture;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

/** Test fixture only. Proves that RetroHatch installed an APK it downloaded and verified. */
public class MainActivity extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        TextView t = new TextView(this);
        t.setText("RetroHatch test APK (fixture)\nInstalled by the RetroHatch Android installer test.\nNot a real application.");
        t.setTextSize(20);
        t.setPadding(40, 80, 40, 40);
        setContentView(t);
    }
}
