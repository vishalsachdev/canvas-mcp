import Std
namespace Grading.Retry
-- Counts transport dispatches, not successful responses: a failed response
-- can follow a remote commit. Terminal uncertainty is not proof of no write.
inductive Method where | read | write deriving DecidableEq
structure State where
  attempts : Nat
  commits : Nat
  ready : Bool
  deriving DecidableEq

def limit : Method → Nat | .read => 4 | .write => 1
def initial : State := ⟨0, 0, true⟩

-- Dispatch and one possible remote effect. Response handling may end the
-- operation early; only reads can regain ready after an ambiguous failure.
inductive Step (m : Method) : State → State → Prop where
  | dispatch {s} (ready : s.ready = true) (budget : s.attempts < 4)
      (effect : Nat) (oneEffect : effect ≤ 1) :
      Step m s ⟨s.attempts + 1, s.commits + effect, false⟩
  | retryRead {s} (readOnly : m = .read) (pending : s.ready = false)
      (budget : s.attempts < 4) : Step m s {s with ready := true}

inductive Reachable (m : Method) : State → Prop where
  | init : Reachable m initial
  | step {s t} : Reachable m s → Step m s t → Reachable m t

-- The loop still has four slots in source. One-write safety follows from
-- the write error path never restoring ready, not from a one-slot guard.
theorem reachable_invariant {m s} (h : Reachable m s) :
    s.commits ≤ s.attempts ∧ s.attempts ≤ 4 ∧
    (m = .write → s.attempts ≤ 1 ∧ (s.ready = true → s.attempts = 0)) := by
  induction h with
  | init => simp [initial]
  | step _ st ih =>
    cases st with
    | dispatch ready budget effect oneEffect =>
      rcases ih with ⟨effects, attempts, writes⟩
      refine ⟨by simp only; omega, by simp only; omega, ?_⟩
      intro hm
      have hw := writes hm
      simp only
      constructor
      · have := hw.2 ready; omega
      · intro impossible; contradiction
    | retryRead readOnly pending budget =>
      subst m
      simpa using ih

theorem bounds {m s} (h : Reachable m s) :
    s.commits ≤ s.attempts ∧ s.attempts ≤ limit m := by
  have inv := reachable_invariant h
  cases m with
  | read => exact ⟨inv.1, inv.2.1⟩
  | write => exact ⟨inv.1, (inv.2.2 rfl).1⟩

theorem at_most_one_write {s} (h : Reachable .write s) : s.commits ≤ 1 := by
  have b := bounds h
  simp [limit] at b
  omega

theorem no_write_replay {s} (h : Reachable .write s) : s.attempts ≤ 1 :=
  (bounds h).2

theorem reads_at_most_four_attempts {s} (h : Reachable .read s) : s.attempts ≤ 4 :=
  (bounds h).2

theorem dispatch_decreases_budget {m : Method} {s : State} (h : s.attempts < limit m) :
    limit m - (s.attempts + 1) < limit m - s.attempts := by omega

-- Original policy retries a write whose first commit's response was lost.
def originalTwoCommittedAttempts : State := ⟨2, 2, false⟩
theorem original_replays : ¬ originalTwoCommittedAttempts.commits ≤ 1 := by decide
#print axioms at_most_one_write
#print axioms reads_at_most_four_attempts
end Grading.Retry
