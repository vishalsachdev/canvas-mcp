-------------------------- MODULE GradingRedirect --------------------------
EXTENDS Naturals
CONSTANT Fixed
VARIABLES pc, commits
vars == <<pc, commits>>
Init == /\ pc = "send" /\ commits = 0
Apply == /\ pc = "send" /\ commits' = commits + 1 /\ pc' = "response"
\* Original fetch follows a write-preserving redirect; the first two requests
\* already refute safety. Fixed redirect:error terminates on the response.
Redirect == /\ pc = "response"
            /\ pc' = IF Fixed \/ commits = 2 THEN "done" ELSE "send"
            /\ UNCHANGED commits
Spec == Init /\ [][Apply \/ Redirect]_vars
OneWrite == commits <= 1
=============================================================================
