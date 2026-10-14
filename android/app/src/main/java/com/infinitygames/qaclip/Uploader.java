package com.infinitygames.qaclip;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

import org.json.JSONObject;
import org.json.JSONArray;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * Sends saved clips to the Mac running qa-inbox.py. Finds it three ways, in order:
 * the last Mac that worked, Bonjour on the Wi-Fi (_qaclip._tcp), and a USB cable (adb reverse to 127.0.0.1).
 * Clips stay in the outbox until the Mac confirms the byte count, so nothing is lost offline.
 */
final class Uploader {
    static final int PORT = 8799;
    private static final String TYPE = "_qaclip._tcp";
    private static Uploader I;

    static synchronized Uploader get(Context c) {
        if (I == null) I = new Uploader(c.getApplicationContext());
        return I;
    }

    volatile boolean ok;
    volatile String state = "Looking for your Mac…";

    private final Context ctx;
    private final SharedPreferences sp;
    private final Object wake = new Object();
    private final Set<String> found = Collections.synchronizedSet(new LinkedHashSet<>());
    private NsdManager nsd;

    private Uploader(Context c) {
        ctx = c;
        sp = c.getSharedPreferences("qaclip", 0);
        discover();
        Thread t = new Thread(this::loop, "qaclip-upload");
        t.setDaemon(true);
        t.start();
    }

    int waiting() { return Clips.waiting(ctx).length; }

    void kick() {
        synchronized (wake) { wake.notifyAll(); }
    }

    private void loop() {
        while (true) {
            try {
                File[] clips = Clips.waiting(ctx);
                String mac = reach();
                if (mac != null) {
                    for (File f : clips) if (!send(mac, f)) break;
                    syncGames(mac);
                }
            } catch (Throwable t) {
                Log.w(Recorder.TAG, "upload: " + t);
            }
            synchronized (wake) {
                try { wake.wait(waiting() > 0 ? 3000 : 6000); } catch (InterruptedException ignored) { }
            }
        }
    }

    private String reach() {
        Set<String> tries = new LinkedHashSet<>();
        String last = sp.getString("last", null);
        if (last != null) tries.add(last);
        synchronized (found) { tries.addAll(found); }
        tries.add("127.0.0.1:" + PORT);
        String why = null;
        for (String t : tries) {
            JSONObject j = ping(t);
            if (j == null) continue;
            String name = j.optString("name", "your Mac"), st = j.optString("status");
            if ("approved".equals(st)) {
                state = name;
                ok = true;
                if (!t.equals(last)) sp.edit().putString("last", t).apply();
                return t;
            }
            why = "pending".equals(st) ? "Click Allow on " + name : name + " said no";
        }
        ok = false;
        state = why != null ? why : "Looking for your Mac…";
        return null;
    }

