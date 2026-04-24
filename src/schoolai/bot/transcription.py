from groq import AsyncGroq


async def transcribe(audio_bytes: bytes, filename: str, api_key: str) -> str:
    client = AsyncGroq(api_key=api_key)
    transcription = await client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model="whisper-large-v3-turbo",
        language="es",
        temperature=0.0,
    )
    return transcription.text
