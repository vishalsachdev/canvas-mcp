"""
Batch extraction of student work from Google Drive folders.
Reads the student CSV, downloads each student's folder, extracts text from the best PDF.
Saves results to exports/student_texts/ as individual JSON files.

Usage:
    python scripts/batch_extract_students.py            # process all students
    python scripts/batch_extract_students.py --start 0 --end 10  # range
    python scripts/batch_extract_students.py --ids 1272 1273      # specific IDs
"""
import csv
import json
import os
import sys
import argparse
from pathlib import Path

# Add project root to path so we can import extract_drive_content
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_drive_content import process_student

CSV_PATH = os.path.expanduser("~/Documents/Dossiers des apprenents - Sheet2.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports", "student_texts")


def load_student_csv(csv_path: str) -> list[dict]:
    """Load the student CSV, returning list of {id, drive_link} dicts (deduped)."""
    seen = set()
    students = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = str(row["id"]).strip()
            link = row["drive_link"].strip()
            if sid not in seen and sid and link:
                seen.add(sid)
                students.append({"id": sid, "drive_link": link})
    return students


def already_processed(student_id: str, output_dir: str) -> bool:
    """Check if this student's JSON already exists and has content."""
    path = os.path.join(output_dir, f"student_{student_id}.json")
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            data = json.load(f)
        # Consider it done if we have content OR a definitive error (not a transient one)
        return bool(data.get("content") or data.get("error"))
    except Exception:
        return False


def save_result(result: dict, output_dir: str):
    """Save a student result dict to JSON."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"student_{result['student_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0, help="Start index (0-based)")
    parser.add_argument("--end", type=int, default=None, help="End index (exclusive)")
    parser.add_argument("--ids", nargs="*", help="Specific student IDs to process")
    parser.add_argument("--force", action="store_true", help="Re-process already-done students")
    args = parser.parse_args()

    students = load_student_csv(CSV_PATH)
    print(f"Loaded {len(students)} unique students from CSV")

    if args.ids:
        students = [s for s in students if s["id"] in args.ids]
        print(f"Filtered to {len(students)} specified students")
    else:
        end = args.end if args.end is not None else len(students)
        students = students[args.start:end]
        print(f"Processing students [{args.start}:{end}] = {len(students)} students")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    success_count = 0
    error_count = 0
    skip_count = 0

    for i, s in enumerate(students):
        sid = s["id"]
        url = s["drive_link"]

        if not args.force and already_processed(sid, OUTPUT_DIR):
            print(f"  [{i+1}/{len(students)}] Student {sid}: already processed, skipping")
            skip_count += 1
            continue

        print(f"\n[{i+1}/{len(students)}] Processing student {sid}...")
        try:
            result = process_student(sid, url)
            save_result(result, OUTPUT_DIR)

            if result.get("content"):
                print(f"  -> {result.get('file_name', 'unknown')} | {result.get('word_count', 0)} words")
                success_count += 1
            else:
                print(f"  -> ERROR: {result.get('error', 'unknown error')}")
                error_count += 1
        except Exception as e:
            print(f"  -> EXCEPTION: {e}")
            save_result({"student_id": sid, "error": str(e), "content": ""}, OUTPUT_DIR)
            error_count += 1

    print(f"\n{'='*60}")
    print(f"Done: {success_count} success, {error_count} errors, {skip_count} skipped")
    print(f"Results saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
