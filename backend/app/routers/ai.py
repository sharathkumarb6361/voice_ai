from fastapi import APIRouter, HTTPException, UploadFile, File
from app.models import ChatRequest, TTSRequest
from app.services.ai_service import AiService
from app.services.voice_service import VoiceService

router = APIRouter(prefix="/api/ai", tags=["AI & Voice Services"])

@router.post("/chat")
def chat_turn(data: ChatRequest):
    try:
        result = AiService.process_conversation(data.model_dump())
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tts")
def text_to_speech(data: TTSRequest):
    try:
        audio = VoiceService.text_to_speech(data.text, data.language or "en")
        return {"success": True, "data": audio}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    try:
        content = await audio.read()
        res = VoiceService.speech_to_text(content, audio.content_type)
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
