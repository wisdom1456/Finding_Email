import logging

import fitz

logger = logging.getLogger(__name__)


def render_pages(
    pdf_bytes: bytes,
    max_pages: int,
    dpi: int,
    max_image_bytes: int,
) -> list[dict]:
    """Render PDF pages to PNG.
    Raises ValueError on invalid PDF or too many pages."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count > max_pages:
            raise ValueError(
                f"PDF has {doc.page_count} pages, "
                f"max is {max_pages}"
            )

        pages = []
        for i, page in enumerate(doc):
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
            if len(png_bytes) > max_image_bytes:
                mat = fitz.Matrix(150 / 72, 150 / 72)
                pix = page.get_pixmap(matrix=mat)
                png_bytes = pix.tobytes("png")
                logger.warning(
                    f"Page {i + 1} re-rendered at 150 DPI "
                    f"(exceeded {max_image_bytes} bytes)"
                )
            pages.append({
                "page": i + 1,
                "image_bytes": png_bytes,
            })
        return pages
    finally:
        doc.close()
