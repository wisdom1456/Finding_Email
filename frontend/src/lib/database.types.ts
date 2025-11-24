/**
 * Database type definitions for Supabase.
 * 
 * These types should ideally be generated from Supabase CLI:
 * npx supabase gen types typescript --project-id YOUR_PROJECT_ID > src/lib/database.types.ts
 */

export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export interface Database {
  public: {
    Tables: {
      profiles: {
        Row: {
          id: string
          email: string
          full_name: string | null
          avatar_url: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id: string
          email: string
          full_name?: string | null
          avatar_url?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          email?: string
          full_name?: string | null
          avatar_url?: string | null
          created_at?: string
          updated_at?: string
        }
      }
      cases: {
        Row: {
          id: string
          user_id: string
          client_name: string
          reference_number: string | null
          description: string | null
          status: 'pending' | 'processing' | 'completed' | 'error'
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          user_id: string
          client_name: string
          reference_number?: string | null
          description?: string | null
          status?: 'pending' | 'processing' | 'completed' | 'error'
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          user_id?: string
          client_name?: string
          reference_number?: string | null
          description?: string | null
          status?: 'pending' | 'processing' | 'completed' | 'error'
          created_at?: string
          updated_at?: string
        }
      }
      documents: {
        Row: {
          id: string
          case_id: string
          file_name: string
          file_type: string
          file_size: number
          storage_path: string
          status: 'uploaded' | 'processing' | 'processed' | 'error'
          extracted_text: string | null
          metadata: Json
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          case_id: string
          file_name: string
          file_type: string
          file_size: number
          storage_path: string
          status?: 'uploaded' | 'processing' | 'processed' | 'error'
          extracted_text?: string | null
          metadata?: Json
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          case_id?: string
          file_name?: string
          file_type?: string
          file_size?: number
          storage_path?: string
          status?: 'uploaded' | 'processing' | 'processed' | 'error'
          extracted_text?: string | null
          metadata?: Json
          created_at?: string
          updated_at?: string
        }
      }
      analysis_results: {
        Row: {
          id: string
          case_id: string
          status: 'pending' | 'processing' | 'completed' | 'error'
          result: Json | null
          error: string | null
          completed_at: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          case_id: string
          status?: 'pending' | 'processing' | 'completed' | 'error'
          result?: Json | null
          error?: string | null
          completed_at?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          case_id?: string
          status?: 'pending' | 'processing' | 'completed' | 'error'
          result?: Json | null
          error?: string | null
          completed_at?: string | null
          created_at?: string
          updated_at?: string
        }
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
  }
}

