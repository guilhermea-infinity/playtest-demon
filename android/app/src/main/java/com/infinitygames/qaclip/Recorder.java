package com.infinitygames.qaclip;

import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import android.media.MediaRecorder;
import android.media.projection.MediaProjection;
import android.util.Log;
import android.view.Surface;

import java.io.File;
import java.nio.ByteBuffer;
import java.util.ArrayDeque;
import java.util.ArrayList;

/**
 * Encodes the screen (and the mic) for the whole session but only keeps the last 15 s in memory.
 * startClip() opens an MP4 that begins with those 15 s and keeps growing; stopClip() closes or throws it away.
 */
final class Recorder {
    static final String TAG = "QAClip";
    static final long PRE_US = 15_000_000L;
    private static final int RATE = 44100;

    static final class Clip {
        File file;
        long preUs, durUs;
        boolean audio;
    }

    private static final class Pkt {
        final byte[] data;
        final long pts;
        final boolean key;
        Pkt(byte[] d, long p, boolean k) { data = d; pts = p; key = k; }
    }

    final int w, h, dpi;
    private final MediaProjection mp;
    private boolean voice;

    private final Object lock = new Object();
    private final ArrayDeque<Pkt> vRing = new ArrayDeque<>(), aRing = new ArrayDeque<>();
    private MediaFormat vFmt, aFmt;
    private MediaCodec venc, aenc;
    private Surface input;
    private VirtualDisplay vd;
    private AudioRecord mic;
    private Thread vThread, aThread;
    private volatile boolean running;

    // the clip being written; all guarded by lock
    private MediaMuxer mux;
    private int vTrack = -1, aTrack = -1;
    private long t0, pressPts, lastPts;
    private File part;

    Recorder(MediaProjection mp, int w, int h, int dpi, boolean voice) {
        this.mp = mp;
        this.w = w;
        this.h = h;
        this.dpi = dpi;
        this.voice = voice;
    }

    boolean voice() { return voice; }

    void start() throws Exception {
        venc = videoEncoder(w, h);
        input = venc.createInputSurface();
        venc.start();
        running = true;
        vd = mp.createVirtualDisplay("QAClip", w, h, dpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, input, null, null);
        vThread = new Thread(this::drainVideo, "qaclip-video");
        vThread.start();
        if (voice) {
            try {
                startMic();
            } catch (Exception e) {
                Log.w(TAG, "mic off: " + e);
                voice = false;
                if (mic != null) mic.release();
                if (aenc != null) aenc.release();
                mic = null;
                aenc = null;
            }
        }
    }

    void stop() {
        if (vd != null) vd.release();
        running = false;
        join(vThread);
        join(aThread);
        if (input != null) input.release();
    }

