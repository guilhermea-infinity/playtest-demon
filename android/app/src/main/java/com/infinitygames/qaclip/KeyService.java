package com.infinitygames.qaclip;

import android.accessibilityservice.AccessibilityService;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.widget.TextView;

import java.util.HashSet;
import java.util.Set;

/**
 * Hears the volume buttons over any game. Outside a session, and for Vol − when no clip is
 * recording, the keys pass through untouched, so the volume works as normal.
 * Also remembers which app is on screen (to name the clip) and draws the small REC pill.
 */
public final class KeyService extends AccessibilityService {
    private static KeyService I;
    private static volatile String fgApp;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final Set<Integer> eaten = new HashSet<>();
    private TextView pill;
    private final Runnable hide = this::removePill;

    static boolean on() { return I != null; }

    static KeyService get() { return I; }

    static String foregroundApp() { return fgApp; }

    @Override protected void onServiceConnected() { I = this; }

    @Override
    public boolean onUnbind(Intent intent) {
        removePill();
        I = null;
        return super.onUnbind(intent);
    }

    @Override public void onInterrupt() { }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent e) {
        if (e.getEventType() != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED || e.getPackageName() == null) return;
        String p = e.getPackageName().toString();
        if (p.equals(getPackageName()) || p.equals("com.android.systemui") || p.equals("android") || p.contains("inputmethod")) return;
        fgApp = p;
    }

    @Override
    protected boolean onKeyEvent(KeyEvent e) {
        return handle(e.getKeyCode(), e.getAction(), e.getRepeatCount());
    }

    /** True = QA Demon used the key (the volume does not change). Also driven by the debug build's adb trigger. */
    boolean handle(int k, int action, int repeat) {
        if (k != KeyEvent.KEYCODE_VOLUME_UP && k != KeyEvent.KEYCODE_VOLUME_DOWN) return false;
        Log.d(Recorder.TAG, "key " + KeyEvent.keyCodeToString(k) + " action=" + action + " session=" + (CaptureService.I != null));
        if (action == KeyEvent.ACTION_UP) return eaten.remove(k);
        if (action != KeyEvent.ACTION_DOWN) return false;
        if (repeat > 0) return eaten.contains(k);
        CaptureService s = CaptureService.I;
        if (s == null) return false;
        if (k == KeyEvent.KEYCODE_VOLUME_UP) {
            eaten.add(k);
            s.volUp();
            return true;
        }
        if (s.clipping()) {
            eaten.add(k);
            s.volDown();
            return true;
        }
        return false;
    }

    // ---- the pill: "● REC 0:23" while recording, then a short "Saved" / "Thrown away" ----

    static void pill(String text, int color) {
        KeyService s = I;
        if (s != null) s.main.post(() -> s.showPill(text, color, 0));
    }

    static void flash(String text, int color) {
        KeyService s = I;
        if (s != null) s.main.post(() -> s.showPill(text, color, 1300));
    }

    static void hidePill() {
        KeyService s = I;
        if (s != null) s.main.post(s::removePill);
    }

    private void showPill(String text, int color, long ms) {
        main.removeCallbacks(hide);
        float dp = getResources().getDisplayMetrics().density;
        if (pill == null) {
            pill = new TextView(this);
            pill.setTextColor(0xFFFFFFFF);
            pill.setTextSize(12);
            pill.setTypeface(Typeface.DEFAULT_BOLD);
            pill.setPadding((int) (9 * dp), (int) (3 * dp), (int) (9 * dp), (int) (3 * dp));
            WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                    WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
                    WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                    PixelFormat.TRANSLUCENT);
            lp.gravity = Gravity.TOP | Gravity.START;
            lp.x = (int) (10 * dp);
            lp.y = (int) (4 * dp);
            lp.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            try {
                getSystemService(WindowManager.class).addView(pill, lp);
            } catch (Exception ex) {
                pill = null;
                return;
            }
        }
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(color);
        bg.setCornerRadius(20 * dp);
        pill.setBackground(bg);
        pill.setText(text);
        if (ms > 0) main.postDelayed(hide, ms);
    }

    private void removePill() {
        main.removeCallbacks(hide);
        if (pill == null) return;
        try {
            getSystemService(WindowManager.class).removeView(pill);
        } catch (Exception ignored) { }
        pill = null;
    }
}
