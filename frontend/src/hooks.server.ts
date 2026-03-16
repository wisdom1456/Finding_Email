import { createServerClient } from '@supabase/ssr';
import { type Handle, redirect } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';
import { PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY } from '$env/static/public';
import type { Profile } from '$lib/types';

const supabase: Handle = async ({ event, resolve }) => {
  event.locals.supabase = createServerClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return event.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value, options }) => {
          event.cookies.set(name, value, { ...options, path: '/' });
        });
      },
    },
  });

  /**
   * Safe session retrieval with strict contract:
   *   - Returns { session, user } only when BOTH are valid
   *   - Returns { session: null, user: null } in all other cases
   *   - Callers can trust: if session is non-null, user is also non-null
   *
   * This prevents a "valid session, null user" state that could bypass
   * downstream auth checks that only inspect the session.
   */
  event.locals.safeGetSession = async () => {
    const {
      data: { session },
    } = await event.locals.supabase.auth.getSession();
    if (!session) {
      return { session: null, user: null };
    }

    const {
      data: { user },
      error,
    } = await event.locals.supabase.auth.getUser();
    if (error || !user) {
      // Invalidate the session when user verification fails.
      // A session without a verified user is not trustworthy.
      return { session: null, user: null };
    }

    return { session, user };
  };

  return resolve(event, {
    filterSerializedResponseHeaders(name) {
      return name === 'content-range' || name === 'x-supabase-api-version';
    },
  });
};

const authGuard: Handle = async ({ event, resolve }) => {
  const { session, user } = await event.locals.safeGetSession();
  event.locals.session = session;
  event.locals.user = user;

  // Determine if the user is fully authenticated (session + valid user.id).
  // A session without a valid user.id is treated as unauthenticated to prevent
  // bypassing the approval check entirely.
  const userId = user?.id;
  const isAuthenticated = !!(session && userId && typeof userId === 'string' && userId.length > 0);

  // Not authenticated - require login for /app routes
  if (!isAuthenticated && event.url.pathname.startsWith('/app')) {
    throw redirect(303, '/login');
  }

  // Authenticated - check approval status
  if (isAuthenticated) {
    // Fetch user profile (single query) to check approval status and populate locals.
    // Wrapped in try-catch: if profile fetch throws (network error, etc.),
    // fail closed — null profile → isApproved = false → /app routes blocked.
    let fullProfile: Profile | null = null;
    try {
      const { data } = await event.locals.supabase
        .from('profiles')
        .select('*')
        .eq('id', userId)
        .single();
      fullProfile = data as Profile | null;
    } catch (err) {
      console.error('Profile fetch failed, denying access:', err);
      fullProfile = null;
    }
    event.locals.profile = fullProfile;

    const isApproved = fullProfile?.approved === true;
    const isAccessingApp = event.url.pathname.startsWith('/app');
    const isOnPendingPage = event.url.pathname === '/account-pending';
    const isOnAuthPage = event.url.pathname === '/login' || event.url.pathname === '/register';

    // Not approved - redirect to pending page when trying to access app
    if (!isApproved && isAccessingApp) {
      throw redirect(303, '/account-pending');
    }

    // Not approved but on pending page - allow access
    if (!isApproved && isOnPendingPage) {
      return resolve(event);
    }

    // Approved and trying to access pending page - redirect to app
    if (isApproved && isOnPendingPage) {
      throw redirect(303, '/app');
    }

    // Approved and on auth pages - redirect to app
    if (isApproved && isOnAuthPage) {
      throw redirect(303, '/app');
    }

    // Not approved and on auth pages (just logged in/registered) - redirect to pending
    if (!isApproved && isOnAuthPage) {
      throw redirect(303, '/account-pending');
    }
  }

  return resolve(event);
};

export const handle: Handle = sequence(supabase, authGuard);