    private JSONObject ping(String target) {
        HttpURLConnection c = null;
        try {
            c = open(target, "/ping");
            c.setConnectTimeout(1200);
            c.setReadTimeout(2500);
            if (c.getResponseCode() != 200) return null;
            return new JSONObject(read(c.getInputStream()));
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private void syncGames(String target) {
        HttpURLConnection c = null;
        try {
            Set<String> pending = Games.pending(ctx);
            // Bound requests even after a long offline session.
            Set<String> batch = new LinkedHashSet<>();
            for (String name : pending) { if (batch.size() == 100) break; batch.add(name); }
            c = open(target, "/games");
            c.setConnectTimeout(2000);
            c.setReadTimeout(3000);
            if (!batch.isEmpty()) {
                c.setRequestMethod("POST"); c.setDoOutput(true);
                byte[] body = new JSONObject().put("games", new JSONArray(batch)).toString().getBytes(StandardCharsets.UTF_8);
                c.setRequestProperty("Content-Type", "application/json");
                c.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = c.getOutputStream()) { out.write(body); }
            }
            if (c.getResponseCode() == 200) {
                JSONArray names = new JSONObject(read(c.getInputStream())).optJSONArray("games");
                if (names != null) Games.received(ctx, names, batch);
            }
        } catch (Exception e) { Log.w(Recorder.TAG, "game sync: " + e); }
        finally { if (c != null) c.disconnect(); }
    }

    private boolean send(String target, File mp4) {
        File js = new File(mp4.getParent(), mp4.getName().replace(".mp4", ".json"));
        HttpURLConnection c = null;
        try {
            String meta = js.exists() ? new String(Files.readAllBytes(js.toPath()), StandardCharsets.UTF_8) : "{}";
            c = open(target, "/clip");
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setConnectTimeout(3000);
            c.setReadTimeout(60000);
            c.setFixedLengthStreamingMode(mp4.length());
            c.setRequestProperty("Content-Type", "video/mp4");
            c.setRequestProperty("X-QA-Name", mp4.getName());
            c.setRequestProperty("X-QA-Meta", URLEncoder.encode(meta.replace("\n", ""), "UTF-8"));
            try (InputStream in = new FileInputStream(mp4); OutputStream out = c.getOutputStream()) {
                byte[] b = new byte[64 * 1024];
                for (int n; (n = in.read(b)) > 0; ) out.write(b, 0, n);
            }
            if (c.getResponseCode() != 200) return false;
            JSONObject j = new JSONObject(read(c.getInputStream()));
            if (!j.optBoolean("ok") || j.optLong("bytes") != mp4.length()) return false;
            File sent = Clips.sent(ctx);
            mp4.renameTo(new File(sent, mp4.getName()));
            if (js.exists()) js.renameTo(new File(sent, js.getName()));
            Clips.prune(sent, 20);
            return true;
        } catch (Exception e) {
            Log.w(Recorder.TAG, "send " + mp4.getName() + ": " + e);
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private HttpURLConnection open(String target, String path) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL("http://" + target + path).openConnection();
        c.setUseCaches(false);
        c.setRequestProperty("X-QA-Key", key());
        c.setRequestProperty("X-QA-Device", URLEncoder.encode(deviceName(), "UTF-8"));
        return c;
    }

    // ---- identity: a random key per install; the Mac approves it once ----

    private String key() {
        String k = sp.getString("key", null);
        if (k == null) {
            byte[] b = new byte[16];
            new SecureRandom().nextBytes(b);
            StringBuilder s = new StringBuilder();
            for (byte x : b) s.append(String.format("%02x", x));
            k = s.toString();
            sp.edit().putString("key", k).apply();
        }
        return k;
    }

    private String deviceName() {
        String n = Settings.Global.getString(ctx.getContentResolver(), Settings.Global.DEVICE_NAME);
        return n != null && !n.isEmpty() ? n : Build.MODEL;
    }

    // ---- Bonjour ----

    private void discover() {
        try {
            nsd = ctx.getSystemService(NsdManager.class);
            nsd.discoverServices(TYPE, NsdManager.PROTOCOL_DNS_SD, new NsdManager.DiscoveryListener() {
                @Override public void onServiceFound(NsdServiceInfo s) { resolve(s); }
                @Override public void onServiceLost(NsdServiceInfo s) { }
                @Override public void onDiscoveryStarted(String t) { }
                @Override public void onDiscoveryStopped(String t) { }
                @Override public void onStartDiscoveryFailed(String t, int e) { Log.w(Recorder.TAG, "bonjour failed " + e); }
                @Override public void onStopDiscoveryFailed(String t, int e) { }
            });
        } catch (Exception e) {
            Log.w(Recorder.TAG, "bonjour: " + e);
        }
    }

    @SuppressWarnings("deprecation")
    private void resolve(NsdServiceInfo s) {
        nsd.resolveService(s, new NsdManager.ResolveListener() {
            @Override public void onResolveFailed(NsdServiceInfo s, int e) { }
            @Override public void onServiceResolved(NsdServiceInfo r) {
                List<InetAddress> all = new ArrayList<>();
                if (Build.VERSION.SDK_INT >= 34) all.addAll(r.getHostAddresses());
                else if (r.getHost() != null) all.add(r.getHost());
                for (InetAddress a : all) {
                    if (a instanceof Inet4Address) {
                        found.add(a.getHostAddress() + ":" + r.getPort());
                        kick();
                        return;
                    }
                }
            }
        });
    }

    private static String read(InputStream in) throws Exception {
        ByteArrayOutputStream o = new ByteArrayOutputStream();
        byte[] b = new byte[8192];
        for (int n; (n = in.read(b)) > 0; ) o.write(b, 0, n);
        in.close();
        return o.toString("UTF-8");
    }
}
