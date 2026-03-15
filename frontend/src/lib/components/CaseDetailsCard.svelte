<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import { formatDate } from '$lib/utils/formatters';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';

	let {
		caseData,
		caseId,
		editingCase = $bindable(false),
		onsaved,
		onerror,
	}: {
		caseData: any;
		caseId: string;
		editingCase?: boolean;
		onsaved: () => void;
		onerror: (message: string) => void;
	} = $props();
	let editClientName = $state('');
	let editReferenceNumber = $state('');
	let editDescription = $state('');
	let savingCase = $state(false);

	function startEditCase() {
		if (!caseData) return;
		editClientName = caseData.client_name;
		editReferenceNumber = caseData.reference_number || '';
		editDescription = caseData.description || '';
		editingCase = true;
		onerror('');
	}

	function cancelEditCase() {
		editingCase = false;
		editClientName = '';
		editReferenceNumber = '';
		editDescription = '';
	}

	async function saveCase() {
		savingCase = true;
		onerror('');

		try {
			const { session, user } = await getSecureSession();

			if (!session || !user) throw new Error('Not authenticated');

			const response = await fetch(`${getApiUrl()}/api/cases/${caseId}`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				body: JSON.stringify({
					client_name: editClientName,
					reference_number: editReferenceNumber || null,
					description: editDescription || null
				})
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Failed to update case');
			}

			editingCase = false;
			onsaved();
		} catch (error: any) {
			onerror(error.message || 'Failed to update case');
		} finally {
			savingCase = false;
		}
	}

	export { startEditCase };
</script>

<div class="card-standard">
	<div class="flex justify-between items-center mb-4">
		<h3 class="text-lg font-semibold text-contrast">Case Details</h3>
	</div>

	{#if editingCase}
		<!-- Edit Form -->
		<form onsubmit={(e) => { e.preventDefault(); saveCase(); }} class="space-y-4">
			<div>
				<label for="edit-client-name" class="block text-sm font-medium text-contrast">
					Client Name <span class="text-red-500">*</span>
				</label>
				<input
					id="edit-client-name"
					type="text"
					bind:value={editClientName}
					required
					class="input-standard focus:ring-accent focus:border-accent"
				/>
			</div>

			<div>
				<label for="edit-reference-number" class="block text-sm font-medium text-contrast">
					Reference Number
				</label>
				<input
					id="edit-reference-number"
					type="text"
					bind:value={editReferenceNumber}
					class="input-standard focus:ring-accent focus:border-accent"
				/>
			</div>

			<div>
				<label for="edit-description" class="block text-sm font-medium text-contrast">
					Description
				</label>
				<textarea
					id="edit-description"
					bind:value={editDescription}
					rows="3"
					class="input-standard focus:ring-accent focus:border-accent"
				></textarea>
			</div>

			<div class="flex justify-end space-x-3 pt-2">
				<button
					type="button"
					onclick={cancelEditCase}
					disabled={savingCase}
					class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
				>
					Cancel
				</button>
				<AsyncButton
					type="submit"
					disabled={!editClientName.trim()}
					loading={savingCase}
					variant="primary"
					loadingText="Saving..."
				>
					Save Changes
				</AsyncButton>
			</div>
		</form>
	{:else}
		<!-- View Mode -->
		<dl class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
			<div>
				<dt class="text-sm font-medium text-gray-500">Client Name</dt>
				<dd class="mt-1 text-sm text-gray-900">{caseData.client_name}</dd>
			</div>
			<div>
				<dt class="text-sm font-medium text-gray-500">Jurisdiction</dt>
				<dd class="mt-1 text-sm text-gray-900">
					<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {caseData.jurisdiction === 'New Mexico' ? 'bg-indigo-100 text-indigo-800' : 'bg-orange-100 text-orange-800'}">
						{caseData.jurisdiction || 'Florida'}
					</span>
				</dd>
			</div>
			{#if caseData.reference_number}
				<div>
					<dt class="text-sm font-medium text-gray-500">Reference Number</dt>
					<dd class="mt-1 text-sm text-gray-900">{caseData.reference_number}</dd>
				</div>
			{/if}
			<div>
				<dt class="text-sm font-medium text-gray-500">Created</dt>
				<dd class="mt-1 text-sm text-gray-900">{formatDate(caseData.created_at)}</dd>
			</div>
			<div>
				<dt class="text-sm font-medium text-gray-500">Last Updated</dt>
				<dd class="mt-1 text-sm text-gray-900">{formatDate(caseData.updated_at)}</dd>
			</div>
			{#if caseData.description}
				<div class="sm:col-span-2">
					<dt class="text-sm font-medium text-gray-500">Description</dt>
					<dd class="mt-1 text-sm text-gray-900">{caseData.description}</dd>
				</div>
			{/if}
		</dl>
	{/if}
</div>
