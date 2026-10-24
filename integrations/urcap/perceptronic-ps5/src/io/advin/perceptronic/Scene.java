package io.advin.perceptronic;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * What the camera computer found in one picture ({@code GET /api/pick/scene}): the parts it
 * would pick, numbered in pick order, with their outlines in picture pixels, and everything
 * else it saw with why not. Parsed from the reply's JSON with no UR API.
 */
final class Scene {
    static final class Part {
        final int order; // 1..; 0: not going to be picked
        final int[][] corners; // 4 × (u, v) picture pixels
        final int u;
        final int v;
        final int lengthMm;
        final int widthMm;
        final int heightMm;
        final String why; // null: pickable
        final boolean near; // nearly the part (the right size but out of reach, a little off the size)

        Part(int order, int[][] corners, int u, int v, int lengthMm, int widthMm, int heightMm, String why,
                boolean near) {
            this.order = order;
            this.corners = corners;
            this.u = u;
            this.v = v;
            this.lengthMm = lengthMm;
            this.widthMm = widthMm;
            this.heightMm = heightMm;
            this.why = why;
            this.near = near;
        }

        String size() {
            return lengthMm + " × " + widthMm + " × " + heightMm + " mm";
        }
    }

    final int width;
    final int height;
    final List<Part> parts;
    final List<Part> rejected;
    final String surface; // "fitted" / "taught"
    final double offsetMm;
    final boolean baseFrame;
    final String reason;
    final List<String> notes;
    /**
     * The program is running (0.10.1, Nick 2026-10-08: "disable errors while it's not actually in a
     * measurement feedback state"): the camera computer judged nothing — what is here is the
     * program's own last measurement, and the picture carries no banner.
     */
    final boolean quiet;

    /** What the picture draws: the candidates that are nearly the part and are not being picked. */
    List<Part> nearMisses() {
        List<Part> out = new ArrayList<Part>();
        for (Part p : rejected) {
            if (p.near) out.add(p);
        }
        return out;
    }

    /**
     * What the operator tapped at picture pixel ({@code u}, {@code v}): the candidate — picked or
     * not, whatever its size — whose outline holds it, else the one whose centre is nearest within
     * {@code reach} pixels; null when nothing is there. The Part step's tap to teach (0.9.0).
     */
    Part at(int u, int v, int reach) {
        List<Part> all = new ArrayList<Part>(parts);
        all.addAll(rejected);
        Part nearest = null;
        long best = (long) reach * reach;
        for (Part p : all) {
            java.awt.Polygon poly = new java.awt.Polygon();
            for (int[] c : p.corners) poly.addPoint(c[0], c[1]);
            if (poly.contains(u, v)) return p;
            long d = (long) (p.u - u) * (p.u - u) + (long) (p.v - v) * (p.v - v);
            if (d <= best) {
                best = d;
                nearest = p;
            }
        }
        return nearest;
    }

    /**
     * Across the top of the picture when nothing will be picked (Nick, 2026-10-06: a node left at
     * its default 110 × 50 × 30 saw 110 × 70 × 30 boxes and said "2 parts touching?"): the size to
     * check, what was seen instead (the first near miss, with why), and the camera computer's
     * notes. Null when a part is found, or when nothing at all is in view and there is no note.
     * {@code part}: {@link PickScreen#sizeWords}. The same words as the PolyScope X node's
     * sceneBanner.
     */
    String banner(String part) {
        if (quiet || !parts.isEmpty()) return null;
        List<Part> near = nearMisses();
        String text;
        if (!near.isEmpty()) {
            Part r = near.get(0);
            String size = r.lengthMm > 0 || r.widthMm > 0 || r.heightMm > 0
                    ? " " + r.lengthMm + " × " + r.widthMm + " × " + r.heightMm + " mm" : "";
            String why = r.why != null ? " (" + r.why + ")" : "";
            String more = near.size() > 1 ? " and " + (near.size() - 1) + " more" : "";
            text = "No part of " + part + " in view — check the part size under Part. Seen instead:" + size + why
                    + more;
        } else if (!rejected.isEmpty()) {
            text = "Nothing like a part of " + part + " in view — check the part size under Part";
        } else {
            return notes.isEmpty() ? null : join(notes);
        }
        return notes.isEmpty() ? text : text + " · " + join(notes);
    }

    private static String join(List<String> xs) {
        StringBuilder b = new StringBuilder();
        for (String x : xs) {
            if (x == null || x.isEmpty()) continue;
            if (b.length() > 0) b.append(" · ");
            b.append(x);
        }
        return b.toString();
    }

