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
    if (!browser) {
        // Server-side: use env var or default to localhost
        return ENV_API_URL || 'http://127.0.0.1:8000';
    }

    // Client-side (Browser)
    
    // If we are on localhost, trust the env var (likely pointing to Python backend port 8000)
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        return ENV_API_URL || 'http://127.0.0.1:8000';
    }

    // Production/Preview (Vercel)
    // Return empty string to use relative paths (e.g. "/api/...")
    // This ensures requests go to the same domain, avoiding CORS
    return '';
}

export const API_URL = getApiUrl();

