# Step 5: Document Categorization Implementation Guide

## Overview
Step 5 creates separate processing branches for intake forms and case documents using a Document Router (Code node) followed by two IF nodes for reliable routing. This approach has been validated to provide superior reliability compared to Switch nodes.

## Node Configuration

### 1. Document Router (Code Node)

**Node Name**: `Categorize Documents`
**Type**: Code
**Position**: After "Extract Binary Files" (Step 4)

**Configuration**:
- **JavaScript Code**: Copy content from [`Step5_DocumentRouter_Code.js`](Step5_DocumentRouter_Code.js)
- **Mode**: Run Once for All Items
- **Continue on Fail**: Disabled (we want to catch errors)

**Key Features**:
- Creates two separate output items (one per branch)
- Preserves binary data for each branch
- Adds routing metadata for the IF nodes
- Maintains error handling patterns from previous steps

### 2. Intake Form Router (IF Node)

**Node Name**: `Route Intake Form`
**Type**: IF
**Position**: After "Categorize Documents"

**IF Configuration**:
- **Expression**: `{{ $json.documentType === "intakeForm" }}`
- **Output on True**: Routes to intake form processing branch
- **Output on False**: No routing (item stops here if not intake form)

### 3. Case Documents Router (IF Node)

**Node Name**: `Route Case Documents`
**Type**: IF
**Position**: After "Categorize Documents" (parallel to "Route Intake Form")

**IF Configuration**:
- **Expression**: `{{ $json.documentType === "caseDocuments" }}`
- **Output on True**: Routes to case documents processing branch
- **Output on False**: No routing (item stops here if not case documents)

### 4. Temporary Response Nodes (For Testing)

For Step 5 testing, add temporary response nodes to each branch:

#### Intake Form Response Node
**Node Name**: `Intake Form Response`
**Type**: Respond to Webhook
**Position**: Connect to "Route Intake Form" true output

**Configuration**:
- **Response Body**: `{{ $json }}`
- **Response Code**: 200

#### Case Documents Response Node
**Node Name**: `Case Documents Response`
**Type**: Respond to Webhook
**Position**: Connect to "Route Case Documents" true output

**Configuration**:
- **Response Body**: `{{ $json }}`
- **Response Code**: 200

## Workflow Connections

```
Step 4 (Extract Binary Files)
    ↓
Categorize Documents (Code)
    ├── Route Intake Form (IF) → True → Intake Form Response (Temporary)
    └── Route Case Documents (IF) → True → Case Documents Response (Temporary)
```

## Data Flow Architecture

### Input from Step 4
The Document Router expects this structure from Step 4:
```json
{
  "isValid": true,
  "structuredData": {
    "caseInfo": { /* case information */ },
    "filesCatalog": {
      "intakeForm": { /* intake form metadata */ },
      "caseDocuments": [/* array of case documents */],
      "fileCount": 3,
      "totalFileSize": 1234567
    }
  }
}
```

### Output Branch 1: Intake Form
```json
{
  "documentType": "intakeForm",
  "caseInfo": {
    "clientName": "Yelena Gurevich",
    "caseReference": "CASE-2025-07-16",
    "attorneyName": "Lourdes Transki"
  },
  "intakeFormData": {
    "fileName": "intake_form.pdf",
    "fileSize": 579842,
    "mimeType": "application/pdf",
    "binaryDataReference": "intakeForm"
  },
  "processingMetadata": {
    "branch": "intake-analysis",
    "documentCount": 1,
    "priority": "high"
  }
}
```

### Output Branch 2: Case Documents
```json
{
  "documentType": "caseDocuments",
  "caseInfo": { /* same as above */ },
  "caseDocumentsData": {
    "documentCount": 2,
    "totalSize": 778069,
    "documents": [
      {
        "index": 1,
        "fileName": "document1.pdf",
        "fileSize": 389034,
        "mimeType": "application/pdf",
        "binaryDataReference": "caseDocument1"
      }
    ]
  },
  "processingMetadata": {
    "branch": "case-documents-analysis",
    "documentCount": 2,
    "priority": "normal"
  }
}
```

## Testing Procedures

### Test 1: Standard Document Set
**Input**: 1 intake form + 2 case documents
**Expected**: Two separate responses from different branches

### Test 2: Intake Form Only  
**Input**: 1 intake form + 0 case documents
**Expected**: Error response (case documents required)

### Test 3: Multiple Case Documents
**Input**: 1 intake form + 5 case documents
**Expected**: Two branches with appropriate document counts

### Testing Commands

Use the same curl command from Step 4 testing, but observe that you'll receive different responses depending on which branch processes first.

```bash
# Standard test with Fefer case files
curl -X POST https://brflorida.app.n8n.cloud/webhook/legal-analysis-upload \
  -F "clientName=Yelena Gurevich" \
  -F "attorneyName=Lourdes Transki" \
  -F "intakeForm=@path/to/intake.pdf" \
  -F "caseDocument0=@path/to/document1.pdf" \
  -F "caseDocument1=@path/to/document2.pdf"
```

## Success Criteria

✅ **Document Router Functionality**:
- Creates two output items from single input
- Preserves binary data for each branch
- Includes proper routing metadata

✅ **IF Node Routing**:
- Intake form items route through "Route Intake Form" IF node
- Case documents items route through "Route Case Documents" IF node
- No items lost or misrouted
- Reliable routing with 100% success rate

✅ **Data Integrity**:
- All case information preserved in both branches
- Binary data references correct for each branch
- File metadata accurate and complete

✅ **Error Handling**:
- Missing intake form triggers error
- Missing case documents triggers error
- Invalid data structure handled gracefully

## Implementation Notes

### Binary Data Handling
- Each branch receives only the binary data it needs
- Intake form branch gets `{ intakeForm: binaryData.intakeForm }`
- Case documents branch gets `{ caseDocument0: ..., caseDocument1: ... }`

### IF Node Behavior
- n8n IF nodes provide reliable binary routing decisions
- Each IF node evaluates a single condition independently
- True output routes to processing branch, false output stops routing
- Multiple items from Document Router are processed by each IF node

### Reliability Advantages
- IF nodes eliminate the routing inconsistencies found with Switch nodes
- Simpler expression evaluation reduces failure points
- Independent routing decisions enable better error isolation
- Clearer debugging when routing issues occur

### Future Integration
After Step 5 testing is complete:
- Remove temporary response nodes
- Connect each branch to appropriate analysis nodes (Step 6+)
- Implement merge logic for reuniting results

## Error Scenarios

### Missing File Catalog
**Symptom**: "File catalog is missing from Step 4 data"
**Solution**: Verify Step 4 completed successfully

### Invalid Document Type
**Symptom**: Item not routed to any branch
**Solution**: Check IF node expressions match code output values

### Binary Data Missing
**Symptom**: Files referenced but binary data empty
**Solution**: Verify Step 4 binary data passthrough working

### IF Node Not Triggering
**Symptom**: No items reaching response nodes
**Solution**: Verify IF node expressions and documentType values in data

## Next Steps

After Step 5 is validated:
1. Document findings in the main findings document
2. Plan Step 6: Document Information Extraction
3. Design branch-specific processing logic
4. Plan merge strategy for reuniting branches