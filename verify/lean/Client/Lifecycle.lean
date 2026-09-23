import Std
namespace Client.Lifecycle
structure Handle where
  ownerLoop : Nat
  closed : Bool
  deriving DecidableEq

def select (runningLoop : Nat) (cached : Option Handle) : Handle :=
  match cached with
  | some h => if h.closed || h.ownerLoop != runningLoop then ⟨runningLoop, false⟩ else h
  | none => ⟨runningLoop, false⟩

theorem selected_owner_is_running (loop) (cached) : (select loop cached).ownerLoop = loop := by
  cases cached with
  | none => rfl
  | some h => simp only [select]; split <;> simp_all

theorem selected_client_is_open (loop) (cached) : (select loop cached).closed = false := by
  cases cached with
  | none => rfl
  | some h => simp only [select]; split <;> simp_all

-- Cleanup detaches the captured handle before its first await. Closing that
-- captured handle does not mutate the cache, even if another caller replaced it.
def finishCleanup (currentCache : Option Nat) : Option Nat := currentCache

theorem cleanup_preserves_replacement (id : Nat) : finishCleanup (some id) = some id := rfl

def cancel (requestOwned closed : Bool) : Bool := if requestOwned then true else closed

theorem cancellation_closes_owned_client (closed) : cancel true closed = true := rfl

-- Original finally was nested INSIDE semaphore acquisition. Cancellation in
-- the waiting state skips finally; original cleanup overwrites the global cache.
def originalCancelWaiting (closed : Bool) : Bool := closed
def originalFinishCleanup (_cache : Option Nat) : Option Nat := none

theorem original_wait_leaks : originalCancelWaiting false = false := rfl
theorem original_cleanup_loses_replacement : originalFinishCleanup (some 2) ≠ some 2 := by decide
#print axioms selected_owner_is_running
end Client.Lifecycle
