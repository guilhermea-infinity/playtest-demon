package com.infinitygames.qaclip;

/** Receiver selection and queued-clip ownership, independent of Android/network APIs. */
final class MacRoute {
    final String code, id;
    MacRoute(String code, String id) { this.code = normalize(code); this.id = id == null ? "" : id; }
    static String normalize(String value) { return value == null ? "" : value.replace("-", "").replace(" ", "").toUpperCase(java.util.Locale.ROOT); }
    static boolean validCode(String value) { return normalize(value).matches("[0-9A-F]{8}"); }
    boolean accepts(String candidate) {
        return validCode(code) && candidate != null && candidate.matches("[0-9a-f]{32}")
            && candidate.substring(0, 8).equalsIgnoreCase(code) && (id.isEmpty() || id.equals(candidate));
    }
    boolean ownsClip(String clipCode, String clipId) {
        return !id.isEmpty() && code.equals(normalize(clipCode)) && (clipId == null || clipId.isEmpty() || id.equals(clipId));
    }
}
