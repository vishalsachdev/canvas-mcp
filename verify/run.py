"""Run Lean proofs and TLC positive/negative controls; requires lake, Java, TLA_JAR."""

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TLA_SHA256 = "9732eea90bdc7432e618184e4bee78700460e83e988238a80151dfd6507cfa0c"


def run(command: list[str], expected_failure: str | None = None) -> None:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = result.stdout + result.stderr
    print(output, end="", flush=True)
    if expected_failure:
        marker = (expected_failure if expected_failure.startswith("Temporal")
                  else f"Invariant {expected_failure} is violated")
        if result.returncode == 0 or marker not in output:
            raise SystemExit("Expected counterexample was not reproduced")
    elif result.returncode != 0:
        raise SystemExit(result.returncode)
    if "sorryAx" in output:
        raise SystemExit("A proof depends on an unfinished proof")


def main() -> None:
    jar = Path(os.environ["TLA_JAR"]).resolve()
    if hashlib.sha256(jar.read_bytes()).hexdigest() != TLA_SHA256:
        raise SystemExit("TLC jar differs from the reviewed toolchain; see verify/README.md")
    run(["lake", "-d", "lean", "build"])
    cases = [
        ("Confirmation", "original", "NoBurnReplay"),
        ("Confirmation", "fixed", None),
        ("Clock", "clock-crossing", "NoDoubleRedeem"),
        ("Clock", "clock-rollback", "NoDoubleRedeem"),
        ("Clock", "clock-fixed", None),
        ("ClientRequests", "client-requests-original", "OwnedClientClosed"),
        ("ClientRequests", "client-requests-fixed", None),
        ("ClientCleanup", "client-cleanup-original", "ReplacementPreserved"),
        ("ClientCleanup", "client-cleanup-fixed", None),
        ("ClientDispatch", "client-dispatch-original", "DispatchOpen"),
        ("ClientDispatch", "client-dispatch-fixed", None),
        ("ClientPagination", "client-pagination-original", "NoSkippedSuccessor"),
        ("ClientPagination", "client-pagination-fixed", None),
        ("ClientPagination", "client-pagination-cycle", None),
        ("ClientPageBudget", "client-budget-original", "Temporal property Termination was violated"),
        ("ClientPageBudget", "client-budget-fixed", None),
    ]
    cases += [
        ("GradingRedirect", "grading-redirect-original", "OneWrite"),
        ("GradingRedirect", "grading-redirect-fixed", None),
        ("GradingStride", "grading-stride-original", "CapRespected"),
        ("GradingStride", "grading-stride-fixed", None),
        ("GradingRetry", "grading-retry-original", "OneWrite"),
        ("GradingRetry", "grading-retry-fixed", None),
        ("GradingRetry", "grading-retry-read", None),
        ("GradingBatch", "grading-batch-duplicate-original", "NoDoubleGrade"),
        ("GradingBatch", "grading-batch-duplicate-fixed", None),
        ("GradingBatch", "grading-batch-fixed", None),
        ("GradingBatch", "grading-batch-mutation-original", "NoDoubleGrade"),
        ("GradingBatch", "grading-batch-mutation-fixed", None),
        ("GradingBatch", "grading-batch-zero-original", "ZeroDelay"),
        ("GradingBatch", "grading-batch-zero-fixed", None),
    ]
    for module, config, failure in cases:
        with tempfile.TemporaryDirectory(prefix="confirmation-tlc-") as states:
            run([
                "java", "-XX:+UseParallelGC", "-cp", str(jar), "tlc2.TLC",
                "-workers", "1", "-noGenerateSpecTE", "-metadir", states,
                "-config", f"{config}.cfg", f"tla/{module}.tla",
            ], failure)


if __name__ == "__main__":
    main()
