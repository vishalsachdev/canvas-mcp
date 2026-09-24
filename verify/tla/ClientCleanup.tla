---------------------------- MODULE ClientCleanup ----------------------------
EXTENDS Naturals
CONSTANT Fixed
VARIABLES cache, phase, replaced
vars == <<cache, phase, replaced>>
Init == /\ cache = 1 /\ phase = "idle" /\ replaced = FALSE
Start == /\ phase = "idle" /\ phase' = "waiting"
         /\ cache' = IF Fixed THEN 0 ELSE cache
         /\ UNCHANGED replaced
Replace == /\ phase = "waiting" /\ ~replaced
           /\ cache' = 2 /\ replaced' = TRUE /\ UNCHANGED phase
Finish == /\ phase = "waiting" /\ phase' = "done"
          /\ cache' = IF Fixed THEN cache ELSE 0
          /\ UNCHANGED replaced
Next == Start \/ Replace \/ Finish
Spec == Init /\ [][Next]_vars
ReplacementPreserved == replaced => cache = 2
=============================================================================
