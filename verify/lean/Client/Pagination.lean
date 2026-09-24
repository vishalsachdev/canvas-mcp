import Std
namespace Client.Pagination
-- URLs are opaque page identities. Identity and successor come from the real
-- HTTP response; this does not prove server-side snapshot consistency.
structure State where
  visited : List Nat
  cursor : Option Nat
  left : Nat

def initial (limit first : Nat) : State := ⟨[], some first, limit⟩

-- Cycle/budget failure is terminal error, not successful partial data.
-- An admitted fetch is the sole progress step. The source for-loop imposes
-- its remaining budget even on an infinite chain of unique next links.
inductive Step (next : Nat → Option Nat) : State → State → Prop where
  | fetch {s p} (cursor : s.cursor = some p) (budget : 0 < s.left)
      (fresh : p ∉ s.visited) :
      Step next s ⟨p :: s.visited, next p, s.left - 1⟩

inductive Reachable (next : Nat → Option Nat) (limit first : Nat) : State → Prop where
  | init : Reachable next limit first (initial limit first)
  | step {s t} : Reachable next limit first s → Step next s t → Reachable next limit first t

theorem no_duplicate_page {next limit first s} (h : Reachable next limit first s) :
    s.visited.Nodup := by
  induction h with
  | init => simp [initial]
  | step _ st ih =>
      cases st with
      | fetch cursor budget fresh => exact List.nodup_cons.mpr ⟨fresh, ih⟩

theorem budget_conserved {next limit first s} (h : Reachable next limit first s) :
    s.visited.length + s.left = limit := by
  induction h with
  | init => simp [initial]
  | step _ st ih => cases st; simp_all; omega

theorem finite_fetch_bound {next limit first s} (h : Reachable next limit first s) :
    s.visited.length ≤ limit := by
  have := budget_conserved h
  omega

theorem termination_variant {next s t} (h : Step next s t) : t.left < s.left := by
  cases h <;> simp <;> omega

theorem follows_server_successor {next s t p} (h : Step next s t)
    (cursor : s.cursor = some p) : t.cursor = next p := by
  cases h <;> simp_all

-- Original length-based decision can terminate despite a successor.
def originalContinue (received requested : Nat) : Bool := received ≥ requested

theorem original_short_page_skips_successor : originalContinue 1 100 = false := by decide
#print axioms no_duplicate_page
#print axioms budget_conserved
#print axioms follows_server_successor
end Client.Pagination
