# Case Edit Feature

## Overview

Added inline editing capability for case details on the case detail page. Users can now edit the client name, reference number, and description after a case has been created.

## Features

### Edit Button
- Located in the top-right corner of the "Case Details" section
- Pencil icon with "Edit" text
- Click to enter edit mode

### Edit Mode
When editing:
- Form appears in place of the read-only details
- All fields are editable:
  - **Client Name** (required)
  - **Reference Number** (optional)
  - **Description** (optional, multi-line textarea)
- Cancel button to discard changes
- Save Changes button (disabled until client name is entered)

### Save Functionality
- Sends PATCH request to `/api/cases/{case_id}`
- Only sends changed fields
- Updates the case in real-time
- Shows "Saving..." state on button
- Automatically refreshes the page data after save
- Returns to view mode after successful save

### Validation
- Client name is required (cannot be empty)
- Reference number and description are optional
- Save button disabled if client name is empty
- Error messages displayed if save fails

## User Experience

### How to Edit a Case

1. **Navigate** to the case detail page
2. **Click** the "Edit" button in the Case Details section
3. **Modify** any of the fields:
   - Client Name
   - Reference Number
   - Description
4. **Save** by clicking "Save Changes" button
5. **Or Cancel** to discard changes

### Visual Feedback

- **Edit Button**: Gray with pencil icon
- **Form Fields**: Standard input fields with focus states
- **Save Button**: Blue, changes to "Saving..." during save
- **Cancel Button**: Gray
- **Error Messages**: Red alert box if save fails
- **Success**: Returns to view mode, shows updated data

## Backend Integration

Uses existing backend endpoint:
```
PATCH /api/cases/{case_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "client_name": "Updated Name",
  "reference_number": "REF-123",
  "description": "Updated description"
}
```

### Backend Logic
- Only updates provided fields (partial updates supported)
- Validates user ownership via RLS
- Returns updated case data
- Respects Row Level Security policies

## Technical Details

### State Variables Added
```typescript
let editingCase = $state(false);        // Edit mode toggle
let editClientName = $state('');        // Client name field
let editReferenceNumber = $state('');   // Reference number field
let editDescription = $state('');       // Description field
let savingCase = $state(false);         // Saving state
```

### Functions Added
```typescript
startEditCase()   // Enters edit mode, populates form
cancelEditCase()  // Exits edit mode, clears form
saveCase()        // Saves changes via API
```

### API Integration
- Uses `fetch()` with PATCH method
- Includes authentication token
- Sends JSON payload with updated fields
- Handles errors gracefully
- Reloads case data after successful save

## UI Components

### Edit Button
```html
<button onclick={startEditCase}>
  <svg><!-- pencil icon --></svg>
  Edit
</button>
```

### Edit Form
- Three input fields (text, text, textarea)
- Cancel and Save buttons
- Form validation
- Disabled states during save

### View Mode
- Read-only display of case details
- Shows all fields in a grid layout
- Formatted dates for created/updated

## Error Handling

### Client-Side
- Validates required fields before submission
- Displays error messages in red alert box
- Prevents multiple simultaneous saves
- Disables buttons during save operation

### Server-Side
- Returns appropriate error codes (400, 403, 404, 500)
- Error messages include detail from backend
- Maintains edit mode if save fails (user can retry)

## Example Usage

### Before Edit
```
Case Details                           [Edit]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Client Name:        John Doe
Reference Number:   CASE-2024-001
Created:            Jan 15, 2024, 10:30 AM
Last Updated:       Jan 15, 2024, 10:30 AM
Description:        Initial consultation regarding...
```

### During Edit
```
Case Details
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Client Name *
[John Doe Updated              ]

Reference Number
[CASE-2024-001-REV            ]

Description
[Initial consultation regarding...
 Updated notes from second meeting
 with additional details          ]

                    [Cancel]  [Save Changes]
```

### After Save
```
Case Details                           [Edit]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Client Name:        John Doe Updated
Reference Number:   CASE-2024-001-REV
Created:            Jan 15, 2024, 10:30 AM
Last Updated:       Jan 15, 2024, 2:45 PM  ← Updated!
Description:        Initial consultation regarding...
                    Updated notes from second meeting
                    with additional details
```

## Testing Checklist

- [ ] Click Edit button enters edit mode
- [ ] Form populates with current values
- [ ] Can edit client name
- [ ] Can edit reference number
- [ ] Can edit description
- [ ] Cancel button discards changes
- [ ] Save button disabled when client name empty
- [ ] Save button shows "Saving..." during save
- [ ] Successful save updates the display
- [ ] Successful save shows new "Last Updated" time
- [ ] Error messages display on save failure
- [ ] Can edit again after successful save
- [ ] Form validation works (required fields)
- [ ] Multi-line description field works

## Future Enhancements

Potential improvements:
1. **Status Change**: Allow changing case status from detail page
2. **Audit Trail**: Show history of changes
3. **Auto-save**: Save changes automatically after typing stops
4. **Keyboard Shortcuts**: Ctrl+S to save, Esc to cancel
5. **Undo**: Undo last saved changes
6. **Rich Text**: Rich text editor for description
7. **Custom Fields**: Add custom metadata fields
8. **Bulk Edit**: Edit multiple cases at once

## Related Files

### Frontend
- `frontend/src/routes/app/cases/[id]/+page.svelte` - Case detail page with edit feature

### Backend
- `src/legal_portal/api/routes/cases.py` - PATCH endpoint at line 184-232

## Notes

- Edit button only appears when not in edit mode
- Cannot edit case status (requires separate workflow)
- Cannot edit created date (immutable)
- Last updated timestamp automatically updates on save
- All edits respect Row Level Security policies
- Users can only edit their own cases

