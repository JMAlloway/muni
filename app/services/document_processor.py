import io
from pathlib import Path
from typing import Any, Dict, Optional

# Optional deps; gracefully degrade if missing.
try:  # PyMuPDF
    import fitz  # type: ignore
except Exception:  # pragma: no cover
    fitz = None

try:  # python-docx
    import docx  # type: ignore
except Exception:  # pragma: no cover
    docx = None


class DocumentProcessor:
    """Lightweight text extraction for PDFs, DOCX, and plaintext."""

    def extract_text(self, file_bytes: bytes, mime: str | None, filename: str) -> Dict[str, Any]:
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
                return {"text": "", "metadata": {}, "status": "failed", "error": str(exc)}
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
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            pages = []
            for page in doc:
                pages.append(page.get_text("text"))
            text = "\n".join([p for p in pages if p]).strip()
            doc.close()
            ratio = (len(text) or 0) / max(len(file_bytes) or 1, 1)
            meta = {
                "pages": len(pages),
                "word_count": len(text.split()),
                "text_ratio": ratio,
                "suspected_scanned": ratio < 0.002,
            }
            return {"text": text, "metadata": meta, "status": "success", "error": None}
        except Exception as exc:  # pragma: no cover
            return {"text": "", "metadata": {}, "status": "failed", "error": str(exc)}

    def _extract_docx(self, file_bytes: bytes) -> Dict[str, Any]:
        if not docx:
            return {
                "text": "",
                "metadata": {},
                "status": "failed",
                "error": "python-docx is not installed",
            }
        try:
            stream = io.BytesIO(file_bytes)
            doc = docx.Document(stream)
            paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
            text = "\n\n".join(paras).strip()
            meta = {
                "paragraphs": len(paras),
                "word_count": len(text.split()),
            }
            return {"text": text, "metadata": meta, "status": "success", "error": None}
        except Exception as exc:  # pragma: no cover
            return {"text": "", "metadata": {}, "status": "failed", "error": str(exc)}
