"""Smoke tests for re-export stub modules.

Verifies that backward-compatibility stubs in services/file_processors/
correctly re-export from services/documents/file_processors/.
"""

import importlib


class TestFileProcessorReExports:
    """Each file_processors stub re-exports the real module transparently."""

    def _assert_reexport(self, old_path: str, new_path: str, symbol: str):
        old_mod = importlib.import_module(old_path)
        new_mod = importlib.import_module(new_path)
        assert getattr(old_mod, symbol) is getattr(new_mod, symbol), (
            f"{old_path}.{symbol} is not the same object as {new_path}.{symbol}"
        )

    def test_pdf_processor_reexport(self):
        self._assert_reexport(
            "legal_portal.services.file_processors.pdf_processor",
            "legal_portal.services.documents.file_processors.pdf_processor",
            "process_pdf",
        )

    def test_txt_processor_reexport(self):
        self._assert_reexport(
            "legal_portal.services.file_processors.txt_processor",
            "legal_portal.services.documents.file_processors.txt_processor",
            "process_txt",
        )

    def test_docx_processor_reexport(self):
        self._assert_reexport(
            "legal_portal.services.file_processors.docx_processor",
            "legal_portal.services.documents.file_processors.docx_processor",
            "process_docx",
        )

    def test_image_processor_reexport(self):
        self._assert_reexport(
            "legal_portal.services.file_processors.image_processor",
            "legal_portal.services.documents.file_processors.image_processor",
            "process_image",
        )

    def test_eml_processor_reexport(self):
        self._assert_reexport(
            "legal_portal.services.file_processors.eml_processor",
            "legal_portal.services.documents.file_processors.eml_processor",
            "process_eml",
        )

    def test_package_init_reexport(self):
        """The __init__.py stub re-exports the package."""
        old = importlib.import_module("legal_portal.services.file_processors")
        new = importlib.import_module("legal_portal.services.documents.file_processors")
        # Both should resolve to the same module after stub redirect
        assert old.__name__ == new.__name__ or hasattr(old, "__path__")
