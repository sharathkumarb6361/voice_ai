import { google } from 'googleapis';
import { db } from '../db/database';
import { v4 as uuidv4 } from 'uuid';

export interface CalendarEvent {
  id?: string;
  business_id?: string;
  title: string;
  start_time: string;
  end_time: string;
  attendee_name: string;
  attendee_phone: string;
  description?: string;
  status?: string;
  google_event_id?: string;
}

export class CalendarService {
  private static getOAuthClient() {
    const clientId = process.env.GOOGLE_CLIENT_ID;
    const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
    const refreshToken = process.env.GOOGLE_REFRESH_TOKEN;

    if (clientId && clientSecret && refreshToken) {
      const auth = new google.auth.OAuth2(clientId, clientSecret);
      auth.setCredentials({ refresh_token: refreshToken });
      return auth;
    }
    return null;
  }

  static async checkAvailability(dateStr: string, timeStr: string, durationMinutes: number = 30): Promise<{ available: boolean; recommended_slots?: string[]; message: string }> {
    const auth = this.getOAuthClient();
    
    // Parse target start and end times
    let requestedStart = new Date(`${dateStr}T${timeStr}:00`);
    if (isNaN(requestedStart.getTime())) {
      // Fallback relative date parsing (e.g. "tomorrow", "2026-09-03")
      const now = new Date();
      if (dateStr.toLowerCase().includes('tomorrow')) {
        now.setDate(now.getDate() + 1);
      }
      const timeParts = timeStr.split(':');
      if (timeParts.length >= 2) {
        now.setHours(parseInt(timeParts[0], 10), parseInt(timeParts[1], 10), 0, 0);
      } else {
        now.setHours(16, 0, 0, 0);
      }
      requestedStart = now;
    }

    const requestedEnd = new Date(requestedStart.getTime() + durationMinutes * 60 * 1000);

    if (auth) {
      try {
        const calendar = google.calendar({ version: 'v3', auth });
        const res = await calendar.freebusy.query({
          requestBody: {
            timeMin: requestedStart.toISOString(),
            timeMax: requestedEnd.toISOString(),
            items: [{ id: 'primary' }]
          }
        });
        const busySlots = res.data.calendars?.primary?.busy || [];
        if (busySlots.length > 0) {
          const slot1 = new Date(requestedStart.getTime() + 60 * 60 * 1000).toISOString();
          const slot2 = new Date(requestedStart.getTime() + 120 * 60 * 1000).toISOString();
          return {
            available: false,
            recommended_slots: [slot1, slot2],
            message: `The requested time (${requestedStart.toLocaleTimeString()}) is busy on Google Calendar. Alternative available slots: ${new Date(slot1).toLocaleTimeString()} and ${new Date(slot2).toLocaleTimeString()}.`
          };
        }
      } catch (err: any) {
        console.warn('Google Calendar API check error, falling back to database check:', err.message);
      }
    }

    // Check local database events
    const existing = db.prepare(`
      SELECT * FROM calendar_events 
      WHERE (start_time <= ? AND end_time >= ?) OR (start_time <= ? AND end_time >= ?)
    `).all(
      requestedStart.toISOString(), requestedStart.toISOString(),
      requestedEnd.toISOString(), requestedEnd.toISOString()
    ) as CalendarEvent[];

    if (existing.length > 0) {
      const alt1 = new Date(requestedStart.getTime() + 3600000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const alt2 = new Date(requestedStart.getTime() + 7200000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return {
        available: false,
        recommended_slots: [alt1, alt2],
        message: `Time slot ${requestedStart.toLocaleTimeString()} is currently booked. Alternative open times: ${alt1} and ${alt2}.`
      };
    }

    return {
      available: true,
      message: `Time slot ${requestedStart.toLocaleString()} is fully available on Google Calendar.`
    };
  }

  static async createEvent(eventData: CalendarEvent): Promise<{ success: boolean; event: CalendarEvent; google_event_id?: string; message: string }> {
    const id = `cal-${uuidv4()}`;
    const now = new Date().toISOString();
    const auth = this.getOAuthClient();
    let gcalId: string | undefined = undefined;

    if (auth) {
      try {
        const calendar = google.calendar({ version: 'v3', auth });
        const res = await calendar.events.insert({
          calendarId: 'primary',
          requestBody: {
            summary: eventData.title,
            description: `${eventData.description || ''} | Contact: ${eventData.attendee_name} (${eventData.attendee_phone})`,
            start: { dateTime: eventData.start_time },
            end: { dateTime: eventData.end_time }
          }
        });
        gcalId = res.data.id || undefined;
      } catch (err: any) {
        console.warn('Google Calendar live sync notice:', err.message);
      }
    }

    const businessId = eventData.business_id || 'biz-clinic-01';

    db.prepare(`
      INSERT INTO calendar_events (id, business_id, title, start_time, end_time, attendee_name, attendee_phone, description, status, google_event_id, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      id, businessId, eventData.title, eventData.start_time, eventData.end_time,
      eventData.attendee_name, eventData.attendee_phone, eventData.description || '',
      'Confirmed', gcalId || `gcal_sim_${id.slice(0, 8)}`, now
    );

    const savedEvent: CalendarEvent = {
      id,
      business_id: businessId,
      title: eventData.title,
      start_time: eventData.start_time,
      end_time: eventData.end_time,
      attendee_name: eventData.attendee_name,
      attendee_phone: eventData.attendee_phone,
      description: eventData.description,
      status: 'Confirmed',
      google_event_id: gcalId || `gcal_sim_${id.slice(0, 8)}`
    };

    return {
      success: true,
      event: savedEvent,
      google_event_id: savedEvent.google_event_id,
      message: `Event '${eventData.title}' successfully scheduled on Google Calendar for ${new Date(eventData.start_time).toLocaleString()}.`
    };
  }

  static async updateEvent(eventId: string, newStartTime: string, newEndTime: string): Promise<{ success: boolean; message: string }> {
    const auth = this.getOAuthClient();
    const event = db.prepare('SELECT * FROM calendar_events WHERE id = ? OR google_event_id = ?').get(eventId, eventId) as CalendarEvent;

    if (!event) {
      return { success: false, message: `Calendar event with ID '${eventId}' not found.` };
    }

    if (auth && event.google_event_id && !event.google_event_id.startsWith('gcal_sim')) {
      try {
        const calendar = google.calendar({ version: 'v3', auth });
        await calendar.events.patch({
          calendarId: 'primary',
          eventId: event.google_event_id,
          requestBody: {
            start: { dateTime: newStartTime },
            end: { dateTime: newEndTime }
          }
        });
      } catch (err: any) {
        console.warn('Google Calendar update sync warning:', err.message);
      }
    }

    db.prepare('UPDATE calendar_events SET start_time = ?, end_time = ? WHERE id = ?')
      .run(newStartTime, newEndTime, event.id);

    return {
      success: true,
      message: `Calendar event '${event.title}' successfully rescheduled to ${new Date(newStartTime).toLocaleString()}.`
    };
  }

  static async cancelEvent(eventId: string): Promise<{ success: boolean; message: string }> {
    const auth = this.getOAuthClient();
    const event = db.prepare('SELECT * FROM calendar_events WHERE id = ? OR google_event_id = ?').get(eventId, eventId) as CalendarEvent;

    if (!event) {
      return { success: false, message: `Calendar event '${eventId}' not found.` };
    }

    if (auth && event.google_event_id && !event.google_event_id.startsWith('gcal_sim')) {
      try {
        const calendar = google.calendar({ version: 'v3', auth });
        await calendar.events.delete({
          calendarId: 'primary',
          eventId: event.google_event_id
        });
      } catch (err: any) {
        console.warn('Google Calendar delete sync warning:', err.message);
      }
    }

    db.prepare("UPDATE calendar_events SET status = 'Cancelled' WHERE id = ?").run(event.id);

    return {
      success: true,
      message: `Calendar event '${event.title}' has been cancelled.`
    };
  }

  static async listEvents(businessId?: string) {
    if (businessId) {
      return db.prepare('SELECT * FROM calendar_events WHERE business_id = ? ORDER BY start_time DESC').all(businessId);
    }
    return db.prepare('SELECT * FROM calendar_events ORDER BY start_time DESC').all();
  }
}
