from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient


# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import os

from main import app


client = TestClient(app)


def test_upload_valid_files():
    """
    Test case for uploading a valid set of files.
    """
    with open("samples/Intake - Miguel and Rachael.pdf", "rb") as f:
        response = client.post(
            "/api/legal-analysis-upload",
            files={"files": ("Intake - Miguel and Rachael.pdf", f, "application/pdf")},
        )
    assert response.status_code == 200


def test_upload_unsupported_file():
    """
    Test case for uploading an unsupported file type.
    """
    with open(
        "samples/Badam, Balaji [MetLife]/Client Docs/imessage - Breanna communication 1.jpg",
        "rb",
    ) as f:
        response = client.post(
            "/api/legal-analysis-upload",
            files={
                "files": ("imessage - Breanna communication 1.jpg", f, "image/jpeg")
            },
        )
    assert response.status_code == 415
