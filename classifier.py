"""Labels a reply using a local Ollama model or the Groq free tier."""
import json
import re
import requests

import config

LABELS = ["interested", "question", "not_interested", "out_of_office",
          "unsubscribe", "bounce", "needs_review"]

PROMPT = """You sort replies to a cold email from a Kenyan bulk SMS company.
Our email introduced our bulk SMS service and asked for a short meeting.

Pick ONE label:
- interested: wants a meeting, a call, pricing, a demo, or says yes in any way
- question: asks something but hasn't said yes or no
- not_interested: declines, already has a provider, not now
- out_of_office: automatic away/holiday reply
- unsubscribe: asks to stop emailing or remove them
- bounce: delivery failure / mailbox doesn't exist
- needs_review: anything unclear

The reply may be in English, Swahili or Sheng.

Return ONLY JSON like:
{{"label": "interested", "summary": "one short sentence on what they said", "confidence": 0.0-1.0}}

Reply:
\"\"\"{text}\"\"\""""


def _ask_ollama(prompt):
    r = requests.post(f"{config.OLLAMA_URL}/api/generate", json={
        "model": config.OLLAMA_MODEL, "prompt": prompt,
        "stream": False, "format": "json", "options": {"temperature": 0},
    }, timeout=120)
    r.raise_for_status()
    return r.json()["response"]


def _ask_groq(prompt, model=None):
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json={"model": model or config.GROQ_MODEL, "temperature": 0,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "user", "content": prompt}]},
        timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def ask(prompt, groq_model=None):
    """Send a prompt to the AI provider set in config; returns its JSON text.
    groq_model replaces GROQ_MODEL for this call when the provider is groq."""
    if config.AI_PROVIDER == "groq":
        return _ask_groq(prompt, groq_model)
    return _ask_ollama(prompt)


def quick_rules(text):
    """Cheap checks before calling the AI. Catches the obvious ones reliably."""
    t = text.lower()
    if re.search(r"\b(unsubscribe|remove (me|us)|take (me|us) off|stop emailing|do not contact)\b", t):
        return "unsubscribe"
    if re.search(r"(delivery status notification|undeliverable|mailbox unavailable|"
                 r"address not found|delivery has failed)", t):
        return "bounce"
    # Out-of-office is not decided from the words: "our IT head is on leave, but we'd like a
    # demo" is interested. inbox.is_auto_reply catches real auto-replies by their headers.
    return None


def classify(text):
    text = text.strip()[:3000]
    rule = quick_rules(text)
    if rule:
        return {"label": rule, "summary": rule.replace("_", " "), "confidence": 1.0}
    try:
        raw = ask(PROMPT.format(text=text))
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        label = data.get("label", "needs_review")
        conf = float(data.get("confidence", 0))
        if label not in LABELS or conf < 0.6:
            label = "needs_review"
        return {"label": label, "summary": data.get("summary", ""), "confidence": conf}
    except Exception as e:
        return {"label": "needs_review", "summary": f"AI failed: {e}", "confidence": 0}


if __name__ == "__main__":
    # Quick test: python classifier.py
    samples = [
        "Hi Florence, sounds good. Can you come by on Thursday at 10am?",
        "We already use another provider, thanks.",
        "What's your price per SMS for 50,000 messages?",
        "Niko interested, tupigie simu kesho.",
        "Please remove me from your list.",
    ]
    for s in samples:
        print(classify(s), "<-", s)
