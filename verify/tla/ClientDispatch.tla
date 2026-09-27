--------------------------- MODULE ClientDispatch ---------------------------
EXTENDS Naturals
CONSTANT Fixed
VARIABLES cache, closed, cleaned, dispatched, bad
vars == <<cache, closed, cleaned, dispatched, bad>>
\* Request captured handle 1, then suspended in semaphore/backoff.
Init == /\ cache = 1 /\ closed = {} /\ cleaned = FALSE
        /\ dispatched = FALSE /\ bad = FALSE
Cleanup == /\ ~cleaned /\ cleaned' = TRUE
           /\ cache' = 0 /\ closed' = {1}
           /\ UNCHANGED <<dispatched, bad>>
Dispatch == /\ ~dispatched /\ dispatched' = TRUE
            /\ LET handle == IF Fixed THEN (IF cache = 0 THEN 2 ELSE cache) ELSE 1
               IN /\ bad' = (handle \in closed)
                  /\ cache' = IF Fixed THEN handle ELSE cache
            /\ UNCHANGED <<closed, cleaned>>
Next == Cleanup \/ Dispatch
Spec == Init /\ [][Next]_vars
DispatchOpen == ~bad
=============================================================================
