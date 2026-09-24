// Types mirroring the NEXUS backend API (see backend/app/api/routes).

export type RiskLevel = "low" | "medium" | "high";

export interface ApiErrorBody {
  code: string;
  message: string;
  reason?: string | null;
  next_step?: string | null;
}

export interface ActionRecord {
  id: string;
  tool: string;
  agent: string | null;
  summary: string;
  status: "succeeded" | "failed" | "denied" | "cancelled";
  risk: RiskLevel;
  approval: string;
  error: ApiErrorBody | null;
  data: Record<string, unknown>;
}

export interface Source {
  title: string;
  url: string | null;
  kind: "web" | "file" | "api";
  snippet?: string;
}

export interface Attachment {
  id: string;
  filename: string;
  kind: FileKind;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  status: "complete" | "error" | "partial";
  request_id: string | null;
  attachments: Attachment[];
  actions: ActionRecord[];
  sources: Source[];
  meta: {
    plan?: { steps: { agent: string; instruction: string }[]; source: string };
    agents?: string[];
    verification?: string[];
    voice?: boolean;
    error?: ApiErrorBody;
    [key: string]: unknown;
  };
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  archived: boolean;
  created_at: string;
  updated_at: string;
  message_count: number | null;
}

export type MemoryCategory =
  | "preference" | "project" | "person" | "place" | "study" | "command" | "date" | "task" | "fact";

export interface Memory {
  id: string;
  category: MemoryCategory;
  subject: string;
  value: string;
  aliases: string[];
  attributes: Record<string, unknown>;
  source: "explicit" | "inferred";
  status: "active" | "pending";
  sensitivity: "normal" | "personal";
  use_count: number;
  created_at: string | null;
  updated_at: string | null;
  last_used_at: string | null;
}

export interface Task {
  id: string;
  title: string;
  notes: string | null;
  status: "open" | "done" | "cancelled";
  priority: "low" | "normal" | "high";
  due_at: string | null;
  completed_at: string | null;
  automation_id: string | null;
  source: string;
  created_at: string;
}

export type AutomationKind = "reminder" | "agent_task" | "price_watch" | "weather_check";

export interface Automation {
  id: string;
  name: string;
  kind: AutomationKind;
  trigger_type: "once" | "interval" | "cron";
  schedule: Record<string, unknown>;
  schedule_text: string;
  timezone: string;
  config: Record<string, unknown>;
  status: "active" | "paused" | "completed" | "failed";
  next_run_at: string | null;
  last_run_at: string | null;
  last_result: Record<string, unknown> & { summary?: string; error?: ApiErrorBody | null };
  run_count: number;
  failure_count: number;
  created_at: string;
}

export type FileKind = "pdf" | "docx" | "text" | "code" | "image";

export interface FileInfo {
  id: string;
  filename: string;
  kind: FileKind;
  mime_type: string;
  size_bytes: number;
  status: "processing" | "ready" | "failed";
  error: string | null;
  page_count: number | null;
  char_count: number | null;
  sections: string[];
  chunks: number | null;
  created_at: string;
}

export interface AgentInfo {
  name: string;
  title: string;
  purpose: string;
  tools: { name: string; risk: RiskLevel; description: string }[];
  permission_level?: RiskLevel;
  requires_ai: boolean;
  status: "available" | "planned";
}

export interface ActivityFeed {
  agent_runs: {
    id: string;
    agent: string;
    status: string;
    task: string;
    summary: string;
    error: ApiErrorBody | null;
    started_at: string;
    finished_at: string | null;
    conversation_id: string | null;
  }[];
  tool_calls: {
    id: string;
    tool: string;
    agent: string | null;
    status: string;
    risk: RiskLevel;
    approval: string;
    summary: string | null;
    error: ApiErrorBody | null;
    duration_ms: number | null;
    created_at: string;
  }[];
}

export interface AuditFeed {
  permission_requests: {
    id: string;
    tool: string;
    agent: string | null;
    risk: RiskLevel;
    summary: string;
    reason: string | null;
    status: string;
    decision: string | null;
    created_at: string;
    decided_at: string | null;
  }[];
  events: { id: string; event: string; detail: Record<string, unknown>; created_at: string }[];
}

