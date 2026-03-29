import requests
import json
from system_prompt import SYSTEM_PROMPT
from cart_manager import CartManager
from memory_manager import MemoryManager
from intent_parser import parse_intent   

import os
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/chat"
MODEL = "qwen2.5:1.5b"


class ConversationManager:
    """
    Orchestrates a full FreshMart conversation session.

    Responsibilities:
    - Initializes CartManager and MemoryManager per session
    - Builds structured prompts via MemoryManager
    - Sends requests to Ollama (streaming or non-streaming)
    - Enforces turn-taking logic and session lifecycle
    - Detects session end (order confirmed or goodbye)
    """

    END_SIGNALS = [
        "goodbye", "bye", "thank you, goodbye", "that's all",
        "order confirmed", "see you", "thanks, bye"
    ]

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.cart = CartManager()
        self.memory = MemoryManager(self.cart)
        self.is_active = True
        self.turn_count = 0

    def chat(self, user_message: str) -> str:
        """
        Process a user message and return the assistant's full response.
        Non-streaming version — returns complete response string.
        """
        if not self.is_active:
            return "This session has ended. Please start a new conversation."

        parse_intent(user_message, self.cart)
        # Add user message to memory
        self.memory.add_message("user", user_message)

        # Build prompt
        messages = self.memory.build_messages(SYSTEM_PROMPT)

        # Call Ollama
        response_text = self._call_ollama(messages)

        # Add assistant response to memory
        self.memory.add_message("assistant", response_text)
        self.turn_count += 1

        # Check if session should end
        if self._should_end_session(user_message, response_text):
            self.is_active = False

        return response_text

    def stream_chat(self, user_message: str):
        """
        Process a user message and yield response tokens one by one.
        Generator — use in async WebSocket context.
        """
        if not self.is_active:
            yield "This session has ended. Please start a new conversation."
            return
        parse_intent(user_message, self.cart)
        self.memory.add_message("user", user_message)
        messages = self.memory.build_messages(SYSTEM_PROMPT)

        full_response = ""

        payload = {
            "model": MODEL,
            "messages": messages,
            "stream": True,
            "options": {
                "num_predict": 300,
                "temperature": 0.7
            }
        }

        try:
            with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_response += token
                            yield token
                        if chunk.get("done"):
                            break
        except requests.exceptions.RequestException as e:
            error_msg = f"Sorry, I'm having trouble connecting right now. Please try again. ({e})"
            yield error_msg
            full_response = error_msg

        self.memory.add_message("assistant", full_response)
        self.turn_count += 1

        if self._should_end_session(user_message, full_response):
            self.is_active = False

    def _call_ollama(self, messages: list) -> str:
        """Non-streaming Ollama call. Returns full response string."""
        payload = {
            "model": MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": 300,
                "temperature": 0.7
            }
        }
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "").strip()
        except requests.exceptions.RequestException as e:
            return f"Sorry, I'm having trouble connecting right now. Please try again. ({e})"

    def _should_end_session(self, user_msg: str, assistant_msg: str) -> bool:
        """Detect if the conversation should be ended."""
        user_lower = user_msg.lower()
        return any(signal in user_lower for signal in self.END_SIGNALS)

    def reset_session(self):
        """Manually reset the session (new session button)."""
        self.cart.clear()
        self.memory.reset()
        self.is_active = True
        self.turn_count = 0

    def get_session_state(self) -> dict:
        """Return current session metadata for debugging/logging."""
        return {
            "session_id": self.session_id,
            "is_active": self.is_active,
            "turn_count": self.turn_count,
            "active_history_length": self.memory.get_turn_count(),
            "has_summary": bool(self.memory.summary_block),
            "cart": self.cart.get_summary()
        }
