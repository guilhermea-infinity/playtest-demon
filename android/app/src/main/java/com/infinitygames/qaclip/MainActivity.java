package com.infinitygames.qaclip;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.res.ColorStateList;
import android.widget.EditText;
import android.widget.SeekBar;
import android.text.InputFilter;
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
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

/** The only screen: one big button, three status lines, one switch. */
public final class MainActivity extends Activity {
    private static final int BG = 0xFF0D131B, TXT = 0xFFF7F9F9, DIM = 0xFF9DAFC3, OK = 0xFF78D5D7, WARN = 0xFFF3BE76, RED = 0xFFFF938C;
    private static final int PERMS = 1, CAPTURE = 2;

    private final Handler h = new Handler(Looper.getMainLooper());
    private SharedPreferences sp;
    private TextView status, keysVal, macVal, clipsVal, gameVal, lookbackVal, lookbackHint;
    private SeekBar lookback;
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

        TextView brand = text("INFINITY GAMES", 12, OK, true);
        brand.setLetterSpacing(.14f);
        brand.setPadding(0, 0, 0, px(16));
        col.addView(brand);
        LinearLayout identity = new LinearLayout(this);
        identity.setGravity(Gravity.CENTER_VERTICAL);
        ImageView devil = new ImageView(this);
        devil.setImageResource(R.drawable.ic_devil);
        identity.addView(devil, new LinearLayout.LayoutParams(px(40), px(40)));
        TextView title = text("QA Demon", 30, TXT, true);
        title.setPadding(px(12), 0, 0, 0);
        identity.addView(title);
        col.addView(identity);
        status = text("", 17, DIM, false);
        status.setPadding(0, px(8), 0, px(24));
        col.addView(status);

        LinearLayout gameCard = card(col);
        gameCard.addView(text("YOUR GAME", 11, OK, true));
        gameVal = text("", 21, TXT, true);
        gameVal.setPadding(0, px(12), 0, px(12));
        gameVal.setContentDescription("Choose game");
        gameVal.setOnClickListener(v -> chooseGame());
        gameCard.addView(gameVal);
        TextView add = text("+ Add game", 15, OK, true);
        add.setPadding(0, px(8), 0, px(8));
        add.setOnClickListener(v -> addGame());
        gameCard.addView(add);
        gameCard.addView(text("Shared with QA Demon when your Mac is connected.", 12, DIM, false));

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

        LinearLayout connections = card(col);
        keysVal = row(connections, "Volume buttons", v -> openKeys());
        macVal = row(connections, "Mac", null);
        clipsVal = row(connections, "Clips", null);

