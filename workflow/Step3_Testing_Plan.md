# Step 3 Testing & Verification Plan
**Node**: "Structure Intake Data"  
**Purpose**: Transform validated form data into standardized caseInfo structure

## Current Implementation Analysis

Based on [`Current-Workflow.json`](workflow/Current-Workflow.json:69), Step 3:

1. **Input**: Validated data from Step 2 with structure `{ isValid: true, validatedData: {...}, processingTimestamp: "..." }`
2. **Process**: Transform validated form data into standardized `caseInfo` structure 
3. **Output**: Structured data with metadata for subsequent workflow steps

## Test Cases

### Test Case 1: Valid Data Processing
**Input** (from Step 2):
```json
{
  "isValid": true,
  "validatedData": {
    "clientName": "Yelena Gurevich",
    "caseReference": "CASE-2024-1",
    "attorneyName": "Lourdes Transki"
  },
  "processingTimestamp": "2025-07-16T15:04:28.474Z"
}
```

**Expected Output**:
```json
{
  "isValid": true,
  "structuredData": {
    "caseInfo": {
      "clientName": "Yelena Gurevich",
      "caseReference": "CASE-2024-1",
      "attorneyName": "Lourdes Transki",
      "processingDate": "[ISO_TIMESTAMP]"
    },
    "dataProcessingStatus": {
      "intakeFormProcessed": true,
      "structuredAt": "[ISO_TIMESTAMP]",
      "dataQuality": "validated"
    },
    "nextStage": "document-processing"
  },
  "processingTimestamp": "2025-07-16T15:04:28.474Z",
  "message": "Intake form data successfully structured for processing"
}
```

### Test Case 2: Empty Case Reference Auto-Generation
**Input**:
```json
{
  "isValid": true,
  "validatedData": {
    "clientName": "John Doe",
    "caseReference": "",
    "attorneyName": "Jane Attorney"
  },
  "processingTimestamp": "2025-07-16T15:04:28.474Z"
}
```

**Expected Behavior**: Should auto-generate case reference as `CASE-2025-07-16`

### Test Case 3: Error Passthrough
**Input** (validation failure from Step 2):
```json
{
  "isValid": false,
  "errors": ["Missing required field: clientName"],
  "processingTimestamp": "2025-07-16T15:04:28.474Z"
}
```

**Expected Output**: Should pass through unchanged (no processing)

## Verification Steps

### 1. Frontend Integration Test
1. Navigate to: `https://findingemail-0w07x.kinsta.page`
2. Fill out form with test data:
   - Client Name: "Test Client Step 3"
   - Case Reference: "" (empty to test auto-generation)
   - Attorney Name: "Test Attorney"
3. Submit form (without files to isolate Step 3)
4. Check browser Network tab for response

### 2. N8N Execution Log Analysis
1. Access n8n Cloud dashboard
2. Go to workflow executions
3. Find most recent execution
4. Check each node's output:
   - **Webhook**: Form data in `body` structure
   - **Validate Form Data**: `isValid: true` with cleaned data
   - **Structure Intake Data**: Structured `caseInfo` format ✅
   - **Prepare Response**: Final formatted response

### 3. Data Structure Verification
Verify "Structure Intake Data" node output contains:
- ✅ `isValid: true`
- ✅ `structuredData.caseInfo` with all required fields
- ✅ `structuredData.dataProcessingStatus` with processing metadata
- ✅ `structuredData.nextStage: "document-processing"`
- ✅ Timestamp fields in valid ISO 8601 format
- ✅ Auto-generated case reference if empty (format: `CASE-YYYY-MM-DD`)

### 4. Specific Checks for Step 3

**Date/Time Handling**:
- ✅ `processingDate` is current timestamp
- ✅ `structuredAt` is current timestamp  
- ✅ Timestamps are in ISO 8601 format
- ✅ Auto-generated case references use correct date format

**Data Transformation**:
- ✅ `validatedData` fields properly mapped to `caseInfo` structure
- ✅ Metadata fields (`dataProcessingStatus`) correctly populated
- ✅ `nextStage` field set for workflow progression

**Error Handling**:
- ✅ Invalid input (missing `validatedData`) handled gracefully
- ✅ Error passthrough works correctly
- ✅ Malformed data doesn't crash the node

## Quick Test Command

```bash
curl -X POST https://brflorida.app.n8n.cloud/webhook/legal-analysis-upload \
  -H "Content-Type: application/json" \
  -H "Origin: https://findingemail-0w07x.kinsta.page" \
  -d '{
    "clientName": "Test Client Step 3",
    "caseReference": "",
    "attorneyName": "Test Attorney"
  }'
```

## Success Criteria

Step 3 passes if:
1. ✅ Valid data transforms into `caseInfo` structure
2. ✅ Empty case reference generates auto-ID with current date
3. ✅ Processing metadata correctly added
4. ✅ Error conditions pass through unchanged
5. ✅ Output format matches expected schema for Step 4 consumption
6. ✅ Timestamps consistent and properly formatted

## Critical Issues to Watch For

1. **Missing `caseInfo` Structure**: Output should have nested `caseInfo` object
2. **Incorrect Date Formatting**: Timestamps should be ISO 8601
3. **Auto-Generation Logic**: Empty case reference should create `CASE-[DATE]` format
4. **Error Passthrough Failure**: Invalid inputs should pass through without processing
5. **Metadata Missing**: `dataProcessingStatus` and `nextStage` must be present

## Next Steps After Testing

1. **If tests pass**: Document findings in Step 3 section
2. **If tests fail**: Identify specific issues and apply corrections
3. **After corrections**: Re-test and then complete documentation