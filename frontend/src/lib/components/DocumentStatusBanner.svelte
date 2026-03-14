<script lang="ts">
	import { CheckCircle2, AlertTriangle, XCircle, FileQuestion } from 'lucide-svelte';

	let { 
		stats = { ready: 0, review: 0, failed: 0, missing: 0 } 
	}: { 
		stats: { ready: number; review: number; failed: number; missing: number } 
	} = $props();
</script>

<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
	<!-- Ready -->
	<div class="bg-green-50 border border-green-100 rounded-xl p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
		<div class="bg-green-500/10 p-3 rounded-lg text-green-600">
			<CheckCircle2 class="w-6 h-6" />
		</div>
		<div>
			<div class="text-2xl font-bold text-green-700">{stats.ready}</div>
			<div class="text-xs font-medium text-green-600 uppercase tracking-wider">Ready</div>
		</div>
	</div>

	<!-- Needs Review -->
	<div class="bg-amber-50 border border-amber-100 rounded-xl p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
		<div class="bg-amber-500/10 p-3 rounded-lg text-amber-600">
			<AlertTriangle class="w-6 h-6" />
		</div>
		<div>
			<div class="text-2xl font-bold text-amber-700">{stats.review}</div>
			<div class="text-xs font-medium text-amber-600 uppercase tracking-wider">Review</div>
		</div>
	</div>

	<!-- Extraction Failed -->
	<div class="bg-red-50 border border-red-100 rounded-xl p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
		<div class="bg-red-500/10 p-3 rounded-lg text-red-600">
			<XCircle class="w-6 h-6" />
		</div>
		<div>
			<div class="text-2xl font-bold text-red-700">{stats.failed}</div>
			<div class="text-xs font-medium text-red-600 uppercase tracking-wider">Failed</div>
		</div>
	</div>

	<!-- Missing / Download Failed -->
	<div class="bg-gray-50 border border-gray-100 rounded-xl p-4 flex items-center gap-4 shadow-sm hover:shadow-md transition-shadow">
		<div class="bg-gray-500/10 p-3 rounded-lg text-gray-600">
			<FileQuestion class="w-6 h-6" />
		</div>
		<div>
			<div class="text-2xl font-bold text-gray-700">{stats.missing}</div>
			<div class="text-xs font-medium text-gray-600 uppercase tracking-wider">Missing</div>
		</div>
	</div>
</div>

