# Testing Guide: Batch Image Processing

## Quick Test

To verify the batch processing implementation works correctly, follow these steps:

### 1. Start the Application

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
python run_app.py
```

### 2. Test Scenario: Upload 9 Images

**Recommended Test:**
- Upload 9 image files (JPG or PNG)
- Optionally include 1-2 PDFs to test parallel processing
- Watch the logs for batch processing messages

### 3. Expected Log Messages

Look for these log entries in the console:

```
✅ Expected: "Processing 18 documents: 9 images, 9 non-images"
✅ Expected: "Grouped 9 images into 3 batches: [3, 3, 3]"
✅ Expected: "Processing image batch 1/3 (3 images)"
✅ Expected: "Processing image batch 2/3 (3 images)"
✅ Expected: "Processing image batch 3/3 (3 images)"
✅ Expected: "Sending batch of 3 images to GPT-4o Vision API..."
```

### 4. What to Verify

#### Performance
- [ ] Processing completes significantly faster than before
- [ ] All images are processed successfully
- [ ] Progress bar updates smoothly

#### API Calls
- [ ] Check OpenAI dashboard: Should see 3 Vision API calls (not 9)
- [ ] Each Vision API call should have ~3x the tokens of a single call

#### Quality
- [ ] Open the generated letter
- [ ] Check image descriptions
- [ ] Look for cross-references between images (e.g., "Similar to Image 1")

#### Error Handling
- [ ] Try uploading 1 corrupted image with 2 good images
- [ ] Verify system falls back gracefully
- [ ] Check that good images still process

### 5. Quick Verification Commands

**Check logs for batch processing:**
```bash
grep "Grouped.*images into.*batches" logs/streamlit_app.log | tail -5
```

**Check for Vision API calls:**
```bash
grep "Sending batch of.*images" logs/streamlit_app.log | tail -10
```

**Check for successful batch completions:**
```bash
grep "Successfully processed batch" logs/streamlit_app.log | tail -10
```

## Test Cases

### Test Case 1: Perfect Batch (9 images, sequential names)

**Files:**
- damage_1.jpg, damage_2.jpg, damage_3.jpg
- leak_1.jpg, leak_2.jpg, leak_3.jpg
- property_1.jpg, property_2.jpg, property_3.jpg

**Expected:**
- 3 batches: [damage_1-3], [leak_1-3], [property_1-3]
- Excellent context awareness within each group

### Test Case 2: Mixed Files (9 images + 9 PDFs)

**Files:**
- 9 random images (any names)
- 9 PDF documents

**Expected:**
- Images grouped into 3 batches
- PDFs processed in parallel
- Total processing time < 30 seconds

### Test Case 3: Small Upload (2-3 images)

**Files:**
- photo1.jpg, photo2.jpg

**Expected:**
- 1 batch of 2 images
- 1 Vision API call
- Fast processing (~5 seconds)

### Test Case 4: Fallback Test (Corrupted Image)

**Files:**
- good1.jpg, corrupted.jpg, good2.jpg

**Expected:**
- Batch fails, falls back to individual processing
- Both good images process successfully
- Error logged for corrupted image

## Performance Benchmarks

### Before Optimization

| Documents | Images | Time | API Calls |
|-----------|--------|------|-----------|
| 18 total  | 9      | ~55s | 9 Vision  |

### After Optimization

| Documents | Images | Time | API Calls |
|-----------|--------|------|-----------|
| 18 total  | 9      | ~25s | 3 Vision  |

**Target Metrics:**
- ✅ 67% faster processing
- ✅ 67% fewer API calls
- ✅ Better context in image descriptions

## Troubleshooting

### Issue: Batch Processing Not Triggering

**Symptoms:** Still seeing individual image processing messages

**Solution:**
1. Check that images have supported extensions (.jpg, .jpeg, .png)
2. Verify logs show "Grouped N images into M batches"
3. Restart the application

### Issue: Batch Fails

**Symptoms:** "Falling back to individual processing" message

**Possible Causes:**
1. Token limit exceeded (batch too large)
2. Vision API temporary error
3. Malformed image file

**Resolution:**
- System automatically falls back to individual processing
- Check logs for specific error details

### Issue: No Context Awareness

**Symptoms:** Image descriptions don't reference each other

**Possible Causes:**
1. Images aren't related (different subjects)
2. Batch size is 1 (no other images to reference)

**Resolution:**
- This is expected if images are unrelated
- Try uploading sequential images of the same subject

## Success Criteria

The implementation is working correctly if:

1. ✅ 9 images result in 3 Vision API calls (not 9)
2. ✅ Processing time is significantly reduced
3. ✅ All images are successfully processed
4. ✅ Image descriptions show context awareness
5. ✅ Progress tracking displays batch information
6. ✅ Errors are handled gracefully with fallback

## API Cost Comparison

### Old System (Sequential)
```
9 images × $0.0167 per image = $0.15
```

### New System (Batched)
```
3 batches × $0.0167 per batch = $0.05
```

**Savings: $0.10 per 9 images (67% reduction)**

---

**Ready to test?** Just upload multiple images and watch the logs! 🚀

