# Tailwind CSS v4 Configuration

## Overview

This project uses **Tailwind CSS v4**, which has a fundamentally different configuration system than v3.

## Key Differences from v3

| Feature | Tailwind v3 | Tailwind v4 |
|---------|-------------|-------------|
| Configuration | `tailwind.config.js` | `@theme` directive in CSS |
| Custom Colors | JS object in config | CSS variables in `@theme` |
| Plugins | JS plugins array | Native CSS features |
| Content Scanning | Manual glob patterns | Automatic detection |

## Current Configuration

### Location
**File:** `frontend/src/app.css`

### Brand Colors
All Bernhardt Riley brand colors are defined in the `@theme` directive:

```css
@theme {
  /* Brand Colors */
  --color-contrast: #181A31;        /* Dark navy for headers */
  --color-contrast-light: #39428E;  /* Secondary text */
  --color-accent: #5AB7A3;          /* Teal for CTAs */
  --color-accent-hover: #49998A;    /* Hover state */
  --color-accent-light: #E8F5F2;    /* Light backgrounds */
  
  /* Primary Palette (50-900) */
  --color-primary-50: #E8F5F2;
  --color-primary-100: #D1EBE5;
  /* ... etc ... */
}
```

### Available Tailwind Classes

Once defined in `@theme`, these colors are automatically available as Tailwind utilities:

#### Background Colors
- `bg-accent` → `#5AB7A3`
- `bg-accent-hover` → `#49998A`
- `bg-accent-light` → `#E8F5F2`
- `bg-accent/10` → 10% opacity accent
- `bg-contrast` → `#181A31`
- `bg-contrast-light` → `#39428E`
- `bg-primary-{50-900}` → Full palette

#### Text Colors
- `text-accent` → `#5AB7A3`
- `text-accent-hover` → `#49998A`
- `text-contrast` → `#181A31`
- `text-contrast-light` → `#39428E`
- `text-primary-{50-900}` → Full palette

#### Border Colors
- `border-accent` → `#5AB7A3`
- `border-accent-hover` → `#49998A`
- `border-accent/20` → 20% opacity
- `border-contrast` → `#181A31`

### Typography

```css
@theme {
  --font-family-heading: 'Raleway', system-ui, sans-serif;
  --font-family-body: 'Montserrat', system-ui, sans-serif;
}
```

**Usage:**
- `font-heading` → Raleway (for headings)
- `font-body` → Montserrat (for body text)

### Custom Utilities

```css
@theme {
  --radius-btn: 6px;
  --radius-card: 8px;
  --radius-pill: 9999px;
  
  --shadow-card: 0 2px 8px 0 rgba(24, 26, 49, 0.08);
  --shadow-dropdown: 0 4px 12px 0 rgba(24, 26, 49, 0.12);
}
```

**Usage:**
- `rounded-btn` → 6px radius
- `rounded-card` → 8px radius
- `rounded-pill` → fully rounded
- `shadow-card` → Subtle elevation
- `shadow-dropdown` → Menu/dropdown shadow

## ❌ Common Mistakes

### DON'T: Use Inline Styles for Brand Colors

```svelte
<!-- ❌ BAD: Inline styles -->
<button style="background-color: #5AB7A3;">
  Click me
</button>
```

### DO: Use Tailwind Classes

```svelte
<!-- ✅ GOOD: Tailwind utilities -->
<button class="bg-accent hover:bg-accent-hover">
  Click me
</button>
```

### DON'T: Modify `tailwind.config.js`

The `tailwind.config.js` file is **ignored** in v4. All configuration goes in CSS `@theme` blocks.

### DO: Add Custom Values to `@theme`

```css
@theme {
  --color-my-custom-color: #FF5733;
}
```

Now use: `bg-my-custom-color`, `text-my-custom-color`, etc.

## Standard Button Pattern

All buttons should follow this pattern for consistency:

```svelte
<button
  onclick={handleClick}
  disabled={isLoading}
  class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
>
  Button Text
</button>
```

### Breakdown:
- `inline-flex items-center` - Flexbox layout
- `px-4 py-2` - Consistent padding
- `text-sm font-medium` - Typography
- `rounded-md` - Standard button radius
- `text-white bg-accent` - Brand colors
- `hover:bg-accent-hover` - Hover state
- `focus:ring-2 focus:ring-accent` - Accessibility
- `disabled:opacity-50` - Disabled state
- `transition-colors` - Smooth transitions

## Troubleshooting

### Colors Not Showing?

1. **Check `@theme` block** in `app.css`
2. **Restart dev server** (Tailwind v4 may need restart for config changes)
3. **Clear build cache**: `rm -rf .svelte-kit` and rebuild
4. **Verify PostCSS config** uses `@tailwindcss/postcss`

### Adding New Colors

1. Add to `@theme` block in `app.css`:
   ```css
   @theme {
     --color-my-new-color: #HEXCODE;
   }
   ```

2. Use immediately:
   ```html
   <div class="bg-my-new-color">...</div>
   ```

3. **No build restart needed** - Tailwind v4 watches for changes

## Benefits of This Approach

✅ **Type-safe** - Colors defined once, used everywhere  
✅ **Consistent** - No magic strings or inline styles  
✅ **Maintainable** - Change color once, updates everywhere  
✅ **Production-optimized** - Tailwind v4 JIT is extremely fast  
✅ **Standard** - Follows Tailwind v4 best practices  
✅ **Accessible** - Easy to add hover/focus states  

## Migration Notes

If you see inline styles for brand colors in any component, they should be replaced with Tailwind classes:

**Before (inline styles):**
```svelte
<button style="background-color: #5AB7A3;">
```

**After (Tailwind classes):**
```svelte
<button class="bg-accent hover:bg-accent-hover">
```

This ensures:
- Consistent behavior across the app
- Proper hover/focus states
- Dark mode support (if added later)
- Better performance (no style recalculation)