export interface PermissionRequest {
  id: string;
  tool: string;
  agent: string | null;
  risk: RiskLevel;
  summary: string;
  reason: string | null;
  details: Record<string, unknown>;
  scope: string;
  allow_always: boolean;
  expires_at: string;
  request_id?: string;
}

export interface ComponentStatus {
  ready: boolean;
  detail?: string;
  [key: string]: unknown;
}

export interface SystemStatus {
  version: string;
  auth_mode: "local" | "supabase";
  components: {
    database: ComponentStatus;
    memory: ComponentStatus;
    ai: {
      configured: boolean;
      ready: boolean;
      provider: string;
      model: string | null;
      mock?: boolean;
      error: ApiErrorBody | null;
    };
    agents: ComponentStatus & { count: number; tools: number };
    voice: ComponentStatus & { stt_server: string | null; tts_server: string | null };
    network: ComponentStatus & { connected?: boolean; latency_ms?: number };
    search: ComponentStatus & { provider: string | null };
    scheduler: ComponentStatus & { mode: string; last_tick_at: string | null };
    computer_control: ComponentStatus & { display: boolean };
  };
}

export interface PublicConfig {
  version: string;
  auth_mode: "local" | "supabase";
  supabase_url: string | null;
  supabase_anon_key: string | null;
  computer_control: boolean;
  max_upload_mb: number;
}

export interface Telemetry {
  host: string;
  os: string;
  platform: string;
  cpu: { percent: number; cores: number; load_avg: number[] | null } | null;
  memory: { percent: number; used_gb: number; total_gb: number } | null;
  disk: { percent: number; free_gb: number; total_gb: number } | null;
  battery: { percent: number; plugged_in: boolean; secs_left: number | null } | null;
  network: { interfaces_up: number; rate: { down_kbps: number; up_kbps: number } | null } | null;
  uptime_seconds: number | null;
  display: boolean;
}

export interface Preferences {
  profile: { user_name: string | null; response_style: string };
  voice: {
    auto_speak: boolean;
    stt_provider: "auto" | "server" | "browser";
    tts_provider: "browser" | "server";
    voice_name: string | null;
    rate: number;
    pitch: number;
    wake_word_enabled: boolean;
  };
  permissions: { confirm_medium_actions: boolean };
  memory: { auto_remember: boolean; require_approval_for_inferred: boolean };
  location: { city: string | null; latitude: number | null; longitude: number | null; country: string | null };
  regional: { timezone: string | null; units: "metric" | "imperial" };
  workspace: { roots: string[] };
  apps: { custom: { id: string; name: string; command: string[]; accepts_path: boolean }[] };
}

export interface SecretStatus {
  name: string;
  label: string;
  used_for: string;
  configured: boolean;
  source: "environment" | "stored" | null;
  hint: string | null;
}

export interface SettingsBundle {
  preferences: Preferences;
  secrets: SecretStatus[];
  ai: SystemStatus["components"]["ai"] & { effort: string; refusal_fallback: boolean };
  workspace_roots: string[];
  env_workspace_roots: string[];
  computer_control: boolean;
  can_edit_secrets: boolean;
  can_edit_host: boolean;
  allowed_commands: { program: string; description: string; risk: RiskLevel }[];
  auth_mode: "local" | "supabase";
}

export interface PermissionGrant {
  id: string;
  tool: string;
  scope: string;
  use_count: number;
  created_at: string;
  last_used_at: string | null;
}

export interface NexusNotification {
  id: string;
  title: string;
  body: string;
  kind: "reminder" | "automation" | "system";
  status: "unread" | "read";
  automation_id: string | null;
  data: Record<string, unknown>;
  created_at: string;
}

export interface AppInfo {
  id: string;
  name: string;
  installed: boolean;
  custom: boolean;
  accepts_path: boolean;
}

export interface DeviceInfo {
  id: string;
  name: string;
  kind: string;
  platform: string | null;
  capabilities: Record<string, boolean>;
  last_seen_at: string | null;
  created_at: string;
}

export interface DevicesResponse {
  host: {
    name: string;
    os: string;
    display: boolean;
    capabilities: Record<string, boolean>;
  };
  clients: DeviceInfo[];
}
