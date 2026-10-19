"""Labels a reply using a local Ollama model or the Groq free tier."""
import json
import re
import time

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


# --- Opt-outs (G-01) ---
# An opt-out stops all outreach for good, so it is decided by these rules alone, never by
# the AI, and only when the reply plainly asks us to stop. A reply that only talks about
# unsubscribing (a question, a negation, how their own members opt out) is held for a
# person to read: needs_review, with an alert.

# Direct requests to stop emailing us, in English, Swahili and Sheng. Each one names who
# is asking (me/us, ni-/tu-) or our emails, so "members can unsubscribe" is not one.
OPT_OUT_REQUESTS = [re.compile(p, re.I) for p in (
    r"\bunsubscribe (me|us)\b",
    r"\b(remove|delete) (me|us|my (email|address)|our (email|address)|this (email|address))"
    r"( \w+)? from (your|the|this) (\w+ )?(list|lists|database|contacts)\b",
    r"\btake (me|us) off\b",
    r"\bstop (emailing|contacting|messaging|mailing|writing to) (me|us)\b",
    r"\bstop (sending|send) (me|us) (any )?(more )?(emails?|mails?|messages?)\b",
    r"\b(i|we)( want| wish| need|'d like| would like) to (unsubscribe|opt out|be removed|stop receiving)\b",
    r"\b(please|kindly|pls|plz) (remove|unsubscribe|delete) (me|us)\b",
    r"\bopt (me|us) out\b",
    r"\b(do not|don't|dont|never) (email|contact|e-mail|mail|message|write to) (me|us)\b",
    r"\bno more (emails?|mails?|messages?)\b",
    # Swahili / Sheng
    r"\b(acha|wacha|acheni|wacheni|stop) ku(ni|tu)(tumia|tumie|text)\w*",
    r"\b(usi|msi)(ni|tu)(tumie|tumia|text|andikie)\w*",
    r"\b(ni|tu)ondoe\w*",
    r"\bondoa (jina langu|email yangu|barua pepe yangu|anwani yangu)\b",
    r"\b(sitaki|hatutaki|hatuhitaji|sihitaji) (tena )?(barua|email|emails|ujumbe|jumbe)\w*",
)]
# Words that mean the reply is about opting out without plainly asking for it
OPT_OUT_WORDS = re.compile(
    r"\b(unsubscrib\w*|opt[- ]?out\w*|remove|removed|removing|mailing list|stop (emailing|sending|contacting)"
    r"|ondoa|ondoe\w*|kujiondoa|ku(ni|tu)ondoa)\b", re.I)
NEGATION = re.compile(r"\b(not|don't|dont|do not|never|no need to|usi\w*|msi\w*|si)\b", re.I)
QUESTION_START = re.compile(r"^\s*(how|what|why|when|where|which|who|can|could|do(?!\s+not\b)|does|did|is|are|will|would|"
                            r"should|may|je|vipi|namna gani|nawezaje|tunawezaje|inawezekana)\b", re.I)
# A sentence that is nothing but the command: "Unsubscribe.", "Please remove us", "STOP"
BARE_COMMAND = re.compile(r"^(please |kindly |tafadhali )?(unsubscribe|remove|stop|opt out|ondoa|niondoe|"
                          r"tuondoe|jiondoe)( me| us)?(,? please|,? tafadhali)?\s*[.!]*$", re.I)
# "Can you remove me from your list?" is a request, not a question: the polite opening is
# taken off and what follows must itself be a request
POLITE_ASK = re.compile(r"^(please )?(can|could|would|will) you (please |kindly )?", re.I)
# The subject our unsubscribe link and mail apps' unsubscribe buttons send
UNSUBSCRIBE_SUBJECT = re.compile(r"^\s*(unsubscribe|remove|jiondoe|niondoe)\s*$", re.I)


def own_text(text):
    """The reply without quoted lines ("> ...") and with "not interested" taken out, so
    it doesn't read as a negation in "not interested, remove us"."""
    lines = [l for l in text.splitlines() if not l.lstrip().startswith(">")]
    return re.sub(r"\bnot interested\b", "uninterested", "\n".join(lines), flags=re.I)


def sentences(text):
    """Sentences with their end mark kept, so a question still ends with "?"."""
    return [s.strip() for s in re.findall(r"[^.!?\n]+[.!?]*", text) if s.strip()]


