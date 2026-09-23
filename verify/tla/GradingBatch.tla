-------------------------- MODULE GradingBatch --------------------------
EXTENDS Naturals, Sequences, FiniteSets
CONSTANTS Duplicates, Cap, Fixed, Delay, Mutate
Users == IF Duplicates THEN <<1,1>> ELSE <<1,2,3,4>>
VARIABLES offset, pc, writes, waiting, rejected, sleeps, target
vars == <<offset, pc, writes, waiting, rejected, sleeps, target>>
Jobs == 1..Len(Users)
Targets == {Users[i] : i \in Jobs}
Unique == \A i,j \in Jobs : i # j => Users[i] # Users[j]
Init == /\ offset = 1 /\ pc = [i \in Jobs |-> "queued"]
        /\ writes = [u \in Targets |-> 0]
        /\ waiting = FALSE /\ rejected = (Fixed /\ ~Unique) /\ sleeps = 0
        /\ target = [i \in Jobs |-> Users[i]]
Active == {i \in Jobs : pc[i] \in {"callback", "request", "remote"}}
Last == IF offset + Cap - 1 < Len(Users) THEN offset + Cap - 1 ELSE Len(Users)
StartBatch == /\ ~rejected /\ ~waiting /\ Active = {} /\ offset <= Len(Users)
              /\ pc' = [i \in Jobs |-> IF i \in offset..Last THEN "callback" ELSE pc[i]]
              /\ offset' = Last + 1
              /\ UNCHANGED <<writes, waiting, rejected, sleeps, target>>
Callback(i) == /\ pc[i] = "callback"
               /\ (\E state \in {"request", "done"} : pc' = [pc EXCEPT ![i] = state])
               /\ target' = [target EXCEPT ![i] = IF Mutate /\ ~Fixed THEN 1 ELSE Users[i]]
               /\ UNCHANGED <<offset, writes, waiting, rejected, sleeps>>
Send(i) == /\ pc[i] = "request"
           /\ pc' = [pc EXCEPT ![i] = "remote"]
           /\ writes' = [writes EXCEPT ![target[i]] = @ + 1]
           /\ UNCHANGED <<offset, waiting, rejected, sleeps, target>>
Finish(i) == /\ pc[i] = "remote" /\ pc' = [pc EXCEPT ![i] = "done"]
             /\ UNCHANGED <<offset, writes, waiting, rejected, sleeps, target>>
\* The barrier and optional delay are explicit, rather than permitting the
\* next batch immediately after the last worker completes.
BatchSettled == /\ ~rejected /\ ~waiting /\ Active = {} /\ offset > 1
                /\ offset <= Len(Users)
                /\ pc[offset-1] = "done"
                /\ waiting' = TRUE
                /\ sleeps' = sleeps + (IF Delay > 0 \/ ~Fixed THEN 1 ELSE 0)
                /\ UNCHANGED <<offset, pc, writes, rejected, target>>
Wake == /\ waiting /\ waiting' = FALSE
        /\ pc' = [pc EXCEPT ![offset-1] = "settled"]
        /\ UNCHANGED <<offset, writes, rejected, sleeps, target>>
\* Admission after batch 1 requires its delay/barrier transition.
Admit == StartBatch /\ (offset = 1 \/ pc[offset-1] = "settled")
Next == Admit \/ BatchSettled \/ Wake \/ (\E i \in Jobs : Callback(i) \/ Send(i) \/ Finish(i))
Spec == Init /\ [][Next]_vars /\ WF_vars(Next)
NoDoubleGrade == \A u \in Targets : writes[u] <= 1
CapRespected == Cardinality(Active) <= Cap
DelayAfterSettlement == waiting => Active = {}
ZeroDelay == Delay = 0 => sleeps = 0
Termination == <>(rejected \/ (offset > Len(Users) /\ Active = {}))
=============================================================================
