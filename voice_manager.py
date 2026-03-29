"""
voice_manager.py
Corrected to yield events sequentially for the frontend to process.
"""
from asr_engine import ASREngine
from tts_engine import TTSEngine
from conversation_manager import ConversationManager

class VoiceManager:
    def __init__(self, session_id: str):
        self.session_id = session_id
        # Note: These are heavy models; ideally pre-load them as in your main.py
        self.asr = ASREngine(model_size="tiny.en")
        self.tts = TTSEngine(model_path="voices/en_US-lessac-medium.onnx")
        self.conv = ConversationManager(session_id=session_id)

    def process_audio_streaming(self, audio_bytes: bytes):
        """
        Processes audio through ASR -> LLM -> TTS.
        Yields results step-by-step.
        """
        # 1. Transcribe
        user_text = self.asr.transcribe_bytes(audio_bytes)
        if not user_text:
            yield {"type": "error", "data": "Could not understand audio."}
            return

        yield {"type": "transcript", "data": user_text}

        # 2. Get LLM response (collected as a whole for TTS sentence splitting)
        # We need the full text for high-quality sentence-based TTS
        full_response = ""
        for token in self.conv.stream_chat(user_text):
            full_response += token
            yield {"type": "token", "data": token}

        # 3. Generate Audio chunks (Sentence by Sentence)
        # synthesize_streaming yields one WAV per sentence
        for audio_chunk in self.tts.synthesize_streaming(full_response):
            yield {"type": "audio", "data": audio_chunk}

        # 4. Final state
        yield {
            "type": "done",
            "cart": self.conv.cart.get_summary(),
            "session_active": self.conv.is_active
        }

    def reset(self):
        self.conv.reset_session()

    def get_state(self) -> dict:
        return self.conv.get_session_state()