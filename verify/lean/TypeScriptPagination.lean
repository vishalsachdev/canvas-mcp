import Client.Pagination
import Grading.Retry
import Std

namespace TypeScriptPagination
open Client.Pagination

-- Reuse the traversal machine, not a second copy of its invariants. URLs are
-- abstract identities; allowed abstracts the tested origin/path/userinfo/hash
-- check. Parsing URL/Link syntax remains an explicit implementation boundary.
def admit (allowed : Nat → Bool) (s : State) : Option Nat :=
  match s.cursor with
  | none => none
  | some p => if 0 < s.left ∧ p ∉ s.visited ∧ allowed p = true then some p else none

theorem admission_safe {allowed s p} (h : admit allowed s = some p) :
    s.cursor = some p ∧ 0 < s.left ∧ p ∉ s.visited ∧ allowed p = true := by
  unfold admit at h
  split at h
  · contradiction
  · split at h <;> simp_all

def commit (next : Nat → Option Nat) (s : State) (p : Nat) : State :=
  ⟨p :: s.visited, next p, s.left - 1⟩

theorem admitted_commit_refines_step {allowed next s p}
    (h : admit allowed s = some p) : Step next s (commit next s p) := by
  have hs := admission_safe h
  exact Step.fetch hs.1 hs.2.1 hs.2.2.1

theorem successful_terminal_has_no_successor {next s p}
    (h : (commit next s p).cursor = none) : next p = none := h

structure Run where
  credential : Nat
  traversal : State

def finishPage (next : Nat → Option Nat) (r : Run) (p : Nat) : Run :=
  {r with traversal := commit next r.traversal p}

theorem credential_snapshot_stable (next r p) :
    (finishPage next r p).credential = r.credential := rfl

-- An interleaved update of one caller does not alter another's cursor/config.
def updateCaller (runs : Nat → Run) (caller : Nat) (r : Run) : Nat → Run :=
  fun c => if c = caller then r else runs c

theorem other_caller_unchanged (runs caller other r) (h : other ≠ caller) :
    updateCaller runs caller r other = runs other := by simp [updateCaller, h]

theorem read_attempt_sum_bound (attempts : List Nat)
    (h : ∀ n ∈ attempts, n ≤ 4) : attempts.sum ≤ 4 * attempts.length := by
  induction attempts with
  | nil => simp
  | cons a tail ih =>
    have ha := h a (by simp)
    have ht := ih (by intro n hn; exact h n (by simp [hn]))
    simp only [List.sum_cons, List.length_cons]
    omega

theorem total_request_bound (attempts : List Nat) (limit : Nat)
    (h : ∀ n ∈ attempts, n ≤ 4) (pages : attempts.length ≤ limit) :
    attempts.sum ≤ 4 * limit := by
  have := read_attempt_sum_bound attempts h
  omega

-- Client.Pagination.reachable supplies no_duplicate_page, finite_fetch_bound,
-- termination_variant, and follows_server_successor for every admitted commit.
#print axioms admitted_commit_refines_step
#print axioms other_caller_unchanged
#print axioms total_request_bound
end TypeScriptPagination
