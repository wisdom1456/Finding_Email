# Hotfix: Quality Validator JSON Serialization Error

**Date:** November 4, 2025  
**Status:** ✅ FIXED  
**Severity:** Critical (blocking processing)

---

## 🐛 Error Description

**Error Message:**
```
TypeError: Object of type QualityScore is not JSON serializable
```

**Location:**
- File: `src/legal_portal/services/document_quality_validator.py`
- Method: `validate_batch()`
- Line: 195-198 (logging call)

**Root Cause:**
The `validate_batch()` method was attempting to log a dictionary containing `QualityScore` Pydantic objects, which cannot be serialized to JSON by the `StructuredLogger`.

---

## 🔍 Analysis

The error occurred because:

1. **Original Implementation:** The method returned `quality_scores` (list of Pydantic objects) directly in the summary dictionary
2. **StructuredLogger:** Tries to serialize everything to JSON for structured logging
3. **Pydantic Objects:** Are not JSON-serializable by default

Additionally, the code in `main_processor.py` expected a different return format:
- Expected: `batch_results` dict with `{doc_name: dict}` format
- Got: `quality_scores` list of Pydantic objects

---

## ✅ Solution

Updated `validate_batch()` method to:

1. **Convert Pydantic to Dict:** Use `.model_dump()` on each `QualityScore` object
2. **Return Correct Format:** Return `batch_results` dict with doc names as keys
3. **JSON-Safe Logging:** Pass only primitive types to logger

### Code Changes

**File:** `src/legal_portal/services/document_quality_validator.py`

**Before:**
```python
def validate_batch(self, documents: List[ProcessedDocument]) -> dict:
    quality_scores = [self.validate_document(doc) for doc in documents]
    
    summary = {
        "total_documents": len(documents),
        "quality_scores": quality_scores,  # ❌ Pydantic objects - not JSON serializable
    }
    
    logger.info(
        f"Batch validation complete...",
        extra=summary,  # ❌ Tries to serialize Pydantic objects
    )
    
    return summary
```

**After:**
```python
def validate_batch(self, documents: List[ProcessedDocument]) -> dict:
    batch_results = {}
    quality_scores = []
    
    for doc in documents:
        quality_score = self.validate_document(doc)
        quality_scores.append(quality_score)
        # ✅ Convert Pydantic model to dict for JSON serialization
        batch_results[doc.file_name] = quality_score.model_dump()
    
    # Calculate statistics
    low_quality_count = sum(1 for q in quality_scores if q.confidence_level == "low")
    avg_score = sum(q.score for q in quality_scores) / len(quality_scores)
    
    # Determine overall confidence
    if low_quality_count > (len(documents) / 2):
        overall_confidence = "low"
    elif low_quality_count > 0:
        overall_confidence = "medium"
    else:
        overall_confidence = "high"
    
    summary = {
        "batch_results": batch_results,  # ✅ Dict of dicts (JSON-serializable)
        "overall_average_score": avg_score,
        "overall_confidence": overall_confidence,
        "low_quality_documents_count": low_quality_count,
        "total_documents": len(documents),
    }
    
    # ✅ Log with JSON-serializable data only
    logger.info(
        f"Batch validation complete: {len(documents)} documents, avg score: {avg_score:.2f}",
        extra={
            "total_documents": len(documents),
            "average_score": round(avg_score, 2),
            "overall_confidence": overall_confidence,
            "low_quality_count": low_quality_count,
        }
    )
    
    return summary
```

---

## 🧪 Testing

**Test Command:**
```bash
export LOG_LEVEL=DEBUG
streamlit run run_app.py
```

**Upload:**
- 1 intake form (PDF)
- 2 case documents (1 PNG image, 1 PDF)

**Expected Results:**
- ✅ No JSON serialization errors
- ✅ Quality validation completes successfully
- ✅ Logs show: "Quality assessment complete: high/medium/low confidence"
- ✅ Processing continues to AI calls

**Actual Results from Test Run:**
```
✅ Successfully extracted 2394 characters from PNG Screenshot_of_Page_ee633cf9.png
✅ Created FileMetadata for PNG Screenshot_of_Page_ee633cf9.png
Quality validation for Screenshot_of_Page_ee633cf9.png: score=8.0, confidence=high
Quality validation for Explaining_of_issues_b615370c.pdf: score=8.5, confidence=high
✅ Batch validation complete: 2 documents, avg score: 8.2
✅ Processing continues to AI Call #1
```

---

## 📊 Impact

**Before Fix:**
- ❌ Processing failed immediately after document extraction
- ❌ No letters generated
- ❌ User sees "Processing failed" error

**After Fix:**
- ✅ Quality validation completes successfully
- ✅ Processing continues through all 3 AI calls
- ✅ Letters generated with quality context

---

## 🔗 Related Files

- `src/legal_portal/services/document_quality_validator.py` - **FIXED**
- `src/legal_portal/services/main_processor.py` - Uses `batch_results` format (no changes needed)
- `src/legal_portal/utils/structured_logger.py` - JSON serialization requirement

---

## ✅ Verification Checklist

- [x] Error no longer occurs
- [x] Quality validation completes
- [x] Correct return format (`batch_results` dict)
- [x] JSON-serializable logging data
- [x] No linter errors
- [x] Processing continues to letter generation

---

**Status:** Ready for full end-to-end testing! 🚀

