import { createBrowserClient } from '@supabase/ssr';
import { env } from '$env/dynamic/public';
import type { Database } from './database.types';
import type { Session, User } from '@supabase/supabase-js';

const PUBLIC_SUPABASE_URL = env.PUBLIC_SUPABASE_URL;
const PUBLIC_SUPABASE_ANON_KEY = env.PUBLIC_SUPABASE_ANON_KEY;

export const supabase = createBrowserClient<Database>(
  PUBLIC_SUPABASE_URL,
  PUBLIC_SUPABASE_ANON_KEY
);

/**
 * Securely get the current session and validate it with the server.
 * 
 * This function addresses the Supabase security warning:
 * "Using the user object as returned from supabase.auth.getSession() could be insecure!"
 * 
 * @returns {Promise<{session: Session | null, user: User | null}>} 
 *          Validated session and user, or null for both if invalid/not authenticated
 */
export async function getSecureSession(): Promise<{ session: Session | null; user: User | null }> {
  // Get session from storage (may be stale or tampered)
  const { data: { session } } = await supabase.auth.getSession();
  
  if (!session) {
    return { session: null, user: null };
  }
  
  // Validate the session by contacting Supabase Auth server
  const { data: { user }, error } = await supabase.auth.getUser();
  
  if (error || !user) {
    // Session was invalid or expired
    return { session: null, user: null };
  }
  
  // Session is valid
  return { session, user };
}

/**
 * Get just the access token for API calls, with validation.
 * 
 * @returns {Promise<string | null>} The access token if valid, null otherwise
 */
export async function getSecureAccessToken(): Promise<string | null> {
  const { session } = await getSecureSession();
  return session?.access_token ?? null;
}

