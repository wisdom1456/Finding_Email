# Multiple Intake Document Selection - Complete

## Feature Implemented

### User Request:
"Consider any document with the word 'intake' in the filename (not case sensitive). If there are multiple, display them all at the top and make the user select the one that is the actual intake document."

## Solution

### 1. Automatic Detection
- **All documents** with "intake" in filename (case-insensitive) are detected
- **Displayed at top** of documents list with blue highlighting
- **Sorted by**: Intake candidates first, then regular documents

### 2. Multiple Candidates Flow
When user clicks "Start Analysis":
1. **Check** if multiple intake candidates exist
2. **Check** if one is already marked as intake form
3. If **not marked** → Show selection modal
4. If **already marked** → Proceed with analysis
5. If **only one** candidate → Use it automatically

### 3. Selection Modal
Shows all intake candidates with:
- **Radio buttons** for selection
- **Document details**: filename, size, type
- **Preview** of first 150 characters
- **Visual indicators**: Clio badge, "CURRENT" badge for already-marked
- **Confirm button** to mark selected document and start analysis

## Implementation Details

### Frontend Changes (`frontend/src/routes/app/cases/[id]/+page.svelte`)

#### New State Variables:
```typescript
// Find all potential intake documents
let intakeCandidates = $derived(
  documents.filter(doc => doc.file_name.toLowerCase().includes('intake'))
);

// Selection modal state
let showIntakeDocumentSelector = $state(false);
let selectedIntakeDocId = $state<string | null>(null);
```

#### Enhanced Sorting:
```typescript
let sortedDocuments = $derived(
  [...documents].sort((a, b) => {
    const aHasIntake = a.file_name.toLowerCase().includes('intake');
    const bHasIntake = b.file_name.toLowerCase().includes('intake');
    
    // Both have "intake" - sort by explicitly marked, then by date
    if (aHasIntake && bHasIntake) {
      const aIsMarked = a.metadata?.is_intake_form || false;
      const bIsMarked = b.metadata?.is_intake_form || false;
      if (aIsMarked && !bIsMarked) return -1;
      if (!aIsMarked && bIsMarked) return 1;
      return by date
    }
    
    // Only one has "intake" - that one goes first
    if (aHasIntake && !bHasIntake) return -1;
    if (!aHasIntake && bHasIntake) return 1;
    
    // Neither has "intake" - sort by date
    return by date
  })
);
```

#### Updated startAnalysis():
```typescript
async function startAnalysis() {
  // Check for multiple intake candidates
  if (intakeCandidates.length > 1) {
    const markedIntake = intakeCandidates.find(doc => doc.metadata?.is_intake_form);
    if (!markedIntake) {
      // Show selection modal
      showIntakeDocumentSelector = true;
      return;
    }
  }
  
  // Proceed with analysis...
}
```

#### New confirmIntakeSelection():
```typescript
async function confirmIntakeSelection() {
  // Update selected document's metadata
  await supabase
    .from('documents')
    .update({ metadata: { ...metadata, is_intake_form: true } })
    .eq('id', selectedIntakeDocId);
  
  // Reload documents
  await loadDocuments();
  
  // Close modal and start analysis
  showIntakeDocumentSelector = false;
  await startAnalysis();
}
```

### Selection Modal UI

```
┌─────────────────────────────────────────────────┐
│ Select Intake Document                          │
│                                                 │
│ Multiple documents contain "intake" in their    │
│ filename. Please select which is the actual     │
│ intake form.                                    │
│                                                 │
│ ┌─────────────────────────────────────────────┐ │
│ │ ○ 🔗 Client_Intake_Form.pdf [CLIO] [DOCUME…│ │
│ │   2.1 MB • application/pdf                  │ │
│ │   Subject: Add subject Date: 2025-06-17...  │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│ ┌─────────────────────────────────────────────┐ │
│ │ ● 🔗 Intake_Call_Notes.txt [COMMUNICATION]  │ │
│ │   1.2 KB • text/plain [CURRENT]            │ │
│ │   Call duration via Dialpad: 47m 20s...     │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│               [Cancel] [Confirm & Start Analysis]│
└─────────────────────────────────────────────────┘
```

