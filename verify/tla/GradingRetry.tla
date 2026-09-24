-------------------------- MODULE GradingRetry --------------------------
EXTENDS Naturals
CONSTANTS Fixed, Write
VARIABLES pc, attempts, commits
vars == <<pc, attempts, commits>>
Init == /\ pc = "ready" /\ attempts = 0 /\ commits = 0
Dispatch == /\ pc = "ready" /\ attempts < 4
            /\ attempts' = attempts + 1
            /\ pc' = "remote"
            /\ UNCHANGED commits
\* Each request may apply once, even if no successful response is received.
Remote == /\ pc = "remote"
          /\ commits' \in IF Write THEN {commits, commits + 1} ELSE {commits}
          /\ pc' = "response"
          /\ UNCHANGED attempts
Response == /\ pc = "response"
            /\ pc' \in IF attempts < 4 /\ (~Fixed \/ ~Write)
                       THEN {"done", "backoff"} ELSE {"done"}
            /\ UNCHANGED <<attempts, commits>>
Wake == /\ pc = "backoff" /\ pc' = "ready"
        /\ UNCHANGED <<attempts, commits>>
Next == Dispatch \/ Remote \/ Response \/ Wake
Spec == Init /\ [][Next]_vars /\ WF_vars(Next)
OneWrite == commits <= 1
AttemptsBound == attempts <= (IF Write /\ Fixed THEN 1 ELSE 4)
Termination == <>(pc = "done")
=============================================================================
