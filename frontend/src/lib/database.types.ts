export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  public: {
    Tables: {
      analysis_results: {
        Row: {
          case_id: string
          chunk_state: Json | null
          completed_at: string | null
          created_at: string | null
          error: string | null
          id: string
          progress: Json | null
          result: Json | null
          status: string | null
          updated_at: string | null
        }
        Insert: {
          case_id: string
          chunk_state?: Json | null
          completed_at?: string | null
          created_at?: string | null
          error?: string | null
          id?: string
          progress?: Json | null
          result?: Json | null
          status?: string | null
          updated_at?: string | null
        }
        Update: {
          case_id?: string
          chunk_state?: Json | null
          completed_at?: string | null
          created_at?: string | null
          error?: string | null
          id?: string
          progress?: Json | null
          result?: Json | null
          status?: string | null
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "analysis_results_case_id_fkey"
            columns: ["case_id"]
            isOneToOne: false
            referencedRelation: "cases"
            referencedColumns: ["id"]
          },
        ]
      }
      case_chat_messages: {
        Row: {
          ai_response: string
          case_id: string
          context_used: Json | null
          created_at: string | null
          id: string
          user_message: string
        }
        Insert: {
          ai_response: string
          case_id: string
          context_used?: Json | null
          created_at?: string | null
          id?: string
          user_message: string
        }
        Update: {
          ai_response?: string
          case_id?: string
          context_used?: Json | null
          created_at?: string | null
          id?: string
          user_message?: string
        }
        Relationships: [
          {
            foreignKeyName: "case_chat_messages_case_id_fkey"
            columns: ["case_id"]
            isOneToOne: false
            referencedRelation: "cases"
            referencedColumns: ["id"]
          },
        ]
      }
      cases: {
        Row: {
          client_name: string
          clio_last_synced_at: string | null
          clio_matter_data: Json | null
          clio_matter_id: string | null
          created_at: string | null
          created_via_clio: boolean | null
          description: string | null
          id: string
          import_progress: Json | null
          jurisdiction: string
          needs_reanalysis: boolean | null
          reference_number: string | null
          status: string | null
          updated_at: string | null
          user_id: string
        }
        Insert: {
          client_name: string
          clio_last_synced_at?: string | null
          clio_matter_data?: Json | null
          clio_matter_id?: string | null
          created_at?: string | null
          created_via_clio?: boolean | null
          description?: string | null
          id?: string
          import_progress?: Json | null
          jurisdiction?: string
          needs_reanalysis?: boolean | null
          reference_number?: string | null
          status?: string | null
          updated_at?: string | null
          user_id: string
        }
        Update: {
          client_name?: string
          clio_last_synced_at?: string | null
          clio_matter_data?: Json | null
          clio_matter_id?: string | null
          created_at?: string | null
          created_via_clio?: boolean | null
          description?: string | null
          id?: string
          import_progress?: Json | null
          jurisdiction?: string
          needs_reanalysis?: boolean | null
          reference_number?: string | null
          status?: string | null
          updated_at?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "cases_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      documents: {
        Row: {
          case_id: string
          created_at: string | null
          extracted_at: string | null
          extracted_text: string | null
          extraction_error: string | null
          extraction_method: string | null
          extraction_quality: string | null
          file_name: string
          file_size: number
          file_type: string
          id: string
          is_flagged_as_junk: boolean | null
          is_verified: boolean | null
          manual_text: string | null
          metadata: Json | null
          ocr_provider: string | null
          page_count: number | null
          status: string | null
          storage_path: string
          text_edited_at: string | null
          updated_at: string | null
        }
        Insert: {
          case_id: string
          created_at?: string | null
          extracted_at?: string | null
          extracted_text?: string | null
          extraction_error?: string | null
          extraction_method?: string | null
          extraction_quality?: string | null
          file_name: string
          file_size: number
          file_type: string
          id?: string
          is_flagged_as_junk?: boolean | null
          is_verified?: boolean | null
          manual_text?: string | null
          metadata?: Json | null
          ocr_provider?: string | null
          page_count?: number | null
          status?: string | null
          storage_path: string
          text_edited_at?: string | null
          updated_at?: string | null
        }
        Update: {
          case_id?: string
          created_at?: string | null
          extracted_at?: string | null
          extracted_text?: string | null
          extraction_error?: string | null
          extraction_method?: string | null
          extraction_quality?: string | null
          file_name?: string
          file_size?: number
          file_type?: string
          id?: string
          is_flagged_as_junk?: boolean | null
          is_verified?: boolean | null
          manual_text?: string | null
          metadata?: Json | null
          ocr_provider?: string | null
          page_count?: number | null
          status?: string | null
          storage_path?: string
          text_edited_at?: string | null
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "documents_case_id_fkey"
            columns: ["case_id"]
            isOneToOne: false
            referencedRelation: "cases"
            referencedColumns: ["id"]
          },
        ]
      }
      integrations_clio: {
        Row: {
          access_token: string
          clio_matter_id: string | null
          clio_user_id: string | null
          created_at: string | null
          expires_at: string
          id: string
          refresh_token: string
          scopes: string[] | null
          token_type: string | null
          updated_at: string | null
          user_id: string
        }
        Insert: {
          access_token: string
          clio_matter_id?: string | null
          clio_user_id?: string | null
          created_at?: string | null
          expires_at: string
          id?: string
          refresh_token: string
          scopes?: string[] | null
          token_type?: string | null
          updated_at?: string | null
          user_id: string
        }
        Update: {
          access_token?: string
          clio_matter_id?: string | null
          clio_user_id?: string | null
          created_at?: string | null
          expires_at?: string
          id?: string
          refresh_token?: string
          scopes?: string[] | null
          token_type?: string | null
          updated_at?: string | null
          user_id?: string
        }
        Relationships: []
      }
      profiles: {
        Row: {
          ai_preferences: Json | null
          approved: boolean | null
          avatar_url: string | null
          bar_number: string | null
          created_at: string | null
          default_demand_deadline: string | null
          default_jurisdiction: string | null
          email: string
          email_signature: string | null
          firm_address: string | null
          firm_name: string | null
          full_name: string | null
          id: string
          phone: string | null
          role: string | null
          updated_at: string | null
        }
        Insert: {
          ai_preferences?: Json | null
          approved?: boolean | null
          avatar_url?: string | null
          bar_number?: string | null
          created_at?: string | null
          default_demand_deadline?: string | null
          default_jurisdiction?: string | null
          email: string
          email_signature?: string | null
          firm_address?: string | null
          firm_name?: string | null
          full_name?: string | null
          id: string
          phone?: string | null
          role?: string | null
          updated_at?: string | null
        }
        Update: {
          ai_preferences?: Json | null
          approved?: boolean | null
          avatar_url?: string | null
          bar_number?: string | null
          created_at?: string | null
          default_demand_deadline?: string | null
          default_jurisdiction?: string | null
          email?: string
          email_signature?: string | null
          firm_address?: string | null
          firm_name?: string | null
          full_name?: string | null
          id?: string
          phone?: string | null
          role?: string | null
          updated_at?: string | null
        }
        Relationships: []
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
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const

