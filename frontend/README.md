# Legal Document Analysis Portal - Frontend

SvelteKit 2 frontend with Svelte 5 (Runes), TypeScript, and Tailwind CSS v4.

## Development

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Type checking
npm run check

# Build for production
npm run build
```

## Testing

```bash
# Unit tests (Vitest)
npx vitest run

# Unit tests with coverage
npx vitest run --coverage

# Watch mode
npx vitest

# E2E tests (Playwright)
npx playwright test
```

## Project Structure

```
src/
├── lib/
│   ├── components/          # Svelte components
│   │   ├── ui/              # Reusable UI (AsyncButton, LoadingOverlay, etc.)
│   │   ├── ClioConnect.svelte
│   │   ├── ClioMatterSearch.svelte
│   │   └── ProgressIndicator.svelte
│   ├── stores/              # Svelte stores
│   │   ├── progressStore.ts # SSE progress tracking
│   │   ├── toastStore.ts    # Toast notifications
│   │   └── loadingStore.ts  # Global loading state
│   ├── utils/               # Utilities
│   │   ├── sseClient.ts     # Server-Sent Events client
│   │   └── pollingClient.ts # Polling fallback
│   ├── config.ts            # API URL configuration
│   └── supabase.ts          # Supabase client
└── routes/
    ├── app/
    │   ├── cases/            # Case management pages
    │   │   ├── [id]/         # Case detail, results
    │   │   └── new/          # New case creation
    │   └── +layout.svelte    # Authenticated layout
    ├── login/
    └── register/
```

## Environment Variables

Create `frontend/.env.local`:

```bash
PUBLIC_API_URL=http://localhost:8000
PUBLIC_SUPABASE_URL=https://your-project.supabase.co
PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## Key Patterns

- **Svelte 5 Runes**: Uses `$state`, `$derived`, `$effect` for reactivity
- **SSR Data Loading**: `+page.server.ts` files fetch data server-side
- **SSE Progress**: Real-time progress via `progressStore` with polling fallback
- **Vercel Adapter**: Configured for Vercel deployment via `@sveltejs/adapter-vercel`
