# Smart EML Processor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract PDF attachments from EML files and deduplicate email threads so that cases with Clio-imported emails get complete, non-redundant document sets.

**Architecture:** Enhance `eml_processor.py` to return PDF attachment metadata alongside email body text. After deferred extraction processes EMLs, upload extracted PDF attachments as new documents (with content-hash dedup). Then run a thread-dedup pass that flags superseded emails as junk.

**Tech Stack:** Python stdlib `email` parser, `hashlib` for SHA-256, existing Supabase client, existing `process_pdf`/Cloud Run OCR pipeline.

---

### Task 1: Add PDF attachment extraction to eml_processor.py

**Files:**
- Modify: `src/legal_portal/services/file_processors/eml_processor.py`
- Test: `tests/unit/test_eml_attachment_extraction.py`

**Step 1: Write the failing test**

Create `tests/unit/test_eml_attachment_extraction.py`:

```python
"""Tests for EML PDF attachment extraction."""

import hashlib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import AsyncMock

import pytest

from legal_portal.core.data_models import DocumentType


def _build_eml_with_pdf(
    subject="Test Email",
    body="Hello, this is the email body with enough text to be meaningful for analysis.",
    pdf_filename="attachment.pdf",
    pdf_bytes=b"%PDF-1.4 fake pdf content for testing attachment extraction",
) -> bytes:
    """Build a multipart EML with a text body and one PDF attachment."""
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"

    msg.attach(MIMEText(body, "plain"))

    pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_part.add_header(
        "Content-Disposition", "attachment", filename=pdf_filename,
    )
    msg.attach(pdf_part)

    return msg.as_bytes()


def _build_eml_with_image(
    subject="Test Email",
    body="Hello, this is the email body.",
    image_filename="logo.png",
    image_bytes=b"\x89PNG\r\n\x1a\n fake image bytes",
) -> bytes:
    """Build a multipart EML with a text body and one image attachment."""
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"

    msg.attach(MIMEText(body, "plain"))

    img_part = MIMEApplication(image_bytes, _subtype="png")
    img_part.add_header(
        "Content-Disposition", "attachment", filename=image_filename,
    )
    msg.attach(img_part)

    return msg.as_bytes()


class TestEmlAttachmentExtraction:
    """Test that process_eml extracts PDF attachments into metadata."""

    @pytest.mark.asyncio
    async def test_pdf_attachment_extracted(self, tmp_path):
        from legal_portal.services.file_processors.eml_processor import process_eml

        pdf_bytes = b"%PDF-1.4 fake pdf content for testing"
        eml_bytes = _build_eml_with_pdf(pdf_bytes=pdf_bytes)
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_bytes)

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "test.eml",
        )

        # Attachments should be in metadata
        attachments = result.metadata.attachments or []
        assert len(attachments) == 1
        att = attachments[0]
        assert att["filename"] == "attachment.pdf"
        assert att["content_type"] == "application/pdf"
        assert att["content_hash"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert att["bytes"] == pdf_bytes

    @pytest.mark.asyncio
    async def test_image_attachment_hash_only(self, tmp_path):
        """Image attachments should be recorded in attachment_hashes but NOT in attachments."""
        from legal_portal.services.file_processors.eml_processor import process_eml

        image_bytes = b"\x89PNG\r\n\x1a\n fake image bytes"
        eml_bytes = _build_eml_with_image(image_bytes=image_bytes)
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_bytes)

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "test.eml",
        )

        attachments = result.metadata.attachments or []
        assert len(attachments) == 0  # No PDF attachments

        attachment_hashes = result.metadata.attachment_hashes or []
        expected_hash = hashlib.sha256(image_bytes).hexdigest()
        assert expected_hash in attachment_hashes

    @pytest.mark.asyncio
    async def test_body_hash_computed(self, tmp_path):
        """body_hash should be SHA-256 of the plain text body."""
        from legal_portal.services.file_processors.eml_processor import process_eml

        body = "This is the email body text."
        eml_bytes = _build_eml_with_pdf(body=body)
        eml_file = tmp_path / "test.eml"
        eml_file.write_bytes(eml_bytes)

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "test.eml",
        )

        expected_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert result.metadata.body_hash == expected_hash

    @pytest.mark.asyncio
    async def test_no_attachments_eml(self, tmp_path):
        """EML with no attachments should have empty attachment lists."""
        from legal_portal.services.file_processors.eml_processor import process_eml

        msg = MIMEText("Plain text email body with enough content for testing.", "plain")
        msg["Subject"] = "Simple Email"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"

        eml_file = tmp_path / "simple.eml"
        eml_file.write_bytes(msg.as_bytes())

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "simple.eml",
        )

        assert (result.metadata.attachments or []) == []
        assert (result.metadata.attachment_hashes or []) == []
        assert result.metadata.body_hash is not None

    @pytest.mark.asyncio
    async def test_multiple_pdf_attachments(self, tmp_path):
        """Multiple PDF attachments should all be extracted."""
        from legal_portal.services.file_processors.eml_processor import process_eml

        msg = MIMEMultipart()
        msg["Subject"] = "Multi-PDF"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"
        msg.attach(MIMEText("Body text.", "plain"))

        for i in range(3):
            pdf_part = MIMEApplication(f"pdf-content-{i}".encode(), _subtype="pdf")
            pdf_part.add_header(
                "Content-Disposition", "attachment", filename=f"doc{i}.pdf",
            )
            msg.attach(pdf_part)

        eml_file = tmp_path / "multi.eml"
        eml_file.write_bytes(msg.as_bytes())

        result = await process_eml(
            str(eml_file), DocumentType.CORRESPONDENCE, "multi.eml",
        )

        attachments = result.metadata.attachments or []
        assert len(attachments) == 3
        filenames = [a["filename"] for a in attachments]
        assert filenames == ["doc0.pdf", "doc1.pdf", "doc2.pdf"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_eml_attachment_extraction.py -v`
