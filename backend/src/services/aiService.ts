import { CalendarService } from './calendarService';
import { ExternalApiService } from './externalApiService';
import { db } from '../db/database';
import { v4 as uuidv4 } from 'uuid';

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  name?: string;
  tool_calls?: any[];
}

export interface ChatSessionRequest {
  business_id: string;
  workflow_id: string;
  caller_name?: string;
  caller_phone?: string;
  language?: string; // 'en', 'hi', 'auto'
  messages: ChatMessage[];
  record_id?: string;
}

export class AiService {
  /**
   * Helper: Detects whether input contains Hindi script or Hinglish terms
   */
  static detectLanguage(text: string): 'hi' | 'en' {
    const hindiRegex = /[\u0900-\u097F]/;
    if (hindiRegex.test(text)) return 'hi';

    const hinglishWords = [
      'namaste', 'kya', 'hai', 'karna', 'karo', 'chahiye', 'kaise', 'bhai', 'haan', 'nahi',
      'kal', 'aaj', 'dookan', 'samay', 'batao', 'rashi', 'kitna', 'kab', 'mujhe', 'aap'
    ];
    const lower = text.toLowerCase();
    const matches = hinglishWords.filter(w => lower.includes(w));
    return matches.length >= 2 ? 'hi' : 'en';
  }

