import os
import httpx
import json
from typing import Any, Dict

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
HF_MODEL = os.getenv("HF_MODEL") or "google/flan-t5-small"
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
HEADERS = {"Authorization": f"Bearer {HF_API_TOKEN}"} if HF_API_TOKEN else {}


async def call_hf_inference(prompt: str, max_length: int = 512, timeout: int = 60) -> Dict[str, Any]:
    """
    Call Hugging Face Inference API asynchronously and return parsed JSON or raw text.

    Returns a dict with keys:
      - text: raw generated text
      - parsed: python object if JSON parsed from text else None
      - raw_response: full response JSON from HF if available
    """
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": max_length, "return_full_text": False},
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(HF_URL, headers=HEADERS, json=payload)
        r.raise_for_status()
        try:
            data = r.json()
        except Exception:
            text = r.text
            parsed = _extract_json(text)
            return {"text": text, "parsed": parsed, "raw_response": None}

    # HF often returns a list or {"generated_text": "..."}
    text = ""
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        text = data[0].get("generated_text") or data[0].get("text") or ""
    elif isinstance(data, dict) and "generated_text" in data:
        text = data.get("generated_text")
    else:
        # fallback to stringifying
        text = json.dumps(data)

    parsed = _extract_json(text)
    return {"text": text, "parsed": parsed, "raw_response": data}


def _extract_json(text: str):
    """Try to find a JSON object/array inside text and parse it."""
    if not text:
        return None
    text = text.strip()
    # find first { or [ and last } or ]
    start = None
    for i, ch in enumerate(text):
        if ch in "[{":
            start = i
            break
    if start is None:
        return None
    # try to find matching closing bracket from the end
    end = None
    for j in range(len(text) - 1, -1, -1):
        if text[j] in "}]":
            end = j + 1
            break
    if end is None:
        return None
    candidate = text[start:end]
    try:
        return json.loads(candidate)
    except Exception:
        return None
