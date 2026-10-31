export type Role = 'staff' | 'admin' | 'super_admin';
export type ApptStatus = 'scheduled' | 'confirmed' | 'cancelled' | 'completed' | 'rescheduled';

// Fields follow TalkAor_Dashboard_Specification.pdf (section 5), plus two optional cancellation fields.
export interface Appointment {
  id: string; customer_id: string; customer_name: string; customer_phone: string; customer_email?: string;
  date: string; // YYYY-MM-DD
  time: string; // HH:MM:SS
  day_of_week: string; service: string; status: ApptStatus;
  staff_name?: string; agent_name?: string; notes?: string; image?: string;
  cancel_reason?: string; cancelled_by?: 'ai_agent' | 'staff';
  created_at: string; updated_at: string;
}
export interface AppointmentHistoryItem {
  id: string; appointment_id: string; event: string; old_value?: string; new_value?: string;
  actor: string; actor_type: 'staff' | 'ai_agent'; timestamp: string;
}
export interface TranscriptLine { speaker: string; text: string; time: string }
export interface Call {
  id: string; customer_name: string; customer_phone: string; agent_name: string; duration_seconds: number;
  status: 'completed' | 'missed' | 'failed' | 'in_progress'; outcome?: 'BOOKED' | 'INQUIRY';
  summary?: string; has_recording: boolean; recording_url?: string; transcript?: TranscriptLine[];
}
export interface Agent {
  id: string; name: string; languages: string; phone: string; online: boolean; calls_today: number; business_id: string;
  provider?: string; provider_agent_id?: string | null; status?: string; tool_token_exists?: boolean;
}
export type Plan = 'Starter' | 'Growth' | 'Business';
export interface Business {
  id: string; name: string; plan: Plan; minutes_used: number; minutes_limit: number;
  status: 'Active' | 'Suspended'; renews_on: string; last_login: string; staff_pin: string;
}
export interface AccessRequest { id: string; business: string; plan: Plan; billing: 'monthly' | 'yearly'; amount: number; status: string }
export interface ContactMessage { id: string; name: string; email: string; phone: string; message: string; received_at: string; read: boolean; handled: boolean }
export type LogLevel = 'info' | 'warn' | 'error';
export interface LogEntry { at: string; text: string; level: LogLevel }
export interface AdminWebhookEvent {
  id: number;
  provider: string;
  event_id: string;
  event_type: string;
  client_id: number | null;
  business_name: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
  processed_at: string | null;
}
export interface AdminWebhookEventDetail extends AdminWebhookEvent { payload: Record<string, unknown> }
export interface AdminToolCall {
  id: number;
  client_id: number | null;
  business_name: string | null;
  tool: string;
  action: string;
  tenant_resolution: string | null;
  success: boolean;
  error_code: string | null;
  message: string | null;
  appointment_id: number | null;
  duration_ms: number;
  request_id: string | null;
  created_at: string;
}
export interface AdminAppointment {
  id: number;
  client_id: number;
  business_name: string;
  customer_name: string;
  date: string;
  time: string;
  status: string;
  source: 'ai_agent' | 'manual' | string;
  created_at: string;
}
export interface AdminMonitoringRow {
  client_id: number;
  business_name: string;
  access_status: string;
  agent_status: string | null;
  provider_agent_id_present: boolean;
  last_call_time: string | null;
  minutes_used: number;
  minutes_limit: number;
  usage_percent: number;
  alert: 'none' | 'warning' | 'limit' | string;
  failed_webhook_events_24h: number;
  last_webhook_received_at: string | null;
  last_tool_call_at: string | null;
  last_tool_call_error: string | null;
}
export interface AdminHealthDetails {
  database_ok: boolean;
  last_webhook_received_at: string | null;
  sarvam_api_key_set: boolean;
  sarvam_base_url_set: boolean;
  sarvam_webhook_secret_set: boolean;
  email_backend: string;
  resend_api_key_set: boolean;
  app_env_production: boolean;
}
export interface AdminPage<T> {
  items: T[];
  page: number;
  limit: number;
  total: number;
}
export interface AdminLinkedAgent {
  id: string;
  name: string;
  provider: string;
  provider_agent_id: string | null;
  phone_number: string | null;
  status: string;
}
export interface AdminClientIntegration {
  signed_event_webhook_url: string;
  tool_url_patterns: Record<string, string>;
  urls_are_absolute: boolean;
  credential_exists: boolean;
  credential_created_at: string | null;
  credential_rotated_at: string | null;
  credential_last_used_at: string | null;
  agents: AdminLinkedAgent[];
}
export interface AdminClientToolToken {
  token: string;
  tool_urls: Record<string, string>;
  urls_are_absolute: boolean;
}
export interface BillingMe {
  plan: string;
  billing_cycle: 'monthly' | 'yearly';
  minutes_limit: number;
  minutes_used: number;
  minutes_remaining: number;
  usage_percent: number;
  alert: 'none' | 'warning' | 'limit';
  renews_on: string;
  next_payment_amount?: number | null;
}
export interface StaffMember { id: string; name: string; title: string; days: boolean[] } // Mon..Sun
export interface DayHours { open: string; close: string; closed: boolean } // Mon..Sun
export interface DashboardUser {
  id: string | number;
  name: string;
  email: string;
  role: Role;
  is_active: boolean;
  is_protected: boolean;
}

export interface MockData {
  appts: Appointment[]; history: Record<string, AppointmentHistoryItem[]>; agents: Agent[]; calls: Call[];
  staff: StaffMember[]; services: string[]; hours: DayHours[]; businesses: Business[];
  requests: AccessRequest[]; messages: ContactMessage[]; logs: LogEntry[];
  users?: DashboardUser[];
}
