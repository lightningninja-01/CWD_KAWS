// Mirrors backend/app/schemas/*.py — keep these in sync manually since
// there's no shared codegen step in this project's scope.

export interface Branding {
  display_name: string;
  primary_color: string;
  logo_url: string | null;
}

export interface Tenant {
  id: string;
  company_name: string;
  phone_number_id: string;
  system_prompt: string;
  media_library: Record<string, string>;
  branding: Branding;
}

export type SessionStatus = "WAITING_FOR_BOT" | "AGENT_RESPONDING" | "RESOLVED" | "NEEDS_HUMAN";

export interface Session {
  id: string;
  tenant_id: string;
  customer_phone: string;
  status: SessionStatus;
  context_variables: Record<string, unknown>;
  last_message_at: string | null;
  created_at: string;
}

export type MessageSender = "customer" | "bot" | "human_agent";
export type MessageType = "text" | "image" | "document";
export type MessageStatus = "PENDING_RESPONSE" | "SENT" | "DELIVERED" | "FAILED";

export interface MediaAttachment {
  url: string;
  mime_type: string;
  filename: string | null;
}

export interface Message {
  id: string;
  session_id: string;
  sender: MessageSender;
  message_type: MessageType;
  text: string | null;
  media: MediaAttachment | null;
  status: MessageStatus;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface BroadcastRequest {
  tenant_id: string;
  target_tags: string[];
  template_name: string;
  template_params: string[];
}

export interface BroadcastResult {
  tenant_id: string;
  total_targeted: number;
  total_sent: number;
  total_failed: number;
  failed_numbers: string[];
}

export interface BroadcastJob {
  job_id: string;
  tenant_id: string;
  status: "queued" | "running" | "completed" | "failed";
  created: boolean;
}

export interface BroadcastJobStatus extends Omit<BroadcastJob, "created"> {
  attempts: number;
  result: BroadcastResult | null;
  last_error: string | null;
}
