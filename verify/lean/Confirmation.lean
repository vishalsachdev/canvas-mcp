import Std

/- One genuinely issued nonce, fixed expiry/fingerprint. Cryptography is
abstracted by selecting an authentic token, not proved. Time is an ordered
integer abstraction of Python clock samples. claim is absent/reserved/burned.
pending/writes/burnedEver are observer-only counters. Release is permitted
ONLY to the owner after a proven no-write outcome. Reset, threads, process
sharing and downstream HTTP retries are outside this model. -/
namespace Confirmation
structure State where
  now : Nat
  claim : Nat -- 0 absent, 1 reserved, 2 burned
  pending : Nat
  writes : Nat
  burnedEver : Nat
  deriving DecidableEq, Repr

def initial : State := ⟨0, 0, 0, 0, 0⟩
def CanReserve (expiry : Nat) (s : State) : Prop :=
  s.now ≤ expiry ∧ s.claim = 0

def CanConfirm (expiry bound requested : Nat) (s : State) : Prop :=
  requested = bound ∧ CanReserve expiry s

/- Atomic reserve has no yield between membership test and insertion.
The network operation can interleave with other callers. Mismatch burns an
existing reservation too. Cleanup and authentication share one clock sample;
Observe abstracts the high-water clock. -/
inductive Step (expiry : Nat) : State → State → Prop where
  | reserve (s) (h : CanReserve expiry s) :
      Step expiry s {s with claim := 1, pending := s.pending + 1}
  | burn (s) (live : s.now ≤ expiry) :
      Step expiry s {s with claim := 2, burnedEver := 1}
  | release (s) (owner : s.pending > 0) :
      Step expiry s {s with pending := s.pending - 1, claim := if s.claim = 1 then 0 else s.claim}
  | write (s) (owner : s.pending > 0) :
      Step expiry s {s with pending := s.pending - 1, writes := s.writes + 1}
  | observe (s) (raw elapsed : Nat) :
      Step expiry s {s with now := max (s.now + elapsed) raw, claim := if expiry < max (s.now + elapsed) raw then 0 else s.claim}
  | check (s) : Step expiry s s

def Safe (expiry : Nat) (s : State) : Prop :=
  s.writes + s.pending ≤ 1 ∧
  (s.now ≤ expiry → s.writes + s.pending > 0 → s.claim ≠ 0) ∧
  (s.now ≤ expiry → s.burnedEver = 1 → s.claim = 2)

theorem initial_safe (expiry) : Safe expiry initial := by
  simp [Safe, initial]

theorem step_preserves (expiry) {s t} (hs : Safe expiry s)
    (h : Step expiry s t) : Safe expiry t := by
  rcases hs with ⟨hcount, hclaim, hburn⟩
  cases h with
  | reserve hr =>
      rcases hr with ⟨hlive, hempty⟩
      simp only [Safe]
      have hz : s.writes + s.pending = 0 := by
        by_cases hz : s.writes + s.pending = 0
        · exact hz
        · have : s.claim ≠ 0 := hclaim hlive (by omega)
          contradiction
      have hb : s.burnedEver ≠ 1 := by
        intro hb
        have := hburn hlive hb
        omega
      dsimp at *
      omega
  | burn hlive =>
      simpa [Safe] using hcount
  | release ho =>
      simp only [Safe]
      split <;> simp_all <;> omega
  | write ho =>
      simp only [Safe]
      constructor
      · omega
      constructor
      · intro hl hp
        apply hclaim hl
        omega
      · exact hburn
  | observe raw elapsed =>
      simp only [Safe]
      split <;> simp_all <;> omega
  | check => exact ⟨hcount, hclaim, hburn⟩

inductive Reachable (expiry : Nat) : State → Prop where
  | init : Reachable expiry initial
  | next {s t} : Reachable expiry s → Step expiry s t → Reachable expiry t

theorem reachable_safe {expiry s} (h : Reachable expiry s) : Safe expiry s := by
  induction h with
  | init => exact initial_safe expiry
  | next _ step ih => exact step_preserves expiry ih step

theorem at_most_one_write {expiry s} (h : Reachable expiry s) : s.writes ≤ 1 := by
  have := (reachable_safe h).1
  omega

