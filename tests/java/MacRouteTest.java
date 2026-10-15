package com.infinitygames.qaclip;

/** Real sender policy: discovery order, old endpoints and old approvals cannot override the owner. */
public final class MacRouteTest {
    private static void check(boolean b, String reason) { if (!b) throw new AssertionError(reason); }
    public static void main(String[] args) {
        String alice="abcd1234000000000000000000000001", bob="beef5678000000000000000000000002";
        MacRoute initial=new MacRoute("", "");
        check(!initial.accepts(alice) && !initial.accepts(bob),"Unpaired phone must send nothing");
        MacRoute route=new MacRoute("ABCD-1234", alice);
        for (String candidate:new String[]{bob,"",alice,bob}) {
            check(route.accepts(candidate)==candidate.equals(alice),"Discovery must select only the paired Mac");
        }
        check(!route.accepts("abcd1234000000000000000000000099"),"Same short code cannot override pinned full identity");
        check(!route.ownsClip("BEEF-5678",bob),"Clip for coworker must remain queued");
        check(route.ownsClip("ABCD1234",alice),"Owner clip may send");
        check(route.ownsClip("ABCD1234",""),"Explicitly adopted legacy clip may bind to this Mac");
        check(!route.ownsClip("",""),"Unaddressed clip must not be silently adopted");
        MacRoute switched=new MacRoute("BEEF-5678",bob);
        check(!switched.ownsClip("ABCD1234",alice),"Switching laptops must not reroute queued clips");
        check(new MacRoute("ABCD1234","").accepts(alice),"Code can establish the initial full identity");
        check(!MacRoute.validCode("bad") && !MacRoute.validCode("GGGG-0000"),"Reject malformed codes");
        System.out.println("Mac routing isolation checks passed");
    }
}
