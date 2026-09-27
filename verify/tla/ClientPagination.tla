-------------------------- MODULE ClientPagination --------------------------
EXTENDS Naturals, Sequences, FiniteSets
CONSTANTS Callers, Fixed, Cycle
VARIABLES cursor, pages, phase
vars == <<cursor, pages, phase>>
Successor(p) == IF Cycle THEN 1 ELSE IF p = 1 THEN 2 ELSE 0
Init == /\ cursor = [c \in Callers |-> 1]
        /\ pages = [c \in Callers |-> <<>>]
        /\ phase = [c \in Callers |-> "active"]
Seen(c) == {pages[c][i] : i \in 1..Len(pages[c])}
Fetch(c) == /\ phase[c] = "active"
    /\ IF cursor[c] \in Seen(c) \/ Len(pages[c]) = 3
       THEN /\ phase' = [phase EXCEPT ![c] = "error"]
            /\ UNCHANGED <<cursor, pages>>
       ELSE /\ pages' = [pages EXCEPT ![c] = Append(@, cursor[c])]
            /\ cursor' = [cursor EXCEPT ![c] = Successor(@)]
            \* Original stops on a short body despite a next link.
            /\ phase' = [phase EXCEPT ![c] = IF ~Fixed \/ cursor'[c] = 0 THEN "done" ELSE "active"]
Next == \E c \in Callers : Fetch(c)
Spec == Init /\ [][Next]_vars /\ WF_vars(Next)
NoDuplicate == \A c \in Callers : Len(pages[c]) = Cardinality(Seen(c))
NoSkippedSuccessor == \A c \in Callers : phase[c] = "done" => cursor[c] = 0
Termination == <> (\A c \in Callers : phase[c] # "active")
=============================================================================
