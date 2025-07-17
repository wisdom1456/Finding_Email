# Legal Document Analysis Form - Output Structure Documentation

## Overview
This document describes the data structure and output format from the Bernhardt Riley Legal Document Analysis Portal form. This form collects case information, an intake form, and case documents for legal analysis processing.

## Form Purpose
The form is designed to collect all necessary information and documents for automated legal case analysis and findings letter generation.

## Output Data Structure

### JSON Data Fields (Text Inputs)
The form produces the following structured JSON data:

```json
{
  "clientName": "string",      // Required: Client's full name
  "caseReference": "string",   // Optional: Case reference number (e.g., "CASE-2024-001")
  "attorneyName": "string"     // Required: Responsible attorney's name
}
```

### Binary File Data
The form uploads files in the following structure:

#### Intake Form (Required)
- **Field Name**: `intakeForm`
- **Description**: Single required client intake form
- **Accepted Formats**: PDF, DOCX, DOC
- **Purpose**: Provides essential case context and client information

#### Case Documents (Required - at least 1)
- **Field Names**: `caseDocument0`, `caseDocument1`, `caseDocument2`, etc.
- **Description**: All relevant case materials
- **Accepted Formats**: PDF, DOCX, DOC, TXT
- **Examples**: Contracts, correspondence, pleadings, invoices, photos
- **Maximum Total Size**: 100MB

## Example Complete Output Structure

When the form is submitted, the processing system receives:

```javascript
{
  // Text data in JSON format
  json: {
    clientName: "Yelena Gurevich",
    caseReference: "CASE-2024-1", 
    attorneyName: "Lourdes Transki"
  },
  
  // Binary file data
  binary: {
    intakeForm: {
      fileName: "Fefer - Intake.pdf",
      size: 415679,
      mimeType: "application/pdf",
      data: [File Buffer]
    },
    caseDocument0: {
      fileName: "Fefer - Correspondence - parents to Carrfour - request for eviction notice.pdf",
      size: 344631,
      mimeType: "application/pdf", 
      data: [File Buffer]
    },
    caseDocument1: {
      fileName: "Fefer- Lease Addendum - Monthly Payment Adjustment.pdf",
      size: 633962,
      mimeType: "application/pdf",
      data: [File Buffer]
    },
    caseDocument2: {
      fileName: "Fefer - Lease Agreement 2023-24.pdf", 
      size: 3830649,
      mimeType: "application/pdf",
      data: [File Buffer]
    },
    caseDocument3: {
      fileName: "Fefer - Correspondence - parents to Carrfour… of David mental health crisis.pdf",
      size: 129611, 
      mimeType: "application/pdf",
      data: [File Buffer]
    }
  }
}
```

## Processing Expectations

### For AI Analysis Systems:
1. **Extract case context** from the intake form (required first)
2. **Process all case documents** in the context of the intake information
3. **Generate legal analysis** based on the combination of intake form + case documents
4. **Produce findings letter** that references both intake details and case document analysis

### Document Categories:
- **Intake Form**: Contains client information, case background, legal issues
- **Case Documents**: Supporting evidence, contracts, correspondence, legal filings

### Recommended Processing Order:
1. Parse intake form first to understand case context
2. Process case documents in the context established by intake form
3. Cross-reference information between intake and case documents
4. Generate comprehensive analysis incorporating all materials

## Validation Rules

### Required Fields:
- `clientName` - Must not be empty
- `attorneyName` - Must not be empty  
- `intakeForm` - Must be present and valid file
- At least one case document must be uploaded

### File Constraints:
- Total upload size must not exceed 100MB
- Only specified file formats accepted
- File names preserved for reference in analysis

## Use Cases

This form output structure supports:
- **Automated Legal Document Review**
- **Case Analysis and Summary Generation**
- **Professional Findings Letter Creation**
- **Client Communication Automation**
- **Legal Research and Precedent Matching**

## Technical Notes

- Files are uploaded via `multipart/form-data` encoding
- All file content is preserved as binary data
- Text fields are UTF-8 encoded
- File metadata (names, sizes, types) is preserved
- System maintains file order for processing consistency

## Integration Guidelines

When processing this form output:
1. Always validate presence of required `intakeForm`
2. Process intake form first to establish case context
3. Use case reference number for file organization if provided
4. Maintain attorney attribution throughout analysis
5. Preserve client confidentiality in all processing steps