-------------------------- MODULE ClientPageBudget --------------------------
EXTENDS Naturals
CONSTANT Fixed
VARIABLES remaining, done, tick
vars == <<remaining, done, tick>>
\* Abstract an endless stream of full pages. The original page counter grows
\* forever; its value affects neither the loop condition nor termination.
Init == /\ remaining = 3 /\ done = FALSE /\ tick = FALSE
More == /\ ~done /\ tick' = ~tick
        /\ remaining' = IF Fixed THEN remaining - 1 ELSE remaining
        /\ done' = (Fixed /\ remaining = 1)
Spec == Init /\ [][More]_vars /\ WF_vars(More)
Termination == <>done
=============================================================================
