import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { initDatabase } from './db/database';
import businessRoutes from './routes/businessRoutes';
import workflowRoutes from './routes/workflowRoutes';
import recordRoutes from './routes/recordRoutes';
import aiRoutes from './routes/aiRoutes';
import toolRoutes from './routes/toolRoutes';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 5000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Initialize SQLite database schema & seeds
initDatabase();

// Health Check
app.get('/api/health', (req, res) => {
  res.json({
    status: 'online',
    system: 'Voice AI Personal Assistant Backend API',
    timestamp: new Date().toISOString(),
    version: '1.0.0'
  });
});

// API Routes
app.use('/api/businesses', businessRoutes);
app.use('/api/workflows', workflowRoutes);
app.use('/api/records', recordRoutes);
app.use('/api/ai', aiRoutes);
app.use('/api/tools', toolRoutes);

// Global Error Handler
app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
  console.error('Global Error Handler:', err);
  res.status(500).json({ success: false, error: err.message || 'Internal Server Error' });
});

app.listen(PORT, () => {
  console.log(`====================================================`);
  console.log(` Voice AI Personal Assistant Backend Server Running `);
  console.log(` URL: http://localhost:${PORT}                      `);
  console.log(` Health Check: http://localhost:${PORT}/api/health  `);
  console.log(`====================================================`);
});

export default app;
