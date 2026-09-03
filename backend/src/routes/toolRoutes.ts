import { Router, Request, Response } from 'express';
import { CalendarService } from '../services/calendarService';
import { ExternalApiService } from '../services/externalApiService';

const router = Router();

// Google Calendar: List events
router.get('/calendar/events', async (req: Request, res: Response) => {
  try {
    const businessId = req.query.business_id as string;
    const events = await CalendarService.listEvents(businessId);
    res.json({ success: true, data: events });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Google Calendar: Check Availability
router.post('/calendar/check-availability', async (req: Request, res: Response) => {
  try {
    const { date, time, duration_minutes } = req.body;
    const result = await CalendarService.checkAvailability(date, time, duration_minutes);
    res.json({ success: true, data: result });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Google Calendar: Create Event
router.post('/calendar/create-event', async (req: Request, res: Response) => {
  try {
    const { business_id, title, start_time, end_time, attendee_name, attendee_phone, description } = req.body;
    const result = await CalendarService.createEvent({
      business_id, title, start_time, end_time, attendee_name, attendee_phone, description
    });
    res.json({ success: true, data: result });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Bonus External REST API: Track Delivery Status
router.get('/delivery/track/:tracking_number', async (req: Request, res: Response) => {
  try {
    const trackingNo = req.params.tracking_number;
    const data = await ExternalApiService.trackDeliveryStatus(trackingNo);
    res.json({ success: true, data });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Bonus External REST API: CRM Lookup
router.get('/crm/customer/:phone', async (req: Request, res: Response) => {
  try {
    const data = await ExternalApiService.lookupCrmCustomer(req.params.phone);
    res.json({ success: true, data });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
