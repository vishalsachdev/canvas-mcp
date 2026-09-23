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
        if result.returncode == 0 or f"Invariant {expected_failure} is violated" not in output:
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
