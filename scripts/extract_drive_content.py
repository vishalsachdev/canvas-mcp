"""
Extract student work content from publicly shared Google Drive folders.
Uses gdown to list and download files, pdfplumber to extract text.
"""
import gdown
import pdfplumber
import io
import json
import os
import re
import shutil
import tempfile

# Priority order for picking the main submission file
PRIORITY_KEYWORDS = [
    "chef d'oeuvre",
    "chef d oeuvre",
    "chef-d'oeuvre",
    "chefoeuvre",
    "sostac",
    "milestone",
    "strategie",
    "stratégie",
    "projet",
    "dossier",
    "pitch",
]

MAX_PAGES = 60  # Limit PDF pages to avoid huge files


def get_folder_file_list(folder_url: str) -> list[dict]:
    """Use gdown to retrieve the file list from a public Google Drive folder."""
    # Not used directly; download_folder_to_tmp handles listing
    return []


def download_pdfs_to_tmp(folder_url: str) -> str | None:
    """List folder contents, then download only PDF files to a temp directory."""
    tmp_dir = tempfile.mkdtemp(prefix="gdrive_")
    try:
        # List all files without downloading
        file_list = gdown.download_folder(
            folder_url,
            output=tmp_dir,
            quiet=True,
            use_cookies=False,
            skip_download=True,
        )
        if not file_list:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        # Filter to PDFs only
        pdf_files = [f for f in file_list if f.path.lower().endswith(".pdf")]
        print(f"  Found {len(file_list)} files, {len(pdf_files)} PDFs")

        if not pdf_files:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None

        # Download each PDF
        os.makedirs(tmp_dir, exist_ok=True)
        downloaded_any = False
        for f in pdf_files:
            local_path = f.local_path
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            try:
                result = gdown.download(
                    url=f"https://drive.google.com/uc?id={f.id}",
                    output=local_path,
                    quiet=True,
                    use_cookies=False,
                )
                if result:
                    downloaded_any = True
            except Exception as e:
                print(f"  Failed to download {f.path}: {e}")

        if not downloaded_any:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None
        return tmp_dir
    except Exception as e:
        print(f"  gdown error: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None


def extract_text_from_pdf(path: str, max_pages: int = MAX_PAGES) -> str:
    """Extract text from a PDF file using pdfplumber."""
    try:
        with pdfplumber.open(path) as pdf:
            pages_text = []
            for i, page in enumerate(pdf.pages):
                if i >= max_pages:
                    break
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n\n".join(pages_text)
    except Exception as e:
        return f"[PDF extraction error: {e}]"


def score_file(name: str) -> int:
    """Score a filename based on relevance keywords."""
    name_lower = name.lower()
    for i, kw in enumerate(PRIORITY_KEYWORDS):
        if kw in name_lower:
            return len(PRIORITY_KEYWORDS) - i
    return 0


def pick_best_pdf(directory: str) -> str | None:
    """Walk the downloaded directory and pick the most relevant PDF."""
    candidates = []
    for root, _, files in os.walk(directory):
        for fname in files:
            if fname.lower().endswith(".pdf"):
                full_path = os.path.join(root, fname)
                size = os.path.getsize(full_path)
                candidates.append((score_file(fname), size, full_path, fname))

    if not candidates:
        return None

    # Sort: highest score first, then by size (larger = more content)
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def process_student(student_id: str, folder_url: str) -> dict:
    """Download a student's Drive folder and extract PDF content from ALL PDFs."""
    print(f"\n[{student_id}] Downloading PDFs from folder...", flush=True)
    tmp_dir = download_pdfs_to_tmp(folder_url)

    if not tmp_dir:
        return {"student_id": student_id, "error": "Failed to download folder", "content": ""}

    try:
        # Collect all PDF files, sorted by relevance score then size
        candidates = []
        for root, _, files in os.walk(tmp_dir):
            for fname in files:
                if fname.lower().endswith(".pdf"):
                    full_path = os.path.join(root, fname)
                    size = os.path.getsize(full_path)
                    candidates.append((score_file(fname), size, full_path, fname))
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

        all_files = [c[3] for c in candidates]
        print(f"[{student_id}] Downloaded {len(all_files)} PDFs: {all_files}", flush=True)

        if not candidates:
            return {
                "student_id": student_id,
                "error": "No PDF found",
                "content": "",
                "files": [],
            }

        # Extract text from ALL PDFs and concatenate (capped at MAX_PAGES each)
        all_texts = []
        extracted_files = []
        total_words = 0
        for score, size, path, fname in candidates:
            text = extract_text_from_pdf(path)
            if text and not text.startswith("[PDF extraction error"):
                words = len(text.split())
                all_texts.append(f"=== {fname} ===\n{text}")
                extracted_files.append(fname)
                total_words += words
                print(f"[{student_id}]   {fname}: {words} words", flush=True)

        combined_text = "\n\n".join(all_texts)
        word_count = len(combined_text.split()) if combined_text else 0
        print(f"[{student_id}] Total: {word_count} words from {len(extracted_files)} PDFs", flush=True)

        return {
            "student_id": student_id,
            "file_name": extracted_files[0] if extracted_files else None,
            "all_files": all_files,
            "extracted_files": extracted_files,
            "content": combined_text,
            "word_count": word_count,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    # Test with first 2 students
    test_cases = [
        ("1272", "https://drive.google.com/drive/folders/12gkNxASLinJcEj427KBVoAuspTDpEkxj"),
    ]

    for sid, url in test_cases:
        result = process_student(sid, url)
        print(f"\n{'='*60}")
        print(f"Student {result['student_id']}: {result.get('file_name', 'N/A')}")
        print(f"Words extracted: {result.get('word_count', 0)}")
        if result.get("error"):
            print(f"Error: {result['error']}")
        if result.get("content"):
            print(f"Content preview:\n{result['content'][:800]}...")
        print("=" * 60)

        out_path = f"/tmp/student_{sid}_content.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Full content saved to {out_path}")
