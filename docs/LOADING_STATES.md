# Loading States & User Feedback Guide

## Problem Statement

**Current Issues:**
- Buttons freeze with no visual feedback
- Users can click multiple times during async operations
- No indication that action is processing
- Poor UX leads to uncertainty and repeated clicks

**Solution:**
Multi-layer feedback system with cursor changes, disabled states, spinners, and overlays.

---

## Components Available

### 1. **AsyncButton** - Self-Managing Loading Button

**Use for:** Any async operation triggered by a button

```svelte
<script>
  import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
  
  async function handleDelete() {
    await api.delete('/case/123');
    // Button automatically shows loading state
  }
</script>

<AsyncButton 
  onclick={handleDelete}
  variant="danger"
  loadingText="Deleting..."
>
  Delete Case
</AsyncButton>
```

**Features:**
- ✅ Automatic loading state
- ✅ Prevents multiple clicks  
- ✅ Shows spinner + custom loading text
- ✅ Cursor changes to 'wait'
- ✅ Button disabled during operation

**Variants:**
- `primary` - Teal accent color (default)
- `secondary` - White with border
- `danger` - Red for destructive actions
- `ghost` - Transparent background

**Sizes:**
- `sm` - Small (text-xs, compact padding)
- `default` - Standard size
- `lg` - Large (text-base, more padding)

---

### 2. **LoadingOverlay** - Full-Screen Blocker

**Use for:** Operations that take >2s or are critical

```svelte
<script>
  import LoadingOverlay from '$lib/components/ui/LoadingOverlay.svelte';
  
  let showOverlay = $state(false);
  
  async function importFromClio() {
    showOverlay = true;
    try {
      await api.importDocuments(caseId);
    } finally {
      showOverlay = false;
    }
  }
</script>

<LoadingOverlay 
  show={showOverlay}
  message="Importing Documents"
  description="This may take a few minutes..."
  allowCancel={true}
  onCancel={() => /* cancel logic */}
/>
```

**Features:**
- ✅ Full-screen backdrop blur
- ✅ Blocks all user interaction
- ✅ Large centered spinner
- ✅ Custom message and description
- ✅ Optional cancel button

---

### 3. **loadingStore** - Global Loading State

**Use for:** Coordinating loading across components

```svelte
<script>
  import { loadingStore, withLoading } from '$lib/stores/loadingStore';
  
  // Automatic cursor management
  async function fetchData() {
    await withLoading('fetch-data', async () => {
      const response = await fetch('/api/data');
      return response.json();
    }, 'Loading data...');
  }
  
  // Manual control
  function startOperation() {
    loadingStore.start('my-operation', 'Processing...');
  }
  
  function finishOperation() {
    loadingStore.stop();
  }
</script>

<!-- Show loading indicator -->
{#if $loadingStore.isLoading}
  <div class="fixed top-4 right-4 bg-white rounded-lg shadow-lg p-4">
    <Loader2 class="h-4 w-4 animate-spin text-accent" />
    {$loadingStore.message || 'Loading...'}
  </div>
{/if}
```

**Features:**
- ✅ Centralized loading state
- ✅ Automatic document.body cursor management
- ✅ Track specific operations
- ✅ Global loading indicator

---

## Implementation Examples

### Example 1: Delete Button (Destructive Action)

**Before:**
```svelte
<button onclick={deleteCase}>
  Delete Case
</button>
```

**After:**
```svelte
<AsyncButton 
  onclick={deleteCase}
  variant="danger"
  loadingText="Deleting..."
  class="min-w-[120px]"
>
  Delete Case
</AsyncButton>
```

---

### Example 2: View Results (Navigation with Data Fetch)

**Before:**
```svelte
<button onclick={() => goto('/results')}>
  View Results
</button>
```

**After:**
```svelte
<script>
  let loading = $state(false);
  
  async function viewResults() {
    loading = true;
    try {
      // Pre-fetch data before navigation
      await fetch(`/api/analysis/${analysisId}`);
      goto('/results');
    } finally {
      loading = false;
    }
  }
</script>

<AsyncButton 
  onclick={viewResults}
  {loading}
  loadingText="Loading..."
>
  View Results
</AsyncButton>
```

---

### Example 3: Document Import (Long Operation)

**Before:**
```svelte
<script>
  async function importDocuments() {
    await api.importFromClio(matterId);
    // User has no feedback, might click again
  }
</script>

<button onclick={importDocuments}>
  Import from Clio
</button>
```

