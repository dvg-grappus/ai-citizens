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
      action_def: {
        Row: {
          base_minutes: number | null
          emoji: string | null
          id: string
          post_effects: string[] | null
          preconds: string[] | null
          title: string | null
        }
        Insert: {
          base_minutes?: number | null
          emoji?: string | null
          id?: string
          post_effects?: string[] | null
          preconds?: string[] | null
          title?: string | null
        }
        Update: {
          base_minutes?: number | null
          emoji?: string | null
          id?: string
          post_effects?: string[] | null
          preconds?: string[] | null
          title?: string | null
        }
        Relationships: []
      }
      action_instance: {
        Row: {
          def_id: string | null
          duration_min: number | null
          id: string
          npc_id: string | null
          object_id: string | null
          start_min: number | null
          status: string | null
        }
        Insert: {
          def_id?: string | null
          duration_min?: number | null
          id?: string
          npc_id?: string | null
          object_id?: string | null
          start_min?: number | null
          status?: string | null
        }
        Update: {
          def_id?: string | null
          duration_min?: number | null
          id?: string
          npc_id?: string | null
          object_id?: string | null
          start_min?: number | null
          status?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "action_instance_def_id_fkey"
            columns: ["def_id"]
            isOneToOne: false
            referencedRelation: "action_def"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "action_instance_npc_id_fkey"
            columns: ["npc_id"]
            isOneToOne: false
            referencedRelation: "npc"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "action_instance_object_id_fkey"
            columns: ["object_id"]
            isOneToOne: false
            referencedRelation: "object"
            referencedColumns: ["id"]
          },
        ]
      }
      area: {
        Row: {
          bounds: Json
          id: string
          name: string
        }
        Insert: {
          bounds: Json
          id?: string
          name: string
        }
        Update: {
          bounds?: Json
          id?: string
          name?: string
        }
        Relationships: []
      }
      dialogue: {
        Row: {
          end_min: number | null
          id: string
          npc_a: string | null
          npc_b: string | null
          start_min: number | null
        }
        Insert: {
          end_min?: number | null
          id?: string
          npc_a?: string | null
          npc_b?: string | null
          start_min?: number | null
        }
        Update: {
          end_min?: number | null
          id?: string
          npc_a?: string | null
          npc_b?: string | null
          start_min?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "dialogue_npc_a_fkey"
            columns: ["npc_a"]
            isOneToOne: false
            referencedRelation: "npc"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "dialogue_npc_b_fkey"
            columns: ["npc_b"]
            isOneToOne: false
            referencedRelation: "npc"
            referencedColumns: ["id"]
          },
        ]
      }
      dialogue_turn: {
        Row: {
          dialogue_id: string | null
          id: string
          sim_min: number | null
          speaker_id: string | null
          text: string | null
        }
        Insert: {
          dialogue_id?: string | null
          id?: string
          sim_min?: number | null
          speaker_id?: string | null
          text?: string | null
        }
        Update: {
          dialogue_id?: string | null
          id?: string
          sim_min?: number | null
          speaker_id?: string | null
          text?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "dialogue_turn_dialogue_id_fkey"
            columns: ["dialogue_id"]
            isOneToOne: false
            referencedRelation: "dialogue"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "dialogue_turn_speaker_id_fkey"
            columns: ["speaker_id"]
            isOneToOne: false
            referencedRelation: "npc"
            referencedColumns: ["id"]
          },
        ]
      }
      encounter: {
        Row: {
          actor_id: string | null
          description: string | null
          id: string
          target_id: string | null
          tick: number | null
        }
        Insert: {
          actor_id?: string | null
          description?: string | null
          id?: string
          target_id?: string | null
          tick?: number | null
        }
        Update: {
          actor_id?: string | null
          description?: string | null
          id?: string
          target_id?: string | null
          tick?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "encounter_actor_id_fkey"
            columns: ["actor_id"]
            isOneToOne: false
            referencedRelation: "npc"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "encounter_target_id_fkey"
            columns: ["target_id"]
            isOneToOne: false
            referencedRelation: "npc"
            referencedColumns: ["id"]
          },
        ]
      }
      environment: {
        Row: {
          day: number | null
          id: number
          speed: number | null
        }
        Insert: {
          day?: number | null
          id: number
          speed?: number | null
        }
        Update: {
          day?: number | null
          id?: number
          speed?: number | null
        }
        Relationships: []
      }
      memory: {
        Row: {
          content: string | null
          embedding: string | null
          id: string
          importance: number | null
          kind: string | null
          npc_id: string | null
          sim_min: number | null
        }
        Insert: {
          content?: string | null
          embedding?: string | null
          id?: string
          importance?: number | null
          kind?: string | null
          npc_id?: string | null
          sim_min?: number | null
        }
        Update: {
          content?: string | null
          embedding?: string | null
          id?: string
          importance?: number | null
          kind?: string | null
          npc_id?: string | null
          sim_min?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "memory_npc_id_fkey"
            columns: ["npc_id"]
            isOneToOne: false
            referencedRelation: "npc"
            referencedColumns: ["id"]
          },
        ]
      }
      npc: {
        Row: {
          backstory: string | null
          current_action_id: string | null
          energy: number | null
          id: string
          name: string
          relationships: Json | null
          spawn: Json
          traits: string[]
        }
        Insert: {
          backstory?: string | null
          current_action_id?: string | null
          energy?: number | null
          id?: string
          name: string
          relationships?: Json | null
          spawn: Json
          traits: string[]
        }
        Update: {
          backstory?: string | null
          current_action_id?: string | null
          energy?: number | null
          id?: string
          name?: string
          relationships?: Json | null
          spawn?: Json
          traits?: string[]
        }
        Relationships: []
      }
      object: {
        Row: {
          area_id: string | null
          id: string
          name: string
          pos: Json
          state: string | null
        }
        Insert: {
          area_id?: string | null
          id?: string
          name: string
          pos: Json
          state?: string | null
        }
        Update: {
          area_id?: string | null
          id?: string
          name?: string
          pos?: Json
          state?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "object_area_id_fkey"
            columns: ["area_id"]
            isOneToOne: false
            referencedRelation: "area"
            referencedColumns: ["id"]
          },
        ]
      }
      plan: {
        Row: {
          actions: string[] | null
          id: string
          npc_id: string | null
          sim_day: number | null
        }
        Insert: {
          actions?: string[] | null
          id?: string
          npc_id?: string | null
          sim_day?: number | null
        }
        Update: {
          actions?: string[] | null
          id?: string
          npc_id?: string | null
          sim_day?: number | null
        }
        Relationships: [
          {
            foreignKeyName: "plan_npc_id_fkey"
            columns: ["npc_id"]
            isOneToOne: false
            referencedRelation: "npc"
            referencedColumns: ["id"]
          },
        ]
      }
      sim_clock: {
        Row: {
          id: number
          sim_min: number | null
          speed: number | null
        }
        Insert: {
          id: number
          sim_min?: number | null
          speed?: number | null
        }
        Update: {
          id?: number
          sim_min?: number | null
          speed?: number | null
        }
        Relationships: []
      }
      sim_event: {
        Row: {
          end_min: number | null
          id: string
          metadata: Json | null
          start_min: number | null
          type: string | null
        }
        Insert: {
          end_min?: number | null
          id?: string
          metadata?: Json | null
          start_min?: number | null
          type?: string | null
        }
        Update: {
          end_min?: number | null
          id?: string
          metadata?: Json | null
          start_min?: number | null
          type?: string | null
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      binary_quantize: {
        Args: { "": string } | { "": unknown }
        Returns: unknown
      }
      halfvec_avg: {
        Args: { "": number[] }
        Returns: unknown
      }
      halfvec_out: {
        Args: { "": unknown }
        Returns: unknown
      }
      halfvec_send: {
        Args: { "": unknown }
        Returns: string
      }
      halfvec_typmod_in: {
        Args: { "": unknown[] }
        Returns: number
      }
      hnsw_bit_support: {
        Args: { "": unknown }
        Returns: unknown
      }
      hnsw_halfvec_support: {
        Args: { "": unknown }
        Returns: unknown
      }
      hnsw_sparsevec_support: {
        Args: { "": unknown }
        Returns: unknown
      }
      hnswhandler: {
        Args: { "": unknown }
        Returns: unknown
      }
      ivfflat_bit_support: {
        Args: { "": unknown }
        Returns: unknown
      }
      ivfflat_halfvec_support: {
        Args: { "": unknown }
        Returns: unknown
      }
      ivfflathandler: {
        Args: { "": unknown }
        Returns: unknown
      }
      l2_norm: {
        Args: { "": unknown } | { "": unknown }
        Returns: number
      }
      l2_normalize: {
        Args: { "": string } | { "": unknown } | { "": unknown }
        Returns: unknown
      }
      sparsevec_out: {
        Args: { "": unknown }
        Returns: unknown
      }
      sparsevec_send: {
        Args: { "": unknown }
        Returns: string
      }
      sparsevec_typmod_in: {
        Args: { "": unknown[] }
        Returns: number
      }
      vector_avg: {
        Args: { "": number[] }
        Returns: string
      }
      vector_dims: {
        Args: { "": string } | { "": unknown }
        Returns: number
      }
      vector_norm: {
        Args: { "": string }
        Returns: number
      }
      vector_out: {
        Args: { "": string }
        Returns: unknown
      }
      vector_send: {
        Args: { "": string }
        Returns: string
      }
      vector_typmod_in: {
        Args: { "": unknown[] }
        Returns: number
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DefaultSchema = Database[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof Database },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof Database
  }
    ? keyof (Database[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        Database[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends { schema: keyof Database }
  ? (Database[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      Database[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
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
    | { schema: keyof Database },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof Database
  }
    ? keyof Database[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends { schema: keyof Database }
  ? Database[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
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
    | { schema: keyof Database },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof Database
  }
    ? keyof Database[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends { schema: keyof Database }
  ? Database[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
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
    | { schema: keyof Database },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof Database
  }
    ? keyof Database[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends { schema: keyof Database }
  ? Database[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof Database },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof Database
  }
    ? keyof Database[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends { schema: keyof Database }
  ? Database[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
