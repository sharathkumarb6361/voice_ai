export interface Business {
  id: string;
  name: string;
  industry: string;
  owner_name: string;
  phone: string;
  email: string;
  address?: string;
  created_at: string;
}

export interface WorkflowField {
  key: string;
  label: string;
  type: 'text' | 'select' | 'number' | 'datetime';
  options?: string[];
  required: boolean;
  description?: string;
}

export interface WorkflowCondition {
  field: string;
  operator: 'equals' | 'within_hours' | 'exists';
  value?: any;
  action_override?: string;
  tool_action?: string;
  note?: string;
}

export interface BusinessHours {
  enabled: boolean;
  days: string[];
  start_time: string;
  end_time: string;
  after_hours_greeting?: string;
  after_hours_action?: string;
}

export interface Workflow {
  id: string;
  business_id: string;
  business_name?: string;
  name: string;
  industry: string;
  trigger_event: string;
  greeting: string;
  fields: WorkflowField[];
  conditions: WorkflowCondition[];
  actions: string[];
  closing_message: string;
  language: string;
  business_hours?: BusinessHours;
  is_active: number;
  created_at: string;
}

export interface ToolLog {
  tool: string;
  args?: any;
  result?: any;
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  name?: string;
}

export interface MissedCallRecord {
  id: string;
  business_id: string;
  workflow_id: string;
  business_name?: string;
  workflow_name?: string;
  caller_name: string;
  caller_phone: string;
  intent: string;
  collected_data: Record<string, any>;
  ai_summary: string;
  urgency: 'Normal' | 'Urgent' | 'Critical';
  followup_status: 'Pending' | 'Contacted' | 'Completed' | 'Closed';
  transcript: ChatMessage[];
  tools_executed: ToolLog[];
  created_at: string;
}

export interface CalendarEvent {
  id: string;
  business_id: string;
  title: string;
  start_time: string;
  end_time: string;
  attendee_name: string;
  attendee_phone: string;
  description?: string;
  status: string;
  google_event_id?: string;
  created_at: string;
}
