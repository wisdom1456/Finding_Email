"""Stub — real code moved to services/documents/file_processors/pdf_processor.py."""
# Re-export everything including underscore-prefixed names used by tests.
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("legal_portal.services.documents.file_processors.pdf_processor")
_sys.modules[__name__] = _real
