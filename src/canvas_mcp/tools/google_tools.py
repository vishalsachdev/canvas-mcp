"""Google Docs and Slides tools for Canvas MCP.

Fetches content from Google Docs (text) and Google Slides (text + slide
thumbnail images) for use in grading workflows. Requires one-time OAuth
setup via google_authenticate.
"""

import asyncio
import io
import re
from base64 import b64encode

from mcp.server.fastmcp import FastMCP, Image

from ..core.google_auth import authenticate_google, get_google_credentials
from ..core.logging import log_error, log_info

MAX_IMAGE_DIMENSION = 1568  # Claude's optimal input size
JPEG_QUALITY = 80
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB per image
CONCURRENT_DOWNLOADS = 8

# URL parsing patterns
DOCS_PATTERN = re.compile(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)")
SLIDES_PATTERN = re.compile(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)")
DRIVE_PATTERN = re.compile(r"drive\.google\.com/(?:file/d/|open\?id=)([a-zA-Z0-9_-]+)")


def _extract_doc_id(url_or_id: str) -> str:
    """Extract a Google document ID from a URL or bare ID."""
    match = DOCS_PATTERN.search(url_or_id)
    if match:
        return match.group(1)
    match = DRIVE_PATTERN.search(url_or_id)
    if match:
        return match.group(1)
    # Assume bare ID if no URL pattern matched
    return url_or_id.strip()


def _extract_slides_id(url_or_id: str) -> str:
    """Extract a Google Slides presentation ID from a URL or bare ID."""
    match = SLIDES_PATTERN.search(url_or_id)
    if match:
        return match.group(1)
    match = DRIVE_PATTERN.search(url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()


# ---------------------------------------------------------------------------
# Google Docs text extraction helpers
# ---------------------------------------------------------------------------

def _read_structural_elements(elements: list) -> str:
    """Recursively extract text from Docs structural elements."""
    text = ""
    for element in elements:
        if "paragraph" in element:
            for paragraph_element in element["paragraph"].get("elements", []):
                text_run = paragraph_element.get("textRun", {})
                if text_run.get("content"):
                    text += text_run["content"]
        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    text += _read_structural_elements(cell.get("content", []))
        elif "tableOfContents" in element:
            text += _read_structural_elements(
                element["tableOfContents"].get("content", [])
            )
    return text


def _get_all_tabs(tabs: list) -> list:
    """Flatten nested tab structure into a single list."""
    all_tabs = []
    for tab in tabs:
        all_tabs.append(tab)
        for child in tab.get("childTabs", []):
            all_tabs.extend(_get_all_tabs([child]))
    return all_tabs


def _extract_text_from_tab(tab: dict) -> str:
    """Extract text from a single Docs tab."""
    content = tab.get("documentTab", {}).get("body", {}).get("content", [])
    return _read_structural_elements(content)


# ---------------------------------------------------------------------------
# Google Slides text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_from_slide(slide: dict) -> str:
    """Extract text from a slide's page elements (shapes + tables)."""
    texts = []
    for element in slide.get("pageElements", []):
        # Text in shapes
        shape = element.get("shape", {})
        text_elements = shape.get("text", {}).get("textElements", [])
        shape_text = "".join(
            te.get("textRun", {}).get("content", "")
            for te in text_elements
            if te.get("textRun", {}).get("content")
        ).strip()
        if shape_text:
            texts.append(shape_text)

        # Text in tables
        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_elements = cell.get("text", {}).get("textElements", [])
                    cell_text = "".join(
                        te.get("textRun", {}).get("content", "")
                        for te in cell_elements
                        if te.get("textRun", {}).get("content")
                    ).strip()
                    if cell_text:
                        texts.append(cell_text)
    return "\n".join(texts)


def _extract_speaker_notes(slide: dict) -> str:
    """Extract speaker notes from a slide."""
    notes_page = slide.get("slideProperties", {}).get("notesPage")
    if not notes_page:
        return ""
    notes_id = notes_page.get("notesProperties", {}).get("speakerNotesObjectId")
    if not notes_id:
        return ""
    for element in notes_page.get("pageElements", []):
        if element.get("objectId") == notes_id:
            text_elements = element.get("shape", {}).get("text", {}).get("textElements", [])
            return "".join(
                te.get("textRun", {}).get("content", "")
                for te in text_elements
                if te.get("textRun", {}).get("content")
            ).strip()
    return ""


def _extract_slide_title(slide: dict) -> str | None:
    """Extract the title from a slide's TITLE or CENTERED_TITLE placeholder."""
    for element in slide.get("pageElements", []):
        placeholder_type = (
            element.get("shape", {}).get("placeholder", {}).get("type")
        )
        if placeholder_type in ("TITLE", "CENTERED_TITLE"):
            text_elements = element.get("shape", {}).get("text", {}).get("textElements", [])
            title = "".join(
                te.get("textRun", {}).get("content", "")
                for te in text_elements
                if te.get("textRun", {}).get("content")
            ).strip()
            if title:
                return title
    return None


# ---------------------------------------------------------------------------
# Image resize helper
# ---------------------------------------------------------------------------

def _resize_image_to_jpeg(image_bytes: bytes) -> tuple[bytes, int, int] | None:
    """Resize image to fit MAX_IMAGE_DIMENSION and convert to JPEG."""
    try:
        from PIL import Image as PILImage

        img = PILImage.open(io.BytesIO(image_bytes))
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), PILImage.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue(), img.width, img.height
    except Exception as exc:
        log_error("Image resize failed", exc=exc)
        return None


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------

