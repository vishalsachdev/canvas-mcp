------------------------- MODULE StudentClaims -------------------------
EXTENDS Naturals, FiniteSets
CONSTANT Fixed
VARIABLES now, deadline, claimed, phase
vars == <<now, deadline, claimed, phase>>
Callers == {1, 2}
Active == {c \in Callers : phase[c] = "active"}
Init == /\ now = 0 /\ deadline = 1 /\ claimed = FALSE
        /\ phase = [c \in Callers |-> "idle"]
\* Each idle caller can hold a fresh, live preview for this same fingerprint.
Confirm(c) == /\ phase[c] = "idle" /\ ~claimed
              /\ claimed' = TRUE
              /\ phase' = [phase EXCEPT ![c] = "active"]
              /\ deadline' = now + 1
              /\ UNCHANGED now
Clock == /\ now = 0 /\ now' = 2
         /\ UNCHANGED <<deadline, claimed, phase>>
Purge == /\ deadline < now /\ claimed
         /\ (~Fixed \/ Active = {})
         /\ claimed' = FALSE
         /\ UNCHANGED <<now, deadline, phase>>
Finish(c) == /\ phase[c] = "active"
             /\ phase' = [phase EXCEPT ![c] = "done"]
             /\ deadline' = IF Fixed THEN now + 1 ELSE deadline
             /\ claimed' = TRUE
             /\ UNCHANGED now
Release(c) == /\ phase[c] = "active"
              /\ phase' = [phase EXCEPT ![c] = "done"]
              /\ claimed' = FALSE
              /\ UNCHANGED <<now, deadline>>
Spec == Init /\ [][Clock \/ Purge \/ (\E c \in Callers : Confirm(c) \/ Finish(c) \/ Release(c))]_vars
OneActive == Cardinality(Active) <= 1
ActiveClaimRetained == Active # {} => claimed
=============================================================================
