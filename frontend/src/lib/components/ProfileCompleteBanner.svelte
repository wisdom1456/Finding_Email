<script lang="ts">
	import { AlertTriangle } from 'lucide-svelte';
	import { isProfileCompleteForLetters, type LetterProfile } from '$lib/profile';

	let { profile }: { profile: LetterProfile | null } = $props();

	let isIncomplete = $derived(!isProfileCompleteForLetters(profile));

	// What's specifically missing — keeps the message actionable
	let missing = $derived.by(() => {
		if (!profile) return ['full name', 'jurisdiction'];
		const items: string[] = [];
		const name = (profile.full_name ?? '').trim();
		const words = name.split(/\s+/).filter((w) => w.length > 0);
		if (words.length < 2) items.push('full name (first and last)');
		const j = (profile.default_jurisdiction ?? '').trim();
		if (!j) items.push('jurisdiction');
		return items;
	});
</script>

{#if isIncomplete}
	<div
		role="alert"
		aria-live="polite"
		class="bg-amber-50 border-l-4 border-amber-400 px-4 py-3 mb-4 rounded-r-md shadow-sm"
		data-testid="profile-complete-banner"
	>
		<div class="flex items-start gap-3 max-w-7xl mx-auto">
			<AlertTriangle class="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
			<div class="flex-1 min-w-0">
				<p class="text-sm font-medium text-amber-900">
					Complete your profile for quality letters
				</p>
				<p class="text-xs text-amber-700 mt-0.5">
					Missing: {missing.join(', ')}. Until these are set, generated letters
					may sign with placeholders instead of your name and jurisdiction.
				</p>
			</div>
			<a
				href="/app/settings"
				class="text-sm font-semibold text-amber-900 hover:text-amber-700 underline whitespace-nowrap"
			>
				Open Settings →
			</a>
		</div>
	</div>
{/if}