## User Flow

### Scenario 1: Single Intake Document
```
1. User imports matter
2. One document has "intake" in filename
3. User clicks "Start Analysis"
4. ✅ Analysis starts immediately (no modal)
```

### Scenario 2: Multiple Intake Documents (None Marked)
```
1. User imports matter
2. Multiple documents have "intake" in filename:
   - Client_Intake_Form.pdf
   - Intake_Call_Notes.txt
   - New_Client_Intake.docx
3. User clicks "Start Analysis"
4. 📋 Modal appears showing all 3 candidates
5. User selects "Client_Intake_Form.pdf"
6. User clicks "Confirm & Start Analysis"
7. ✅ Document marked as intake form
8. ✅ Analysis starts with correct intake
```

### Scenario 3: Multiple Intake Documents (One Already Marked)
```
1. User imports matter
2. Multiple documents have "intake" in filename
3. One is already marked with is_intake_form: true
4. User clicks "Start Analysis"
5. ✅ Analysis starts with marked document (no modal)
```

### Scenario 4: Re-selecting Intake
```
1. Analysis already run with wrong intake
2. User wants to change intake document
3. User clicks intake document badge in list
4. Modal appears (future enhancement)
5. User selects different document
6. User re-runs analysis
```

## Visual Indicators

### Documents List:
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  ← BLUE BG
┃ 📋 Client_Intake_Form.pdf             ┃  ← INTAKE #1
┃    [INTAKE FORM] [DOCUMENT] [processed]┃  ← HAS "INTAKE"
┃    2.1 MB • application/pdf            ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  ← BLUE BG
┃ 📄 Intake_Call_Notes.txt              ┃  ← INTAKE #2
┃    [COMMUNICATION] [processed]         ┃  ← HAS "INTAKE"
┃    1.2 KB • text/plain                 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

📄 Contract_Agreement.pdf [processed]      ← REGULAR DOC
📄 Evidence_Photo.jpg [uploaded]           ← REGULAR DOC
```

## Benefits

### ✅ User Control:
- User decides which is the actual intake form
- Clear visual comparison of all candidates
- Preview content before selecting

### ✅ Flexibility:
- Works with any filename containing "intake"
- Case-insensitive detection
- Handles Clio imports and manual uploads

### ✅ Smart Defaults:
- Single candidate → Auto-selected
- Already marked → Uses existing selection
- Multiple unmarked → Asks user

### ✅ Clear Feedback:
- All intake candidates highlighted at top
- Selected intake shows "INTAKE FORM" badge
- Modal shows current selection if re-selecting

## Edge Cases Handled

### 1. No Intake Documents:
- First document used as intake (existing behavior)

### 2. One Intake Document:
- Auto-selected, no modal shown

### 3. Multiple Intake Documents:
- Modal shown, user must choose

### 4. User Cancels Selection:
- Modal closes, analysis doesn't start

### 5. Re-running Analysis:
- Uses already-marked intake document
- No modal unless user wants to change

## Files Modified

1. **frontend/src/routes/app/cases/[id]/+page.svelte**
   - Added `intakeCandidates` derived state
   - Enhanced sorting to show all intake candidates first
   - Added `showIntakeDocumentSelector` state
   - Added `selectedIntakeDocId` state
   - Updated `startAnalysis()` to check for multiple candidates
   - Added `confirmIntakeSelection()` function
   - Added intake document selector modal UI

## Ready to Test! 🎉

Test scenarios:
1. ✅ Import matter with 1 intake document → Auto-selected
2. ✅ Import matter with 3 intake documents → Modal appears
3. ✅ Select intake and confirm → Document marked, analysis starts
4. ✅ All intake candidates shown at top of list
5. ✅ Already-marked intake → No modal, uses existing

The user now has full control over which document is used as the intake form when multiple candidates exist!

