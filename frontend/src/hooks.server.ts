import { createServerClient } from '@supabase/ssr';
import { type Handle, redirect } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';
import { PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY } from '$env/static/public';

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
    if (error) {
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

  // Not logged in - require login for /app routes
  if (!event.locals.session && event.url.pathname.startsWith('/app')) {
    throw redirect(303, '/login');
  }

  // Logged in - check approval status
  if (event.locals.session && event.locals.user?.id) {
    // Fetch user profile to check approval status
    const { data: profile } = await event.locals.supabase
      .from('profiles')
      .select('approved, role')
      .eq('id', event.locals.user.id)
      .single();

    // Store full profile in locals for use in load functions - fetch separately
    const { data: fullProfile } = await event.locals.supabase
      .from('profiles')
      .select('*')
      .eq('id', event.locals.user.id)
      .single();
    event.locals.profile = fullProfile;

    const isApproved = (profile as { approved?: boolean } | null)?.approved === true;
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

