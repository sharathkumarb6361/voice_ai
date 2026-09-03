import { Router, Request, Response } from 'express';
import { db } from '../db/database';
import { v4 as uuidv4 } from 'uuid';

const router = Router();

// List all workflows
router.get('/', (req: Request, res: Response) => {
  try {
    const businessId = req.query.business_id as string;
    let query = 'SELECT w.*, b.name as business_name FROM workflows w JOIN businesses b ON w.business_id = b.id ORDER BY w.created_at DESC';
    let params: any[] = [];

    if (businessId) {
      query = 'SELECT w.*, b.name as business_name FROM workflows w JOIN businesses b ON w.business_id = b.id WHERE w.business_id = ? ORDER BY w.created_at DESC';
      params = [businessId];
    }

    const rows = db.prepare(query).all(...params) as any[];
    const formatted = rows.map(r => ({
      ...r,
      fields: JSON.parse(r.fields || '[]'),
      conditions: JSON.parse(r.conditions || '[]'),
      actions: JSON.parse(r.actions || '[]')
    }));

    res.json({ success: true, data: formatted });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Get single workflow by ID
router.get('/:id', (req: Request, res: Response) => {
  try {
    const row = db.prepare('SELECT w.*, b.name as business_name FROM workflows w JOIN businesses b ON w.business_id = b.id WHERE w.id = ?').get(req.params.id) as any;
    if (!row) {
      return res.status(404).json({ success: false, error: 'Workflow not found' });
    }
    row.fields = JSON.parse(row.fields || '[]');
    row.conditions = JSON.parse(row.conditions || '[]');
    row.actions = JSON.parse(row.actions || '[]');

    res.json({ success: true, data: row });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Create Custom Workflow (Custom Workflow Builder Backend)
router.post('/', (req: Request, res: Response) => {
  try {
    const {
      business_id, name, industry, trigger_event = 'Missed Call',
      greeting, fields = [], conditions = [], actions = [],
      closing_message, language = 'en-hi'
    } = req.body;

    if (!business_id || !name || !greeting || !closing_message) {
      return res.status(400).json({ success: false, error: 'Missing required workflow fields' });
    }

    const id = `wf-${uuidv4().slice(0, 8)}`;
    const now = new Date().toISOString();

    db.prepare(`
      INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, is_active, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
    `).run(
      id, business_id, name, industry || 'Custom Small Business',
      trigger_event, greeting, JSON.stringify(fields),
      JSON.stringify(conditions), JSON.stringify(actions),
      closing_message, language, now
    );

    const created = db.prepare('SELECT * FROM workflows WHERE id = ?').get(id) as any;
    created.fields = JSON.parse(created.fields);
    created.conditions = JSON.parse(created.conditions);
    created.actions = JSON.parse(created.actions);

    res.status(201).json({ success: true, data: created });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Update workflow
router.put('/:id', (req: Request, res: Response) => {
  try {
    const {
      name, industry, greeting, fields, conditions, actions, closing_message, language, is_active
    } = req.body;

    db.prepare(`
      UPDATE workflows 
      SET name = ?, industry = ?, greeting = ?, fields = ?, conditions = ?, actions = ?, closing_message = ?, language = ?, is_active = ?
      WHERE id = ?
    `).run(
      name, industry, greeting, JSON.stringify(fields || []),
      JSON.stringify(conditions || []), JSON.stringify(actions || []),
      closing_message, language || 'en-hi', is_active ?? 1, req.params.id
    );

    const updated = db.prepare('SELECT * FROM workflows WHERE id = ?').get(req.params.id) as any;
    updated.fields = JSON.parse(updated.fields);
    updated.conditions = JSON.parse(updated.conditions);
    updated.actions = JSON.parse(updated.actions);

    res.json({ success: true, data: updated });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Delete workflow
router.delete('/:id', (req: Request, res: Response) => {
  try {
    db.prepare('DELETE FROM workflows WHERE id = ?').run(req.params.id);
    res.json({ success: true, message: 'Workflow deleted successfully' });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
