"""Voice module - OpenAI Whisper (STT) and TTS (Nova voice)."""

import os
import tempfile
from openai import OpenAI
import config

client = OpenAI(api_key=config.OPENAI_API_KEY)


async def transcribe_voice(file_path: str) -> str:
    """Transcribe a voice file using OpenAI Whisper."""
    try:
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return transcript.text
    except Exception as e:
        return f"[Voice transcription failed: {str(e)}]"


async def generate_voice(text: str) -> str | None:
    """Generate a voice audio file from text using OpenAI TTS. Returns file path."""
    try:
        # Truncate for voice - keep it punchy (under ~30 seconds)
        voice_text = text
        if len(voice_text) > 500:
            voice_text = voice_text[:497] + "..."

        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=voice_text,
        )

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        temp_file.write(response.content)
        temp_file.close()
        return temp_file.name

    except Exception as e:
        print(f"TTS Error: {e}")
        return None


def cleanup_file(file_path: str):
    """Remove a temporary file."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass
