# Step 4: Binary Data Reception - Testing Procedures

## Prerequisites
- Completed Steps 1-3 and verified working
- Test files prepared (PDFs, DOCX files)
- Frontend application accessible

## Test Execution Steps

### 1. Prepare Test Files
Create a test folder with:
- `test-intake.pdf` (< 1MB) - Mock intake form
- `test-doc1.pdf` (< 5MB) - Case document 1
- `test-doc2.docx` (< 5MB) - Case document 2
- `large-file.pdf` (> 100MB) - For size limit testing
- `invalid-file.zip` - For file type validation testing

### 2. Valid File Upload Test
1. Open frontend at `https://findingemail-0w07x.kinsta.page`
2. Fill form fields:
   - Client Name: "Test Client Step 4"
   - Case Reference: "CASE-TEST-4"
   - Attorney Name: "Test Attorney"
3. Upload files:
   - Intake Form: Select `test-intake.pdf`
   - Case Documents: Add `test-doc1.pdf` and `test-doc2.docx`
4. Submit form
5. Check n8n execution:
   - Verify "Extract Binary Files" node output
   - Confirm file catalog structure
   - Check binary data preservation

### 3. Missing Intake Form Test
1. Refresh frontend
2. Fill form fields
3. Skip intake form upload
4. Add only case documents
5. Submit and verify error: "Required intake form is missing"

### 4. Invalid File Type Test
1. Refresh frontend
2. Fill form fields
3. Try uploading `invalid-file.zip`
4. Verify frontend prevents upload OR
5. If upload allowed, verify n8n returns error

### 5. Size Limit Test
1. Create multiple large PDFs totaling > 100MB
2. Upload all files
3. Submit and verify error message about size limit

### 6. No Files Test
1. Fill form fields only
2. Submit without any files
3. Verify error: "No files were uploaded"

## Expected Outputs

### Successful Upload
```json
{
  "isValid": true,
  "filesCatalog": {
    "intakeForm": {
      "fileName": "test-intake.pdf",
      "fileSize": 415679,
      "mimeType": "application/pdf",
      "uploadedAt": "2025-07-16T18:30:00.000Z"
    },
    "caseDocuments": [
      {
        "index": 0,
        "fileName": "test-doc1.pdf",
        "fileSize": 2344631,
        "mimeType": "application/pdf",
        "uploadedAt": "2025-07-16T18:30:00.000Z"
      },
      {
        "index": 1,
        "fileName": "test-doc2.docx",
        "fileSize": 633962,
        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "uploadedAt": "2025-07-16T18:30:00.000Z"
      }
    ],
    "totalFileSize": 3394272,
    "fileCount": 3
  },
  "message": "Files successfully received and cataloged"
}
```

### Error Scenarios
Each error test should produce appropriate error messages in the response.

## Verification Checklist

- [ ] Binary data accessible via `$items("Webhook")`
- [ ] File metadata correctly extracted
- [ ] File count accurate
- [ ] Total size calculation correct
- [ ] MIME type validation working
- [ ] Error messages clear and specific
- [ ] Binary data passed forward to next node
- [ ] Integration with Step 3 data maintained

## Debugging Tips

1. **Binary Data Not Found**
   - Check webhook node name matches exactly
   - Verify multipart/form-data encoding
   - Check browser Network tab for file upload

2. **File Size Issues**
   - Verify fileSize property exists
   - Check for undefined values
   - Ensure size calculation handles all files

3. **MIME Type Problems**
   - Log actual MIME types received
   - Verify browser sends correct types
   - Check file extension mapping

## Success Criteria

Step 4 passes when:
1. ✅ Valid uploads create complete file catalog
2. ✅ All file metadata accurately captured
3. ✅ Size limits enforced (100MB total)
4. ✅ File type validation working
5. ✅ Error handling covers all scenarios
6. ✅ Binary data preserved for downstream use
7. ✅ Integration with intake data successful