def _direct_request(sentence):
    """Whether one sentence plainly asks us to stop: a request phrase that is not
    negated just before it ("please don't remove us") and not asked as a question."""
    if BARE_COMMAND.match(sentence):
        return True
    polite = POLITE_ASK.match(sentence)
    if polite:
        sentence = sentence[polite.end():].rstrip("?").strip()
        return any(p.match(sentence) for p in OPT_OUT_REQUESTS) or bool(BARE_COMMAND.match(sentence))
    if sentence.endswith("?") or QUESTION_START.search(sentence):
        return False
    for pattern in OPT_OUT_REQUESTS:
        for m in pattern.finditer(sentence):
            before = sentence[:m.start()].split()[-4:]
            # the request's own "do not email us" / "usinitumie" carries its negation inside the match
            if not NEGATION.search(" ".join(before)):
                return True
    return False


def opt_out(text):
    """"unsubscribe" for a plain request to stop emailing us, "needs_review" for a reply
    that mentions opting out without plainly asking, otherwise None. `text` is the reply
    as classify gets it: "Subject: ...\n\n<body>"."""
    subject, _, body = text.partition("\n\n") if text.startswith("Subject:") else ("", "", text)
    subject = subject.removeprefix("Subject:").strip()
    body = own_text(body)
    said = sentences(body)
    if any(_direct_request(s) for s in said):
        return "unsubscribe"
    mentions = [s for s in said if OPT_OUT_WORDS.search(s) or any(p.search(s) for p in OPT_OUT_REQUESTS)]
    if UNSUBSCRIBE_SUBJECT.match(subject):
        # Our unsubscribe link and mail apps' unsubscribe buttons: subject "unsubscribe",
        # with an empty body or a body that doesn't talk about opting out in another way
        return "needs_review" if mentions else "unsubscribe"
    return "needs_review" if mentions else None


BOUNCE_WORDS = re.compile(r"(delivery status notification|undeliverable|mailbox unavailable|"
                          r"address not found|delivery has failed)", re.I)


def quick_rules(text):
    """Cheap checks before calling the AI. "unsubscribe" only for a plain request to stop,
    "needs_review" for a reply that mentions opting out without plainly asking, "bounce"
    for a delivery failure, otherwise None."""
    rule = opt_out(text)
    if rule:
        return rule
    if BOUNCE_WORDS.search(text):
        return "bounce"
    # Out-of-office is not decided from the words: "our IT head is on leave, but we'd like a
    # demo" is interested. inbox.is_auto_reply catches real auto-replies by their headers.
    return None


# --- Asking the AI (G-02) ---
# Network trouble, rate limits and server errors are tried again a few times; anything
# else (a bad key, a bad answer) is not. If it still fails the reply is held for you.
AI_TRIES = 3
AI_RETRY_SECONDS = 5  # waited after the first failure, then doubled
TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
MIN_CONFIDENCE = 0.6


def transient(error):
    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
        return True
    response = getattr(error, "response", None)
    return response is not None and response.status_code in TRANSIENT_STATUS


def ask_with_retry(prompt):
    """ask(), tried up to AI_TRIES times while the failure is transient. Raises the last
    error. There is no second provider: if the configured one fails, nothing else is asked."""
    for attempt in range(1, AI_TRIES + 1):
        try:
            return ask(prompt)
        except Exception as e:
            if attempt == AI_TRIES or not transient(e):
                raise
            time.sleep(AI_RETRY_SECONDS * 2 ** (attempt - 1))


def review(summary):
    """A reply held for a person: needs_review, alerted, and changes nothing else."""
    return {"label": "needs_review", "summary": summary, "confidence": 0, "hold": True}


def classify(text):
    """The reply's label, summary and confidence. Opt-outs and bounces are decided by the
    rules above before the AI is asked, so the AI never overrides a plain opt-out; and the
    AI alone never opts anyone out: its "unsubscribe" is held for you. A failure, an
    unknown label or low confidence is held for you too ("hold": alert, act on nothing)."""
    text = text.strip()[:3000]
    rule = quick_rules(text)
    if rule == "needs_review":
        return review("Mentions unsubscribing or being removed, but is not a plain request to "
                      "stop; not acted on. Please read it.")
    if rule:
        return {"label": rule, "summary": rule.replace("_", " "), "confidence": 1.0}
    try:
        raw = ask_with_retry(PROMPT.format(text=text))
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        label = data.get("label", "needs_review")
        conf = float(data.get("confidence", 0))
        summary = str(data.get("summary", ""))
    except Exception as e:
        return review(f"The AI could not read this reply ({type(e).__name__}: {str(e)[:200]}). "
                      "Please read it.")
    if label == "unsubscribe":
        return review(f"The AI thinks this may be an opt-out, but it is not a plain request to stop; "
                      f"not acted on. Please read it. AI summary: {summary}")
    if label not in LABELS or label == "needs_review" or conf < MIN_CONFIDENCE:
        return review(f"The AI was unsure (label {label}, confidence {conf:.2f}). Please read it. "
                      f"AI summary: {summary}")
    return {"label": label, "summary": summary, "confidence": conf}


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
