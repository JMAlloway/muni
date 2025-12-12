import io
import logging
from pathlib import Path
from typing import Any, Dict, Optional

# Optional deps; gracefully degrade if missing.
try:  # PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None

try:  # python-docx
    import docx  # type: ignore
except ImportError:  # pragma: no cover
    docx = None

logger = logging.getLogger("document_processor")

MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB hard cap
MAX_PDF_PAGES = 300
MAX_DOCX_PARAS = 2000
SCANNED_RATIO_THRESHOLD = 0.002


class DocumentProcessor:
    """Lightweight text extraction for PDFs, DOCX, and plaintext."""

    def extract_text(self, file_bytes: bytes, mime: str | None, filename: str) -> Dict[str, Any]:
        if not file_bytes:
            return {"text": "", "metadata": {}, "status": "failed", "error": "Empty file"}
        if len(file_bytes) > MAX_FILE_BYTES:
            return {"text": "", "metadata": {}, "status": "failed", "error": "File too large"}

        mime = (mime or "").lower().strip()
        name = filename or "document"
        suffix = Path(name).suffix.lower()

        if mime == "application/pdf" or suffix == ".pdf":
            return self._extract_pdf(file_bytes)

        if mime in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        } or suffix in {".docx", ".doc"}:
            return self._extract_docx(file_bytes)

        if mime.startswith("text/") or suffix in {".txt", ".md"}:
            try:
                text = file_bytes.decode("utf-8", errors="ignore")
            except Exception as exc:  # pragma: no cover
                logger.warning("document_processor txt decode failed: %s", exc)
                return {"text": "", "metadata": {}, "status": "failed", "error": "Could not decode text file"}
            return {
                "text": text,
                "metadata": {"word_count": len(text.split())},
                "status": "success",
                "error": None,
            }

        return {
            "text": "",
            "metadata": {},
            "status": "unsupported",
            "error": f"Unsupported file type: {mime or suffix or 'unknown'}",
        }

    def _extract_pdf(self, file_bytes: bytes) -> Dict[str, Any]:
        if not fitz:
            return {
                "text": "",
                "metadata": {},
                "status": "failed",
                "error": "PyMuPDF is not installed",
            }
        if not file_bytes.startswith(b"%PDF"):
            return {"text": "", "metadata": {}, "status": "failed", "error": "Invalid PDF signature"}
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            pages = []
            truncated = False
            for idx, page in enumerate(doc):
                if idx >= MAX_PDF_PAGES:
                    truncated = True
                    break
                pages.append(page.get_text("text"))
            text = "\n".join([p for p in pages if p]).strip()
            doc.close()
            ratio = len(text) / max(len(file_bytes), 1)
            meta = {
                "pages": len(pages),
                "word_count": len(text.split()),
                "text_ratio": ratio,
                "suspected_scanned": ratio < SCANNED_RATIO_THRESHOLD,
                "truncated_pages": truncated,
            }
            return {"text": text, "metadata": meta, "status": "success", "error": None}
        except Exception as exc:  # pragma: no cover
            logger.warning("document_processor pdf failed: %s", exc)
            return {"text": "", "metadata": {}, "status": "failed", "error": "Failed to read PDF"}

    def _extract_docx(self, file_bytes: bytes) -> Dict[str, Any]:
        if not docx:
            return {
                "text": "",
                "metadata": {},
                "status": "failed",
                "error": "python-docx is not installed",
            }
        # Basic magic check for ZIP (DOCX is zip)
        if not file_bytes.startswith(b"PK"):
            return {"text": "", "metadata": {}, "status": "failed", "error": "Invalid DOCX signature"}
        try:
            stream = io.BytesIO(file_bytes)
            doc = docx.Document(stream)
            paras = []
            truncated = False
            for idx, p in enumerate(doc.paragraphs):
                if idx >= MAX_DOCX_PARAS:
                    truncated = True
                    break
                if p.text and p.text.strip():
                    paras.append(p.text.strip())
            text = "\n\n".join(paras).strip()
            meta = {
                "paragraphs": len(paras),
                "word_count": len(text.split()),
                "truncated_paragraphs": truncated,
            }
            return {"text": text, "metadata": meta, "status": "success", "error": None}
        except Exception as exc:  # pragma: no cover
            logger.warning("document_processor docx failed: %s", exc)
            return {"text": "", "metadata": {}, "status": "failed", "error": "Failed to read DOCX"}
