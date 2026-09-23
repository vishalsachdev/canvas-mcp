-------------------------- MODULE Confirmation --------------------------
EXTENDS Naturals, FiniteSets
CONSTANTS Callers, FixBurn
VARIABLES pc, held, burned, burnedEver, writes, replay
vars == <<pc, held, burned, burnedEver, writes, replay>>
Init == /\ pc = [c \in Callers |-> "idle"]
        /\ held = FALSE /\ burned = FALSE /\ burnedEver = FALSE
        /\ writes = 0 /\ replay = FALSE
Check(c) == /\ pc[c] = "idle" /\ ~held
            /\ pc' = [pc EXCEPT ![c] = "checked"]
            /\ UNCHANGED <<held, burned, burnedEver, writes, replay>>
Reserve(c) == /\ pc[c] = "checked" /\ ~held
              /\ pc' = [pc EXCEPT ![c] = "inflight"] /\ held' = TRUE
              /\ replay' = (replay \/ burnedEver)
              /\ UNCHANGED <<burned, burnedEver, writes>>
Reject(c) == /\ pc[c] = "checked" /\ held
             /\ pc' = [pc EXCEPT ![c] = "idle"]
             /\ UNCHANGED <<held, burned, burnedEver, writes, replay>>
Mismatch(c) == /\ pc[c] = "idle"
               /\ held' = TRUE /\ burned' = FixBurn /\ burnedEver' = TRUE
               /\ UNCHANGED <<pc, writes, replay>>
Release(c) == /\ pc[c] = "inflight"
              /\ pc' = [pc EXCEPT ![c] = "idle"]
              /\ held' = burned
              /\ UNCHANGED <<burned, burnedEver, writes, replay>>
Write(c) == /\ pc[c] = "inflight"
            /\ pc' = [pc EXCEPT ![c] = "done"] /\ writes' = writes + 1
            /\ UNCHANGED <<held, burned, burnedEver, replay>>
Next == \E c \in Callers : Check(c) \/ Reserve(c) \/ Reject(c)
                          \/ Mismatch(c) \/ Release(c) \/ Write(c)
Spec == Init /\ [][Next]_vars
NoDoubleWrite == writes <= 1
NoConcurrent == Cardinality({c \in Callers : pc[c] = "inflight"}) <= 1
NoBurnReplay == ~replay
=============================================================================