def register_google_tools(mcp: FastMCP) -> None:
    """Register Google Docs/Slides tools with the MCP server."""

    @mcp.tool()
    async def google_authenticate() -> str:
        """Authenticate with Google for Docs and Slides access.

        Opens a browser window for one-time OAuth consent. Grants read-only
        access to Google Docs and Google Slides. The refresh token is saved
        at ~/.canvas-mcp/google_token.json for future use.
        """
        return await authenticate_google()

    @mcp.tool()
    async def fetch_google_doc(doc_url_or_id: str) -> str:
        """Fetch the text content of a Google Doc.

        Accepts a Google Docs URL or bare document ID. Extracts text from
        all tabs (including nested tabs), paragraphs, and tables.

        Args:
            doc_url_or_id: A Google Docs URL or document ID
        """
        document_id = _extract_doc_id(doc_url_or_id)
        log_info(f"Fetching Google Doc: {document_id}")

        # Try public export first (works for docs shared publicly)
        text = await _try_public_export(document_id)
        if text is not None:
            return text

        # Fall back to Docs API with OAuth
        creds = get_google_credentials()
        if not creds:
            return (
                "Error: Google not authenticated. Run google_authenticate first, "
                "or ensure the document is publicly shared."
            )

        try:
            from googleapiclient.discovery import build

            service = build("docs", "v1", credentials=creds)
            doc = service.documents().get(
                documentId=document_id, includeTabsContent=True
            ).execute()

            tabs = _get_all_tabs(doc.get("tabs", []))

            # If no tabs, try legacy body field
            if not tabs and doc.get("body", {}).get("content"):
                return _read_structural_elements(doc["body"]["content"])

            if len(tabs) == 1:
                return _extract_text_from_tab(tabs[0])

            parts = []
            for tab in tabs:
                title = tab.get("tabProperties", {}).get("title", "Untitled")
                parts.append(f"--- Tab: {title} ---\n{_extract_text_from_tab(tab)}")
            return "\n\n".join(parts)

        except Exception as exc:
            error_code = getattr(exc, "status_code", None) or getattr(exc, "resp", {}).get("status")
            if str(error_code) == "403":
                return "Error: Access denied to this document. Check sharing settings."
            if str(error_code) == "404":
                return "Error: Document not found or has been deleted."
            if str(error_code) == "429":
                return "Error: Rate limited — please try again shortly."
            log_error("Google Docs API error", exc=exc)
            return f"Error fetching Google Doc: {exc}"

    @mcp.tool()
    async def fetch_google_slides(slides_url_or_id: str) -> list:
        """Fetch text and slide thumbnail images from a Google Slides presentation.

        Returns a list starting with text content, followed by Image objects
        for each slide thumbnail. Text includes slide titles, body text,
        and speaker notes.

        Args:
            slides_url_or_id: A Google Slides URL or presentation ID
        """
        presentation_id = _extract_slides_id(slides_url_or_id)
        log_info(f"Fetching Google Slides: {presentation_id}")

        creds = get_google_credentials()
        if not creds:
            return [
                "Error: Google not authenticated. Run google_authenticate first."
            ]

        try:
            from googleapiclient.discovery import build

            service = build("slides", "v1", credentials=creds)
            presentation = service.presentations().get(
                presentationId=presentation_id
            ).execute()

            slides = presentation.get("slides", [])
            if not slides:
                return [f"Presentation '{presentation.get('title', 'Untitled')}' has no slides."]

            # Extract text from all slides
            text_parts = []
            slide_ids = []
            for idx, slide in enumerate(slides):
                slide_id = slide.get("objectId", f"slide-{idx}")
                slide_title = _extract_slide_title(slide) or f"Slide {idx + 1}"
                slide_text = _extract_text_from_slide(slide)
                speaker_notes = _extract_speaker_notes(slide)

                slide_ids.append((slide_id, idx + 1, slide_title))

                text_parts.append(f"--- Slide {idx + 1}: {slide_title} ---")
                if slide_text:
                    text_parts.append(slide_text)
                if speaker_notes:
                    text_parts.append(f"[Speaker Notes: {speaker_notes}]")

            combined_text = "\n\n".join(text_parts)

            # Download slide thumbnails concurrently
            thumbnails = await _download_slide_thumbnails(
                service, presentation_id, slide_ids, creds
            )

            result: list = [combined_text]
            result.extend(thumbnails)
            return result

        except Exception as exc:
            error_code = getattr(exc, "status_code", None) or getattr(exc, "resp", {}).get("status")
            if str(error_code) == "403":
                if "not been used in project" in str(exc):
                    return ["Error: Google Slides API not enabled. Enable it in Google Cloud Console."]
                return ["Error: Access denied to this presentation. Check sharing settings."]
            if str(error_code) == "404":
                return ["Error: Presentation not found or has been deleted."]
            if str(error_code) == "429":
                return ["Error: Rate limited — please try again shortly."]
            log_error("Google Slides API error", exc=exc)
            return [f"Error fetching Google Slides: {exc}"]


