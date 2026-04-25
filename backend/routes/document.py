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

    # Log all search paths for debugging
    search_paths = [
        os.path.join(DOCS_DIR, filename),
        os.path.join("/app", "generated_docs", filename),
        os.path.join("/app/backend/services/../../generated_docs", filename),
    ]
    search_paths = [os.path.normpath(p) for p in search_paths]

    logger.info(f"Looking for PDF: {filename}")
    for path in search_paths:
        logger.info(f"  Checking: {path} — exists={os.path.exists(path)}")

    filepath = next((p for p in search_paths if os.path.exists(p)), None)

    if not filepath:
        # List what IS in generated_docs for debugging
        for d in [DOCS_DIR, "/app/generated_docs"]:
            if os.path.isdir(d):
                files = os.listdir(d)
                logger.error(f"Files in {d}: {files}")
        raise HTTPException(status_code=404, detail=f"Document not found: {filename}")

    logger.info(f"Serving PDF from: {filepath}")
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
