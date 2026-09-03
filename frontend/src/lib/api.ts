import { Business, Workflow, MissedCallRecord, CalendarEvent } from '../types';

const API_BASE = '/api';

export async function fetchBusinesses(): Promise<Business[]> {
  const res = await fetch(`${API_BASE}/businesses`);
  const json = await res.json();
  return json.data || [];
}

export async function createBusiness(data: Partial<Business>): Promise<Business> {
  const res = await fetch(`${API_BASE}/businesses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to create business');
  return json.data;
}

export async function fetchWorkflows(businessId?: string): Promise<Workflow[]> {
  const url = businessId ? `${API_BASE}/workflows?business_id=${businessId}` : `${API_BASE}/workflows`;
  const res = await fetch(url);
  const json = await res.json();
  return json.data || [];
}

export async function createWorkflow(data: Partial<Workflow>): Promise<Workflow> {
  const res = await fetch(`${API_BASE}/workflows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to create workflow');
  return json.data;
}

export async function updateWorkflow(id: string, data: Partial<Workflow>): Promise<Workflow> {
  const res = await fetch(`${API_BASE}/workflows/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to update workflow');
  return json.data;
}

export async function fetchRecords(params?: { business_id?: string; status?: string; urgency?: string }): Promise<MissedCallRecord[]> {
  const query = new URLSearchParams(params as any).toString();
  const res = await fetch(`${API_BASE}/records?${query}`);
  const json = await res.json();
  return json.data || [];
}

export async function updateRecordStatus(id: string, status: string): Promise<MissedCallRecord> {
  const res = await fetch(`${API_BASE}/records/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status })
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to update status');
  return json.data;
}

export async function sendChatMessage(payload: {
  business_id: string;
  workflow_id: string;
  caller_name?: string;
  caller_phone?: string;
  language?: string;
  messages: any[];
  record_id?: string;
}) {
  const res = await fetch(`${API_BASE}/ai/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'AI request failed');
  return json.data;
}

export async function fetchCalendarEvents(businessId?: string, status?: string, search?: string): Promise<CalendarEvent[]> {
  const params = new URLSearchParams();
  if (businessId) params.append('business_id', businessId);
  if (status) params.append('status', status);
  if (search) params.append('search', search);

  const url = `${API_BASE}/tools/calendar/events?${params.toString()}`;
  const res = await fetch(url);
  const json = await res.json();
  return json.data || [];
}

export async function createCalendarEvent(data: Partial<CalendarEvent>): Promise<any> {
  const res = await fetch(`${API_BASE}/tools/calendar/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to schedule appointment');
  return json.data;
}

export async function updateCalendarEvent(eventId: string, data: Partial<CalendarEvent>): Promise<any> {
  const res = await fetch(`${API_BASE}/tools/calendar/events/${eventId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || json.detail || 'Failed to update appointment');
  return json.data;
}

export async function checkCalendarAvailability(date: string, time: string, businessId?: string, duration?: number): Promise<any> {
  const res = await fetch(`${API_BASE}/tools/calendar/check-availability`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, time, business_id: businessId, duration })
  });
  const json = await res.json();
  return json.data;
}

export async function syncGoogleCalendar(): Promise<any> {
  const res = await fetch(`${API_BASE}/tools/calendar/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  const json = await res.json();
  return json.data;
}

export async function cancelCalendarEvent(eventId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/tools/calendar/cancel-event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_id: eventId })
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to cancel appointment');
  return json.data;
}

export async function generateTTS(text: string, language: string = 'en') {
  const res = await fetch(`${API_BASE}/ai/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language })
  });
  const json = await res.json();
  return json.data;
}
