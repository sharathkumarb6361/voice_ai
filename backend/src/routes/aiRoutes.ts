import { Router, Request, Response } from 'express';
import { AiService } from '../services/aiService';
import { VoiceService } from '../services/voiceService';
import multer from 'multer';

const upload = multer({ limits: { fileSize: 10 * 1024 * 1024 } });
const router = Router();

// AI Chat Conversation Turn (with Tool Calling + Language Detection)
router.post('/chat', async (req: Request, res: Response) => {
  try {
    const { business_id, workflow_id, caller_name, caller_phone, language, messages, record_id } = req.body;
    if (!business_id || !workflow_id || !messages) {
      return res.status(400).json({ success: false, error: 'Missing required parameters (business_id, workflow_id, messages)' });
    }

    const result = await AiService.processConversation({
      business_id,
      workflow_id,
      caller_name,
      caller_phone,
      language,
      messages,
      record_id
    });

    res.json({ success: true, data: result });
  } catch (err: any) {
    console.error('AI Chat Error:', err);
    res.status(500).json({ success: false, error: err.message });
  }
});

// Text-to-Speech (TTS) Voice Synthesis Endpoint
router.post('/tts', async (req: Request, res: Response) => {
  try {
    const { text, language = 'en' } = req.body;
    if (!text) {
      return res.status(400).json({ success: false, error: 'Text parameter is required' });
    }

    const audio = await VoiceService.textToSpeech(text, language);
    res.json({ success: true, data: audio });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Speech-to-Text (STT) Audio Decode Endpoint
router.post('/stt', upload.single('audio'), async (req: Request, res: Response) => {
  try {
    if (!req.file) {
      return res.status(400).json({ success: false, error: 'Audio file upload is required' });
    }

    const result = await VoiceService.speechToText(req.file.buffer, req.file.mimetype);
    res.json({ success: true, data: result });
  } catch (err: any) {
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
