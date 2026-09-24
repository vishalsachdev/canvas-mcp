------------------------- MODULE ReminderReceipt -------------------------
EXTENDS Naturals
CONSTANT Fixed
VARIABLES started, applied, done, reportsNoSend, spent
vars == <<started, applied, done, reportsNoSend, spent>>
Init == /\ started = FALSE /\ applied = FALSE /\ done = FALSE
        /\ reportsNoSend = FALSE /\ spent = FALSE
Send == /\ ~done /\ ~spent
        /\ started' = TRUE /\ spent' = TRUE
        /\ UNCHANGED <<applied, done, reportsNoSend>>
\* The remote server may apply before OR after a local exception/lost reply.
Apply == /\ started /\ ~applied /\ applied' = TRUE
         /\ UNCHANGED <<started, done, reportsNoSend, spent>>
Exception == /\ ~done /\ done' = TRUE
             /\ reportsNoSend' = IF Fixed THEN ~started ELSE TRUE
             /\ UNCHANGED <<started, applied, spent>>
Spec == Init /\ [][Send \/ Apply \/ Exception]_vars
NoFalseUnsent == reportsNoSend => ~applied
ClaimRetained == started => spent
=============================================================================
