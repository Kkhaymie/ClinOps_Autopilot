# backend/processing/audio_processor.py
import os
import tempfile
import httpx
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))


async def transcribe_voice_note(audio_url: str,
                                 auth_header: str = None) -> dict:
    """
    Download a voice note from any URL and transcribe it.
    Supports Yoruba, Hausa, Igbo, Pidgin, Arabic, Hindi,
    French, Japanese, Mandarin — auto-detected by Whisper.
    auth_header: pass when downloading from Meta (WhatsApp Cloud API).
    """
    try:
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                audio_url, follow_redirects=True, headers=headers
            )
        audio_bytes = resp.content

        # Determine file extension from content-type
        ct = resp.headers.get("content-type", "")
        if "mp4" in ct or "mp4a" in ct:
            suffix = ".mp4"
        elif "wav" in ct:
            suffix = ".wav"
        elif "mpeg" in ct or "mp3" in ct:
            suffix = ".mp3"
        else:
            suffix = ".ogg"

        return await transcribe_bytes(audio_bytes, suffix)

    except Exception as e:
        print(f"transcribe_voice_note error: {e}")
        return {"success": False, "transcript": None, "error": str(e)}


async def transcribe_bytes(audio_bytes: bytes,
                            suffix: str = ".ogg") -> dict:
    """
    Transcribe audio from raw bytes.
    Used by Telegram (downloads as bytes) and video processor.
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False
        ) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        with open(tmp_path, "rb") as af:
            result = groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=af,
                response_format="verbose_json"
            )

        return {
            "success":          True,
            "transcript":       result.text,
            "language_detected": getattr(result, "language", "unknown"),
            "duration_seconds": getattr(result, "duration", 0),
        }

    except Exception as e:
        print(f"transcribe_bytes error: {e}")
        return {
            "success":   False,
            "transcript": None,
            "error":     str(e)
        }
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
