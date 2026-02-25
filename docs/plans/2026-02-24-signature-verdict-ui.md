# Signature Verdict UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Signed / Not Signed / Unclear verdict buttons to the VerificationHub document viewer modal footer so attorneys can record a signature verdict while viewing the PDF inline.

**Architecture:** All changes in one file — `VerificationHub.svelte`. Add 3 state vars, generalize the existing `handleMarkSigned()` into `handleSetVerdict()`, keep the old function as a thin wrapper (so DocumentCard `onMarkSigned` callbacks keep working), and replace the modal footer's sole "Close" button with a verdict button row + collapsible notes input.

**Tech Stack:** Svelte 5 ($state, $derived, {#snippet}), TypeScript, Tailwind CSS, existing `toastStore`, existing `/api/documents/{id}/verify` PATCH endpoint.

---

### Task 1: Add state variables for verdict UI

**Files:**
- Modify: `frontend/src/lib/components/VerificationHub.svelte` (near line 52, after `let viewingDocument`)

**Step 1: Add the three state variables**

Find the line:
```typescript
let viewingDocument = $state<any>(null);
```

Insert immediately after it:
```typescript
let verdictSaving = $state(false);
let verdictNotes = $state('');
let showNotesInput = $state(false);
```

**Step 2: Verify the file compiles (no build errors)**

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npx tsc --noEmit 2>&1 | head -30
```
Expected: no errors (or only pre-existing ones).

**Step 3: Commit**

```bash
git add frontend/src/lib/components/VerificationHub.svelte
git commit -m "feat: add verdict state vars to VerificationHub"
```

---

### Task 2: Add `handleSetVerdict()` and update `handleMarkSigned()`

**Files:**
- Modify: `frontend/src/lib/components/VerificationHub.svelte` (lines 173–196, the `handleMarkSigned` function)

**Step 1: Replace `handleMarkSigned` with a generalized version**

Find the entire `handleMarkSigned` function (lines ~173–196):
```typescript
async function handleMarkSigned(doc: any) {
```

Replace the entire function with:
```typescript
async function handleSetVerdict(verdict: 'signed' | 'not_signed' | 'unknown', notes?: string) {
		if (!viewingDocument) return;
		verdictSaving = true;
		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/documents/${viewingDocument.id}/verify`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`,
				},
				body: JSON.stringify({
					is_verified: Boolean(viewingDocument.is_verified),
					is_flagged_as_junk: Boolean(viewingDocument.is_flagged_as_junk),
					signature_verification: verdict,
					...(notes ? { signature_verification_notes: notes } : {}),
				}),
			});

			if (!response.ok) throw new Error('Failed to save signature verdict');

			// Optimistic local update so buttons reflect new state immediately
			if (!viewingDocument.metadata) viewingDocument.metadata = {};
			viewingDocument.metadata.signature_verification = {
				status: verdict,
				notes: notes || '',
			};
			showNotesInput = false;
			verdictNotes = '';

			const label = verdict === 'signed' ? 'Signed' : verdict === 'not_signed' ? 'Not Signed' : 'Unclear';
			toastStore.success(`Marked as ${label} (attorney verified)`);
			await onDocumentsUpdated();
		} catch (error: any) {
			toastStore.error(error.message);
		} finally {
			verdictSaving = false;
		}
	}

	// Thin wrapper so DocumentCard onMarkSigned callbacks continue to work
	async function handleMarkSigned(doc: any) {
		// Temporarily set viewingDocument so handleSetVerdict can use it,
		// then restore previous value
		const prev = viewingDocument;
		viewingDocument = doc;
		await handleSetVerdict('signed');
		if (!viewingDocument || viewingDocument.id === doc.id) {
			viewingDocument = prev;
		}
	}
```

**Step 2: Verify TypeScript**

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npx tsc --noEmit 2>&1 | head -30
```
Expected: no new errors.

**Step 3: Commit**

```bash
git add frontend/src/lib/components/VerificationHub.svelte
git commit -m "feat: generalize handleSetVerdict in VerificationHub"
```

---

### Task 3: Update the modal footer with verdict buttons

**Files:**
- Modify: `frontend/src/lib/components/VerificationHub.svelte` (lines ~1116–1122, the `{#snippet footer()}` block)

**Step 1: Replace the footer snippet**

Find:
```svelte
	{#snippet footer()}
		<button
			onclick={closeDocumentViewer}
			class="btn btn-secondary px-6"
		>
			Close
		</button>
	{/snippet}
```

