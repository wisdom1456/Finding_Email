<script lang="ts">
	import { slide } from 'svelte/transition';
	import {
		ChevronRight,
		Mail,
		FileStack,
		Image,
		Landmark,
		Layers,
		FileText
	} from 'lucide-svelte';
	import type { GroupType } from '$lib/types';
	import { GROUP_TYPE_LABELS } from '$lib/types';
	import Badge from './ui/Badge.svelte';

	interface Props {
		groupType: GroupType;
		label: string;
		memberCount: number;
		memberDocumentNames: string[];
		authorityScore?: number | null;
		narrative?: string;
		keyFindings?: string[];
		legalSignificance?: string | null;
		defaultExpanded?: boolean;
		onMemberClick?: (documentName: string) => void;
	}

	let {
		groupType,
		label,
		memberCount,
		memberDocumentNames,
		authorityScore = null,
		narrative = '',
		keyFindings = [],
		legalSignificance = null,
		defaultExpanded = false,
		onMemberClick
	}: Props = $props();

	let isExpanded = $state(defaultExpanded);

	const groupIcons: Record<string, typeof Mail> = {
		email_thread: Mail,
		contract_family: FileStack,
		photo_sequence: Image,
		bank_statements: Landmark,
		generic: Layers,
	};

	const groupColors: Record<string, string> = {
		email_thread: 'bg-blue-50 border-blue-200 text-blue-800',
		contract_family: 'bg-violet-50 border-violet-200 text-violet-800',
		photo_sequence: 'bg-amber-50 border-amber-200 text-amber-800',
		bank_statements: 'bg-emerald-50 border-emerald-200 text-emerald-800',
		generic: 'bg-gray-50 border-gray-200 text-gray-800',
	};

	const GroupIcon = $derived(groupIcons[groupType] || Layers);
	const colorClass = $derived(groupColors[groupType] || groupColors.generic);
	const typeLabel = $derived(GROUP_TYPE_LABELS[groupType] || 'Related Documents');

	function getPriorityLabel(score: number | null): string {
		if (score === null) return '';
		if (score >= 80) return 'High Priority';
		if (score >= 60) return 'Medium Priority';
		if (score >= 40) return 'Standard';
		return 'Low Priority';
	}

	function getPriorityColor(score: number | null): string {
		if (score === null) return '';
		if (score >= 80) return 'bg-red-100 text-red-700';
		if (score >= 60) return 'bg-amber-100 text-amber-700';
		return 'bg-gray-100 text-gray-600';
	}
</script>

<div class="border rounded-xl overflow-hidden transition-all duration-200 hover:shadow-md {colorClass}">
	<!-- Header -->
	<button
		onclick={() => isExpanded = !isExpanded}
		class="w-full p-4 sm:p-5 text-left flex items-start gap-3"
	>
		<div class="mt-0.5 p-2 rounded-lg bg-white shadow-sm flex-shrink-0">
			<GroupIcon class="w-5 h-5" />
		</div>

		<div class="flex-1 min-w-0">
			<div class="flex items-center gap-2 flex-wrap">
				<h4 class="text-sm font-bold truncate">{label}</h4>
				<ChevronRight
					class="w-4 h-4 transition-transform duration-200 flex-shrink-0 opacity-50 {isExpanded ? 'rotate-90' : ''}"
				/>
			</div>

			<div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
				<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border bg-white/60">
					{typeLabel}
				</span>
				<span class="text-xs text-current opacity-60">
					{memberCount} document{memberCount !== 1 ? 's' : ''}
				</span>
				{#if authorityScore !== null}
					<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold {getPriorityColor(authorityScore)}">
						{getPriorityLabel(authorityScore)}
					</span>
				{/if}
			</div>

			{#if narrative && !isExpanded}
				<p class="text-xs opacity-70 mt-2 line-clamp-2">{narrative}</p>
			{/if}
		</div>
	</button>

	<!-- Expanded content -->
	{#if isExpanded}
		<div class="px-4 sm:px-5 pb-4 sm:pb-5 space-y-4 border-t border-current/10" transition:slide={{ duration: 200 }}>
			<!-- Narrative -->
			{#if narrative}
				<div class="mt-4">
					<p class="text-xs font-semibold uppercase tracking-wide opacity-50 mb-1.5">Summary</p>
					<p class="text-sm leading-relaxed opacity-90">{narrative}</p>
				</div>
			{/if}

			<!-- Key Findings -->
			{#if keyFindings.length > 0}
				<div>
					<p class="text-xs font-semibold uppercase tracking-wide opacity-50 mb-1.5">Key Findings</p>
					<ul class="space-y-1">
						{#each keyFindings as finding}
							<li class="text-sm opacity-80 flex items-start gap-1.5">
								<span class="opacity-40 mt-0.5">-</span>
								<span>{finding}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			<!-- Legal Significance -->
			{#if legalSignificance}
				<div class="bg-white/50 rounded-lg p-3 border border-current/10">
					<p class="text-xs font-semibold uppercase tracking-wide opacity-50 mb-1">Legal Significance</p>
					<p class="text-sm opacity-90">{legalSignificance}</p>
				</div>
			{/if}

			<!-- Member Documents -->
			<div>
				<p class="text-xs font-semibold uppercase tracking-wide opacity-50 mb-1.5">
					Documents in this group ({memberCount})
				</p>
				<div class="flex flex-wrap gap-1.5">
					{#each memberDocumentNames as name}
						{#if onMemberClick}
							<button
								onclick={() => onMemberClick(name)}
								class="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs bg-white/70 border border-current/15 hover:bg-white hover:shadow-sm transition-all cursor-pointer"
								title="View {name}"
							>
								<FileText class="w-3 h-3 opacity-40" />
								<span class="truncate max-w-[180px]">{name}</span>
							</button>
						{:else}
							<span class="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs bg-white/70 border border-current/15">
								<FileText class="w-3 h-3 opacity-40" />
								<span class="truncate max-w-[180px]">{name}</span>
							</span>
						{/if}
					{/each}
				</div>
			</div>
		</div>
	{/if}
</div>
