import { writable } from 'svelte/store';

interface ClioState {
	connected: boolean;
	clioUserId: string | null;
	expiresAt: string | null;
}

function createClioStore() {
	const { subscribe, set, update } = writable<ClioState>({
		connected: false,
		clioUserId: null,
		expiresAt: null
	});

	return {
		subscribe,
		setConnected: (connected: boolean, clioUserId: string | null = null, expiresAt: string | null = null) =>
			set({ connected, clioUserId, expiresAt }),
		disconnect: () => set({ connected: false, clioUserId: null, expiresAt: null }),
		reset: () => set({ connected: false, clioUserId: null, expiresAt: null })
	};
}

export const clioStore = createClioStore();

