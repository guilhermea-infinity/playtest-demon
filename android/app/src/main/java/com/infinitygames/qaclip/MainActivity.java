package com.infinitygames.qaclip;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.projection.MediaProjectionConfig;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

/** The only screen: one big button, three status lines, one switch. */
public final class MainActivity extends Activity {
    private static final int BG = 0xFF0E0E10, TXT = 0xFFFFFFFF, DIM = 0xFF8E8E93, OK = 0xFF34C759, WARN = 0xFFFF9F0A, RED = 0xFFFF3B30;
    private static final int PERMS = 1, CAPTURE = 2;

    private final Handler h = new Handler(Looper.getMainLooper());
    private SharedPreferences sp;
    private TextView status, keysVal, macVal, clipsVal;
    private Button go;
    private Switch voice;
    private float dp;

    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            render();
            h.postDelayed(this, 700);
        }
    };

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        sp = getSharedPreferences("qaclip", 0);
        dp = getResources().getDisplayMetrics().density;
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);

        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(px(24), px(28), px(24), px(28));

        TextView title = text("QA Clip", 32, TXT, true);
        col.addView(title);
        status = text("", 17, DIM, false);
        status.setPadding(0, px(6), 0, px(28));
        col.addView(status);

        go = new Button(this);
        go.setAllCaps(false);
        go.setTextSize(20);
        go.setTypeface(Typeface.DEFAULT_BOLD);
        go.setTextColor(TXT);
        go.setStateListAnimator(null);
        go.setOnClickListener(v -> onGo());
        col.addView(go, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(68)));

        View gap = new View(this);
        col.addView(gap, new LinearLayout.LayoutParams(1, px(24)));

        keysVal = row(col, "Volume buttons", v -> openKeys());
        macVal = row(col, "Mac", null);
        clipsVal = row(col, "Clips", null);

        LinearLayout vr = rowFrame(col);
        vr.addView(text("Record my voice", 16, DIM, false), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        voice = new Switch(this);
        voice.setChecked(sp.getBoolean("voice", true));
        voice.setOnCheckedChangeListener((s, on) -> sp.edit().putBoolean("voice", on).apply());
        vr.addView(voice);

        TextView hint = text("Vol +   saves the last 15 s and keeps recording\n"
                + "Vol +   again stops it and sends it to your Mac\n"
                + "Vol −   while recording throws it away", 14, DIM, false);
        hint.setLineSpacing(px(5), 1f);
        hint.setPadding(0, px(26), 0, 0);
        col.addView(hint);

        ScrollView root = new ScrollView(this);
        root.setBackgroundColor(BG);
        root.setFitsSystemWindows(true);
        root.addView(col);
        setContentView(root);

        Uploader.get(this);
    }

    @Override
    protected void onResume() {
        super.onResume();
        Uploader.get(this).kick();
        h.post(refresh);
    }

    @Override
    protected void onPause() {
        super.onPause();
        h.removeCallbacks(refresh);
    }

    private void render() {
        boolean keys = KeyService.on();
        CaptureService s = CaptureService.I;
        boolean armed = s != null;
        if (armed && s.clipping()) status.setText("● Recording a clip");
        else if (armed) status.setText("Session on. Open your game and play.");
        else if (!keys) status.setText("First, turn on the volume buttons.");
        else status.setText("Ready.");
        status.setTextColor(armed ? RED : DIM);

        go.setText(armed ? "Stop session" : "Start session");
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(px(18));
        bg.setColor(armed ? 0xFF2C2C2E : RED);
        go.setBackground(bg);

        keysVal.setText(keys ? "On" : "Turn on ›");
        keysVal.setTextColor(keys ? OK : WARN);

        Uploader u = Uploader.get(this);
        macVal.setText(u.ok ? u.state + "  ✓" : u.state);
        macVal.setTextColor(u.ok ? OK : WARN);

        int n = u.waiting();
        clipsVal.setText(n == 0 ? "All sent" : n + " waiting");
        clipsVal.setTextColor(n == 0 ? TXT : WARN);
    }

    // ---- start / stop ----

    private void onGo() {
        if (CaptureService.I != null) {
            startService(new Intent(this, CaptureService.class).setAction(CaptureService.STOP));
            h.postDelayed(this::render, 300);
            return;
        }
        if (!KeyService.on()) {
            Toast.makeText(this, "Turn on “QA Clip volume buttons”, then come back", Toast.LENGTH_LONG).show();
            openKeys();
            return;
        }
        List<String> need = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= 33 && !granted(Manifest.permission.POST_NOTIFICATIONS)) need.add(Manifest.permission.POST_NOTIFICATIONS);
        if (voice.isChecked() && !granted(Manifest.permission.RECORD_AUDIO)) need.add(Manifest.permission.RECORD_AUDIO);
        if (!need.isEmpty()) requestPermissions(need.toArray(new String[0]), PERMS);
        else askCapture();
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] p, int[] r) {
        if (code == PERMS) askCapture();
    }

    private void askCapture() {
        MediaProjectionManager m = getSystemService(MediaProjectionManager.class);
        Intent i = Build.VERSION.SDK_INT >= 34
                ? m.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
                : m.createScreenCaptureIntent();
        startActivityForResult(i, CAPTURE);
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code != CAPTURE) return;
        if (result != RESULT_OK || data == null) {
            Toast.makeText(this, "Screen capture was not allowed", Toast.LENGTH_SHORT).show();
            return;
        }
        Intent s = new Intent(this, CaptureService.class).setAction(CaptureService.START)
                .putExtra("code", result)
                .putExtra("data", data)
                .putExtra("voice", voice.isChecked() && granted(Manifest.permission.RECORD_AUDIO));
        startForegroundService(s);
        // give the service a moment to go foreground while we are still on screen, then get out of the way
        h.postDelayed(() -> moveTaskToBack(true), 900);
    }

    private void openKeys() {
        Intent i = new Intent("android.settings.ACCESSIBILITY_DETAILS_SETTINGS")
                .putExtra(Intent.EXTRA_COMPONENT_NAME, getPackageName() + "/" + KeyService.class.getName());
        try {
            startActivity(i);
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
        }
    }

    // ---- views ----

    private boolean granted(String p) { return checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED; }

    private int px(float v) { return Math.round(v * dp); }

    private TextView text(String s, float sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    private LinearLayout rowFrame(LinearLayout col) {
        View line = new View(this);
        line.setBackgroundColor(0xFF2C2C2E);
        col.addView(line, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Math.max(1, px(0.5f))));
        LinearLayout r = new LinearLayout(this);
        r.setGravity(Gravity.CENTER_VERTICAL);
        r.setPadding(0, px(15), 0, px(15));
        col.addView(r);
        return r;
    }

    private TextView row(LinearLayout col, String label, View.OnClickListener click) {
        LinearLayout r = rowFrame(col);
        r.addView(text(label, 16, DIM, false), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        TextView v = text("", 16, TXT, true);
        v.setGravity(Gravity.END);
        r.addView(v);
        if (click != null) r.setOnClickListener(click);
        return v;
    }
}