theorem at_most_one_inflight {expiry s} (h : Reachable expiry s) : s.pending ≤ 1 := by
  have := (reachable_safe h).1
  omega

theorem no_double_reserve {expiry s} (h : Reachable expiry s)
    (pending : s.pending > 0) : ¬ CanReserve expiry s := by
  intro ⟨live, empty⟩
  have := (reachable_safe h).2.1 live (by omega)
  contradiction

theorem mismatch_never_authorizes {expiry bound requested s}
    (different : requested ≠ bound) : ¬ CanConfirm expiry bound requested s := by
  intro h
  exact different h.1

theorem expired_never_authorizes {expiry bound requested s}
    (expired : expiry < s.now) : ¬ CanConfirm expiry bound requested s := by
  intro h
  have := h.2.1
  omega

theorem burn_blocks_future_reserve {expiry s} (h : Reachable expiry s)
    (burned : s.burnedEver = 1) : ¬ CanReserve expiry s := by
  intro ⟨live, empty⟩
  have := (reachable_safe h).2.2 live burned
  omega

theorem clock_never_decreases {expiry s t} (h : Step expiry s t) : s.now ≤ t.now := by
  cases h <;> simp <;> omega

/- Executable abstraction of redeem_confirmation, for an authentic token.
A successful result records its requested fingerprint; a mismatch burns but
cannot produce an authorization. Clock samples are Observe transitions. -/
def confirm (expiry bound requested : Nat) (s : State) : State × Option Nat :=
  if requested = bound then
    if s.now ≤ expiry ∧ s.claim = 0 then
      ({s with claim := 1, pending := s.pending + 1}, some requested)
    else (s, none)
  else
    if s.now ≤ expiry then
      ({s with claim := 2, burnedEver := 1}, none)
    else (s, none)

theorem confirm_refines_step (expiry bound requested s) :
    Step expiry s (confirm expiry bound requested s).1 := by
  unfold confirm
  split
  · split
    · rename_i h
      exact Step.reserve s h
    · exact Step.check s
  · split
    · rename_i h
      exact Step.burn s h
    · exact Step.check s

theorem authorized_target_is_bound {expiry bound requested target s}
    (h : (confirm expiry bound requested s).2 = some target) : target = bound := by
  unfold confirm at h
  split at h <;> split at h <;> simp_all

theorem expired_confirm_denied {expiry bound requested s} (h : expiry < s.now) :
    (confirm expiry bound requested s).2 = none := by
  unfold confirm
  split <;> split <;> simp_all <;> omega

theorem mismatch_burns_without_authorizing {expiry bound requested s}
    (h : requested ≠ bound) (live : s.now ≤ expiry) :
    (confirm expiry bound requested s).1.claim = 2 ∧
    (confirm expiry bound requested s).1.writes = s.writes ∧
    (confirm expiry bound requested s).2 = none := by
  simp [confirm, h, live]

-- Rollback cannot freeze TTL: each sample advances by monotonic elapsed time.
theorem sampled_clock_advances (s : State) (raw elapsed : Nat) :
    s.now + elapsed ≤ max (s.now + elapsed) raw := Nat.le_max_left _ _

namespace Original
-- The two separate time samples in the original reserve/authenticate/purge.
def reserve (expiry authTime purgeTime : Nat) (spent : Bool) : Bool × Bool :=
  if expiry < authTime then (false, spent)
  else
    let retained := spent && !(expiry < purgeTime)
    if retained then (false, retained) else (true, true)
def release (_spent : Bool) : Bool := false

theorem expiry_crossing_double_redeem : reserve 1 1 2 true = (true, true) := by decide
theorem rollback_replay : reserve 1 0 0 false = (true, true) := by decide
-- Existing reservation, failed burn, release, reverted request succeeds.
theorem release_erases_burn : reserve 1 0 0 (release true) = (true, true) := by decide
-- Intended retry semantics refute an unconditional reservation-count bound.
theorem unrestricted_at_most_once_is_false :
    (reserve 1 0 0 false).1 = true ∧
    (reserve 1 0 0 (release (reserve 1 0 0 false).2)).1 = true := by decide
end Original
#print axioms authorized_target_is_bound
#print axioms confirm_refines_step
#print axioms reachable_safe
#print axioms at_most_one_write
#print axioms burn_blocks_future_reserve
end Confirmation
