import asyncio
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import (
    Depends, FastAPI, File, Header, HTTPException,
    Request, UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .models import OCRPageResult, OCRResponse, VisionAPIError
from .pdf_renderer import render_pages
from .vision_client import StrictVisionClient

settings = Settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_TYPES = {
    "image/png", "image/jpeg", "image/tiff",
    "image/webp", "image/bmp",
}
IMAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp", ".bmp",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.vision_client = StrictVisionClient(settings)
    logger.info(
        "Vision client ready",
        extra={"project_id": app.state.vision_client.project_id},
    )
    yield


app = FastAPI(title="OCR Service", lifespan=lifespan)


# --- Exception handler: flatten HTTPException detail for consistent schema ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    content = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    trace_id = getattr(request.state, "trace_id", "unknown")
    if "trace_id" not in content:
        content["trace_id"] = trace_id
    if "provider" not in content:
        content["provider"] = "google_vision"
    response = JSONResponse(
        status_code=exc.status_code,
        content=content,
    )
    response.headers["X-Trace-ID"] = trace_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    trace_id = getattr(request.state, "trace_id", "unknown")
    response = JSONResponse(
        status_code=400,
        content={
            "error": f"Validation error: {exc.errors()}",
            "trace_id": trace_id,
            "provider": "google_vision",
        },
    )
    response.headers["X-Trace-ID"] = trace_id
    return response


# --- Middleware: assign trace_id to every request ---
@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    request.state.trace_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Trace-ID"] = request.state.trace_id
    return response


# --- Auth dependency ---
async def verify_service_token(
    request: Request,
    authorization: str = Header(""),
):
    if authorization != f"Bearer {settings.service_token}":
        raise HTTPException(
            status_code=401,
            detail={
                "error": "Invalid service token",
                "trace_id": request.state.trace_id,
                "provider": "google_vision",
            },
        )


# --- Health (no auth required) ---
@app.get("/health")
async def health():
    client = app.state.vision_client
    return {
        "status": "healthy" if client.is_ready else "unhealthy",
        "vision_client_ready": client.is_ready,
        "project_id": client.project_id,
        "max_pages": settings.max_pages,
        "page_render_dpi": settings.page_render_dpi,
    }


# --- Main OCR endpoint ---
@app.post(
    "/ocr",
    response_model=OCRResponse,
    dependencies=[Depends(verify_service_token)],
)
async def ocr_endpoint(request: Request, file: UploadFile = File(...)):
    trace_id = request.state.trace_id
    t0 = time.monotonic()
    warnings: list[str] = []
    errors: list[str] = []

    file_bytes = await file.read()
    if len(file_bytes) > settings.max_request_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "error": (
                    f"File exceeds "
                    f"{settings.max_request_bytes} bytes"
                ),
                "trace_id": trace_id,
                "provider": "google_vision",
            },
        )

    content_type = file.content_type or ""
    filename = file.filename or ""
    vision_client = app.state.vision_client

    if (
        content_type == "application/pdf"
        or filename.lower().endswith(".pdf")
    ):
        # PDF: render pages then OCR each in parallel
        try:
            rendered = render_pages(
                file_bytes,
                settings.max_pages,
                settings.page_render_dpi,
                settings.max_image_bytes,
            )
        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": str(e),
                    "trace_id": trace_id,
                    "provider": "google_vision",
                },
            )

        semaphore = asyncio.Semaphore(8)

        async def ocr_page(rp: dict) -> OCRPageResult:
            async with semaphore:
                try:
                    text = await asyncio.to_thread(
                        vision_client.extract_text,
                        rp["image_bytes"],
                        settings.max_image_bytes,
                    )
                    return OCRPageResult(
                        page=rp["page"], text=text
                    )
                except VisionAPIError as e:
                    return OCRPageResult(
                        page=rp["page"], text="", error=str(e)
                    )

        pages = await asyncio.gather(
            *[ocr_page(rp) for rp in rendered]
        )
        pages = sorted(pages, key=lambda p: p.page)
        file_type = "pdf"

        failed = [p for p in pages if p.error]
        if failed:
            errors = [
                f"Page {p.page}: {p.error}" for p in failed
            ]
            if len(failed) == len(pages):
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": (
                            f"All {len(pages)} pages "
                            f"failed OCR"
                        ),
                        "trace_id": trace_id,
                        "provider": "google_vision",
                        "errors": errors,
                    },
                )
            warnings.append(
                f"{len(failed)} of {len(pages)} "
                f"pages failed OCR"
            )

    elif (
        content_type in SUPPORTED_IMAGE_TYPES
        or filename.lower().endswith(IMAGE_EXTENSIONS)
    ):
        try:
            text = await asyncio.to_thread(
                vision_client.extract_text,
                file_bytes,
                settings.max_image_bytes,
            )
        except VisionAPIError as e:
            return JSONResponse(
                status_code=503,
                content={
                    "error": str(e),
                    "trace_id": trace_id,
                    "provider": "google_vision",
                },
            )
        pages = [OCRPageResult(page=1, text=text)]
        file_type = "image"

    else:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Unsupported file type: {content_type}",
                "trace_id": trace_id,
                "provider": "google_vision",
            },
        )

    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    full_text = "\n\n".join(
        p.text for p in pages if not p.error
    )

    logger.info(
        "OCR completed",
        extra={
            "trace_id": trace_id,
            "provider": "google_vision",
            "file_type": file_type,
            "page_count": len(pages),
            "latency_ms": latency_ms,
            "ocr_filename": filename,
            "errors_count": len(errors),
        },
    )

    return OCRResponse(
        provider="google_vision",
        file_type=file_type,
        page_count=len(pages),
        pages=pages,
        full_text=full_text,
        latency_ms=latency_ms,
        warnings=warnings,
        errors=errors,
        trace_id=trace_id,
    )
