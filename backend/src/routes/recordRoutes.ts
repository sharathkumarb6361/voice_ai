import { Router, Request, Response } from 'express';
import { db } from '../db/database';

const router = Router();

// List all customer missed call records
router.get('/', (req: Request, res: Response) => {
  try {
    const businessId = req.query.business_id as string;
    const status = req.query.status as string;
    const urgency = req.query.urgency as string;

    let query = `
      SELECT r.*, b.name as business_name, w.name as workflow_name
      FROM records r
      JOIN businesses b ON r.business_id = b.id
      JOIN workflows w ON r.workflow_id = w.id
      WHERE 1=1
    `;
    const params: any[] = [];

    if (businessId) {
      query += ' AND r.business_id = ?';
      params.push(businessId);
    }
    if (status) {
      query += ' AND r.followup_status = ?';
      params.push(status);
    }
    if (urgency) {
      query += ' AND r.urgency = ?';
      params.push(urgency);
    }

    query += ' ORDER BY r.created_at DESC';

    const rows = db.prepare(query).all(...params) as any[];
    const formatted = rows.map(r => ({
      ...r,
      collected_data: JSON.parse(r.collected_data || '{}'),
      transcript: JSON.parse(r.transcript || '[]'),
      tools_executed: JSON.parse(r.tools_executed || '[]')
    }));

    res.json({ success: true, data: formatted });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Update customer record follow-up status (Mark as Contacted, Completed, Closed)
router.patch('/:id/status', (req: Request, res: Response) => {
  try {
    const { status } = req.body;
    if (!['Pending', 'Contacted', 'Completed', 'Closed'].includes(status)) {
      return res.status(400).json({ success: false, error: 'Invalid status value. Must be Pending, Contacted, Completed, or Closed.' });
    }

    db.prepare('UPDATE records SET followup_status = ? WHERE id = ?').run(status, req.params.id);

    const updated = db.prepare('SELECT * FROM records WHERE id = ?').get(req.params.id) as any;
    updated.collected_data = JSON.parse(updated.collected_data || '{}');
    updated.transcript = JSON.parse(updated.transcript || '[]');
    updated.tools_executed = JSON.parse(updated.tools_executed || '[]');

    res.json({ success: true, data: updated });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Delete record
router.delete('/:id', (req: Request, res: Response) => {
  try {
    db.prepare('DELETE FROM records WHERE id = ?').run(req.params.id);
    res.json({ success: true, message: 'Record deleted' });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