    /** Opens a clip on the newest key frame at least 15 s back (or as far back as the session goes). */
    boolean startClip(File dir, String name) {
        synchronized (lock) {
            if (mux != null || vFmt == null || vRing.isEmpty()) return false;
            Pkt head = null;
            for (Pkt p : vRing) if (p.key) { head = p; break; }
            if (head == null) return false;
            t0 = head.pts;
            pressPts = lastPts;
            part = new File(dir, name + ".mp4.part");
            try {
                mux = new MediaMuxer(part.getPath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
                vTrack = mux.addTrack(vFmt);
                aTrack = aFmt != null ? mux.addTrack(aFmt) : -1;
                mux.start();
            } catch (Exception e) {
                Log.w(TAG, "muxer: " + e);
                if (mux != null) mux.release();
                mux = null;
                part.delete();
                return false;
            }
            // the pre-roll: everything held, both tracks merged in time order
            ArrayList<Pkt> vs = new ArrayList<>(vRing), as = new ArrayList<>(aRing);
            int i = 0, j = 0;
            while (i < vs.size() || j < as.size()) {
                boolean takeV = j >= as.size() || (i < vs.size() && vs.get(i).pts <= as.get(j).pts);
                if (takeV) write(true, vs.get(i++));
                else write(false, as.get(j++));
            }
            return true;
        }
    }

    /** Closes the open clip. keep=false deletes it. Returns null when nothing was kept. */
    Clip stopClip(boolean keep) {
        MediaMuxer m;
        File f;
        Clip c = new Clip();
        synchronized (lock) {
            if (mux == null) return null;
            m = mux;
            mux = null;
            f = part;
            c.preUs = pressPts - t0;
            c.durUs = lastPts - t0;
            c.audio = aTrack >= 0;
            vTrack = aTrack = -1;
        }
        boolean ok = true;
        try {
            m.stop();
        } catch (Exception e) {
            Log.w(TAG, "muxer stop: " + e);
            ok = false;
        }
        m.release();
        if (!keep || !ok) {
            f.delete();
            return null;
        }
        File mp4 = new File(f.getPath().replace(".mp4.part", ".mp4"));
        if (!f.renameTo(mp4)) return null;
        c.file = mp4;
        return c;
    }

    // ---- encoders ----

    private static MediaCodec videoEncoder(int w, int h) throws Exception {
        MediaFormat f = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h);
        f.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        f.setInteger(MediaFormat.KEY_BIT_RATE, 6_000_000);
        f.setInteger(MediaFormat.KEY_FRAME_RATE, 30);
        f.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1);
        // a still screen still makes frames, so key frames keep coming every second
        f.setLong(MediaFormat.KEY_REPEAT_PREVIOUS_FRAME_AFTER, 100_000L);
        MediaCodec c = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
        try {
            c.configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        } catch (Exception e) {
            Log.w(TAG, "encoder retry without frame repeat: " + e);
            c.release();
            f.removeKey(MediaFormat.KEY_REPEAT_PREVIOUS_FRAME_AFTER);
            c = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC);
            c.configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        }
        return c;
    }

    private void drainVideo() {
        MediaCodec.BufferInfo bi = new MediaCodec.BufferInfo();
        while (running) {
            int i;
            try {
                i = venc.dequeueOutputBuffer(bi, 20_000);
            } catch (IllegalStateException e) {
                break;
            }
            if (i == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                synchronized (lock) { vFmt = venc.getOutputFormat(); }
            } else if (i >= 0) {
                if ((bi.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0 && bi.size > 0) {
                    add(true, new Pkt(copy(venc.getOutputBuffer(i), bi), bi.presentationTimeUs,
                            (bi.flags & MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0));
                }
                venc.releaseOutputBuffer(i, false);
            }
        }
        try { venc.stop(); } catch (Exception ignored) { }
        venc.release();
    }

    private void startMic() throws Exception {
        int min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        mic = new AudioRecord(MediaRecorder.AudioSource.MIC, RATE, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, Math.max(min * 2, 16384));
        if (mic.getState() != AudioRecord.STATE_INITIALIZED) throw new IllegalStateException("mic not available");
        MediaFormat f = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, RATE, 1);
        f.setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC);
        f.setInteger(MediaFormat.KEY_BIT_RATE, 64_000);
        f.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16384);
        aenc = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC);
        aenc.configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        aenc.start();
        mic.startRecording();
        aThread = new Thread(this::pumpAudio, "qaclip-audio");
        aThread.start();
    }

    private void pumpAudio() {
        MediaCodec.BufferInfo bi = new MediaCodec.BufferInfo();
        long samples = 0, base = -1;
        try {
            while (running) {
                int in = aenc.dequeueInputBuffer(10_000);
                if (in >= 0) {
                    ByteBuffer b = aenc.getInputBuffer(in);
                    b.clear();
                    int n = Math.max(0, mic.read(b, Math.min(b.capacity(), 4096)));
                    long now = System.nanoTime() / 1000;
                    if (base < 0) base = now - (n / 2) * 1_000_000L / RATE;
                    long pts = base + samples * 1_000_000L / RATE;
                    if (now - pts > 250_000) { base += now - pts; pts = now; } // the mic dropped audio: catch up
                    samples += n / 2;
                    aenc.queueInputBuffer(in, 0, n, pts, 0);
                }
                for (;;) {
                    int out = aenc.dequeueOutputBuffer(bi, 0);
                    if (out == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                        synchronized (lock) { aFmt = aenc.getOutputFormat(); }
                    } else if (out >= 0) {
                        if ((bi.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0 && bi.size > 0) {
                            add(false, new Pkt(copy(aenc.getOutputBuffer(out), bi), bi.presentationTimeUs, true));
                        }
                        aenc.releaseOutputBuffer(out, false);
                    } else {
                        break;
                    }
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "audio: " + e);
        }
        try { mic.stop(); } catch (Exception ignored) { }
        mic.release();
        try { aenc.stop(); } catch (Exception ignored) { }
        aenc.release();
    }

    // ---- ring + muxer ----

    private void add(boolean video, Pkt p) {
        synchronized (lock) {
            if (video) {
                vRing.addLast(p);
                lastPts = p.pts;
                trimVideo(p.pts - PRE_US);
            } else {
                aRing.addLast(p);
                while (aRing.size() > 1 && aRing.peekFirst().pts < p.pts - PRE_US - 2_000_000L) aRing.pollFirst();
            }
            if (mux != null) write(video, p);
        }
    }

    /** Keeps the newest key frame at or before the cut as the head, so a clip always opens on a key frame. */
    private void trimVideo(long cut) {
        int head = -1, i = 0;
        for (Pkt q : vRing) {
            if (q.pts > cut) break;
            if (q.key) head = i;
            i++;
        }
        for (int k = 0; k < head; k++) vRing.pollFirst();
    }

    private void write(boolean video, Pkt p) {
        int track = video ? vTrack : aTrack;
        if (track < 0 || p.pts < t0) return;
        MediaCodec.BufferInfo bi = new MediaCodec.BufferInfo();
        bi.set(0, p.data.length, p.pts - t0, p.key ? MediaCodec.BUFFER_FLAG_KEY_FRAME : 0);
        try {
            mux.writeSampleData(track, ByteBuffer.wrap(p.data), bi);
        } catch (Exception e) {
            Log.w(TAG, "write: " + e);
        }
    }

    private static byte[] copy(ByteBuffer b, MediaCodec.BufferInfo bi) {
        byte[] d = new byte[bi.size];
        b.position(bi.offset);
        b.limit(bi.offset + bi.size);
        b.get(d);
        return d;
    }

    private static void join(Thread t) {
        if (t == null) return;
        try { t.join(1500); } catch (InterruptedException ignored) { }
    }
}
