# API Reference

## Overview

The Legal Document Analysis Portal backend provides a RESTful API built with FastAPI. All endpoints return JSON responses and use standard HTTP status codes.

## Base URL

- **Development**: `http://localhost:8000`
- **Production**: `https://your-production-domain.com`

## Authentication

Currently, the API does not require authentication. Future versions may implement API key or JWT-based authentication.

## API Endpoints

### Health Check

#### GET /health

Check if the API is running and healthy.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-31T17:24:00Z",
  "version": "1.0.0"
}
```

### Document Analysis

#### POST /api/v1/analysis/full-pipeline

Process uploaded documents through the complete analysis pipeline.

**Request:**
- Content-Type: `multipart/form-data`
- Body: Form data with file uploads and case information

**Form Fields:**
- `files`: Multiple file uploads (PDF, DOCX, DOC, TXT, EML)
- `case_name`: String - Name of the case
- `client_name`: String - Client name
- `attorney_name`: String - Attorney name
- `firm_name`: String - Law firm name

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/analysis/full-pipeline" \
  -H "Content-Type: multipart/form-data" \
  -F "files=@intake.pdf" \
  -F "files=@contract.docx" \
  -F "case_name=Smith vs Jones" \
  -F "client_name=John Smith" \
  -F "attorney_name=Jane Doe" \
  -F "firm_name=Legal Associates"
```

**Response:**
```json
{
  "case_id": "case_20250131_172400",
  "status": "completed",
  "processing_time": 245.7,
  "case_results": {
    "intake_analysis": {
      "client_info": {
        "name": "John Smith",
        "contact": "john@example.com",
        "address": "123 Main St"
      },
      "case_details": {
        "case_type": "Contract Dispute",
        "incident_date": "2024-01-15",
        "description": "Breach of service contract"
      }
    },
    "document_analysis": [
      {
        "filename": "contract.docx",
        "analysis": {
          "key_entities": ["John Smith", "ABC Corp"],
          "important_dates": ["2024-01-15"],
          "legal_issues": ["Breach of contract"],
          "summary": "Service contract between parties..."
        }
      }
    ],
    "timeline": [
      {
        "date": "2024-01-15",
        "event": "Contract signed",
        "source": "contract.docx"
      }
    ],
    "findings_letter": {
      "content": "Dear John Smith...",
      "download_links": {
        "eml": "data:message/rfc822;base64,....."
        "txt": "data:text/plain;base64,....."
      }
    }
  }
}
```

### File Processing

#### POST /api/v1/documents/process

Process individual documents for text extraction.

**Request:**
- Content-Type: `multipart/form-data`
- Body: Single file upload

**Response:**
```json
{
  "filename": "document.pdf",
  "file_type": "pdf",
  "file_size": 1024576,
  "text_content": "Extracted text content...",
  "metadata": {
    "pages": 10,
    "creation_date": "2024-01-15",
    "author": "Document Author"
  }
}
```

## Error Responses

### Standard Error Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid file format",
    "details": {
      "field": "files",
      "allowed_types": ["pdf", "docx", "doc", "txt", "eml"]
    }
  }
}
```

### HTTP Status Codes

- `200` - Success
- `400` - Bad Request (validation errors)
- `413` - Payload Too Large (file size exceeded)
- `415` - Unsupported Media Type (invalid file format)
- `422` - Unprocessable Entity (processing errors)
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error

### Common Error Codes

| Code | Description |
|------|-------------|
| `VALIDATION_ERROR` | Request validation failed |
| `FILE_TOO_LARGE` | File exceeds maximum size limit |
| `UNSUPPORTED_FILE_TYPE` | File type not supported |
| `PROCESSING_ERROR` | Error during document processing |
| `AI_SERVICE_ERROR` | Error from AI analysis service |
| `RATE_LIMIT_EXCEEDED` | Too many requests |

## Rate Limiting

The API implements rate limiting to ensure fair usage:

- **Document Processing**: 10 requests per minute per IP
- **Analysis Pipeline**: 5 requests per minute per IP

Rate limit headers are included in responses:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 8
X-RateLimit-Reset: 1643723040
```

## File Specifications

### Supported File Types

| Format | Extension | Max Size | Notes |
|--------|-----------|----------|-------|
| PDF | `.pdf` | 50MB | Text extraction via PDF.co API |
| Word Document | `.docx` | 25MB | Native Python processing |
| Legacy Word | `.doc` | 25MB | Converted to DOCX |
| Plain Text | `.txt` | 10MB | Direct text processing |
| Email | `.eml` | 10MB | Email header and body extraction |

### File Validation

- Maximum total upload size: 100MB
- Maximum number of files: 50 per request
- File name restrictions: No special characters
- Content validation: Files must contain readable text

## Response Formats

### Download Links

Files are returned as base64-encoded data URLs for immediate download:

```json
{
  "download_links": {
    "eml": "data:message/rfc822;base64,RnJvbTo6IGpvaG4uZG9l...",
    "txt": "data:text/plain;base64,RGVhciBKb2huIFNtaXRo..."
  }
}
```

### Date Formats

All dates use ISO 8601 format: `YYYY-MM-DDTHH:mm:ssZ`

### Currency and Numbers

- Currency values include currency code: `{"amount": 1500.00, "currency": "USD"}`
- Numbers use standard JSON number format

## SDK and Libraries

### Python Example

```python
import requests

# Upload files for analysis
files = [
    ('files', open('intake.pdf', 'rb')),
    ('files', open('contract.docx', 'rb'))
]

data = {
    'case_name': 'Smith vs Jones',
    'client_name': 'John Smith',
    'attorney_name': 'Jane Doe',
    'firm_name': 'Legal Associates'
}

response = requests.post(
    'http://localhost:8000/api/v1/analysis/full-pipeline',
    files=files,
    data=data
)

result = response.json()
print(f"Case ID: {result['case_id']}")
```

### JavaScript Example

```javascript
const formData = new FormData();
formData.append('files', fileInput.files[0]);
formData.append('case_name', 'Smith vs Jones');
formData.append('client_name', 'John Smith');

fetch('/api/v1/analysis/full-pipeline', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => console.log(data));
```

## Changelog

### Version 1.0.0
- Initial API release
- Document processing pipeline
- AI analysis integration
- Email generation functionality