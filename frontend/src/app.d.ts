import { SupabaseClient, Session, User } from '@supabase/supabase-js';
import { Database } from './lib/database.types';
import type { Profile } from './lib/types';

declare global {
	namespace App {
		interface Locals {
			supabase: SupabaseClient<Database>;
			safeGetSession: () => Promise<{ session: Session | null; user: User | null }>;
			session: Session | null;
			user: User | null;
			profile: Profile | null;
		}
		interface PageData {
			session: Session | null;
			user: User | null;
			profile: Profile | null;
		}
		// interface Error {}
		// interface Platform {}
	}
}

export {};
