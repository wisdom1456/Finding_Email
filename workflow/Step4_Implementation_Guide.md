# Step 4: Binary Data Reception - Implementation Guide

## Manual Node Creation Instructions

### 1. Access Your n8n Workflow

1. Open your n8n Cloud dashboard
2. Navigate to your "Generate Findings Email" workflow
3. Ensure you're in edit mode

### 2. Add the "Extract Binary Files" Node

1. **Position the Node**:
   - Click the "+" button on the connection line between "Structure Intake Data" and "Prepare Response"
   - This will insert a new node in the middle of the workflow

2. **Select Node Type**:
   - In the node selection menu, search for "Code"
   - Select "Code" node (not "Code Expression")

3. **Configure the Node**:
   - **Node Name**: Change from "Code" to "Extract Binary Files"
   - **Language**: JavaScript (should be default)
   - **Mode**: "Run Once for All Items" (should be default)

### 3. Add the JavaScript Code

1. **Copy the Code**:
   - Open [`Step4_ExtractBinaryFiles_Code.js`](workflow/Step4_ExtractBinaryFiles_Code.js)
   - Select all content (Ctrl+A / Cmd+A)
   - Copy (Ctrl+C / Cmd+C)

2. **Paste into n8n**:
   - In the Code node's code editor, clear any existing code
   - Paste the copied code (Ctrl+V / Cmd+V)
   - Verify the code appears correctly formatted

### 4. Verify Connections

After adding the node, your workflow should look like this:

```
Webhook → Validate Form Data → Structure Intake Data → Extract Binary Files → Prepare Response → Respond to Webhook
```

**Connection Details**:
- **Input**: "Extract Binary Files" receives data from "Structure Intake Data"
- **Output**: "Extract Binary Files" sends data to "Prepare Response"

### 5. Save the Workflow

1. Click "Save" in the top-right corner
2. Verify no syntax errors are reported
3. Ensure all connections are properly established

## Testing the Implementation

### 6. Prepare Test Files

Create test files on your computer:
- `test-intake.pdf` (any PDF under 5MB)
- `test-doc1.pdf` (any PDF under 5MB) 
- `test-doc2.docx` (any Word document under 5MB)

### 7. Execute Test

1. **Navigate to Frontend**:
   - Open `https://findingemail-0w07x.kinsta.page`

2. **Fill Form**:
   - Client Name: "Test Client Step 4"
   - Case Reference: "STEP4-TEST"
   - Attorney Name: "Test Attorney"

3. **Upload Files**:
   - Intake Form: Upload `test-intake.pdf`
   - Case Documents: Upload `test-doc1.pdf` and `test-doc2.docx`

4. **Submit Form**:
   - Click "Generate Findings Letter"
   - Monitor the submission process

### 8. Verify Results in n8n

1. **Check Execution**:
   - Go to n8n workflow executions
   - Find the most recent execution
   - Should show green (successful) status

2. **Examine "Extract Binary Files" Output**:
   ```json
   {
     "isValid": true,
     "filesCatalog": {
       "intakeForm": {
         "fileName": "test-intake.pdf",
         "fileSize": 123456,
         "mimeType": "application/pdf"
       },
       "caseDocuments": [
         {
           "index": 0,
           "fileName": "test-doc1.pdf",
           "fileSize": 234567,
           "mimeType": "application/pdf"
         },
         {
           "index": 1,
           "fileName": "test-doc2.docx",
           "fileSize": 345678,
           "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
         }
       ],
       "totalFileSize": 703701,
       "fileCount": 3
     }
   }
   ```

## Troubleshooting

### Common Issues

1. **"Cannot read property 'binary' of undefined"**
   - **Cause**: Webhook node name doesn't match code reference
   - **Solution**: Ensure webhook node is named exactly "Webhook"

2. **"No files were uploaded"**
   - **Cause**: Frontend not sending multipart/form-data
   - **Solution**: Check browser Network tab for file uploads

3. **"Invalid file type" errors**
   - **Cause**: Browser sending unexpected MIME types
   - **Solution**: Check actual MIME types in execution log

4. **Binary data not accessible**
   - **Cause**: Node positioning or connection issues
   - **Solution**: Verify node is correctly connected and positioned

### Debug Steps

1. **Add Console Logging** (if needed):
   ```javascript
   console.log("Binary data keys:", Object.keys(binaryData));
   console.log("Webhook items:", webhookItems.length);
   ```

2. **Check Binary Data Structure**:
   - Look at webhook node output in execution log
   - Verify binary section contains expected files

3. **Verify MIME Types**:
   - Common types: `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

## Success Criteria

✅ **Step 4 is successful when**:
1. Node executes without errors
2. File catalog is properly populated
3. Binary data is preserved and passed forward
4. File validation works correctly
5. Error handling responds appropriately to invalid inputs

## Next Steps

Once Step 4 is working:
1. Test all error scenarios (missing files, invalid types, size limits)
2. Verify frontend integration remains intact
3. Prepare for Step 5: Document Categorization
4. Document any findings or deviations in the main findings document

## Important Notes

- **Binary Data Preservation**: The node passes binary data forward using `binary: binaryData`
- **Webhook Reference**: Code uses `$items("Webhook")` - webhook node name must be exact
- **File Naming**: Frontend sends files as `intakeForm`, `caseDocument0`, `caseDocument1`, etc.
- **Size Calculation**: Total file size includes all uploaded files combined