import { Router, Request, Response } from 'express';
import { db } from '../db/database';
import { v4 as uuidv4 } from 'uuid';

const router = Router();

// List all business profiles
router.get('/', (req: Request, res: Response) => {
  try {
    const businesses = db.prepare('SELECT * FROM businesses ORDER BY created_at DESC').all();
    res.json({ success: true, data: businesses });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Get single business by ID
router.get('/:id', (req: Request, res: Response) => {
  try {
    const biz = db.prepare('SELECT * FROM businesses WHERE id = ?').get(req.params.id);
    if (!biz) {
      return res.status(404).json({ success: false, error: 'Business not found' });
    }
    res.json({ success: true, data: biz });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Create new business profile
router.post('/', (req: Request, res: Response) => {
  try {
    const { name, industry, owner_name, phone, email, address } = req.body;
    if (!name || !industry || !owner_name || !phone || !email) {
      return res.status(400).json({ success: false, error: 'Missing required business fields' });
    }

    const id = `biz-${uuidv4().slice(0, 8)}`;
    const now = new Date().toISOString();

    db.prepare(`
      INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).run(id, name, industry, owner_name, phone, email, address || '', now);

    const created = db.prepare('SELECT * FROM businesses WHERE id = ?').get(id);
    res.status(201).json({ success: true, data: created });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Update business profile
router.put('/:id', (req: Request, res: Response) => {
  try {
    const { name, industry, owner_name, phone, email, address } = req.body;
    db.prepare(`
      UPDATE businesses 
      SET name = ?, industry = ?, owner_name = ?, phone = ?, email = ?, address = ?
      WHERE id = ?
    `).run(name, industry, owner_name, phone, email, address, req.params.id);

    const updated = db.prepare('SELECT * FROM businesses WHERE id = ?').get(req.params.id);
    res.json({ success: true, data: updated });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
