import Std
namespace ConfirmationClaim

-- Generation abstracts Python object identity, not the signed token nonce.
structure State where
  owner : Option Nat
  next : Nat
  spent : Bool
  burned : Bool
  deriving DecidableEq

def reserve (s : State) : State :=
  if s.spent then s else
    { s with owner := some s.next, next := s.next + 1, spent := true }

def finish (s : State) (generation : Nat) (noWrite : Bool) : State :=
  if s.owner = some generation then
    { s with owner := none, spent := if noWrite && !s.burned then false else s.spent }
  else s

theorem foreign_or_stale_no_change (s : State) (g : Nat) (n : Bool)
    (h : s.owner ≠ some g) : finish s g n = s := by
  simp [finish, h]

theorem uncertain_retains_spent (s : State) (g : Nat) :
    (finish s g false).spent = s.spent := by
  simp [finish]; split <;> rfl

theorem burned_retains_spent (s : State) (g : Nat) (n : Bool)
    (h : s.burned = true) : (finish s g n).spent = s.spent := by
  simp [finish, h]; split <;> rfl

theorem release_requires_owner_and_no_write (s : State) (g : Nat) (n : Bool)
    (spent : s.spent = true) (freed : (finish s g n).spent = false) :
    s.owner = some g ∧ n = true ∧ s.burned = false := by
  unfold finish at freed
  split at freed
  · rename_i owner
    simp only at freed
    split at freed
    · rename_i safe
      simp only [Bool.and_eq_true, Bool.not_eq_true'] at safe
      exact ⟨owner, safe.1, safe.2⟩
    · simp [spent] at freed
  · simp [spent] at freed

-- Reacquisition gives a different owner; an old completion cannot release it.
theorem reacquired_owner_is_fresh (s : State) (old : Nat) (n : Bool)
    (free : s.spent = false) (fresh : old < s.next) :
    finish (reserve s) old n = reserve s := by
  apply foreign_or_stale_no_change
  simp [reserve, free]
  omega

#print axioms foreign_or_stale_no_change
#print axioms uncertain_retains_spent
#print axioms burned_retains_spent
#print axioms release_requires_owner_and_no_write
#print axioms reacquired_owner_is_fresh
end ConfirmationClaim