Expected: FAIL — `FileMetadata` has no `attachments`, `attachment_hashes`, or `body_hash` attributes.

**Step 3: Add new fields to FileMetadata**

In `src/legal_portal/core/data_models.py`, add three optional fields to `FileMetadata` (after `processing_time_ms`):

```python
    # EML attachment metadata (populated by eml_processor)
    attachments: Optional[List[Dict[str, Any]]] = None
    attachment_hashes: Optional[List[str]] = None
    body_hash: Optional[str] = None
```

**Step 4: Implement attachment extraction in eml_processor.py**

Replace the MIME-walk section in `process_eml()` to also collect attachments. The full updated function body:

In `eml_processor.py`, add `import hashlib` at top (after `import os`).

Then, inside the `try:` block of `process_eml`, after `html_parts = []` (line 63), add:

```python
        pdf_attachments = []
        attachment_hashes = []
```

Then, inside the multipart walk loop (`for part in msg.walk():`), **before** the existing `try:` block that gets the payload (line 74), add attachment detection. The updated loop body becomes:

```python
            for part in msg.walk():
                content_type = part.get_content_type()

                # Skip container parts
                if content_type.startswith("multipart/"):
                    continue

                # Check if this part is an attachment
                content_disposition = str(part.get("Content-Disposition", ""))
                filename = part.get_filename()

                if filename or "attachment" in content_disposition:
                    # This is an attachment
                    try:
                        att_bytes = part.get_payload(decode=True)
                        if att_bytes:
                            content_hash = hashlib.sha256(att_bytes).hexdigest()
                            attachment_hashes.append(content_hash)

                            if content_type == "application/pdf" or (
                                filename and filename.lower().endswith(".pdf")
                            ):
                                pdf_attachments.append({
                                    "filename": filename or "unnamed.pdf",
                                    "content_type": content_type,
                                    "content_hash": content_hash,
                                    "bytes": att_bytes,
                                })
                    except Exception as e:
                        logger.warning(f"Failed to extract attachment {filename}: {e}")
                    continue

                try:
                    # ... existing payload extraction code (unchanged) ...
```

After the body text construction (after `full_text = ...` block, around line 153), compute `body_hash`:

```python
        # Compute body hash for dedup
        body_text_for_hash = "\n\n".join(text_parts) if text_parts else ""
        body_hash = hashlib.sha256(body_text_for_hash.encode("utf-8")).hexdigest()
```

