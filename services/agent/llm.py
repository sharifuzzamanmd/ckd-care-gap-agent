"""One small helper to talk to the local Qwen model (or any OpenAI-style server)."""
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # reads LLM_BASE_URL and LLM_MODEL from .env

client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key="not-needed-locally")
MODEL = os.environ["LLM_MODEL"]


def ask(system: str, user: str, max_tokens: int = 400) -> str:
    """Send one question to Qwen and return its answer as plain text."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user + " /no_think"}],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content or ""
    # Qwen3 may add an empty <think></think> block; remove it
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()