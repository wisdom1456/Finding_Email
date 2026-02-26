<script lang="ts">
    import { Link2, X, Plus } from 'lucide-svelte';

    type Relationship = {
        related_doc_id: string;
        relationship_type: string;
        related_doc_name?: string;
    };

    type AvailableDoc = {
        id: string;
        name: string;
    };

    let {
        documentId,
        relationships = [],
        availableDocuments = [],
        onAddRelationship,
        onRemoveRelationship,
    }: {
        documentId: string;
        relationships: Relationship[];
        availableDocuments: AvailableDoc[];
        onAddRelationship: (relatedDocId: string, type: string) => void;
        onRemoveRelationship: (relatedDocId: string) => void;
    } = $props();

    let showDropdown = $state(false);
    let selectedDocId = $state('');
    let selectedType = $state('modifies');

    // Docs not already linked
    const unlinkedDocs = $derived(
        availableDocuments.filter(
            (d) => !relationships.some((r) => r.related_doc_id === d.id)
        )
    );

    function truncate(str: string, max = 20): string {
        return str.length > max ? str.slice(0, max) + '…' : str;
    }

    function handleAdd() {
        if (!selectedDocId) return;
        onAddRelationship(selectedDocId, selectedType);
        selectedDocId = '';
        selectedType = 'modifies';
        showDropdown = false;
    }

    function handleClickOutside(event: MouseEvent) {
        const target = event.target as HTMLElement;
        const wrapper = document.getElementById(`doc-rel-wrapper-${documentId}`);
        if (wrapper && !wrapper.contains(target)) {
            showDropdown = false;
        }
    }

    $effect(() => {
        if (showDropdown) {
            document.addEventListener('click', handleClickOutside);
        } else {
            document.removeEventListener('click', handleClickOutside);
        }
        return () => {
            document.removeEventListener('click', handleClickOutside);
        };
    });
</script>

<div
    id={`doc-rel-wrapper-${documentId}`}
    class="relative flex flex-wrap gap-2 items-center"
>
    <!-- Existing relationship pills -->
    {#each relationships as rel (rel.related_doc_id)}
        <span
            class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 border border-blue-200 text-blue-700"
        >
            <Link2 class="w-3 h-3 flex-shrink-0" />
            <span>{truncate(rel.related_doc_name ?? rel.related_doc_id)}</span>
            <em class="text-blue-500 not-italic">{rel.relationship_type}</em>
            <button
                type="button"
                data-remove={rel.related_doc_id}
                onclick={() => onRemoveRelationship(rel.related_doc_id)}
                class="ml-0.5 rounded-full hover:bg-blue-200 p-0.5 transition-colors"
                aria-label={`Remove relationship with ${rel.related_doc_name ?? rel.related_doc_id}`}
            >
                <X class="w-3 h-3" />
            </button>
        </span>
    {/each}

    <!-- "Link to..." trigger button -->
    <button
        type="button"
        onclick={() => (showDropdown = !showDropdown)}
        class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border border-dashed border-gray-300 text-gray-500 hover:border-accent hover:text-accent transition-colors cursor-pointer"
    >
        <Plus class="w-3 h-3" />
        Link to...
    </button>

    <!-- Dropdown panel -->
    {#if showDropdown}
        <div
            class="absolute z-50 mt-1 top-full left-0 bg-white rounded-xl shadow-lg border border-gray-200 p-3 min-w-64"
        >
            <div class="flex flex-col gap-2">
                <!-- Document selector -->
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1" for={`rel-doc-${documentId}`}>
                        Document
                    </label>
                    <select
                        id={`rel-doc-${documentId}`}
                        bind:value={selectedDocId}
                        class="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-300"
                    >
                        <option value="" disabled>Select a document…</option>
                        {#each unlinkedDocs as doc (doc.id)}
                            <option value={doc.id}>{doc.name}</option>
                        {/each}
                    </select>
                </div>

                <!-- Relationship type selector -->
                <div>
                    <label class="block text-xs font-medium text-gray-600 mb-1" for={`rel-type-${documentId}`}>
                        Relationship type
                    </label>
                    <select
                        id={`rel-type-${documentId}`}
                        bind:value={selectedType}
                        class="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-300"
                    >
                        <option value="modifies">modifies</option>
                        <option value="relates to">relates to</option>
                        <option value="supersedes">supersedes</option>
                        <option value="supports">supports</option>
                    </select>
                </div>

                <!-- Add button -->
                <button
                    type="button"
                    onclick={handleAdd}
                    disabled={!selectedDocId}
                    class="mt-1 w-full inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                    <Link2 class="w-3 h-3" />
                    Add Link
                </button>
            </div>
        </div>
    {/if}
</div>
