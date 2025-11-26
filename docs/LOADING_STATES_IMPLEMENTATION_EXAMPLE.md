# Loading States - Quick Implementation Example

## Real-World Example: Delete Case Button

### Before (Current Implementation)
```svelte
<!-- Delete button with no feedback -->
<button
    onclick={deleteCase}
    disabled={deleteCaseText !== 'DELETE'}
    class="px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
>
    Delete Case
</button>
```

**Problems:**
- ❌ No visual feedback during deletion
- ❌ User can click multiple times if network is slow  
- ❌ Cursor doesn't change
- ❌ No indication operation is in progress

---

### After (With AsyncButton)
```svelte
<script>
  import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
  
  let deleteCaseText = $state('');
  let deleting = $state(false);
  
  async function deleteCase() {
    try {
      const {
        data: { session }
      } = await supabase.auth.getSession();

      if (!session) {
        throw new Error('Not authenticated');
      }

      const apiUrl = getApiUrl();
      const response = await fetch(`${apiUrl}/api/cases/${caseId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${session.access_token}`
        }
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete case');
      }

      toastStore.addToast({ message: 'Case deleted successfully!', type: 'success' });
      goto('/app/cases');
    } catch (error: any) {
      errorMessage = error.message || 'Failed to delete case.';
      toastStore.addToast({ message: errorMessage, type: 'error' });
      throw error; // Re-throw to let AsyncButton handle loading state
    }
  }
</script>

<!-- Replace plain button with AsyncButton -->
<AsyncButton
    onclick={deleteCase}
    disabled={deleteCaseText !== 'DELETE'}
    loading={deleting}
    loadingText="Deleting..."
    variant="danger"
    class="min-w-[120px]"
>
    Delete Case
</AsyncButton>
```

**Benefits:**
- ✅ Automatic loading spinner
- ✅ Prevents double-clicks automatically
- ✅ Cursor changes to 'wait' 
- ✅ Shows "Deleting..." text
- ✅ Button stays disabled during operation
- ✅ Re-enables on error

---

## Quick Migration Pattern

### 1. Import AsyncButton
```svelte
import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
```

### 2. Replace `<button>` with `<AsyncButton>`
```diff
- <button onclick={myFunction}>
+ <AsyncButton onclick={myFunction}>
    Click Me
- </button>
+ </AsyncButton>
```

### 3. Add variant and loading text
```svelte
<AsyncButton 
    onclick={myFunction}
    variant="primary"      // or 'secondary', 'danger', 'ghost'
    loadingText="Processing..."
>
    Click Me
</AsyncButton>
```

### 4. Keep existing props
```svelte
<AsyncButton 
    onclick={myFunction}
    disabled={!formValid}
    class="my-custom-classes"
    type="submit"
    variant="primary"
    loadingText="Saving..."
>
    Save
</AsyncButton>
```

---

## Priority Buttons to Update

Search for these patterns in your codebase:

### High Priority (Destructive/Critical Operations)
- ✅ Delete case button → `variant="danger"`
- ✅ Delete document button → `variant="danger"`
- ✅ Import from Clio → Add LoadingOverlay + AsyncButton
- ✅ Start analysis → Add LoadingOverlay (can take 30+ seconds)

### Medium Priority (Data Fetching)
- ✅ View results button → `variant="primary"`
- ✅ Form submit buttons → `variant="primary"`
- ✅ Upload documents → Show progress indicator

### Low Priority (Fast Operations)
- ✅ Navigation buttons (instant, no loading needed)
- ✅ Modal open/close (instant, no loading needed)

---

## Testing Checklist

For each updated button, test:

1. **Click once** - Should show loading state immediately
2. **Try rapid clicking** - Should only trigger once
3. **Check cursor** - Should change to 'wait' cursor
4. **Wait for completion** - Button should re-enable
5. **Test error case** - Button should re-enable on error
6. **Check disabled state** - Disabled buttons shouldn't load

---

## Common Patterns

### Pattern 1: Simple Button
```svelte
<AsyncButton onclick={save} variant="primary" loadingText="Saving...">
    Save
</AsyncButton>
```

### Pattern 2: Button with Disabled Logic
```svelte
<AsyncButton 
    onclick={submit}
    disabled={!isValid}
    variant="primary"
    loadingText="Submitting..."
>
    Submit
</AsyncButton>
```

### Pattern 3: Destructive Action with Confirmation
```svelte
<script>
  let confirmText = $state('');
  
  async function deleteItem() {
    // Delete logic
  }
</script>

<AsyncButton 
    onclick={deleteItem}
    disabled={confirmText !== 'DELETE'}
    variant="danger"
    loadingText="Deleting..."
>
    Delete
</AsyncButton>
```

### Pattern 4: Form Submit
```svelte
<form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
    <!-- form fields -->
    
    <AsyncButton 
        type="submit"
        variant="primary"
        loadingText="Saving..."
    >
        Save Changes
    </AsyncButton>
</form>
```

### Pattern 5: With Loading Overlay (Long Operations)
```svelte
<script>
  import LoadingOverlay from '$lib/components/ui/LoadingOverlay.svelte';
  let importing = $state(false);
  
  async function importDocuments() {
    importing = true;
    try {
      await api.import(caseId);
    } finally {
      importing = false;
    }
  }
</script>

<AsyncButton 
    onclick={importDocuments}
    variant="primary"
>
    Import from Clio
</AsyncButton>

<LoadingOverlay 
    show={importing}
    message="Importing Documents"
    description="This may take several minutes..."
/>
```

---

## Gradual Migration Strategy

You don't have to update everything at once. Priority order:

### Week 1: Critical Operations
- Delete buttons
- Import/Export operations
- Any operation that takes >2 seconds

### Week 2: Forms
- All form submit buttons
- Create/Update operations

### Week 3: Polish
- Navigation with data fetching
- All remaining async buttons

### Week 4: Optimization
- Add progress indicators
- Implement optimistic updates
- Add cancellation support

---

## Need Help?

See `docs/LOADING_STATES.md` for complete documentation including:
- Full component API
- Advanced patterns
- Optimization techniques
- Troubleshooting guide

