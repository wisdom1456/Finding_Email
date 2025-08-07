"""
Handles the final delivery of the generated letter.
"""

from __future__ import annotations

import logging


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def convert_to_pdf(html_content: str) -> bytes:
    """
    Converts HTML content to a PDF file.

    Args:
        html_content: The HTML content to convert.

    Returns:
        The generated PDF as an in-memory byte stream.
    """
    logging.info("Entering convert_to_pdf.")
    # Placeholder for HTML to PDF conversion logic (e.g., using WeasyPrint or other libraries)
    pdf_content = b"PDF content placeholder"
    logging.info("Exiting convert_to_pdf.")
    return pdf_content


def convert_to_docx(html_content: str) -> bytes:
    """
    Converts HTML content to a DOCX file.

    Args:
        html_content: The HTML content to convert.

    Returns:
        The generated DOCX as an in-memory byte stream.
    """
    logging.info("Entering convert_to_docx.")
    # Placeholder for HTML to DOCX conversion (e.g., using pandoc or python-docx)
    docx_content = b"DOCX content placeholder"
    logging.info("Exiting convert_to_docx.")
    return docx_content


def provision_files(files: dict[str, bytes]) -> dict[str, str]:
    """
    Makes the generated files available for download.

    Args:
        files: A dictionary where keys are filenames and values are file contents as bytes.

    Returns:
        A dictionary containing download links for the provisioned files.
    """
    logging.info("Entering provision_files.")
    download_links = {}
    for filename, _content in files.items():
        # Placeholder for file provisioning logic (e.g., saving to a temporary
        # location and generating a download link)
        download_links[filename] = f"/downloads/{filename}"
        logging.info(f"Provisioned {filename} with link: {download_links[filename]}")

    logging.info("Exiting provision_files.")
    return download_links


if __name__ == "__main__":
    logging.info("delivery.py is being run standalone for testing.")

    html = "<html><body><h1>Test</h1><p>This is a test.</p></body></html>"

    pdf_data = convert_to_pdf(html)
    docx_data = convert_to_docx(html)

    files_to_provision = {"letter.pdf": pdf_data, "letter.docx": docx_data}

    links = provision_files(files_to_provision)
    logging.info(f"Download links: {links}")