    /** One line for the screen's status: how many parts will be picked, how many nearly. */
    String summary() {
        int near = nearMisses().size();
        if (quiet) {
            return parts.isEmpty() && near == 0 ? "program running · the picture is measured only where the program asks"
                    : "program running · last measured: " + parts.size() + (parts.size() == 1 ? " part" : " parts")
                            + " to pick";
        }
        if (parts.isEmpty() && near == 0) return "no part in view";
        String s = parts.size() + (parts.size() == 1 ? " part" : " parts") + " to pick";
        return near == 0 ? s : s + " · " + near + " not (yellow, with why)";
    }

    Scene(int width, int height, List<Part> parts, List<Part> rejected, String surface, double offsetMm,
            boolean baseFrame, String reason, List<String> notes, boolean quiet) {
        this.quiet = quiet;
        this.width = width;
        this.height = height;
        this.parts = parts;
        this.rejected = rejected;
        this.surface = surface;
        this.offsetMm = offsetMm;
        this.baseFrame = baseFrame;
        this.reason = reason;
        this.notes = notes;
    }

    static Scene empty() {
        List<Part> none = Collections.emptyList();
        return new Scene(0, 0, none, none, null, 0, false, null, Collections.<String>emptyList(), false);
    }

    /** The reply's JSON object → a Scene; missing or malformed pieces are left out, never thrown. */
    static Scene parse(Map<String, Object> o) {
        if (o != null && Boolean.TRUE.equals(o.get("quiet"))) {
            Object last = o.get("last");
            Scene seen = last instanceof Map ? parse(cast(last)) : empty();
            return new Scene(seen.width, seen.height, seen.parts, seen.rejected, seen.surface, seen.offsetMm,
                    seen.baseFrame, seen.reason, seen.notes, true);
        }
        if (o == null || !Boolean.TRUE.equals(o.get("ok"))) return empty();
        List<String> notes = new ArrayList<String>();
        Object ns = o.get("notes");
        if (ns instanceof List) {
            for (Object n : (List<?>) ns) {
                if (n instanceof String) notes.add((String) n);
            }
        }
        String surface = null;
        double offset = 0;
        Object s = o.get("surface");
        if (s instanceof Map) {
            Object src = ((Map<?, ?>) s).get("source");
            surface = src instanceof String ? (String) src : null;
            Object off = ((Map<?, ?>) s).get("offset_mm");
            offset = off instanceof Number ? ((Number) off).doubleValue() : 0;
        }
        Object reason = o.get("reason");
        return new Scene(integer(o.get("width")), integer(o.get("height")), parts(o.get("parts")),
                parts(o.get("rejected")), surface, offset, Boolean.TRUE.equals(o.get("base_frame")),
                reason instanceof String ? (String) reason : null, notes, false);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> cast(Object o) {
        return (Map<String, Object>) o;
    }

    private static List<Part> parts(Object xs) {
        List<Part> out = new ArrayList<Part>();
        if (!(xs instanceof List)) return out;
        for (Object x : (List<?>) xs) {
            if (!(x instanceof Map)) continue;
            Map<?, ?> m = (Map<?, ?>) x;
            int[][] c = new int[4][];
            Object cs = m.get("corners_px");
            if (!(cs instanceof List) || ((List<?>) cs).size() != 4) continue;
            boolean ok = true;
            for (int i = 0; i < 4; i++) {
                c[i] = pair(((List<?>) cs).get(i));
                if (c[i] == null) ok = false;
            }
            int[] px = pair(m.get("pixel"));
            int[] size = pair(m.get("size_mm"));
            if (!ok || px == null) continue;
            Object why = m.get("why");
            out.add(new Part(integer(m.get("order")), c, px[0], px[1], size == null ? 0 : size[0],
                    size == null ? 0 : size[1], integer(m.get("height_mm")), why instanceof String ? (String) why : null,
                    !Boolean.FALSE.equals(m.get("near")))); // a cockpit before 0.7.0 says nothing: draw it
        }
        return out;
    }

    private static int[] pair(Object xs) {
        if (!(xs instanceof List) || ((List<?>) xs).size() != 2) return null;
        Object a = ((List<?>) xs).get(0), b = ((List<?>) xs).get(1);
        if (!(a instanceof Number) || !(b instanceof Number)) return null;
        return new int[] {((Number) a).intValue(), ((Number) b).intValue()};
    }

    private static int integer(Object v) {
        return v instanceof Number ? ((Number) v).intValue() : 0;
    }
}
