import os
import io
import logging
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend.services.llm import generate_document_content
from backend.services.document_gen import generate_pdf
from backend.config import BACKEND_URL, VALID_DOC_TYPES

logger = logging.getLogger(__name__)
router = APIRouter()

# Absolute path — works on both local and Railway
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS_DIR = os.path.join(BASE_DIR, "generated_docs")
os.makedirs(DOCS_DIR, exist_ok=True)


class DocumentRequest(BaseModel):
    user_id: str
    doc_type: str
    details: dict


class DocumentResponse(BaseModel):
    document_url: str
    status: str
    filename: str


@router.post("/generate-document", response_model=DocumentResponse)
async def generate_document(req: DocumentRequest):
    if req.doc_type not in VALID_DOC_TYPES:
        logger.warning(f"Non-standard doc_type requested: {req.doc_type}")

    if not req.details:
        raise HTTPException(status_code=400, detail="Details cannot be empty")

    content = generate_document_content(req.doc_type, req.details)

    if content.startswith("[Document generation failed"):
        raise HTTPException(status_code=500, detail="Document generation failed")

    filepath = generate_pdf(
        user_id=req.user_id,
        doc_type=req.doc_type,
        content=content,
        details=req.details,
    )

    filename = os.path.basename(filepath)
    # Use /api/docs/ route which reads from disk in the same process
    document_url = f"{BACKEND_URL}/api/docs/{filename}"

    logger.info(f"Document generated: {filename} at {filepath}")
    return DocumentResponse(
        document_url=document_url,
        status="generated",
        filename=filename,
    )


@router.get("/docs/{filename}")
async def serve_document(filename: str):
    """Serve a generated PDF document."""
    # Sanitize to prevent path traversal
    filename = os.path.basename(filename)

    # Try the standard DOCS_DIR first
    filepath = os.path.join(DOCS_DIR, filename)

    # Also try the document_gen.py DOCS_DIR (relative to services folder)
    if not os.path.exists(filepath):
        alt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "services", "..", "..", "generated_docs", filename
        )
        alt_path = os.path.normpath(alt_path)
        if os.path.exists(alt_path):
            filepath = alt_path

    # Try /app/generated_docs (Railway container path)
    if not os.path.exists(filepath):
        railway_path = os.path.join("/app", "generated_docs", filename)
        if os.path.exists(railway_path):
            filepath = railway_path

    if not os.path.exists(filepath):
        logger.error(f"PDF not found: {filename}. Searched: {DOCS_DIR}, /app/generated_docs")
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(f"Serving PDF: {filepath}")
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
