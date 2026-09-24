import Std
namespace Grading.Scheduler
-- Unique targets are validated before any grading callback. This models one
-- invocation; separate invocations intentionally permit regrading.
def preflight (users : List Nat) : Option (List Nat) :=
  if users.Nodup then some users else none

theorem admitted_unique {xs ys} (h : preflight xs = some ys) : ys.Nodup := by
  unfold preflight at h
  split at h <;> simp_all

structure State where
  queue : List Nat
  issued : List Nat
  active : Nat
  finished : Nat

def initial (users : List Nat) : State := ⟨users, [], 0, 0⟩

-- Overapproximates batch scheduling: allows a replacement job as soon as one
-- completes. Actual allSettled waits for the entire batch, a stronger barrier.
inductive Step (cap : Nat) : State → State → Prop where
  | start {s u rest} (head : s.queue = u :: rest) (room : s.active < cap) :
      Step cap s ⟨rest, u :: s.issued, s.active + 1, s.finished⟩
  | finish {s} (busy : 0 < s.active) :
      Step cap s {s with active := s.active - 1, finished := s.finished + 1}

inductive Reachable (cap : Nat) (users : List Nat) : State → Prop where
  | init : Reachable cap users (initial users)
  | step {s t} : Reachable cap users s → Step cap s t → Reachable cap users t

def Safe (cap : Nat) (s : State) : Prop :=
  (s.queue ++ s.issued).Nodup ∧ s.active ≤ cap ∧
  s.finished + s.active = s.issued.length

theorem preserved {cap s t} (h : Safe cap s) (step : Step cap s t) : Safe cap t := by
  rcases h with ⟨unique, bound, accounting⟩
  cases step with
  | start head room =>
    simp only [head, List.cons_append, List.nodup_cons] at unique
    rcases unique with ⟨fresh, tail⟩
    unfold Safe
    simp only
    constructor
    · exact (List.perm_middle).nodup_iff.mpr (List.nodup_cons.mpr ⟨fresh, tail⟩)
    · simp only [List.length_cons]; omega
  | finish busy =>
    unfold Safe
    simp only
    exact ⟨unique, by omega, by omega⟩

theorem reachable_safe {cap users s} (valid : users.Nodup)
    (h : Reachable cap users s) : Safe cap s := by
  induction h with
  | init => simp [Safe, initial, valid]
  | step _ st ih => exact preserved ih st

theorem no_duplicate_dispatch {cap users s} (valid : users.Nodup)
    (h : Reachable cap users s) : s.issued.Nodup := by
  exact (List.pairwise_append.mp (reachable_safe valid h).1).2.1

theorem in_flight_cap {cap users s} (valid : users.Nodup)
    (h : Reachable cap users s) : s.active ≤ cap := (reachable_safe valid h).2.1

theorem accounted {cap users s} (valid : users.Nodup)
    (h : Reachable cap users s) : s.finished + s.active = s.issued.length :=
  (reachable_safe valid h).2.2

-- A positive integer slice stride partitions the finite queue; TS validation
-- is required before using this natural-number abstraction.
theorem slice_partition (xs : List Nat) (cap : Nat) : xs.take cap ++ xs.drop cap = xs :=
  List.take_append_drop cap xs

theorem batch_size_bound (xs : List Nat) (cap : Nat) : (xs.take cap).length ≤ cap := by
  simp only [List.length_take]; omega

-- Actual Promise.allSettled barrier: inter-batch sleep only when all jobs end.
def maySleep (active remaining delay : Nat) : Bool :=
  active == 0 && remaining > 0 && delay > 0

theorem sleep_requires_settlement {a r d} (h : maySleep a r d = true) : a = 0 := by
  simp [maySleep] at h
  omega

theorem zero_delay_no_sleep (a r) : maySleep a r 0 = false := by simp [maySleep]
#print axioms reachable_safe
#print axioms no_duplicate_dispatch
#print axioms in_flight_cap
end Grading.Scheduler
