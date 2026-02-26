<!--
  KeyFactsChips - Editable pill-shaped chips displaying key case facts

  Features:
  - Icon mapped from fact key name
  - Amber styling for unconfirmed facts, green for confirmed
  - Inline editing via Edit2 icon (hover-revealed)
  - Confirm button per unconfirmed chip; static Check icon for confirmed
-->
<script lang="ts">
  import { Calendar, DollarSign, Users, Home, Tag, Check, Edit2 } from 'lucide-svelte';

  let {
    facts,
    onFactUpdate,
    onFactConfirm
  }: {
    facts: Record<string, { value: string; confirmed: boolean }>;
    onFactUpdate: (key: string, value: string) => void;
    onFactConfirm: (key: string) => void;
  } = $props();

  // Track which chip is currently being edited
  let editingKey = $state<string | null>(null);
  let editValue = $state('');

  function getIcon(key: string) {
    const k = key.toLowerCase();
    if (k === 'date') return Calendar;
    if (k === 'amount' || k === 'price' || k === 'value') return DollarSign;
    if (k === 'parties' || k === 'buyer' || k === 'seller' || k === 'party') return Users;
    if (k === 'property' || k === 'address') return Home;
    return Tag;
  }

  function startEdit(key: string, currentValue: string) {
    editingKey = key;
    editValue = currentValue;
  }

  function commitEdit(key: string) {
    if (editingKey === key) {
      onFactUpdate(key, editValue);
      editingKey = null;
    }
  }

  function cancelEdit() {
    editingKey = null;
  }

  function handleKeydown(event: KeyboardEvent, key: string) {
    if (event.key === 'Enter') {
      commitEdit(key);
    } else if (event.key === 'Escape') {
      cancelEdit();
    }
  }

  function formatLabel(key: string): string {
    return key.charAt(0).toUpperCase() + key.slice(1);
  }

  // Svelte action: focuses the element on mount, avoiding the a11y-autofocus lint warning
  function focusOnMount(node: HTMLElement) {
    node.focus();
  }
</script>

<div class="flex flex-wrap gap-2 items-center">
  {#each Object.entries(facts) as [key, fact]}
    {@const Icon = getIcon(key)}
    {@const isEditing = editingKey === key}
    {@const chipStyle = fact.confirmed
      ? 'border border-green-200 bg-green-50 text-green-800'
      : 'border-2 border-dashed border-amber-300 bg-amber-50 text-amber-800'}

    <div
      data-key={key}
      class="group relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold cursor-default {chipStyle}"
    >
      <!-- Fact-type icon -->
      <Icon class="w-3.5 h-3.5 shrink-0" />

      <!-- Key label -->
      <span class="opacity-60 capitalize">{formatLabel(key)}:</span>

      <!-- Value or inline input -->
      {#if isEditing}
        <input
          class="bg-transparent border-b border-current outline-none w-24 text-xs font-semibold"
          bind:value={editValue}
          onblur={() => commitEdit(key)}
          onkeydown={(e) => handleKeydown(e, key)}
          use:focusOnMount
        />
      {:else}
        <span>{fact.value}</span>
      {/if}

      <!-- Confirmed: static Check icon; Unconfirmed: interactive confirm button -->
      {#if fact.confirmed}
        <Check class="w-3 h-3 shrink-0 text-green-600" />
      {:else}
        <button
          type="button"
          title="Confirm {key}"
          class="opacity-0 group-hover:opacity-100 transition-opacity ml-0.5 hover:text-amber-600"
          onclick={() => onFactConfirm(key)}
        >
          <Check class="w-3 h-3" />
        </button>
      {/if}

      <!-- Edit button (hover only) -->
      {#if !isEditing}
        <button
          type="button"
          title="Edit {key}"
          class="opacity-0 group-hover:opacity-100 transition-opacity hover:opacity-80"
          onclick={() => startEdit(key, fact.value)}
        >
          <Edit2 class="w-3 h-3" />
        </button>
      {/if}
    </div>
  {/each}
</div>
