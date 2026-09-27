-------------------------- MODULE GradingStride --------------------------
EXTENDS Naturals
CONSTANT Fixed
VARIABLES offset2, active, rejected
vars == <<offset2, active, rejected>>
\* Exact integer encoding of JS stride 1.5: scaled by two. slice truncates
\* each nonnegative boundary; the second batch [1.5,3) contains two jobs.
Init == /\ offset2 = 0 /\ active = 0 /\ rejected = Fixed
Admit == /\ ~rejected /\ active = 0 /\ offset2 < 8
         /\ active' = ((offset2 + 3) \div 2) - (offset2 \div 2)
         /\ offset2' = offset2 + 3
         /\ UNCHANGED rejected
Finish == /\ active > 0 /\ active' = 0 /\ UNCHANGED <<offset2, rejected>>
Spec == Init /\ [][Admit \/ Finish]_vars
CapRespected == 2 * active <= 3
=============================================================================
