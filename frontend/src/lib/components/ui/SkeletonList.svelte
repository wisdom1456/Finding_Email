<!--
  SkeletonList - Loading placeholder for list content

  Pre-composed skeleton pattern for loading list items.
  Displays multiple rows with avatar and text placeholders.

  Props:
  - count?: number - Number of items to show (default: 3)
  - hasAvatar?: boolean - Include avatar circle (default: true)
  - class?: string - Additional CSS classes

  Usage:
    Basic list loading:
      SkeletonList with default props

    Without avatars:
      SkeletonList with hasAvatar=false

    Many items:
      SkeletonList with count=10
-->
<script lang="ts">
  import Skeleton from './Skeleton.svelte';

  let {
    count = 3,
    hasAvatar = true,
    class: className = '',
  }: {
    count?: number;
    hasAvatar?: boolean;
    class?: string;
  } = $props();
</script>

<div class="space-y-4 {className}">
  {#each Array(count) as _, i}
    <div class="flex items-start gap-3">
      {#if hasAvatar}
        <Skeleton variant="circle" width="40px" height="40px" class="flex-shrink-0" />
      {/if}

      <div class="flex-1 space-y-2">
        <Skeleton width="40%" height="16px" />
        <Skeleton width="100%" height="14px" />
        <Skeleton width="80%" height="14px" />
      </div>
    </div>
  {/each}
</div>
