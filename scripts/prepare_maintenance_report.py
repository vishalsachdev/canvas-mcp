"""Turn the agent's structured report into one fixed, bounded Markdown artifact."""

import argparse
import json
import os
import tempfile
from pathlib import Path


def write_report(raw_json: str, output: Path) -> None:
    if len(raw_json.encode("utf-8")) > 512_000:
        raise ValueError("Structured report exceeds size limit")
    data = json.loads(raw_json)
    if not isinstance(data, dict) or set(data) != {"report"}:
        raise ValueError("Expected only a report text field")
    text = data["report"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Report must be nonempty text, never a file path object")
    if len(text) > 32_000 or len(text.encode("utf-8")) > 64_000:
        raise ValueError("Report exceeds size limit")
    if any(ord(char) < 32 and char not in "\n\t\r" for char in text):
        raise ValueError("Report contains control characters")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as temporary:
        temporary.write(text.rstrip() + "\n")
        path = Path(temporary.name)
    try:
        os.replace(path, output)
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_report(os.environ["REPORT_JSON"], args.output)


if __name__ == "__main__":
    main()
