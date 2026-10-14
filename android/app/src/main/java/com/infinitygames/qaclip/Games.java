package com.infinitygames.qaclip;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONArray;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Offline-first game names; the uploader merges them with the paired Mac. */
final class Games {
    private static SharedPreferences prefs(Context c) { return c.getSharedPreferences("qaclip", 0); }
    static synchronized List<String> list(Context c) {
        List<String> result = new ArrayList<>(prefs(c).getStringSet("games", new HashSet<>()));
        result.sort(String.CASE_INSENSITIVE_ORDER);
        return result;
    }
    static String selected(Context c) { return prefs(c).getString("game", ""); }
    static void select(Context c, String name) { prefs(c).edit().putString("game", name).apply(); }
    static synchronized String add(Context c, String value) {
        String name = value.trim().replaceAll("\\s+", " ");
        if (name.isEmpty() || name.length() > 80) throw new IllegalArgumentException("Use 1–80 characters");
        for (int i = 0; i < name.length(); i++) if (Character.isISOControl(name.charAt(i))) throw new IllegalArgumentException("Use a plain game name");
        Set<String> all = new HashSet<>(list(c));
        for (String n : all) if (n.equalsIgnoreCase(name)) { select(c, n); return n; }
        all.add(name);
        Set<String> pending = new HashSet<>(prefs(c).getStringSet("pendingGames", new HashSet<>()));
        pending.add(name);
        prefs(c).edit().putStringSet("games", all).putStringSet("pendingGames", pending).putString("game", name).apply();
        return name;
    }
    static synchronized Set<String> pending(Context c) {
        return new HashSet<>(prefs(c).getStringSet("pendingGames", new HashSet<>()));
    }
    static synchronized void received(Context c, JSONArray names, Set<String> sent) {
        Set<String> pending = pending(c);
        pending.removeAll(sent);
        Set<String> all = new HashSet<>(pending);
        String selected = selected(c);
        for (int i = 0; i < names.length(); i++) {
            String name = names.optString(i);
            if (!name.isEmpty()) all.add(name);
            if (name.equalsIgnoreCase(selected)) selected = name;
        }
        if (!selected.isEmpty()) all.add(selected);
        prefs(c).edit().putStringSet("games", all).putStringSet("pendingGames", pending).putString("game", selected).apply();
    }
}
