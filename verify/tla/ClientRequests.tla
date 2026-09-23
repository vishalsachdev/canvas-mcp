--------------------------- MODULE ClientRequests ---------------------------
EXTENDS Naturals, FiniteSets
CONSTANTS Callers, Cap, Fixed
VARIABLES pc, attempts, closed
vars == <<pc, attempts, closed>>
Holders == {c \in Callers : pc[c] \in {"running", "backoff", "finish"}}
Init == /\ pc = [c \in Callers |-> "queued"]
        /\ attempts = [c \in Callers |-> 0]
        /\ closed = [c \in Callers |-> FALSE]
Acquire(c) == /\ pc[c] = "queued" /\ Cardinality(Holders) < Cap
              /\ pc' = [pc EXCEPT ![c] = "running"]
              /\ UNCHANGED <<attempts, closed>>
Attempt(c) == /\ pc[c] = "running" /\ attempts[c] < 4
              /\ attempts' = [attempts EXCEPT ![c] = @ + 1]
              /\ pc' = [pc EXCEPT ![c] = IF attempts'[c] = 4 THEN "finish" ELSE "backoff"]
              /\ UNCHANGED closed
Wake(c) == /\ pc[c] = "backoff"
           /\ pc' = [pc EXCEPT ![c] = "running"]
           /\ UNCHANGED <<attempts, closed>>
Finish(c) == /\ pc[c] = "finish"
             /\ pc' = [pc EXCEPT ![c] = "done"]
             /\ closed' = [closed EXCEPT ![c] = TRUE]
             /\ UNCHANGED attempts
Cancel(c) == /\ pc[c] # "done"
             /\ pc' = [pc EXCEPT ![c] = "done"]
             /\ closed' = [closed EXCEPT ![c] = (Fixed \/ pc[c] # "queued")]
             /\ UNCHANGED attempts
Next == \E c \in Callers : Acquire(c) \/ Attempt(c) \/ Wake(c) \/ Finish(c) \/ Cancel(c)
Spec == Init /\ [][Next]_vars
CapRespected == Cardinality(Holders) <= Cap
RetryBound == \A c \in Callers : attempts[c] <= 4
OwnedClientClosed == \A c \in Callers : pc[c] = "done" => closed[c]
=============================================================================
