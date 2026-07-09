# backend/processing/video_processor.py
import os
import tempfile
import base64
import json
import httpx
from mistralai import Mistral
from processing.audio_processor import transcribe_bytes
from dotenv import load_dotenv

load_dotenv()

mistral = Mistral(api_key=os.getenv("MISTRAL_API_KEY", ""))

FRAME_PROMPT = """Analyse this video frame from a clinical trial patient.
Look for: visible symptoms (swelling, rash, skin changes, wounds),
medicine bottles or packaging in background,
food items (especially starfruit, grapefruit, zobo drink, kola nut).
Return JSON only:
{
  "symptoms_visible": ["symptom1"],
  "objects_detected": ["object1"],
  "medical_relevance": "high|medium|low"
}"""


async def process_video_message(video_url: str,
                                 auth_header: str = None) -> dict:
    """
    Process a patient video message:
    1. Extract and transcribe audio track (Groq Whisper)
    2. Extract key frames and analyse visually (Mistral Pixtral)
    3. Merge into single clinical summary
    auth_header: pass when URL is from WhatsApp Cloud API.
    """
    try:
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header

        async with httpx.AsyncClient(timeout=90) as c:
            resp = await c.get(
                video_url, follow_redirects=True, headers=headers
            )
        video_bytes = resp.content

        with tempfile.NamedTemporaryFile(
            suffix=".mp4", delete=False
        ) as f:
            f.write(video_bytes)
            vpath = f.name

        audio_result  = await _extract_and_transcribe_audio(vpath)
        frame_results = _extract_and_analyse_frames(vpath)
        merged        = _merge_streams(audio_result, frame_results)

        try:
            os.unlink(vpath)
        except Exception:
            pass

        return {
            "success":               True,
            "audio_transcript":      audio_result.get("transcript"),
            "language_detected":     audio_result.get("language_detected"),
            "visual_analysis":       frame_results,
            "merged_clinical_summary": merged,
        }

    except Exception as e:
        print(f"process_video_message error: {e}")
        return {
            "success":               False,
            "error":                 str(e),
            "merged_clinical_summary": "Video processing failed"
        }


async def _extract_and_transcribe_audio(vpath: str) -> dict:
    """Extract audio track from video and transcribe."""
    try:
        from moviepy import VideoFileClip
        clip  = VideoFileClip(vpath)
        apath = vpath.replace(".mp4", "_audio.wav")
        clip.audio.write_audiofile(apath, verbose=False, logger=None)
        clip.close()
        with open(apath, "rb") as f:
            audio_bytes = f.read()
        try:
            os.unlink(apath)
        except Exception:
            pass
        return await transcribe_bytes(audio_bytes, ".wav")
    except Exception as e:
        return {"success": False, "transcript": None, "error": str(e)}


def _extract_and_analyse_frames(vpath: str) -> list:
    """Extract frames every 3 seconds and analyse medically relevant ones."""
    results = []
    try:
        import cv2
        cap      = cv2.VideoCapture(vpath)
        fps      = cap.get(cv2.CAP_PROP_FPS) or 25
        interval = int(fps * 3)
        fc       = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if fc % interval == 0:
                _, buf = cv2.imencode(".jpg", frame)
                b64    = base64.b64encode(buf.tobytes()).decode()
                try:
                    r   = mistral.chat.complete(
                        model="pixtral-large-latest",
                        messages=[{"role": "user", "content": [
                            {"type": "image_url",
                             "image_url": f"data:image/jpeg;base64,{b64}"},
                            {"type": "text", "text": FRAME_PROMPT}
                        ]}]
                    )
                    raw = r.choices[0].message.content.strip()
                    if "```" in raw:
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:].strip()
                    fa  = json.loads(raw)
                    if fa.get("medical_relevance") in ["high", "medium"]:
                        results.append({
                            "time_seconds": round(fc / fps, 1),
                            "analysis":     fa
                        })
                except Exception:
                    pass
            fc += 1
        cap.release()
    except Exception as e:
        results.append({"error": str(e)})
    return results


def _merge_streams(audio: dict, frames: list) -> str:
    """Merge audio transcript and visual analysis into one clinical summary."""
    parts    = []
    symptoms = []
    objects  = []

    if audio.get("transcript"):
        parts.append(f"Patient stated: '{audio['transcript']}'")

    for f in frames:
        a = f.get("analysis", {})
        symptoms += a.get("symptoms_visible", [])
        objects  += a.get("objects_detected", [])

    if symptoms:
        parts.append(f"Visible symptoms observed: {', '.join(set(symptoms))}")
    if objects:
        parts.append(f"Items visible in video background: {', '.join(set(objects))}")

    return ". ".join(parts) if parts else "No clinical content detected in video."