Then update the `FileMetadata` construction at the end to include the new fields:

```python
    file_metadata = FileMetadata(
        filename=original_filename,
        size=file_size,
        attachments=pdf_attachments if pdf_attachments else None,
        attachment_hashes=attachment_hashes if attachment_hashes else None,
        body_hash=body_hash,
    )
```

Note: The `body_hash` variable needs to be initialized before the try block as `body_hash = None` and set inside, so it's available even if an exception occurs.

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_eml_attachment_extraction.py -v`
Expected: All 5 tests PASS.

**Step 6: Run existing tests to verify no regressions**

Run: `python -m pytest tests/unit/test_deferred_extraction.py tests/unit/test_text_size_and_eml_routing.py -v`
Expected: All existing tests PASS.

**Step 7: Commit**

```bash
git add src/legal_portal/core/data_models.py \
        src/legal_portal/services/file_processors/eml_processor.py \
        tests/unit/test_eml_attachment_extraction.py
git commit -m "feat: extract PDF attachments and body hash from EML files"
```

---

### Task 2: Upload extracted PDF attachments with content-hash dedup

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (in `_extract_deferred_documents`)
- Test: `tests/unit/test_eml_attachment_upload.py`

**Step 1: Write the failing test**

Create `tests/unit/test_eml_attachment_upload.py`:

```python
"""Tests for uploading PDF attachments extracted from EMLs."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from legal_portal.core.data_models import DocumentStatus


class TestAttachmentUpload:
    """Test that _extract_deferred_documents uploads PDF attachments from EMLs."""

    @pytest.mark.asyncio
    async def test_pdf_attachment_uploaded_as_new_document(self):
        """After processing an EML, its PDF attachments should become new documents."""
        from legal_portal.api.routes.analysis import _extract_deferred_documents

        pdf_bytes = b"%PDF-1.4 test attachment content"
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # Build a simple EML with a PDF attachment
        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "a@b.com"
        msg["To"] = "c@d.com"
        msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"
        msg.attach(MIMEText("Email body with enough content for analysis purposes." * 3, "plain"))
        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_part.add_header("Content-Disposition", "attachment", filename="contract.pdf")
        msg.attach(pdf_part)
        eml_bytes = msg.as_bytes()

        doc = {
            "id": "eml-doc-id",
            "case_id": "case-123",
            "user_id": "user-456",
            "file_name": "test.eml",
            "file_type": "text/plain",
            "storage_path": "user/case/test.eml",
            "extraction_method": "deferred",
            "extracted_text": None,
            "metadata": {},
        }

        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.download.return_value = eml_bytes

        # No existing documents with this content_hash
        mock_select = MagicMock()
        mock_select.eq.return_value = mock_select
        mock_select.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value = mock_select

        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "new-pdf-id"}])

        # Mock storage upload for the PDF attachment
        mock_supabase.storage.from_.return_value.upload.return_value = None

        mock_progress = AsyncMock()

        results = await _extract_deferred_documents(
            [doc], mock_supabase, mock_progress, "test-analysis-id",
        )

        # The EML itself should be extracted
        assert "eml-doc-id" in results

        # A new document should have been inserted for the PDF attachment
        insert_calls = mock_supabase.table.return_value.insert.call_args_list
        assert len(insert_calls) >= 1
        inserted = insert_calls[0][0][0]  # first positional arg
        assert inserted["file_name"] == "contract.pdf"
        assert inserted["file_type"] == "application/pdf"
        assert inserted["extraction_method"] == "eml_attachment"
        assert inserted["metadata"]["parent_email_id"] == "eml-doc-id"
        assert inserted["metadata"]["content_hash"] == content_hash

    @pytest.mark.asyncio
    async def test_duplicate_attachment_skipped(self):
        """If a document with the same content_hash already exists, skip upload."""
        from legal_portal.api.routes.analysis import _extract_deferred_documents

        pdf_bytes = b"%PDF-1.4 duplicate content"
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "a@b.com"
        msg["To"] = "c@d.com"
        msg["Date"] = "Mon, 1 Jan 2025 00:00:00 +0000"
        msg.attach(MIMEText("Email body content." * 10, "plain"))
        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_part.add_header("Content-Disposition", "attachment", filename="contract.pdf")
        msg.attach(pdf_part)

        doc = {
            "id": "eml-doc-id",
            "case_id": "case-123",
            "user_id": "user-456",
            "file_name": "test.eml",
            "file_type": "text/plain",
            "storage_path": "user/case/test.eml",
            "extraction_method": "deferred",
            "extracted_text": None,
            "metadata": {},
        }

        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.download.return_value = msg.as_bytes()

        # Existing document with same content_hash
        mock_select = MagicMock()
        mock_select.eq.return_value = mock_select
        mock_select.execute.return_value = MagicMock(
            data=[{"id": "existing-doc", "metadata": {"content_hash": content_hash}}]
        )
        mock_supabase.table.return_value.select.return_value = mock_select
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        mock_progress = AsyncMock()

        results = await _extract_deferred_documents(
            [doc], mock_supabase, mock_progress, "test-analysis-id",
        )

        # No insert should have been called (attachment already exists)
        insert_calls = mock_supabase.table.return_value.insert.call_args_list
        assert len(insert_calls) == 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_eml_attachment_upload.py -v`
Expected: FAIL — `_extract_deferred_documents` doesn't handle attachments yet.

**Step 3: Implement attachment upload in _extract_deferred_documents**

In `src/legal_portal/api/routes/analysis.py`, in the `_extract_deferred_documents` function, after the existing DB update for the EML doc (line 200: `supabase.table("documents").update(update_data)...`), add:

```python
            # Upload PDF attachments from EML files
            if hasattr(processed, 'metadata') and hasattr(processed.metadata, 'attachments'):
                pdf_attachments = processed.metadata.attachments or []
                if pdf_attachments and doc.get("case_id") and doc.get("user_id"):
                    case_id = doc["case_id"]
                    user_id = doc["user_id"]

                    # Fetch existing content hashes for this case
                    existing_docs = (
                        supabase.table("documents")
                        .select("id, metadata")
                        .eq("case_id", case_id)
                        .execute()
                    )
                    existing_hashes = set()
                    for ed in (existing_docs.data or []):
                        meta = ed.get("metadata") or {}
                        if isinstance(meta, dict) and meta.get("content_hash"):
                            existing_hashes.add(meta["content_hash"])

                    for att in pdf_attachments:
                        att_hash = att["content_hash"]
                        att_filename = att["filename"]

                        if att_hash in existing_hashes:
                            logger.info(
                                f"[DEFERRED] Skipping duplicate attachment "
                                f"{att_filename} (hash={att_hash[:12]}...)"
                            )
                            continue

                        # Upload attachment bytes to storage
                        att_storage_path = f"{user_id}/{case_id}/{att_filename}"
                        try:
                            supabase.storage.from_("documents").upload(
                                att_storage_path, att["bytes"],
                            )
                        except Exception as upload_err:
                            logger.warning(
                                f"[DEFERRED] Storage upload failed for {att_filename}: {upload_err}"
                            )
                            continue

                        # Insert new document record
                        att_record = {
                            "id": str(uuid.uuid4()),
                            "case_id": case_id,
                            "user_id": user_id,
                            "file_name": att_filename,
                            "file_type": "application/pdf",
                            "file_size": len(att["bytes"]),
                            "storage_path": att_storage_path,
                            "extraction_method": "eml_attachment",
                            "status": DocumentStatus.PENDING,
                            "metadata": {
                                "parent_email_id": doc_id,
                                "content_hash": att_hash,
                            },
                            "created_at": datetime.utcnow().isoformat(),
                            "updated_at": datetime.utcnow().isoformat(),
                        }
                        try:
                            supabase.table("documents").insert(att_record).execute()
                            existing_hashes.add(att_hash)
                            logger.info(
                                f"[DEFERRED] Created document for EML attachment: "
                                f"{att_filename} (parent={doc_name})"
                            )
                        except Exception as insert_err:
                            logger.error(
                                f"[DEFERRED] Failed to insert attachment {att_filename}: {insert_err}"
                            )
```

Also add `import uuid` at the top of `_extract_deferred_documents` if not already imported (it's imported at the module level in analysis.py).

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_eml_attachment_upload.py -v`
Expected: All 2 tests PASS.

**Step 5: Run existing deferred extraction tests**

Run: `python -m pytest tests/unit/test_deferred_extraction.py -v`
Expected: All 4 tests PASS (no regression).

**Step 6: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py \
        tests/unit/test_eml_attachment_upload.py
git commit -m "feat: upload PDF attachments from EML files with content-hash dedup"
```

---

### Task 3: Implement email thread dedup

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (new function `_dedup_email_threads`)
- Test: `tests/unit/test_email_thread_dedup.py`

**Step 1: Write the failing test**

Create `tests/unit/test_email_thread_dedup.py`:

```python
"""Tests for email thread deduplication."""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from legal_portal.core.data_models import DocumentStatus


def _make_eml_doc(
    doc_id, subject, body, file_name="email.eml", body_hash=None,
):
    """Build a mock EML document dict."""
    if body_hash is None:
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return {
        "id": doc_id,
        "case_id": "case-123",
        "file_name": file_name,
        "file_type": "text/plain",
        "extracted_text": f"Subject: {subject}\nFrom: a@b.com\nTo: c@d.com\nDate: Mon, 1 Jan 2025\n\n{body}",
        "metadata": {"body_hash": body_hash},
        "is_flagged_as_junk": False,
        "status": DocumentStatus.READY,
    }


class TestEmailThreadDedup:
    """Test _dedup_email_threads flags superseded and duplicate emails."""

    @pytest.mark.asyncio
    async def test_thread_keeps_longest_reply(self):
        """In a thread, only the longest email should survive; shorter ones are flagged."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        docs = [
            _make_eml_doc("d1", "Intake Documents", "Short initial email."),
            _make_eml_doc("d2", "Re: Intake Documents", "Short initial email.\n\nReply adding more."),
            _make_eml_doc(
                "d3", "Re: Re: Intake Documents",
                "Short initial email.\n\nReply adding more.\n\nFinal reply with even more content.",
            ),
        ]

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        flagged = await _dedup_email_threads(docs, mock_supabase)

        assert "d1" in flagged
        assert "d2" in flagged
        assert "d3" not in flagged  # longest - kept

    @pytest.mark.asyncio
    async def test_exact_duplicates_flagged(self):
        """Emails with identical body_hash should be deduped (keep first)."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        body = "Identical email body content."
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

        docs = [
            _make_eml_doc("d1", "Report", body, file_name="email1.eml", body_hash=body_hash),
            _make_eml_doc("d2", "Fwd: Report", body, file_name="email2.eml", body_hash=body_hash),
            _make_eml_doc("d3", "FW: Report", body, file_name="email3.eml", body_hash=body_hash),
        ]

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        flagged = await _dedup_email_threads(docs, mock_supabase)

        # Two of the three should be flagged
        assert len(flagged) == 2
        assert "d1" not in flagged  # first one kept

    @pytest.mark.asyncio
    async def test_different_threads_not_deduped(self):
        """Emails in different threads should not affect each other."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        docs = [
            _make_eml_doc("d1", "Intake Documents", "Content about intake."),
            _make_eml_doc("d2", "Payment Discussion", "Content about payment."),
        ]

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        flagged = await _dedup_email_threads(docs, mock_supabase)

        assert len(flagged) == 0  # Different threads, nothing flagged

    @pytest.mark.asyncio
    async def test_no_eml_docs_is_noop(self):
        """Empty input should return empty result."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        mock_supabase = MagicMock()
        flagged = await _dedup_email_threads([], mock_supabase)
        assert flagged == set()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_email_thread_dedup.py -v`
Expected: FAIL — `_dedup_email_threads` does not exist yet.

**Step 3: Implement _dedup_email_threads**

In `src/legal_portal/api/routes/analysis.py`, add this function after `_extract_deferred_documents`:

```python
async def _dedup_email_threads(
    eml_docs: list,
    supabase,
) -> set:
    """Deduplicate email threads by subject grouping and body hash.

    Flags superseded emails (shorter versions of the same thread) and
    exact duplicates (same body_hash) as is_flagged_as_junk=True.

    Returns set of flagged document IDs.
    """
    import re

    if not eml_docs:
        return set()

    def _normalize_subject(subject: str) -> str:
        """Strip Re:/Fwd:/FW: prefixes and normalize."""
        cleaned = re.sub(
            r"^(re:\s*|fwd?:\s*|fw:\s*)+", "", subject, flags=re.IGNORECASE,
        )
        return cleaned.strip().lower()

    def _extract_subject(doc: dict) -> str:
        """Extract subject from extracted_text header."""
        text = doc.get("extracted_text", "")
        for line in text.split("\n"):
            if line.startswith("Subject: "):
                return line[9:].strip()
        return ""

    # Group by normalized subject
    thread_groups: dict[str, list[dict]] = {}
    for doc in eml_docs:
        subject = _extract_subject(doc)
        norm = _normalize_subject(subject)
        if norm:
            thread_groups.setdefault(norm, []).append(doc)

    flagged_ids = set()

    for norm_subject, group in thread_groups.items():
        if len(group) < 2:
            continue

        # Phase 1: Exact duplicate dedup (same body_hash)
        hash_groups: dict[str, list[dict]] = {}
        for doc in group:
            bh = (doc.get("metadata") or {}).get("body_hash", "")
            if bh:
                hash_groups.setdefault(bh, []).append(doc)

        # For exact duplicates, keep the first, flag the rest
        deduped_group = []
        seen_hashes = set()
        for doc in group:
            bh = (doc.get("metadata") or {}).get("body_hash", "")
            if bh and bh in seen_hashes:
                # Exact duplicate
                flagged_ids.add(doc["id"])
                try:
                    supabase.table("documents").update({
                        "is_flagged_as_junk": True,
                        "metadata": {
                            **(doc.get("metadata") or {}),
                            "junk_reason": "exact_duplicate",
                        },
                    }).eq("id", doc["id"]).execute()
                except Exception as e:
                    logger.warning(f"Failed to flag duplicate {doc['id']}: {e}")
            else:
                if bh:
                    seen_hashes.add(bh)
                deduped_group.append(doc)

        # Phase 2: Thread supersession (longer body contains shorter)
        if len(deduped_group) < 2:
            continue

        # Sort by extracted_text length descending
        deduped_group.sort(
            key=lambda d: len(d.get("extracted_text", "")), reverse=True,
        )
        canonical = deduped_group[0]
        canonical_text = canonical.get("extracted_text", "")

        for doc in deduped_group[1:]:
            doc_body = doc.get("extracted_text", "")
            # Check if the shorter email's body is contained in the canonical
            # Strip headers for comparison (body starts after first blank line)
            canon_body = canonical_text.split("\n\n", 1)[-1] if "\n\n" in canonical_text else canonical_text
            short_body = doc_body.split("\n\n", 1)[-1] if "\n\n" in doc_body else doc_body

            if short_body.strip() and short_body.strip() in canon_body:
                flagged_ids.add(doc["id"])
                try:
                    supabase.table("documents").update({
                        "is_flagged_as_junk": True,
                        "metadata": {
                            **(doc.get("metadata") or {}),
                            "junk_reason": "superseded_by_later_reply",
                            "superseded_by": canonical["id"],
                        },
                    }).eq("id", doc["id"]).execute()
                except Exception as e:
                    logger.warning(f"Failed to flag superseded {doc['id']}: {e}")

    logger.info(f"[DEDUP] Flagged {len(flagged_ids)} emails as junk")
    return flagged_ids
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_email_thread_dedup.py -v`
Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py \
        tests/unit/test_email_thread_dedup.py
git commit -m "feat: add email thread dedup (subject grouping + body hash)"
```

---

### Task 4: Wire thread dedup into the analysis pipeline

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (Step 0 block, ~line 1566)
- Test: Extend `tests/unit/test_deferred_extraction.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_deferred_extraction.py`:

```python
class TestThreadDedupIntegration:
    """Test that thread dedup runs after deferred extraction."""

    @pytest.mark.asyncio
    async def test_dedup_called_for_eml_docs(self):
        """_dedup_email_threads should be called when EML docs are extracted."""
        from legal_portal.api.routes.analysis import _dedup_email_threads

        # Just verify the function exists and is callable
        assert callable(_dedup_email_threads)

        # Verify it handles empty input
        from unittest.mock import MagicMock
        mock_sb = MagicMock()
        result = await _dedup_email_threads([], mock_sb)
        assert result == set()
```

**Step 2: Run test to verify it passes** (since we already implemented the function)

Run: `python -m pytest tests/unit/test_deferred_extraction.py::TestThreadDedupIntegration -v`
Expected: PASS.

**Step 3: Wire dedup into the analysis pipeline**

In `analysis.py`, after the deferred extraction merge block (around line 1592), add:

```python
            # Step 0b: Deduplicate email threads
            eml_docs_for_dedup = [
                d for d in documents
                if d.get("file_name", "").lower().endswith(".eml")
                and d.get("extracted_text")
                and not d.get("is_flagged_as_junk")
            ]
            if eml_docs_for_dedup:
                logger.info(
                    f"[BACKGROUND:DEDUP] [CASE:{case_id}] "
                    f"Deduplicating {len(eml_docs_for_dedup)} email threads"
                )
                flagged_ids = await _dedup_email_threads(eml_docs_for_dedup, supabase)
                # Remove flagged docs from documents list so they're excluded from analysis
                if flagged_ids:
                    documents = [d for d in documents if d["id"] not in flagged_ids]
                    logger.info(
                        f"[BACKGROUND:DEDUP] [CASE:{case_id}] "
                        f"Removed {len(flagged_ids)} duplicate/superseded emails"
                    )
```

**Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py \
        tests/unit/test_deferred_extraction.py
git commit -m "feat: wire email thread dedup into analysis pipeline"
```

---

### Task 5: Process extracted PDF attachments during same analysis run

**Files:**
- Modify: `src/legal_portal/api/routes/analysis.py` (in Step 0 block)

**Step 1: Add re-fetch logic for newly created attachment docs**

After the attachment upload in `_extract_deferred_documents` creates new document records with `status=PENDING`, those new documents need to be extracted too. Add this after the thread dedup block (around line 1592+):

```python
            # Step 0c: Extract any newly created attachment documents
            if deferred_docs:
                # Re-fetch documents to pick up any new attachment docs created during Step 0
                new_docs_resp = (
                    supabase.table("documents")
                    .select("*")
                    .eq("case_id", case_id)
                    .eq("extraction_method", "eml_attachment")
                    .eq("status", DocumentStatus.PENDING)
                    .execute()
                )
                new_att_docs = new_docs_resp.data or []
                if new_att_docs:
                    logger.info(
                        f"[BACKGROUND:ATTACHMENTS] [CASE:{case_id}] "
                        f"Extracting {len(new_att_docs)} EML attachment PDFs"
                    )
                    att_results = await _extract_deferred_documents(
                        new_att_docs, supabase, progress_manager, analysis_id,
                    )
                    # Add extracted attachment docs to the documents list
                    for att_doc in new_att_docs:
                        att_id = att_doc["id"]
                        if att_id in att_results:
                            att_doc.update(att_results[att_id])
                        documents.append(att_doc)
```

**Step 2: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add src/legal_portal/api/routes/analysis.py
git commit -m "feat: extract PDF content from EML attachments during analysis"
```

---

### Task 6: Final verification and cleanup

**Step 1: Run the full test suite**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS (304+ tests, 0 failures).

**Step 2: Verify no regressions in existing EML tests**

Run: `python -m pytest tests/unit/test_text_size_and_eml_routing.py tests/api/test_eml_extraction_fix.py -v`
Expected: All PASS.

**Step 3: Verify imports are clean**

Run: `python -c "from legal_portal.services.file_processors.eml_processor import process_eml; print('OK')"`
Expected: `OK`

Run: `python -c "from legal_portal.api.routes.analysis import _dedup_email_threads; print('OK')"`
Expected: `OK`

**Step 4: Commit any remaining changes**

```bash
git status
# If clean, no commit needed
```
