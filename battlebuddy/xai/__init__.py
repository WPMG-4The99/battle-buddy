"""Optional xAI reason loop. Env key only. Absent key is Yard 1."""

from battlebuddy.xai.loop import (
    answer_ask,
    api_key,
    chat_out,
    handle_line,
    reason_utterance,
    xai_model,
)

__all__ = [
    "answer_ask",
    "api_key",
    "chat_out",
    "handle_line",
    "reason_utterance",
    "xai_model",
]