**After:**
```svelte
<script>
  import LoadingOverlay from '$lib/components/ui/LoadingOverlay.svelte';
  import AsyncButton from '$lib/components/ui/AsyncButton.svelte';
  
  let importing = $state(false);
  let progress = $state(0);
  
  async function importDocuments() {
    importing = true;
    try {
      // Use SSE for progress updates
      const eventSource = new EventSource(`/api/import/${matterId}`);
      eventSource.onmessage = (e) => {
        progress = JSON.parse(e.data).progress;
      };
      await waitForImportComplete();
    } finally {
      importing = false;
      progress = 0;
    }
  }
</script>

<AsyncButton 
  onclick={importDocuments}
  variant="primary"
  size="lg"
>
  Import from Clio
</AsyncButton>

<LoadingOverlay 
  show={importing}
  message="Importing Documents from Clio"
  description={`${progress}% complete - This may take a few minutes...`}
/>
```

---

### Example 4: Form Submission

**Before:**
```svelte
<form onsubmit={handleSubmit}>
  <button type="submit">Save</button>
</form>
```

**After:**
```svelte
<script>
  let submitting = $state(false);
  
  async function handleSubmit(e: Event) {
    e.preventDefault();
    submitting = true;
    
    try {
      await api.saveCase(caseData);
      toastStore.addToast({ message: 'Saved!', type: 'success' });
    } catch (error) {
      toastStore.addToast({ message: 'Error saving', type: 'error' });
    } finally {
      submitting = false;
    }
  }
</script>

<form onsubmit={handleSubmit}>
  <!-- form fields -->
  
  <AsyncButton 
    type="submit"
    loading={submitting}
    loadingText="Saving..."
    variant="primary"
  >
    Save Changes
  </AsyncButton>
</form>
```

---

## CSS Cursor Classes

Add these to `app.css` for instant cursor feedback:

```css
/* Loading cursor utilities */
.cursor-wait {
  cursor: wait !important;
}

.cursor-progress {
  cursor: progress !important;
}

.cursor-not-allowed {
  cursor: not-allowed !important;
}

/* Apply to children too */
.cursor-wait *,
.cursor-progress *,
.cursor-not-allowed * {
  cursor: inherit !important;
}
```

**Usage:**
```svelte
<div class={isLoading ? 'cursor-wait' : ''}>
  <!-- Content -->
</div>
```

---

## Best Practices

### ✅ DO

1. **Use AsyncButton for all async button clicks**
   - Automatic loading state
   - Prevents double-clicks
   - Consistent UX

2. **Show LoadingOverlay for operations >2 seconds**
   - Imports, exports, bulk operations
   - Prevents user from navigating away

3. **Provide specific loading text**
   - "Deleting..." not "Loading..."
   - "Importing 50 documents..." not "Please wait..."

4. **Disable form during submission**
   ```svelte
   <fieldset disabled={submitting}>
     <!-- form fields -->
   </fieldset>
   ```

5. **Use optimistic updates when possible**
   ```svelte
   // Update UI immediately
   cases = cases.filter(c => c.id !== deletedId);
   
   try {
     await api.delete(deletedId);
   } catch {
     // Revert on error
     cases = [...originalCases];
   }
   ```

### ❌ DON'T

1. **Don't use plain buttons for async operations**
   - No feedback = confused users

2. **Don't forget to handle errors**
   ```svelte
   // ❌ Bad
   async function save() {
     await api.save(data);
   }
   
   // ✅ Good
   async function save() {
     try {
       await api.save(data);
       toastStore.success('Saved!');
     } catch (error) {
       toastStore.error('Failed to save');
       throw error; // Let AsyncButton handle state
     }
   }
   ```

3. **Don't block UI for fast operations (<500ms)**
   - Just disable button, skip overlay

4. **Don't forget loading text**
   - Generic "Loading..." is lazy
   - Be specific: "Deleting case...", "Importing 10 files..."

---

## Migration Checklist

Search codebase for these patterns and update:

- [ ] `onclick={deleteCase}` → Use AsyncButton
- [ ] `onclick={() => goto(...)}` → Add loading state
- [ ] Form submit buttons → Use AsyncButton with type="submit"
- [ ] Document upload → Add LoadingOverlay
- [ ] Clio import → Add LoadingOverlay with progress
- [ ] Analysis start → Add LoadingOverlay
- [ ] Bulk operations → Add LoadingOverlay

---

## Testing

1. **Test double-click prevention**
   - Click button rapidly
   - Should only trigger once

2. **Test cursor changes**
   - Cursor should change to 'wait' immediately
   - Should reset after operation

3. **Test error handling**
   - Button should re-enable after error
   - Loading state should clear

4. **Test cancellation**
   - Cancel button should work
   - Operation should actually cancel (if supported)

---

## Performance Notes

- AsyncButton adds ~2KB to bundle (includes Loader2 icon)
- LoadingOverlay adds ~1KB
- loadingStore adds ~0.5KB
- **Total:** ~3.5KB for complete loading system

**Worth it?** Absolutely. Prevents support tickets and user frustration.

