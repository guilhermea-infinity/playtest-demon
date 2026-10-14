package com.infinitygames.qaclip;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.view.KeyEvent;

/** adb shell am broadcast -a com.infinitygames.qaclip.KEY --es key up|down  (one full press: down + up) */
public final class DebugKeys extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        KeyService s = KeyService.get();
        if (s == null) return;
        int k = "down".equals(i.getStringExtra("key")) ? KeyEvent.KEYCODE_VOLUME_DOWN : KeyEvent.KEYCODE_VOLUME_UP;
        boolean used = s.handle(k, KeyEvent.ACTION_DOWN, 0);
        s.handle(k, KeyEvent.ACTION_UP, 0);
        setResultData(used ? "used" : "passed through");
    }
}
