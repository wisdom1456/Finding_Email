<script lang="ts">
    import { CheckCircle2, PenLine, AlertCircle, Tag } from 'lucide-svelte';

    let {
        documents,
        activeFilters,
        onFilterToggle
    }: {
        documents: any[];
        activeFilters: Set<string>;
        onFilterToggle: (filter: string) => void;
    } = $props();

    // Missing signatures: use denormalized columns (signature_expected + signed_status)
    // Excludes emails and photos which should never trigger signature review
    const missingSigCount = $derived(
        documents.filter(d => {
            const sigExpected = d.signature_expected === true ||
                                d.metadata?.registry?.signature_expected === true;
            const sigSatisfied =
                d.signed_status === 'signed' ||
                d.metadata?.attorney_enrichment?.signature_verification === 'signed';
            return sigExpected && !sigSatisfied;
        }).length
    );

    // Low OCR quality
    const lowOcrCount = $derived(
        documents.filter(d => {
            const quality = d.metadata?.quality_score ?? 10;
            return quality < 5;
        }).length
    );

    // Needs type classification — uses denormalized document_type_label column
    const needsTypeCount = $derived(
        documents.filter(d => {
            return !d.document_type_label &&
                   !d.metadata?.attorney_enrichment?.document_type_override;
        }).length
    );

    // Ready docs
    const readyCount = $derived(documents.filter(d => d.status === 'ready').length);
    const totalCount = $derived(documents.length);

    // All-clear condition
    const allClear = $derived(missingSigCount === 0 && lowOcrCount === 0 && totalCount > 0);

    // Smart summary sentence parts
    const issueCount = $derived(missingSigCount + lowOcrCount + needsTypeCount);

    const summaryParts = $derived(() => {
        const parts: Array<{ text: string; color: string }> = [];
        if (missingSigCount > 0) {
            parts.push({ text: `${missingSigCount} missing signature${missingSigCount !== 1 ? 's' : ''}`, color: 'text-red-600' });
        }
        if (lowOcrCount > 0) {
            parts.push({ text: `${lowOcrCount} low OCR quality`, color: 'text-amber-600' });
        }
        if (needsTypeCount > 0) {
            parts.push({ text: `${needsTypeCount} unclassified type${needsTypeCount !== 1 ? 's' : ''}`, color: 'text-purple-600' });
        }
        return parts;
    });

    // Build the chip list
    const chips = $derived([
        {
            key: 'missing-signatures',
            label: 'Missing Signatures',
            count: missingSigCount,
            icon: PenLine,
            theme: 'bg-red-50 border-red-200 text-red-700',
            alwaysShow: false,
        },
        {
            key: 'low-ocr',
            label: 'Low OCR Quality',
            count: lowOcrCount,
            icon: AlertCircle,
            theme: 'bg-amber-50 border-amber-200 text-amber-700',
            alwaysShow: false,
        },
        {
            key: 'needs-type',
            label: 'Needs Classification',
            count: needsTypeCount,
            icon: Tag,
            theme: 'bg-purple-50 border-purple-200 text-purple-700',
            alwaysShow: false,
        },
        {
            key: 'ready',
            label: 'Ready',
            count: readyCount,
            icon: CheckCircle2,
            theme: 'bg-green-50 border-green-200 text-green-700',
            alwaysShow: true,
        },
    ].filter(chip => chip.alwaysShow || chip.count > 0));

    const progressPercent = $derived(totalCount > 0 ? Math.round((readyCount / totalCount) * 100) : 0);
    const progressWidth = $derived(totalCount > 0 ? (readyCount / totalCount) * 100 : 0);
</script>

<div class="bg-white rounded-2xl shadow-card p-6 mb-6">
    <!-- Summary line -->
    <div class="mb-4">
        {#if allClear}
            <p class="text-sm font-medium text-green-700">
                All {totalCount} documents verified and ready for analysis
            </p>
        {:else if totalCount === 0}
            <p class="text-sm font-medium text-gray-500">No documents loaded yet</p>
        {:else}
            <p class="text-sm font-medium text-gray-700">
                <span class="text-red-600 font-semibold">{issueCount} document{issueCount !== 1 ? 's' : ''}</span>
                <span> need attention</span>
                {#if summaryParts().length > 0}
                    <span>: </span>
                    {#each summaryParts() as part, i}
                        <span class={part.color + ' font-semibold'}>{part.text}</span>{#if i < summaryParts().length - 1}<span class="text-gray-500">, </span>{/if}
                    {/each}
                {/if}
            </p>
        {/if}
    </div>

    <!-- Filter chips row -->
    {#if chips.length > 0}
        <div class="flex flex-wrap gap-2 mb-4">
            {#each chips as chip}
                {@const isActive = activeFilters.has(chip.key)}
                <button
                    type="button"
                    onclick={() => onFilterToggle(chip.key)}
                    class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs transition-all duration-150
                           {chip.theme}
                           {isActive ? 'ring-2 ring-offset-1 ring-current font-bold' : 'font-medium hover:opacity-80'}"
                    aria-pressed={isActive}
                >
                    <chip.icon class="w-3.5 h-3.5" />
                    <span class="tabular-nums font-semibold">{chip.count}</span>
                    <span>{chip.label}</span>
                </button>
            {/each}
        </div>
    {/if}

    <!-- Progress bar -->
    <div class="mt-4">
        <div class="flex justify-between text-xs text-gray-500 mb-1">
            <span>{readyCount} of {totalCount} documents ready</span>
            <span>{progressPercent}%</span>
        </div>
        <div class="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
                class="h-full bg-accent rounded-full transition-all duration-500"
                style="width: {progressWidth}%"
            ></div>
        </div>
    </div>
</div>
