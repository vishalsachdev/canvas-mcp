import Confirmation
import Std

namespace ConfirmedWorkflow
/- After successful guard admission, each tool retains the exact resolved plan.
   Targets stand for full request identities (endpoint/recipient set/payload),
   not just a displayed name. Bulk tools consume a sequential prefix; an error
   can stop execution, but cannot add a target or restart the plan. -/
structure PlanState where
  approved : List Nat
  dispatched : List Nat
  remaining : List Nat
  stopped : Bool
  deriving DecidableEq, Repr

def initialPlan (plan : List Nat) : PlanState := ⟨plan, [], plan, false⟩
def authorizePlan (bound requested : List Nat) : Option PlanState :=
  if requested = bound then some (initialPlan requested) else none

theorem plan_is_bound {bound requested s} (h : authorizePlan bound requested = some s) :
    s.approved = bound := by
  unfold authorizePlan at h
  split at h
  · simp only [Option.some.injEq] at h
    cases h
    simp_all [initialPlan]
  · simp at h

inductive PlanStep : PlanState → PlanState → Prop where
  | dispatch (s target rest) (running : s.stopped = false)
      (next : s.remaining = target :: rest) :
      PlanStep s {s with dispatched := s.dispatched ++ [target], remaining := rest}
  | stop (s) : PlanStep s {s with stopped := true}

def PlanSafe (s : PlanState) : Prop := s.approved = s.dispatched ++ s.remaining

theorem plan_step_safe {s t} (hs : PlanSafe s) (h : PlanStep s t) : PlanSafe t := by
  cases h with
  | dispatch target rest running next => simpa [PlanSafe, next, List.append_assoc] using hs
  | stop => exact hs

inductive PlanReachable (plan : List Nat) : PlanState → Prop where
  | init : PlanReachable plan (initialPlan plan)
  | next {s t} : PlanReachable plan s → PlanStep s t → PlanReachable plan t

theorem plan_conserved {plan s} (h : PlanReachable plan s) :
    PlanSafe s ∧ s.approved = plan := by
  induction h with
  | init => simp [PlanSafe, initialPlan]
  | next _ step ih =>
      constructor
      · exact plan_step_safe ih.1 step
      · cases step <;> exact ih.2

theorem only_confirmed_targets {plan s target} (h : PlanReachable plan s)
    (sent : target ∈ s.dispatched) : target ∈ plan := by
  have hp := plan_conserved h
  rw [← hp.2, hp.1]
  exact List.mem_append_left _ sent

theorem bounded_dispatch {plan s} (h : PlanReachable plan s) :
    s.dispatched.length ≤ plan.length := by
  have hp := plan_conserved h
  have hl := congrArg List.length hp.1
  simp only [List.length_append] at hl
  rw [hp.2] at hl
  omega

/- A separate receipt machine models the reminder's exception handler. A POST
   can already have applied when its response cannot be interpreted. Only
   pre-dispatch failures or definitive no-write rejection may claim no send. -/
structure Receipt where
  started : Bool
  possibleEffect : Bool
  done : Bool
  reportsNoSend : Bool
  deriving DecidableEq, Repr

def initialReceipt : Receipt := ⟨false, false, false, false⟩
def catchFailure (s : Receipt) : Receipt :=
  {s with done := true, reportsNoSend := !s.started}

inductive ReceiptStep : Receipt → Receipt → Prop where
  | dispatch (s) (ready : s.done = false ∧ s.started = false) (effect : Bool) :
      ReceiptStep s {s with started := true, possibleEffect := effect, reportsNoSend := false}
  | definiteRejection (s) :
      ReceiptStep s {s with possibleEffect := false, done := true, reportsNoSend := true}
  | complete (s) : ReceiptStep s {s with done := true, reportsNoSend := false}
  | exception (s) : ReceiptStep s (catchFailure s)

def ReceiptSafe (s : Receipt) : Prop :=
  (s.started = false → s.possibleEffect = false) ∧
  (s.reportsNoSend = true → s.possibleEffect = false)

theorem receipt_step_safe {s t} (hs : ReceiptSafe s) (h : ReceiptStep s t) : ReceiptSafe t := by
  cases h <;> simp_all [ReceiptSafe, catchFailure]

inductive ReceiptReachable : Receipt → Prop where
  | init : ReceiptReachable initialReceipt
  | next {s t} : ReceiptReachable s → ReceiptStep s t → ReceiptReachable t

theorem no_false_unsent {s} (h : ReceiptReachable s) :
    s.reportsNoSend = true → s.possibleEffect = false := by
  have safe : ReceiptSafe s := by
    induction h with
    | init => simp [ReceiptSafe, initialReceipt]
    | next _ step ih => exact receipt_step_safe ih step
  exact safe.2

namespace Original
def catchFailure (s : Receipt) : Receipt := {s with done := true, reportsNoSend := true}
theorem applied_post_reported_unsent :
    (catchFailure ⟨true, true, false, false⟩).reportsNoSend = true ∧
    (catchFailure ⟨true, true, false, false⟩).possibleEffect = true := by decide
end Original
#print axioms plan_is_bound
#print axioms only_confirmed_targets
#print axioms bounded_dispatch
#print axioms no_false_unsent
end ConfirmedWorkflow
