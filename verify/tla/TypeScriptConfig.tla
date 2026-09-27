------------------------- MODULE TypeScriptConfig -------------------------
EXTENDS Naturals
CONSTANT Fixed
VARIABLES globalConfig, saved, page, sentWith, changed
vars == <<globalConfig, saved, page, sentWith, changed>>
Init == /\ globalConfig = 1 /\ saved = 1 /\ page = 0
        /\ sentWith = 1 /\ changed = FALSE
\* Reinitialize while a traversal is suspended between two full pages.
Reinitialize == /\ page = 1 /\ ~changed
                /\ globalConfig' = 2 /\ changed' = TRUE
                /\ UNCHANGED <<saved, page, sentWith>>
Fetch == /\ page < 2
         /\ page' = page + 1
         /\ sentWith' = IF Fixed THEN saved ELSE globalConfig
         /\ UNCHANGED <<globalConfig, saved, changed>>
Spec == Init /\ [][Reinitialize \/ Fetch]_vars
CredentialBound == sentWith = saved
=============================================================================
