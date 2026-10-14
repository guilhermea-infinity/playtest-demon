package com.infinitygames.qaclip;

import android.content.Context;
import android.os.Build;
import android.os.VibrationAttributes;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;

/** Eyes-free confirmation: one tick = recording, two ticks = saved, one long buzz = thrown away. */
final class Feedback {
    static final long[] START = { 0, 60 };
    static final long[] SAVE = { 0, 50, 90, 50 };
    static final long[] DISCARD = { 0, 350 };
    static final int RED = 0xE6FF3B30, GREEN = 0xE630B05A, GREY = 0xE6555559;

    static void buzz(Context c, long[] pattern) {
        try {
            Vibrator v = Build.VERSION.SDK_INT >= 31
                    ? c.getSystemService(VibratorManager.class).getDefaultVibrator()
                    : c.getSystemService(Vibrator.class);
            VibrationEffect e = VibrationEffect.createWaveform(pattern, -1);
            if (Build.VERSION.SDK_INT >= 33) {
                v.vibrate(e, VibrationAttributes.createForUsage(VibrationAttributes.USAGE_ACCESSIBILITY));
            } else {
                v.vibrate(e);
            }
        } catch (Exception ignored) { }
    }
}