async def _try_public_export(document_id: str) -> str | None:
    """Try to export a Google Doc as plain text via the public export URL.

    Works for documents shared as 'Anyone with the link'. Returns None
    if the doc is not publicly accessible.
    """
    import httpx

    export_url = f"https://docs.google.com/document/d/{document_id}/export?format=txt"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(export_url)
            if resp.status_code == 200 and "text/" in resp.headers.get("content-type", ""):
                text = resp.text.strip()
                if text and not text.startswith("<!DOCTYPE"):
                    return text
    except Exception:
        pass
    return None


async def _download_slide_thumbnails(
    service, presentation_id: str, slide_ids: list[tuple[str, int, str]], creds
) -> list[Image]:
    """Download and resize thumbnails for all slides concurrently."""
    import httpx

    semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)
    thumbnails: list[tuple[int, Image]] = []

    async def _download_one(slide_id: str, slide_number: int, slide_title: str) -> None:
        async with semaphore:
            try:
                # Get thumbnail URL from Slides API (sync call in executor)
                def _get_thumbnail_url():
                    return service.presentations().pages().getThumbnail(
                        presentationId=presentation_id,
                        pageObjectId=slide_id,
                        **{
                            "thumbnailProperties.mimeType": "PNG",
                            "thumbnailProperties.thumbnailSize": "LARGE",
                        },
                    ).execute()

                loop = asyncio.get_event_loop()
                thumb_response = await loop.run_in_executor(None, _get_thumbnail_url)
                content_url = thumb_response.get("contentUrl")
                if not content_url:
                    return

                # Download the thumbnail image
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        content_url,
                        headers={"Authorization": f"Bearer {creds.token}"},
                    )
                    if resp.status_code != 200:
                        log_error(f"Slide thumbnail HTTP {resp.status_code} for {slide_id}")
                        return

                    image_bytes = resp.content
                    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                        log_error(f"Slide {slide_id} thumbnail exceeds 5MB")
                        return

                    result = _resize_image_to_jpeg(image_bytes)
                    if not result:
                        return
                    jpeg_bytes, width, height = result

                    thumbnails.append((
                        slide_number,
                        Image(data=b64encode(jpeg_bytes).decode(), format="jpeg"),
                    ))
            except Exception as exc:
                log_error(f"Failed to download slide {slide_id} thumbnail", exc=exc)

    await asyncio.gather(
        *[_download_one(sid, num, title) for sid, num, title in slide_ids]
    )

    # Sort by slide number and return just the Image objects
    thumbnails.sort(key=lambda x: x[0])
    return [img for _, img in thumbnails]
