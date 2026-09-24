------------------------------- MODULE Clock -------------------------------
EXTENDS Naturals
CONSTANTS Snapshot, HighWater, CrossOnly
VARIABLES now, spent, redemptions, expiredSuccess
vars == <<now, spent, redemptions, expiredSuccess>>
Expiry == 1
Max(a,b) == IF a >= b THEN a ELSE b
Init == /\ now = 0 /\ spent = FALSE
        /\ redemptions = 0 /\ expiredSuccess = FALSE
Observe(raw) == /\ raw \in 0..2 /\ (~CrossOnly \/ raw >= now)
                /\ now' = IF HighWater THEN Max(now, raw) ELSE raw
                /\ spent' = IF now' > Expiry THEN FALSE ELSE spent
                /\ UNCHANGED <<redemptions, expiredSuccess>>
\* One synchronous Python call; time can advance between its clock reads.
Reserve(purgeTime) ==
    /\ purgeTime \in now..2
    /\ (~Snapshot \/ purgeTime = now)
    /\ now <= Expiry
    /\ ~(spent /\ purgeTime <= Expiry)
    /\ now' = purgeTime /\ spent' = TRUE
    /\ redemptions' = redemptions + 1
    /\ expiredSuccess' = (expiredSuccess \/ (purgeTime > Expiry))
Next == (\E raw \in 0..2 : Observe(raw)) \/
        (\E t \in 0..2 : Reserve(t))
Spec == Init /\ [][Next]_vars
NoDoubleRedeem == redemptions <= 1
NoExpiredSuccess == ~expiredSuccess
=============================================================================
