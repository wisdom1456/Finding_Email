<script lang="ts">
	import { getApiUrl } from '$lib/config';
	import { getSecureSession } from '$lib/supabase';
	import { toastStore } from '$lib/stores/toastStore';
	import { parseMarkdown } from '$lib/utils/markdown';
	import { onDestroy } from 'svelte';
	import AsyncButton from '$lib/components/ui/AsyncButton.svelte';

	let {
		analysisId,
	}: {
		analysisId: string;
	} = $props();

	type ActiveChatRequest = {
		requestId: number;
		controller: AbortController;
		messageIndex: number;
	};

	let chatMessages = $state<Array<{ user: string; assistant: string }>>([]);
	let chatInput = $state('');
	let sendingMessage = $state(false);
	let activeChatRequest: ActiveChatRequest | null = null;
	let chatRequestCounter = 0;

	onDestroy(() => {
		activeChatRequest?.controller.abort();
		activeChatRequest = null;
	});

	async function sendChatMessage() {
		if (!chatInput.trim()) return;

		const message = chatInput.trim();
		chatInput = '';

		const previousRequest = activeChatRequest;
		if (previousRequest) {
			previousRequest.controller.abort();
			chatMessages = chatMessages.filter((_, idx) => idx !== previousRequest.messageIndex);
			activeChatRequest = null;
		}

		sendingMessage = true;

		// Add user message and placeholder for assistant
		const currentMessageIndex = chatMessages.length;
		chatMessages = [...chatMessages, { user: message, assistant: '' }];
		const controller = new AbortController();
		const requestId = ++chatRequestCounter;
		activeChatRequest = { requestId, controller, messageIndex: currentMessageIndex };
		const isCurrentRequest = () => activeChatRequest?.requestId === requestId;

		try {
			const { session, user } = await getSecureSession();
			if (!session || !user) throw new Error('Not authenticated');

			const apiUrl = getApiUrl();
			const chatPayload = { message };
			const response = await fetch(`${apiUrl}/api/analysis/${analysisId}/chat/stream`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.access_token}`
				},
				signal: controller.signal,
				body: JSON.stringify(chatPayload)
			});

			if (!response.ok) {
				const detail = await response.json().catch(() => ({}));
				throw new Error(detail?.detail || 'Chat request failed');
			}

			const reader = response.body?.getReader();
			if (!reader) throw new Error('No reader available');

			const decoder = new TextDecoder();
			let assistantResponse = '';
			let pendingAssistantTokens = '';
			let flushTimer: ReturnType<typeof setTimeout> | null = null;
			let processedEventCount = 0;

			const updateAssistantMessage = () => {
				if (!isCurrentRequest()) return;
				const nextMessages = [...chatMessages];
				const currentMessage = nextMessages[currentMessageIndex];
				if (!currentMessage) return;
				nextMessages[currentMessageIndex] = {
					...currentMessage,
					assistant: assistantResponse
				};
				chatMessages = nextMessages;
			};

			const flushAssistantTokens = () => {
				if (!isCurrentRequest()) return;
				if (pendingAssistantTokens) {
					assistantResponse += pendingAssistantTokens;
					pendingAssistantTokens = '';
					updateAssistantMessage();
				}
				if (flushTimer) {
					clearTimeout(flushTimer);
					flushTimer = null;
				}
			};

			const queueAssistantToken = (token: string) => {
				if (!isCurrentRequest()) return;
				pendingAssistantTokens += token;
				if (flushTimer) return;
				flushTimer = setTimeout(() => {
					if (!isCurrentRequest()) {
						pendingAssistantTokens = '';
						flushTimer = null;
						return;
					}
					if (!pendingAssistantTokens) {
						flushTimer = null;
						return;
					}
					assistantResponse += pendingAssistantTokens;
					pendingAssistantTokens = '';
					flushTimer = null;
					updateAssistantMessage();
				}, 50);
			};

			while (true) {
				if (!isCurrentRequest()) {
					throw new DOMException('Chat request superseded', 'AbortError');
				}
				const { done, value } = await reader.read();
				if (done) {
					flushAssistantTokens();
					break;
				}

				const chunk = decoder.decode(value);
				const lines = chunk.split('\n');

				for (const line of lines) {
					if (line.startsWith('data: ')) {
						try {
							const data = JSON.parse(line.slice(6));
							if (data.token) {
								queueAssistantToken(data.token);
							}
							if (data.done) {
								flushAssistantTokens();
								break;
							}
						} catch (e) {
							// Ignore parse errors for incomplete chunks
						}
					}

					processedEventCount += 1;
					if (processedEventCount % 150 === 0) {
						await new Promise((resolve) => setTimeout(resolve, 0));
					}
				}
			}
			flushAssistantTokens();
		} catch (err: any) {
			if (err?.name !== 'AbortError') {
				toastStore.error(err.message || 'Chat failed');
				if (isCurrentRequest()) {
					chatMessages = chatMessages.filter((_, idx) => idx !== currentMessageIndex);
				}
			}
		} finally {
			if (activeChatRequest?.requestId === requestId) {
				activeChatRequest = null;
				sendingMessage = false;
			}
		}
	}
</script>

<div class="card-standard h-[700px] flex flex-col">
	<div class="mb-6">
		<h3 class="text-xl font-heading font-bold text-contrast">Case Chat Assistant</h3>
		<p class="text-sm text-gray-500 mt-1">Ask questions about this case—responses include specific facts and citations.</p>
	</div>

	<div class="flex-1 overflow-y-auto space-y-6 mb-6 p-6 bg-gray-50 rounded-xl border border-gray-200 shadow-inner">
		{#if chatMessages.length === 0}
			<div class="h-full flex flex-col items-center justify-center text-center opacity-50">
				<svg class="w-12 h-12 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
				</svg>
				<p class="text-gray-500 font-medium">No messages yet. Ask a question to get started.</p>
			</div>
		{:else}
			{#each chatMessages as message}
				<div class="space-y-3 animate-fade-in-up">
					<div class="flex justify-end">
						<div class="bg-contrast text-white rounded-2xl rounded-tr-none px-5 py-3 max-w-[85%] shadow-sm text-sm font-medium">
							{message.user}
						</div>
					</div>
					<div class="flex justify-start">
						<div class="bg-white border border-gray-200 rounded-2xl rounded-tl-none px-5 py-3 max-w-[85%] text-gray-800 shadow-sm chat-prose text-sm">
							{#if message.assistant && message.assistant !== '...'}
								{@html parseMarkdown(message.assistant)}
							{:else}
								<div class="flex gap-1 py-1">
									<span class="w-1.5 h-1.5 bg-accent rounded-full animate-bounce"></span>
									<span class="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:0.2s]"></span>
									<span class="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:0.4s]"></span>
								</div>
							{/if}
						</div>
					</div>
				</div>
			{/each}
		{/if}
	</div>

	<div class="flex gap-3 bg-white p-2 rounded-lg border border-gray-200 shadow-sm focus-within:ring-2 focus-within:ring-accent/20 focus-within:border-accent transition-all">
		<textarea
		class="flex-1 border-0 focus:ring-0 text-sm py-3 px-4 text-contrast placeholder-gray-400 font-medium resize-none min-h-[48px] max-h-[200px]"
		rows="1"
		placeholder="Ask a question about case facts, documents, or legal strategy..."
		bind:value={chatInput}
		onkeydown={(event) => {
			if (event.key === 'Enter' && !event.shiftKey) {
				event.preventDefault();
				sendChatMessage();
			}
		}}
		disabled={sendingMessage}
	></textarea>
		<AsyncButton
			variant="primary"
			onclick={sendChatMessage}
			disabled={!chatInput.trim()}
			loading={sendingMessage}
			loadingText="..."
			class="px-6 rounded-md font-bold"
		>
			Send
		</AsyncButton>
	</div>
</div>
