import { browser } from '$app/environment';
import { PUBLIC_API_URL as ENV_API_URL } from '$env/static/public';

/**
 * Dynamically determines the API URL.
 * 
 * In production (browser), we want to use the current origin to avoid CORS issues
 * and leverage Vercel's rewrites (which route /api/* to the backend).
 * 
 * In development, we use the provided environment variable (usually localhost:8000).
 * 
 * This solves the issue where PUBLIC_API_URL is baked in at build time with the wrong value.
 */
export function getApiUrl(): string {
    // Explicitly check for window to ensure we are in the browser
    const isBrowser = typeof window !== 'undefined';
    
    if (!isBrowser) {
        // Server-side: use env var or default to localhost
        return ENV_API_URL || 'http://127.0.0.1:8000';
    }

    // Client-side (Browser)
    try {
        const hostname = window.location.hostname;
        
        // If we are on localhost, trust the env var (likely pointing to Python backend port 8000)
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
            return ENV_API_URL || 'http://127.0.0.1:8000';
        }
        
        // For Vercel deployments: use relative paths to avoid CORS issues
        return '';
    } catch {
        return '';
    }
}

// Export as function for runtime evaluation
export const getApiUrlValue = getApiUrl;

// REMOVED: API_URL constant export (deprecated - use getApiUrl() instead)
// All code has been migrated to use getApiUrl() for dynamic runtime evaluation

