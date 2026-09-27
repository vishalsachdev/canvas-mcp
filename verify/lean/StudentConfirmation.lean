import Confirmation

/- Student submissions additionally deduplicate identical fingerprint/attempt
   across distinct preview nonces. This is a second machine: one fingerprint's
   claim plus its active owner, not another implementation of token crypto. -/
namespace StudentConfirmation
structure State where
  now : Nat
  deadline : Nat
  claimed : Bool
  active : Nat
  deriving DecidableEq, Repr

def initial : State := ⟨0, 0, false, 0⟩
def purge (s : State) : State :=
  if s.deadline < s.now ∧ s.active = 0 then {s with claimed := false} else s

def reserve (ttl : Nat) (s : State) : State × Bool :=
  let clean := purge s
  if clean.claimed then (clean, false)
  else ({clean with claimed := true, active := clean.active + 1, deadline := clean.now + ttl}, true)

inductive Step (ttl : Nat) : State → State → Prop where
  | claim (s) : Step ttl s (reserve ttl s).1
  | release (s) (owner : s.active > 0) :
      Step ttl s {s with claimed := false, active := s.active - 1}
  | finish (s) (owner : s.active > 0) :
      Step ttl s {s with claimed := true, active := s.active - 1, deadline := s.now + ttl}
  | clock (s) (wall elapsed : Nat) :
      Step ttl s {s with now := max (s.now + elapsed) wall}
  | cleanup (s) : Step ttl s (purge s)

def Safe (s : State) : Prop := s.active ≤ 1 ∧ (s.active > 0 → s.claimed = true)

theorem purge_safe {s} (h : Safe s) : Safe (purge s) := by
  unfold purge
  split <;> simp_all [Safe]

theorem purge_preserves_active (s) : (purge s).active = s.active := by
  unfold purge
  split <;> rfl

theorem inflight_cannot_expire {ttl s} (h : Safe s) (active : s.active > 0) :
    purge s = s ∧ (reserve ttl s).2 = false := by
  have hn : s.active ≠ 0 := by omega
  have hc := h.2 active
  simp [purge, hn, reserve, hc]

theorem step_safe {ttl s t} (hs : Safe s) (h : Step ttl s t) : Safe t := by
  cases h with
  | claim =>
      have hp := purge_safe hs
      unfold reserve
      dsimp only
      split
      · exact hp
      · simp_all [Safe]
  | release owner => simp_all [Safe]; omega
  | finish owner => simp_all [Safe]; omega
  | clock wall elapsed => exact hs
  | cleanup => exact purge_safe hs

inductive Reachable (ttl : Nat) : State → Prop where
  | init : Reachable ttl initial
  | next {s t} : Reachable ttl s → Step ttl s t → Reachable ttl t

theorem reachable_safe {ttl s} (h : Reachable ttl s) : Safe s := by
  induction h with
  | init => simp [Safe, initial]
  | next _ step ih => exact step_safe ih step

theorem one_active_submission {ttl s} (h : Reachable ttl s) : s.active ≤ 1 :=
  (reachable_safe h).1

-- The exact shared token machine is reused by the Python workflow. Its
-- authorization decision is further restricted by the fingerprint claim above.
-- This function projects only the decision; rejected-token burn transitions
-- remain those of Confirmation.check/confirm, which runs before this filter.
def authorize (expiry bound requested : Nat) (token : Confirmation.State) (claim : State) :=
  if (purge claim).claimed then none
  else (Confirmation.confirm expiry bound requested token).2

theorem authorized_payload_bound {expiry bound requested token claim target}
    (h : (authorize expiry bound requested token claim) = some target) : target = bound := by
  unfold authorize at h
  split at h
  · simp at h
  · exact Confirmation.authorized_target_is_bound h

theorem expired_denied {expiry bound requested token claim} (h : expiry < token.now) :
    (authorize expiry bound requested token claim) = none := by
  unfold authorize
  split
  · rfl
  · exact Confirmation.expired_confirm_denied h

namespace Original
-- Original cleanup ignored active owners. A second nonce at the same attempt
-- could claim after TTL, while the first POST was still awaiting a response.
def purge (s : State) : State :=
  if s.deadline < s.now then {s with claimed := false} else s

def reserve (s : State) : State :=
  let clean := purge s
  if clean.claimed then clean else {clean with claimed := true, active := clean.active + 1}

theorem expiry_admits_second_owner : (reserve ⟨301, 300, true, 1⟩).active = 2 := by decide
-- The old fingerprint MAC did not record a failed mismatch at all.
def mismatch (spent : Bool) : Bool := spent
theorem mismatch_leaves_unspent : mismatch false = false := rfl
end Original
#print axioms reachable_safe
#print axioms authorized_payload_bound
#print axioms expired_denied
end StudentConfirmation
