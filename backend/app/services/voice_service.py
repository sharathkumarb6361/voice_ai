import os
import base64
import io
import math
import re
import struct
import httpx
from gtts import gTTS
from dotenv import load_dotenv

load_dotenv()

_invalid_sarvam_keys: set[str] = set()

class PipecatVoicePipeline:
    """
    Pipecat Audio Frame Pipeline Orchestrator.
    Routes audio frames between Deepgram / Sarvam AI / Groq Whisper for STT
    and ElevenLabs / Sarvam AI / gTTS for TTS synthesis.
    No browser speech APIs required.
    """
    @staticmethod
    def _audio_filename(content_type: str, filename: str | None = None) -> str:
        """Preserve the recording container so STT providers decode it correctly."""
        if filename and "." in filename:
            return filename

        mime_type = (content_type or "").split(";", 1)[0].strip().lower()
        extensions = {
            "audio/webm": "webm",
            "audio/ogg": "ogg",
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/mpeg": "mp3",
            "audio/mp4": "m4a",
        }
        return f"recording.{extensions.get(mime_type, 'webm')}"

    @staticmethod
    def process_stt(
        audio_bytes: bytes,
        content_type: str = "audio/wav",
        language: str = "auto",
        filename: str | None = None,
    ) -> dict:
        sarvam_key = os.getenv("SARVAM_API_KEY")
        deepgram_key = os.getenv("DEEPGRAM_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        audio_filename = PipecatVoicePipeline._audio_filename(content_type, filename)
        provider_errors = []

        # 1. Primary Indic-language STT. Saaras preserves code-mixed Hindi/Kannada speech.
        if sarvam_key and sarvam_key not in _invalid_sarvam_keys:
            try:
                stt_model = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
                stt_mode = os.getenv("SARVAM_STT_MODE", "codemix")
                print(f"[Pipecat -> Sarvam AI STT] Decoding Indian language audio frame with {stt_model}...")
                url = "https://api.sarvam.ai/speech-to-text"
                headers = {"api-subscription-key": sarvam_key}
                files = {"file": (audio_filename, audio_bytes, content_type)}
                lang_code = "hi-IN" if language == "hi" else ("kn-IN" if language == "kn" else ("en-IN" if language == "en" else "unknown"))
                data = {"model": stt_model, "language_code": lang_code, "mode": stt_mode}
                with httpx.Client(timeout=4.0) as client:
                    resp = client.post(url, headers=headers, files=files, data=data)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        text = res_json.get("transcript", "")
                        if text:
                            return {
                                "text": text,
                                "language": res_json.get("language_code", lang_code),
                                "provider": f"Sarvam AI {stt_model}",
                                "confidence": 0.99,
                            }
                    else:
                        print(f"Sarvam AI STT API error ({resp.status_code}): {resp.text[:150]}")
                        if resp.status_code in (401, 403):
                            _invalid_sarvam_keys.add(sarvam_key)
                        provider_errors.append("Sarvam AI could not transcribe this recording")
            except Exception as e:
                print(f"Sarvam AI STT notice ({e}), falling back...")
                provider_errors.append("Sarvam AI transcription request failed")

        # 2. Try Groq Whisper STT if GROQ_API_KEY is available
        if groq_key:
            try:
                print(f"[Pipecat -> Groq Whisper STT] Decoding audio frame with whisper-large-v3...")
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                headers = {"Authorization": f"Bearer {groq_key}"}
                clean_mime = (content_type or "audio/webm").split(";")[0].strip()
                files = {"file": (audio_filename, audio_bytes, clean_mime)}
                data = {"model": "whisper-large-v3", "response_format": "json"}
                if language in {"hi", "kn", "en"}:
                    data["language"] = language
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, headers=headers, files=files, data=data)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        text = res_json.get("text", "")
                        if text:
                            return {"text": text, "provider": "Groq Whisper-v3", "confidence": 0.99}
                    else:
                        print(f"Groq Whisper STT error ({resp.status_code}): {resp.text[:200]}")
                        provider_errors.append(f"Groq Whisper error ({resp.status_code})")
            except Exception as e:
                print(f"Groq Whisper STT notice ({e}), falling back...")
                provider_errors.append("Groq transcription request failed")

        # 3. Try Deepgram Nova-2 STT if DEEPGRAM_API_KEY is available
        if deepgram_key:
            try:
                print(f"[Pipecat -> Deepgram STT] Decoding audio frame with Nova-2...")
                lang_param = "hi" if language == "hi" else ("kn" if language == "kn" else "en-US")
                url = f"https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&language={lang_param}"
                headers = {"Authorization": f"Token {deepgram_key}", "Content-Type": content_type}
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, headers=headers, content=audio_bytes)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        transcript = res_json["results"]["channels"][0]["alternatives"][0]["transcript"]
                        if transcript:
                            return {"text": transcript, "provider": "Deepgram Nova-2", "confidence": 0.99}
            except Exception as e:
                print(f"Deepgram STT notice ({e}), falling back...")
                provider_errors.append("Deepgram transcription request failed")

        # Do not invent an English transcript when all providers fail; it corrupts the conversation.
        return {
            "text": "",
            "provider": "No STT provider available",
            "confidence": 0.0,
            "error": "Could not transcribe the recording. Please try again or check the speech service configuration."
        }

    @staticmethod
    def clean_for_speech(text: str) -> str:
        """
        Cleans and normalizes conversational text for ultra-natural, human-like voice synthesis.
        Eliminates markdown syntax, emojis, technical symbols, and converts abbreviations.
        """
        if not text:
            return ""
        # 1. Remove parenthetical technical / language switch notices
        t = re.sub(r'^\*\([^*]+\)\*\s*', '', text)
        t = re.sub(r'\([A-Za-z\s]+switched to[^\)]+\)', '', t)
        # 2. Remove markdown formatting (bold, italics, headings, code, bullets)
        t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
        t = re.sub(r'\*([^*]+)\*', r'\1', t)
        t = re.sub(r'__([^_]+)__', r'\1', t)
        t = re.sub(r'_([^_]+)_', r'\1', t)
        t = re.sub(r'#+\s*', '', t)
        t = re.sub(r'^[ \t]*[-*+]\s+', '', t, flags=re.MULTILINE)
        t = re.sub(r'`[^`]*`', '', t)
        # 3. Normalize currency, units, and waybills to natural spoken words
        t = re.sub(r'\bINR\s*(\d+)', r'\1 rupees', t, flags=re.IGNORECASE)
        t = re.sub(r'\bRs\.?\s*(\d+)', r'\1 rupees', t, flags=re.IGNORECASE)
        t = re.sub(r'\b(\d+)\s*kg\b', r'\1 kilograms', t, flags=re.IGNORECASE)
        t = re.sub(r'TRK-([A-Za-z0-9-]+)', r'tracking number \1', t)
        # 4. Remove emojis and non-speech symbols
        emoji_pattern = re.compile('[\U00010000-\U0010ffff]', flags=re.UNICODE)
        t = emoji_pattern.sub('', t)
        t = re.sub(r'[✓✔✕✖•●★☆🍰🎂🚚📦📞🤖👤🗓️📅🔄⚠️]', '', t)
        # 5. Normalize whitespace
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    @staticmethod
    def process_tts(text: str, language: str = "en") -> dict:
        clean_text = PipecatVoicePipeline.clean_for_speech(text)
        if not clean_text:
            clean_text = text.strip() or "Hello, how may I help you?"

        sarvam_key = os.getenv("SARVAM_API_KEY")
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel voice
        sarvam_speaker = os.getenv("SARVAM_SPEAKER", "kavya")  # kavya provides warm, natural, human-like voice

        # 1. Primary Indian Voice AI: Sarvam AI Bulbul v3 with High-Definition 24kHz audio & natural prosody
        if sarvam_key and sarvam_key not in _invalid_sarvam_keys:
            try:
                target_code = "hi-IN" if language == "hi" else ("kn-IN" if language == "kn" else "en-IN")
                print(f"[Pipecat -> Sarvam AI Bulbul v3 TTS] Synthesizing natural human voice ({target_code}, speaker: {sarvam_speaker}, 24kHz)...")
                url = "https://api.sarvam.ai/text-to-speech"
                headers = {"api-subscription-key": sarvam_key, "Content-Type": "application/json"}
                payload = {
                    "inputs": [clean_text],
                    "target_language_code": target_code,
                    "speaker": sarvam_speaker,
                    "model": "bulbul:v3",
                    "pace": 0.98,
                    "speech_sample_rate": 24000,
                    "enable_preprocessing": True
                }
                with httpx.Client(timeout=4.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        audios = res_json.get("audios", [])
                        if audios:
                            return {
                                "audio_base64": audios[0],
                                "format": "audio/wav",
                                "provider": f"Sarvam AI Bulbul v3 Natural ({target_code})",
                                "duration_seconds": max(len(clean_text) * 0.075, 1.5)
                            }
                    else:
                        print(f"Sarvam AI TTS API notice ({resp.status_code}): {resp.text[:150]}")
                        if resp.status_code in (401, 403):
                            _invalid_sarvam_keys.add(sarvam_key)
            except Exception as e:
                print(f"Sarvam AI TTS notice ({e}), falling back...")

        # 2. Studio Natural Voice: ElevenLabs Multilingual v2
        if elevenlabs_key:
            try:
                print(f"[Pipecat -> ElevenLabs TTS] Synthesizing expressive human voice with ElevenLabs ({voice_id})...")
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                headers = {"xi-api-key": elevenlabs_key, "Content-Type": "application/json"}
                payload = {
                    "text": clean_text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.45,
                        "similarity_boost": 0.85,
                        "style": 0.20,
                        "use_speaker_boost": True
                    }
                }
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        audio_b64 = base64.b64encode(resp.content).decode("utf-8")
                        return {
                            "audio_base64": audio_b64,
                            "format": "audio/mp3",
                            "provider": "ElevenLabs Multilingual v2 (Human Studio)",
                            "duration_seconds": max(len(clean_text) * 0.075, 1.5)
                        }
            except Exception as e:
                print(f"ElevenLabs TTS notice ({e}), falling back...")

        # 3. Natural gTTS synthesis fallback
        try:
            print(f"[Pipecat -> gTTS] Synthesizing conversational audio ({language})...")
            lang_code = "kn" if language == "kn" else ("hi" if language == "hi" else "en")
            tld = "co.in" if lang_code == "en" else "com"
            tts = gTTS(text=clean_text, lang=lang_code, tld=tld, slow=False)
            mp3_fp = io.BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            audio_b64 = base64.b64encode(mp3_fp.read()).decode("utf-8")
            return {
                "audio_base64": audio_b64,
                "format": "audio/mp3",
                "provider": "gTTS Natural Engine",
                "duration_seconds": max(len(clean_text) * 0.075, 1.5)
            }
        except Exception as e:
            print(f"gTTS fallback notice: {e}")
            return {
                "audio_base64": "",
                "format": "audio/mp3",
                "provider": "Client Speech Synthesis",
                "duration_seconds": 1.0
            }

class VoiceService:
    @staticmethod
    def text_to_speech(text: str, language: str = "en"):
        return PipecatVoicePipeline.process_tts(text, language)

    @staticmethod
    def speech_to_text(
        audio_bytes: bytes,
        content_type: str = "audio/wav",
        language_hint: str = "auto",
        filename: str | None = None,
    ):
        return PipecatVoicePipeline.process_stt(audio_bytes, content_type, language_hint, filename)
