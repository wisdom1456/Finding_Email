# Testing the Enhanced Upload Features

## Quick Start

### 1. Start the Backend
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
./start_backend.sh
```

Backend will start on: http://localhost:8000

### 2. Start the Frontend
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

Frontend will start on: http://localhost:5173

### 3. Login and Navigate
1. Open http://localhost:5173 in your browser
2. Login with your credentials
3. Navigate to a case or create a new one

## Feature Testing Guide

### Test 1: Multi-File Drag-and-Drop Upload

**Steps:**
1. Go to a case detail page
2. Drag 3-5 files onto the upload zone
3. Verify files appear in the list
4. Check that files show name and size

**Expected Result:**
- Dashed border turns blue on drag-over
- Files appear in a list below the drop zone
- Each file shows an X button to remove

### Test 2: Automatic Intake Form Detection (Single Match)

**Steps:**
1. Prepare files where ONE has "intake" in the filename
   - Example: `intake_form.pdf`, `medical_records.pdf`, `police_report.pdf`
2. Upload these files via drag-and-drop or file picker
3. Check the file list

**Expected Result:**
- File with "intake" in name shows blue "INTAKE FORM" badge
- No selector modal appears
- Other files don't have the badge

### Test 3: Multiple Intake Form Detection

**Steps:**
1. Prepare files where MULTIPLE have "intake" in the filename
   - Example: `intake_form.pdf`, `client_intake.pdf`, `other.pdf`
2. Upload these files
3. Modal should appear asking you to select

**Expected Result:**
- Modal appears: "Multiple files contain 'intake'"
- Radio buttons for each matching file
- Option for "No intake form"
- Must select one before uploading

### Test 4: No Intake Form Detection

**Steps:**
1. Prepare files with NO "intake" in filenames
   - Example: `document1.pdf`, `document2.pdf`
2. Upload these files
3. Modal should appear asking you to select

**Expected Result:**
- Modal appears: "No intake form detected"
- Radio buttons for all files
- Option for "No intake form - analyze all equally"
- Must make a selection before uploading

### Test 5: Remove Files Before Upload

**Steps:**
1. Select multiple files
2. Click the X button on one or more files
3. Verify files are removed from the list
4. Click "Upload Files"

**Expected Result:**
- Clicked files disappear from list
- Remaining files upload successfully
- Intake form selection adjusts if needed

### Test 6: Upload Progress

**Steps:**
1. Select 3-5 files
2. Click "Upload Files"
3. Watch the progress bar

**Expected Result:**
- Progress bar appears below file list
- Percentage increases from 0% to 100%
- "Uploading... X%" text shown
- Button disabled during upload

### Test 7: Document List with Intake Badge

**Steps:**
1. After successful upload
2. Scroll down to "Documents" section
3. Look at uploaded documents

**Expected Result:**
- All uploaded files appear in list
- File marked as intake has blue "INTAKE" badge
- Each file shows name, size, and type
- Status shows "uploaded"

### Test 8: Delete Document

**Steps:**
1. Hover over a document in the list
2. Trash icon appears
3. Click the trash icon
4. Confirmation modal appears
5. Click "Delete"

**Expected Result:**
- Trash icon appears on hover
- Modal shows document filename
- After confirmation, document disappears from list
- Page updates automatically

### Test 9: Delete Case

**Steps:**
1. On case detail page, click red "Delete Case" button
2. Read the warning in modal
3. Type "DELETE" in the text field
4. Click "Delete Case"

**Expected Result:**
- Modal shows case name and document count
- Warning about permanent deletion
- Delete button disabled until "DELETE" is typed
- After deletion, redirects to cases list

### Test 10: Analysis Uses Intake Form

**Steps:**
1. Upload documents with intake form marked
2. Click "Start Analysis"
3. Wait for analysis to complete
4. Check backend logs

**Expected Result:**
- Backend logs show: "Identified intake form: [filename]"
- Analysis completes successfully
- Results available in "View Results"

## Verification Checklist

After testing, verify:

- [ ] Can upload multiple files at once
- [ ] Drag-and-drop works smoothly
- [ ] Intake form auto-detection works
- [ ] Manual intake form selection works
- [ ] Can remove files before upload
- [ ] Upload progress shows correctly
- [ ] Uploaded documents show intake badge
- [ ] Can delete individual documents
- [ ] Can delete entire case
- [ ] Case deletion removes all documents
- [ ] Analysis uses correct intake form
- [ ] All confirmations work properly
- [ ] No console errors in browser
- [ ] No backend errors in logs

## Common Issues and Solutions

### Issue: Drag-and-drop doesn't work
**Solution:** Make sure you're dragging over the dashed border area, not the uploaded documents list.

### Issue: Upload fails with 403 error
**Solution:** Check that you're logged in and the session token is valid. Refresh the page and try again.

### Issue: Intake selector doesn't appear
**Solution:** This is expected if exactly one file has "intake" in the name. Check the file list for the badge.

### Issue: Document delete fails
**Solution:** Check backend logs for errors. Verify Supabase storage permissions.

### Issue: Case delete fails
**Solution:** Check backend logs. Verify the service client is properly configured for storage operations.

## Debug Tips

### Backend Logs
Look for these markers in the backend console:
```
🔍 DEBUG upload_document:
🔍 DEBUG delete_document:
🔍 DEBUG delete_case:
  - Identified intake form: [filename]
✅ Success messages
❌ Error messages
```

### Frontend Console
Open browser console (F12) and look for:
- Network requests to `/api/documents/upload`
- Network requests to `/api/documents/{id}` (DELETE)
- Network requests to `/api/cases/{id}` (DELETE)
- Any red error messages

### Network Tab
Check the Network tab in browser DevTools:
- Verify POST to `/api/documents/upload` includes `is_intake_form` in FormData
- Verify DELETE requests return 204 No Content
- Check Authorization headers are present

## Test Data Preparation

Create test files for uploading:

### Scenario 1: Clear Intake Form
```
Files:
- intake_form.pdf (mock intake form)
- medical_records.pdf
- police_report.pdf
```

### Scenario 2: Ambiguous Intake Forms
```
Files:
- client_intake.pdf
- intake_questionnaire.pdf
- witness_statement.pdf
```

### Scenario 3: No Intake Form
```
Files:
- evidence_photo1.jpg
- evidence_photo2.jpg
- witness_statement.pdf
```

## Success Criteria

All tests pass if:
1. ✅ Can upload multiple files via drag-and-drop
2. ✅ Intake form is correctly detected and marked
3. ✅ Can manually select intake form when needed
4. ✅ Can remove individual files before upload
5. ✅ Upload progress is visible and accurate
6. ✅ Documents appear with correct badges
7. ✅ Can delete documents with confirmation
8. ✅ Can delete cases with confirmation
9. ✅ All storage files are cleaned up
10. ✅ Analysis uses the marked intake form

## Next Steps After Testing

If all tests pass:
1. ✅ Implementation complete
2. Consider deploying to staging environment
3. Create user documentation
4. Train users on new features

If tests fail:
1. Check debug logs for errors
2. Verify environment variables
3. Check Supabase RLS policies
4. Review network requests for failures
5. Report specific error messages

## Questions or Issues?

If you encounter any problems:
1. Check `ENHANCED_UPLOAD_FEATURES.md` for detailed implementation info
2. Review backend logs for 🔍 DEBUG markers
3. Check browser console for JavaScript errors
4. Verify Supabase configuration in `.env`