        LinearLayout capture = card(col);
        capture.addView(text("CAPTURE SETTINGS", 11, OK, true));
        LinearLayout vr = rowFrame(capture);
        vr.addView(text("Record my voice", 16, TXT, false), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        voice = new Switch(this);
        voice.setThumbTintList(ColorStateList.valueOf(OK));
        voice.setChecked(sp.getBoolean("voice", true));
        voice.setOnCheckedChangeListener((v, on) -> sp.edit().putBoolean("voice", on).apply());
        vr.addView(voice);
        lookbackVal = text("", 18, TXT, true);
        lookbackVal.setPadding(0, px(14), 0, px(8));
        capture.addView(lookbackVal);
        TextView explanation = text("A bug just happened—and you can’t reproduce it? Lookback includes the moments BEFORE you press Volume Up, so you can still catch it.", 14, DIM, false);
        explanation.setLineSpacing(px(3), 1f);
        capture.addView(explanation);
        lookback = new SeekBar(this);
        lookback.setMax(30);
        lookback.setProgress(Math.max(0, Math.min(30, sp.getInt("lookback", 10))));
        lookback.setContentDescription("Lookback window in seconds, from zero to thirty");
        lookback.setProgressTintList(ColorStateList.valueOf(OK));
        lookback.setThumbTintList(ColorStateList.valueOf(OK));
        capture.addView(lookback, new LinearLayout.LayoutParams(-1, px(52)));
        lookback.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar bar, int value, boolean user) {
                if (user) sp.edit().putInt("lookback", value).apply();
                lookbackVal.setText("Lookback · " + value + " seconds");
            }
            public void onStartTrackingTouch(SeekBar bar) { }
            public void onStopTrackingTouch(SeekBar bar) { }
        });
        capture.addView(text("0 s · off                                      30 s · maximum", 12, DIM, false));
        TextView suggested = text("10 seconds suggested  ↺", 14, OK, true);
        suggested.setPadding(0, px(16), 0, px(6));
        suggested.setOnClickListener(v -> {
            if (CaptureService.I != null) { Toast.makeText(this, "Stop the session to change lookback", Toast.LENGTH_SHORT).show(); return; }
            sp.edit().putInt("lookback", 10).apply(); lookback.setProgress(10);
        });
        capture.addView(suggested);
        capture.addView(text("Enough time to notice a bug and press Record, without adding too much footage to every clip. Longer windows use more memory. With 0 seconds, recording starts when you press.", 13, DIM, false));
        lookbackHint = text("", 12, WARN, false);
        lookbackHint.setPadding(0, px(10), 0, 0);
        capture.addView(lookbackHint);

        TextView hint = text("HOW IT WORKS\n\nVolume Up   Start a clip, including lookback\nVolume Up   Press again to save & send\nVolume Down   Discard the current clip\n\nQA Demon  /  Android → Mac → your agent", 13, DIM, false);
        hint.setLineSpacing(px(6), 1f);
        hint.setPadding(0, px(8), 0, 0);
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
        String selected = Games.selected(this);
        gameVal.setText((selected.isEmpty() ? "Detect automatically" : selected) + "  ▾");
        lookbackVal.setText("Lookback · " + lookback.getProgress() + " seconds");
        boolean keys = KeyService.on();
        CaptureService s = CaptureService.I;
        boolean armed = s != null;
        voice.setEnabled(!armed);
        lookback.setEnabled(!armed);
        lookbackHint.setText(armed ? "Stop the session to change capture settings." : "Applies when you start a session. Timing may vary slightly to keep the video playable.");
        if (armed && s.clipping()) status.setText("● Recording a clip");
        else if (armed) status.setText("Session on. Open your game and play.");
        else if (!keys) status.setText("First, turn on the volume buttons.");
        else status.setText("Choose your game. Start a QA session.");
        status.setTextColor(armed ? RED : DIM);

        go.setText(armed ? "Stop session" : "Start session");
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(px(18));
        bg.setColor(armed ? 0xFF26384B : OK);
        go.setTextColor(armed ? TXT : BG);
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

    private void chooseGame() {
        List<String> names = Games.list(this);
        List<String> choices = new ArrayList<>();
        choices.add("Detect automatically"); choices.addAll(names); choices.add("+ Add game");
        int selected = names.indexOf(Games.selected(this)) + 1;
        new AlertDialog.Builder(this).setTitle("Choose your game")
            .setSingleChoiceItems(choices.toArray(new String[0]), selected, (dialog, which) -> {
                dialog.dismiss();
                if (which == choices.size() - 1) addGame();
                else { Games.select(this, which == 0 ? "" : names.get(which - 1)); render(); }
            }).setNegativeButton("Cancel", null).show();
    }

    private void addGame() {
        EditText input = new EditText(this);
        input.setSingleLine(true); input.setHint("Game name"); input.setTextColor(TXT);
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(80)});
        LinearLayout content = new LinearLayout(this);
        content.setPadding(px(24), px(12), px(24), 0); content.addView(input, new LinearLayout.LayoutParams(-1, -2));
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("Add a game").setMessage("Just a name. We’ll share it with QA Demon.")
            .setView(content).setNegativeButton("Cancel", null).setPositiveButton("Add & select", null).create();
        dialog.setOnShowListener(d -> {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                try { Games.add(this, input.getText().toString()); Uploader.get(this).kick(); render(); dialog.dismiss(); }
                catch (IllegalArgumentException e) { input.setError(e.getMessage()); }
            });
            input.requestFocus();
            dialog.getWindow().setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE);
        });
        dialog.show();
    }

    private LinearLayout card(LinearLayout parent) {
        LinearLayout box = new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(px(18), px(18), px(18), px(18));
        GradientDrawable bg = new GradientDrawable(); bg.setColor(0xFF1B2737); bg.setCornerRadius(px(18)); bg.setStroke(px(1), 0xFF2C4056);
        box.setBackground(bg);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2); lp.bottomMargin = px(20);
        parent.addView(box, lp); return box;
    }

    // ---- start / stop ----

    private void onGo() {
        if (CaptureService.I != null) {
            startService(new Intent(this, CaptureService.class).setAction(CaptureService.STOP));
            h.postDelayed(this::render, 300);
            return;
        }
        if (!KeyService.on()) {
            Toast.makeText(this, "Turn on “QA Demon volume buttons”, then come back", Toast.LENGTH_LONG).show();
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
        line.setBackgroundColor(0xFF2C4056);
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
        r.addView(v, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        if (click != null) r.setOnClickListener(click);
        return v;
    }
}
