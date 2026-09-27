import Std
namespace Client.Requests
-- One fixed event loop and fixed positive configured capacity. Waiting tasks
-- own no permit; a request retains its permit over every 429 backoff/retry.
inductive PermitStep (cap : Nat) : Nat → Nat → Prop where
  | acquire {n} : n < cap → PermitStep cap n (n+1)
  | release {n} : 0 < n → PermitStep cap n (n-1)
  | waitOrRetry {n} : PermitStep cap n n

inductive Reachable (cap : Nat) : Nat → Prop where
  | init : Reachable cap 0
  | next {n m} : Reachable cap n → PermitStep cap n m → Reachable cap m

theorem cap_preserved {cap n m} (h : n ≤ cap) (step : PermitStep cap n m) : m ≤ cap := by
  cases step <;> omega

theorem semaphore_bound {cap n} (h : Reachable cap n) : n ≤ cap := by
  induction h with
  | init => omega
  | next _ step ih => exact cap_preserved ih step

-- The source loops over range(MAX_RETRIES + 1). Each completed transport
-- attempt consumes one unit; network waits/sleeps must finish or be cancelled.
inductive Attempt (limit : Nat) : Nat → Nat → Prop where
  | send {n} : n < limit → Attempt limit n (n+1)

theorem attempt_bound {limit n m} (step : Attempt limit n m) : m ≤ limit := by
  cases step <;> omega

theorem retry_variant_decreases {limit n m} (step : Attempt limit n m) :
    limit - m < limit - n := by
  cases step <;> omega

theorem max_three_retries_four_attempts {n m} (step : Attempt (3+1) n m) : m ≤ 4 :=
  attempt_bound step

theorem default_backoff_total : 2 * 2^0 + 2 * 2^1 + 2 * 2^2 = 14 := by decide
#print axioms semaphore_bound
#print axioms retry_variant_decreases
end Client.Requests