Replace with:
```svelte
	{#snippet footer()}
		<!-- Verdict buttons -->
		{@const currentStatus = viewingDocument?.metadata?.signature_verification?.status}
		<div class="flex flex-wrap items-center gap-2 flex-1">
			<button
				onclick={() => handleSetVerdict('signed')}
				disabled={verdictSaving}
				class="btn btn-sm px-3 py-1.5 text-xs font-bold border transition-colors {currentStatus === 'signed'
					? 'bg-green-600 border-green-600 text-white'
					: 'bg-white border-green-300 text-green-700 hover:bg-green-50'}"
			>
				✓ Signed
			</button>
			<button
				onclick={() => handleSetVerdict('not_signed')}
				disabled={verdictSaving}
				class="btn btn-sm px-3 py-1.5 text-xs font-bold border transition-colors {currentStatus === 'not_signed'
					? 'bg-red-600 border-red-600 text-white'
					: 'bg-white border-red-300 text-red-700 hover:bg-red-50'}"
			>
				✗ Not Signed
			</button>
			<button
				onclick={() => { showNotesInput = !showNotesInput; verdictNotes = viewingDocument?.metadata?.signature_verification?.notes || ''; }}
				disabled={verdictSaving}
				class="btn btn-sm px-3 py-1.5 text-xs font-bold border transition-colors {currentStatus === 'unknown'
					? 'bg-amber-500 border-amber-500 text-white'
					: 'bg-white border-amber-300 text-amber-700 hover:bg-amber-50'}"
			>
				? Unclear…
			</button>

			{#if showNotesInput}
				<div class="w-full flex items-center gap-2 mt-1">
					<input
						type="text"
						bind:value={verdictNotes}
						placeholder="Add notes (optional)…"
						class="flex-1 text-xs border border-gray-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400"
					/>
					<button
						onclick={() => handleSetVerdict('unknown', verdictNotes)}
						disabled={verdictSaving}
						class="btn btn-sm px-3 py-1.5 text-xs font-bold bg-amber-500 text-white border-amber-500 hover:bg-amber-600"
					>
						{verdictSaving ? '…' : 'Save'}
					</button>
					<button
						onclick={() => { showNotesInput = false; verdictNotes = ''; }}
						class="btn btn-sm px-3 py-1.5 text-xs font-bold bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
					>
						Cancel
					</button>
				</div>
			{/if}
		</div>

		<button
			onclick={closeDocumentViewer}
			class="btn btn-secondary px-6"
		>
			Close
		</button>
	{/snippet}
```

**Step 2: Verify TypeScript**

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npx tsc --noEmit 2>&1 | head -30
```
Expected: no new errors.

**Step 3: Commit**

```bash
git add frontend/src/lib/components/VerificationHub.svelte
git commit -m "feat: add signature verdict buttons to viewer modal footer"
```

---

### Task 4: Reset notes input state when modal closes

**Files:**
- Modify: `frontend/src/lib/components/VerificationHub.svelte` (~line 502, the `closeDocumentViewer` / `viewingDocument = null` call)

**Background:** When the modal closes, `verdictNotes` and `showNotesInput` should reset so the next document doesn't inherit stale state.

**Step 1: Find the close function**

Search for `viewingDocument = null` — this is either in `closeDocumentViewer()` or assigned inline. It's around line 502.

**Step 2: Update the close function**

Find:
```typescript
viewingDocument = null;
```
(in the context of closing the viewer — there's likely a `function closeDocumentViewer()` or similar)

If it's inside a named function, replace the body to include cleanup:
```typescript
viewingDocument = null;
pdfBlobUrl = null;
previewBlobDocumentId = null;
documentSummary = null;
documentViewerTab = 'preview';
showNotesInput = false;
verdictNotes = '';
```

If those other resets are already there (check the function body), just add the two new lines:
```typescript
showNotesInput = false;
verdictNotes = '';
```

**Step 3: Verify TypeScript**

```bash
npx tsc --noEmit 2>&1 | head -30
```

**Step 4: Commit**

```bash
git add frontend/src/lib/components/VerificationHub.svelte
git commit -m "feat: reset verdict state on modal close"
```

---

### Task 5: Manual verification

**Step 1: Start the dev server**

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

**Step 2: Open a case in the browser and navigate to the Verification Hub**

- Open VerificationHub (Documents tab of any case with documents)
- Click "View" on any document

**Step 3: Verify the verdict buttons appear in the modal footer**

Expected: Footer shows `[ ✓ Signed ] [ ✗ Not Signed ] [ ? Unclear… ]` to the left of `[ Close ]`

**Step 4: Test "Signed"**

- Click "✓ Signed"
- Expected: Button turns green, toast "Marked as Signed (attorney verified)", DocumentCard signature badge updates

**Step 5: Close and reopen the modal**

- Close and click View on the same document
- Expected: "✓ Signed" button is pre-highlighted green (reflects saved state)

**Step 6: Test "Not Signed"**

- Click "✗ Not Signed"
- Expected: Red highlight, toast, state updates

**Step 7: Test "Unclear…" with notes**

- Click "? Unclear…"
- Expected: notes input row appears below buttons
- Type "Missing page 3 signature"
- Click "Save"
- Expected: Amber highlight, toast, notes saved

**Step 8: Test "Unclear…" Cancel**

- Click "? Unclear…" again
- Expected: notes input appears
- Click "Cancel"
- Expected: input disappears, no API call, state unchanged

**Step 9: Test existing "Mark Signed" button on DocumentCard still works**

- On any doc with signature review needed, click "Mark Signed" on the card directly (without opening the viewer)
- Expected: works as before

**Step 10: Final commit (if any cleanup needed)**

```bash
git add -p  # review any stray changes
git commit -m "chore: cleanup after manual verification"
```

---

## Summary of Changes

| File | What Changed |
|------|-------------|
| `frontend/src/lib/components/VerificationHub.svelte` | Added 3 state vars; generalized `handleSetVerdict()`; kept `handleMarkSigned()` as wrapper; replaced modal footer with verdict button row + collapsible notes input; reset state on close |

No backend changes. No new files. No new components.
