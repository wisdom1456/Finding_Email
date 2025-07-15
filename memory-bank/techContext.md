# Tech Context

## Development Environment

### Modern Frontend Stack
- **Build Tool**: Vite 5.0.10 - Modern build tool with fast HMR and optimized production builds
- **Language**: TypeScript 5.3.3 - Strict typing for better code quality and maintainability
- **Module System**: ES2020 modules with bundler resolution
- **Package Manager**: npm (compatible with Node.js ecosystem)

### TypeScript Configuration
- **Target**: ES2020 for modern browser support
- **Strict Mode**: Enabled for type safety
- **Path Mapping**: Configured aliases (@/, @/components/, @/assets/)
- **Module Resolution**: Bundler mode for Vite compatibility
- **Linting**: Strict rules including no unused locals/parameters

### Development Scripts
```json
{
  "dev": "vite",           // Development server with HMR
  "build": "tsc && vite build", // Type check + production build
  "preview": "vite preview",    // Preview production build
  "type-check": "tsc --noEmit" // Type checking only
}
```

### Key Dependencies
- **@types/node**: TypeScript definitions for Node.js APIs
- **Vite**: Fast build tool and development server
- **TypeScript**: Type-safe JavaScript

## File Structure

```
/
├── src/                    # Source code directory
│   ├── components/         # Reusable UI components
│   ├── assets/            # Static assets (images, fonts, etc.)
│   ├── index.html         # Main HTML entry point
│   └── main.ts            # TypeScript application entry point
├── memory-bank/           # Project documentation
├── package.json           # Dependencies and scripts
├── tsconfig.json          # TypeScript main configuration
├── tsconfig.node.json     # TypeScript config for Node.js tools
└── vite.config.ts         # Vite build configuration
```

## Deployment

This project will be deployed as a static site on Kinsta.

### Build Output
- **Output Directory**: `dist/`
- **Entry Point**: `src/index.html`
- **Assets Directory**: `dist/assets/`
- **Source Maps**: Enabled for debugging
- **Base Path**: `./` for static site compatibility

### Vite Configuration Features
- Path aliases for clean imports
- Development server on port 3000
- Auto-open browser in development
- Optimized for static site deployment