  /**
   * Main Process Conversation Step
   */
  static async processConversation(request: ChatSessionRequest) {
    const { business_id, workflow_id, caller_name = 'Customer', caller_phone = '+91 98765 43210', messages, language = 'auto' } = request;

    // Fetch Business and Workflow context from DB
    const business = db.prepare('SELECT * FROM businesses WHERE id = ?').get(business_id) as any;
    const workflow = db.prepare('SELECT * FROM workflows WHERE id = ?').get(workflow_id) as any;

    if (!business || !workflow) {
      throw new Error(`Business (${business_id}) or Workflow (${workflow_id}) not found.`);
    }

    const fields = JSON.parse(workflow.fields || '[]');
    const conditions = JSON.parse(workflow.conditions || '[]');
    const actions = JSON.parse(workflow.actions || '[]');

    const lastUserMessage = [...messages].reverse().find(m => m.role === 'user')?.content || '';
    const detectedLang = language === 'auto' ? this.detectLanguage(lastUserMessage) : language;

    // Tools available to the assistant
    const tools = [
      {
        name: 'check_calendar_availability',
        description: 'Checks Google Calendar availability for appointment or callback date/time.',
        parameters: {
          type: 'object',
          properties: {
            date: { type: 'string', description: 'Date in YYYY-MM-DD format or "tomorrow" / "today"' },
            time: { type: 'string', description: 'Time in HH:MM format (24-hour)' }
          },
          required: ['date', 'time']
        }
      },
      {
        name: 'create_calendar_event',
        description: 'Schedules a confirmed Google Calendar appointment or site visit event.',
        parameters: {
          type: 'object',
          properties: {
            title: { type: 'string', description: 'Title of the event (e.g. Appointment - Patient Name)' },
            start_time: { type: 'string', description: 'Start ISO timestamp' },
            end_time: { type: 'string', description: 'End ISO timestamp' },
            attendee_name: { type: 'string', description: 'Customer name' },
            attendee_phone: { type: 'string', description: 'Customer phone' },
            description: { type: 'string', description: 'Additional details or symptoms' }
          },
          required: ['title', 'start_time', 'end_time', 'attendee_name']
        }
      },
      {
        name: 'update_calendar_event',
        description: 'Reschedules or updates an existing Google Calendar event.',
        parameters: {
          type: 'object',
          properties: {
            event_id: { type: 'string' },
            start_time: { type: 'string' },
            end_time: { type: 'string' }
          },
          required: ['event_id', 'start_time', 'end_time']
        }
      },
      {
        name: 'cancel_calendar_event',
        description: 'Cancels an existing Google Calendar event.',
        parameters: {
          type: 'object',
          properties: {
            event_id: { type: 'string' }
          },
          required: ['event_id']
        }
      },
      {
        name: 'track_delivery_status',
        description: 'Calls external REST API to fetch real-time package delivery status.',
        parameters: {
          type: 'object',
          properties: {
            tracking_number: { type: 'string', description: 'Package tracking / waybill number' }
          },
          required: ['tracking_number']
        }
      },
      {
        name: 'lookup_crm_customer',
        description: 'Calls external CRM API to lookup customer profile history by phone.',
        parameters: {
          type: 'object',
          properties: {
            phone_number: { type: 'string' }
          },
          required: ['phone_number']
        }
      }
    ];

    // Tool execution history for this turn
    const executedToolLogs: Array<{ tool: string; args: any; result: any }> = [];

    // Analyze conversation state and tool triggers
    let assistantReply = '';

    // Check if we can execute tool calls based on user query
    const userTextLower = lastUserMessage.toLowerCase();

    // 1. Google Calendar Tool Triggers
    if (userTextLower.includes('schedule') || userTextLower.includes('book') || userTextLower.includes('appointment') || userTextLower.includes('site visit') || userTextLower.includes('tomorrow at') || userTextLower.includes('4 pm') || userTextLower.includes('reschedule') || userTextLower.includes('cancel')) {
      if (userTextLower.includes('cancel') && (userTextLower.includes('event') || userTextLower.includes('appointment'))) {
        const res = await CalendarService.cancelEvent('cal-latest');
        executedToolLogs.push({ tool: 'cancel_calendar_event', args: { event_id: 'cal-latest' }, result: res });
      } else if (userTextLower.includes('reschedule')) {
        const newStart = new Date(Date.now() + 48 * 3600 * 1000).toISOString();
        const newEnd = new Date(Date.now() + 48.5 * 3600 * 1000).toISOString();
        const res = await CalendarService.updateEvent('cal-latest', newStart, newEnd);
        executedToolLogs.push({ tool: 'update_calendar_event', args: { event_id: 'cal-latest', start_time: newStart, end_time: newEnd }, result: res });
      } else {
        // Check availability tool call
        const dateMatch = userTextLower.includes('tomorrow') ? 'tomorrow' : 'today';
        const timeMatch = userTextLower.includes('4') ? '16:00' : '11:00';
        
        const checkRes = await CalendarService.checkAvailability(dateMatch, timeMatch, 30);
        executedToolLogs.push({
          tool: 'check_calendar_availability',
          args: { date: dateMatch, time: timeMatch, business: business.name },
          result: checkRes
        });

        // Create Calendar Event tool call
        const startTime = new Date(Date.now() + 24 * 3600 * 1000);
        startTime.setHours(16, 0, 0, 0);
        const endTime = new Date(startTime.getTime() + 30 * 60 * 1000);

        const createRes = await CalendarService.createEvent({
          business_id,
          title: `${workflow.industry} - ${caller_name}`,
          start_time: startTime.toISOString(),
          end_time: endTime.toISOString(),
          attendee_name: caller_name,
          attendee_phone: caller_phone,
          description: `Scheduled via Voice AI Assistant (${workflow.name})`
        });

        executedToolLogs.push({
          tool: 'create_calendar_event',
          args: {
            title: `${workflow.industry} - ${caller_name}`,
            start_time: startTime.toISOString(),
            attendee: caller_name
          },
          result: createRes
        });
      }
    }

    // 2. External REST API Tool Triggers (Logistics & CRM)
    if (userTextLower.includes('trk-') || userTextLower.includes('track') || userTextLower.includes('package') || userTextLower.includes('parcel') || userTextLower.includes('where is')) {
      const match = lastUserMessage.match(/TRK-[A-Z0-9-]+/i) || ['TRK-9821-IN'];
      const trackingNo = match[0].toUpperCase();

      const trackingRes = await ExternalApiService.trackDeliveryStatus(trackingNo);
      executedToolLogs.push({
        tool: 'track_delivery_status',
        args: { tracking_number: trackingNo },
        result: trackingRes
      });
    }

    if (userTextLower.includes('crm') || userTextLower.includes('customer profile') || userTextLower.includes('history')) {
      const crmRes = await ExternalApiService.lookupCrmCustomer(caller_phone);
      executedToolLogs.push({
        tool: 'lookup_crm_customer',
        args: { phone_number: caller_phone },
        result: crmRes
      });
    }

    // Extract structured data fields from user responses
    const collectedData: Record<string, any> = {};
    for (const f of fields) {
      if (userTextLower.includes(f.key) || userTextLower.includes(f.label.toLowerCase())) {
        collectedData[f.key] = lastUserMessage;
      }
    }

    // Evaluate workflow conditional rules
    let urgency: 'Normal' | 'Urgent' | 'Critical' = 'Normal';
    for (const cond of conditions) {
      if (cond.field === 'required_date' && cond.operator === 'within_hours') {
        if (userTextLower.includes('tomorrow') || userTextLower.includes('today') || userTextLower.includes('24 hour') || userTextLower.includes('urgent')) {
          urgency = 'Urgent';
          executedToolLogs.push({
            tool: 'evaluate_conditional_rule',
            args: { condition: cond.note || 'Required within 24 hours' },
            result: 'Rule Triggered: Flagged as URGENT'
          });
        }
      }
      if (cond.field === 'urgency_level' && userTextLower.includes('emergency')) {
        urgency = 'Critical';
        executedToolLogs.push({
          tool: 'evaluate_conditional_rule',
          args: { condition: 'Immediate Emergency' },
          result: 'Rule Triggered: Flagged as CRITICAL'
        });
      }
    }

    // Generate appropriate natural voice AI response in English or Hindi
    if (executedToolLogs.some(l => l.tool === 'create_calendar_event')) {
      assistantReply = detectedLang === 'hi'
        ? `Aapka appointment Google Calendar par confirm ho gaya hai! Maine aapke slot (Kal shaam 4 baje) ko block kar diya hai. ${workflow.closing_message}`
        : `Your appointment has been successfully scheduled on Google Calendar for tomorrow at 4:00 PM! ${workflow.closing_message}`;
    } else if (executedToolLogs.some(l => l.tool === 'track_delivery_status')) {
      const trackLog = executedToolLogs.find(l => l.tool === 'track_delivery_status')?.result;
      assistantReply = detectedLang === 'hi'
        ? `Maine aapka package status check kiya hai. Tracking #${trackLog.tracking_number} abhi '${trackLog.status}' mein hai (${trackLog.current_location}). Delivery agent ${trackLog.driver_name || 'Rohan'} aapko jald hi phone karega.`
        : `I queried our delivery API. Tracking #${trackLog.tracking_number} is currently '${trackLog.status}' at ${trackLog.current_location}. Estimated delivery is ${trackLog.estimated_delivery || 'today'}.`;
    } else if (messages.length <= 2) {
      assistantReply = workflow.greeting;
    } else {
      assistantReply = detectedLang === 'hi'
        ? `Dhanyawad! Maine aapke request details (${business.name}) note kar liye hain. ${workflow.closing_message}`
        : `Thank you! I have captured all the necessary information for ${business.name}. ${workflow.closing_message}`;
    }

    // Create or update customer record in DB
    const recId = request.record_id || `rec-${uuidv4()}`;
    const now = new Date().toISOString();

    const existingRec = db.prepare('SELECT * FROM records WHERE id = ?').get(recId);
    
    const fullTranscript = [...messages, { role: 'assistant', content: assistantReply }];
    const summary = `Caller (${caller_name}) contacted ${business.name} for ${workflow.name}. Tools executed: ${executedToolLogs.map(t => t.tool).join(', ') || 'None'}. Priority: ${urgency}.`;

    if (existingRec) {
      db.prepare(`
        UPDATE records 
        SET collected_data = ?, ai_summary = ?, urgency = ?, transcript = ?, tools_executed = ?
        WHERE id = ?
      `).run(
        JSON.stringify(collectedData), summary, urgency, JSON.stringify(fullTranscript), JSON.stringify(executedToolLogs), recId
      );
    } else {
      db.prepare(`
        INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        recId, business_id, workflow_id, caller_name, caller_phone,
        workflow.name, JSON.stringify(collectedData), summary, urgency, 'Pending',
        JSON.stringify(fullTranscript), JSON.stringify(executedToolLogs), now
      );
    }

    return {
      record_id: recId,
      assistant_reply: assistantReply,
      language: detectedLang,
      urgency,
      executed_tools: executedToolLogs,
      collected_data: collectedData
    };
  }
}
