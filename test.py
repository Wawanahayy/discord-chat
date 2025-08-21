#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import random
import time
import os
import json
import re
from datetime import datetime
from multiprocessing import Process
from colorama import Fore, init

# =========================================================
# Global flags
# =========================================================
HEADLESS = (os.getenv("HEADLESS", "n").lower() == "y")

POST_SEND_COOLDOWN = int(os.getenv("POST_SEND_COOLDOWN", "30"))  # detik  # NEW: default 30s
MIN_WORDS = 5
MAX_WORDS = 10

ALLOW_TIME_GREETINGS = False
NAME_MENTION_PROB = 0.0

# Thread control
MAX_THREAD_REPLIES = 3
FOLLOWUP_CONTINUE_PROB = 0.60

# Delays
MIN_REPLY_DELAY = 3
MAX_REPLY_DELAY = 10

STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")
MAX_PROCESSED_MEMORY = 5000
MAX_OWN_IDS_MEMORY = 5000

# === Discord API v9 ===
BASE_URL = "https://discord.com/api/v9"

# Emoji config (will be overwritten by menu/env)
EMOJI_ALLOWED = True
EMOJI_PERCENT = 25  # 0..100
# ========================================================================

# Emoji pool (max 1 per reply; NO greeting/chart emojis)
EMOJI_POOL = [
    "🙂","😉","😄","😁","😊","😌","😎","👍","🆗","✅","🔥","🎯","🚀","🙌","👏",
    "😅","😂","😆","🤣","😜","🤗","🥳","🤩","😇",
    "😐","🤔","😮","😲","😯","😴","🥱","😪","😬","😳",
    "🍀","☕","🍵","💪","🧠","🫶","🫡","🙏","📝"
]
DISALLOWED_EMOJIS = {"👋","🤝","📈","📉","📊"}

KEYWORD_EMOJI_MAP = {
    r"\bshrimp|prawn|udang\b": "🦐",
    r"\bcow|sapi|moo+\b": "🐮",
    r"\bcat|kucing\b": "🐱",
    r"\bdog|anjing\b": "🐶",
    r"\bfish|ikan\b": "🐟",
    r"\brocket|to the moon\b": "🚀",
    r"\bfire|panas|hot\b": "🔥",
    r"\bheart|love|cinta\b": "❤️",
    r"\bstar|bintang\b": "⭐",
    r"\bmoney|duit|uang|cash\b": "💸",
    r"\bcoffee|kopi\b": "☕",
    r"\btea|teh\b": "🍵",
    r"\bidea|ide\b": "💡",
    r"\bbrain|otak\b": "🧠",
    r"\bmuscle|gym|angkat besi\b": "💪",
    r"\bthumbs? up\b": "👍",
    r"\bparty|pesta|selametan\b": "🎉",
    r"\blaugh|lol|wkwk+\b": "😂",
    r"\bsad|sedih\b": "😢",
}

# In-memory state
THREAD_REPLY_COUNTS = {}   # { bot_message_id: count }
_processed_ids_list = []   # ordered list for eviction
processed_messages = set()
_own_ids_list = []
OWN_IDS = set()

# Init colorama
init(autoreset=True)

# ----------------------- UI / Logs -----------------------
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    """
    Jalankan banner dari display.sh.
    Tidak ada fallback teks. Jika gagal, diam saja.
    """
    DISPLAY_URL = "https://raw.githubusercontent.com/Wawanahayy/JawaPride-all.sh/refs/heads/main/display.sh"
    try:
        exit_code = os.system(f'curl -fsSL {DISPLAY_URL} | bash')
        if exit_code == 0:
            return
    except Exception:
        pass

    try:
        import requests
        r = requests.get(DISPLAY_URL, timeout=15)
        r.raise_for_status()
        with open("display.sh", "w", encoding="utf-8") as f:
            f.write(r.text)
        os.chmod("display.sh", 0o755)
        os.system("bash display.sh")
    except Exception:
        return

def log_message(message, status="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = {"INFO": Fore.WHITE, "SUCCESS": Fore.GREEN, "ERROR": Fore.RED, "WARNING": Fore.YELLOW}.get(status, Fore.WHITE)
    print(f"{Fore.BLUE}[{timestamp}] {color}[{status}] {message}")

# ----------------------- Persistence -----------------------
def load_state():
    global THREAD_REPLY_COUNTS, _processed_ids_list, processed_messages, _own_ids_list, OWN_IDS
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        THREAD_REPLY_COUNTS = {str(k): int(v) for k, v in data.get("thread_counts", {}).items()}
        _processed_ids_list = [str(x) for x in data.get("processed", [])][-MAX_PROCESSED_MEMORY:]
        processed_messages = set(_processed_ids_list)
        _own_ids_list = [str(x) for x in data.get("own_ids", [])][-MAX_OWN_IDS_MEMORY:]
        OWN_IDS = set(_own_ids_list)
        log_message(
            f"Loaded state: {len(THREAD_REPLY_COUNTS)} threads, "
            f"{len(_processed_ids_list)} processed, {len(_own_ids_list)} own IDs", "SUCCESS"
        )
    except FileNotFoundError:
        THREAD_REPLY_COUNTS = {}
        _processed_ids_list, processed_messages = [], set()
        _own_ids_list, OWN_IDS = [], set()
    except Exception as e:
        THREAD_REPLY_COUNTS = {}
        _processed_ids_list, processed_messages = [], set()
        _own_ids_list, OWN_IDS = [], set()
        log_message(f"Failed to load state: {e}", "WARNING")

def save_state():
    try:
        data = {
            "thread_counts": THREAD_REPLY_COUNTS,
            "processed": _processed_ids_list[-MAX_PROCESSED_MEMORY:],
            "own_ids": _own_ids_list[-MAX_OWN_IDS_MEMORY:]
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        log_message(f"Failed to save state: {e}", "WARNING")

def add_processed(msg_id: str):
    if not msg_id or msg_id in processed_messages:
        return
    _processed_ids_list.append(str(msg_id))
    processed_messages.add(str(msg_id))
    while len(_processed_ids_list) > MAX_PROCESSED_MEMORY:
        old = _processed_ids_list.pop(0)
        processed_messages.discard(old)
    save_state()

def record_own_message_id(msg_id: str):
    if not msg_id or msg_id in OWN_IDS:
        return
    _own_ids_list.append(str(msg_id))
    OWN_IDS.add(str(msg_id))
    while len(_own_ids_list) > MAX_OWN_IDS_MEMORY:
        old = _own_ids_list.pop(0)
        OWN_IDS.discard(old)
    save_state()

# ----------------------- Helpers -----------------------
BANNED_GREETINGS = [
    "good morning", "good afternoon", "good evening",
    "selamat pagi", "selamat siang", "selamat malam"
]
TIME_GREETINGS_RE = re.compile(r"\b(good morning|good afternoon|good evening)\b", re.I)
GREETING_RE = re.compile(r"\b(good\s+morning|good\s+afternoon|good\s+evening)\b", re.I)

EMOJI_RE = re.compile(
    "["  # Basic wide emoji ranges
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002600-\U000026FF"
    "]", flags=re.UNICODE
)

def contains_emoji(t: str) -> bool:
    return bool(EMOJI_RE.search(t or ""))

def strip_all_emojis(t: str) -> str:
    return EMOJI_RE.sub("", t or "").strip()

def has_risky_chars(t: str) -> bool:
    return any(c in (":", "@", "#", "<", ">", "|", "`") for c in (t or ""))

def strip_greetings(t: str) -> str:
    s = t.strip()
    low = s.lower()
    for g in BANNED_GREETINGS:
        if low.startswith(g):
            s = s[len(g):].lstrip(" ,.-!?")
            break
    return s

def user_greeted(s: str) -> bool:
    return bool(GREETING_RE.search(s or ""))

def scrub_banned(resp: str, user_msg: str) -> str:
    r = (resp or "")
    r = re.sub(r"\bgm\b", "", r, flags=re.I)
    r = re.sub(r"\bcode\b", "snippet", r, flags=re.I)
    r = re.sub(r"\bhey\s*bro\b", "hey", r, flags=re.I)
    r = re.sub(r"\bgood\b(?!\s+morning\b)", "", r, flags=re.I)
    r = re.sub(r"\bnice\b", "", r, flags=re.I)
    if not user_greeted(user_msg):
        r = re.sub(r"\bgood\s+morning\b", "", r, flags=re.I)
    r = re.sub(r"\s{2,}", " ", r).strip(" ,.-!?")
    return r

def sanitize_response(text: str, user_message: str) -> str:
    t = (text or "").replace('\n', ' ').strip().strip('"').strip("'")
    t = re.sub(r"\s+", " ", t)
    if not ALLOW_TIME_GREETINGS:
        if not user_greeted(user_message):
            t = GREETING_RE.sub("", t)
            t = strip_greetings(t)
        t = re.sub(r"\s{2,}", " ", t).strip(" ,.-!?")
    t = scrub_banned(t, user_message)
    if t.endswith('.'):
        t = t[:-1]
    return t.strip()

def clamp_words(text: str, min_w: int = MIN_WORDS, max_w: int = MAX_WORDS) -> str:
    words = [w for w in text.split() if w.strip()]
    if len(words) > max_w:
        words = words[:max_w]
    if len(words) < min_w:
        fillers = ["thoughts?", "okay?", "agree?", "wdym?"]
        while len(words) < min_w:
            words.append(random.choice(fillers))
    return " ".join(words)

def enforce_single_emoji(text: str) -> str:
    emojis = EMOJI_RE.findall(text or "")
    if len(emojis) <= 1:
        return text
    no_emoji = EMOJI_RE.sub("", text).strip()
    return (no_emoji + " " + emojis[0]).strip()

# mood/emoji helper
MOOD_PATTERNS = {
    "celebration": re.compile(r"\b(selamat|congrats?|mantap|hebat|keren|great|awesome|win|menang)\b", re.I),
    "gratitude":   re.compile(r"\b(terima kasih|makasih|thanks?|thx)\b", re.I),
    "success":     re.compile(r"\b(berhasil|sukses|fixed|solved|kelar|done)\b", re.I),
    "agreement":   re.compile(r"\b(setuju|agree|oke|ok|sip|siap|noted)\b", re.I),
    "humor":       re.compile(r"\b(wkwk+|haha(ha)*|lol|ngakak)\b", re.I),
    "sad":         re.compile(r"\b(sedih|kecewa|galau|capek|lelah|pusing)\b", re.I),
    "confused":    re.compile(r"\b(bingung|confus(ed)?|gimana|gmn)\b", re.I),
    "positive":    re.compile(r"\b(nice|good|bagus|happy|senang|gembira|bahagia)\b", re.I),
}
MOOD_EMOJI = {"celebration":"🎉","gratitude":"🙏","success":"✅","agreement":"👍","humor":"😆","sad":"😕","confused":"🤔","positive":"🙂"}
MOOD_PRIORITY = ["celebration","gratitude","success","agreement","humor","positive","sad","confused"]

def first_keyword_emoji(text: str):
    t = (text or "").lower()
    for pattern, emo in KEYWORD_EMOJI_MAP.items():
        if re.search(pattern, t):
            if emo not in DISALLOWED_EMOJIS:
                return emo
    return None

def maybe_add_emoji(reply: str, user_message: str) -> (str, bool):
    global EMOJI_ALLOWED, EMOJI_PERCENT
    base_reply = strip_all_emojis(reply)
    keyword_emo = first_keyword_emoji(user_message)
    mood = None
    combined = f"{user_message or ''} {base_reply or ''}"
    for key in MOOD_PRIORITY:
        if MOOD_PATTERNS[key].search(combined):
            mood = key
            break

    if not EMOJI_ALLOWED:
        if keyword_emo:
            new = (base_reply + " " + keyword_emo).strip()
            return enforce_single_emoji(new), True
        if mood in ("celebration","gratitude","success","agreement","humor","sad","confused"):
            if random.random() < 0.20 and MOOD_EMOJI.get(mood) not in DISALLOWED_EMOJIS:
                new = (base_reply + " " + MOOD_EMOJI[mood]).strip()
                return enforce_single_emoji(new), True
        return base_reply, False

    use_prob = max(0.0, min(1.0, EMOJI_PERCENT / 100.0))
    if mood in ("celebration","gratitude","success","agreement","humor","positive"):
        use_prob = max(use_prob, 0.25)
    elif mood in ("sad","confused"):
        use_prob = max(use_prob, 0.15)
    if keyword_emo:
        use_prob = max(use_prob, 0.60)

    if random.random() >= use_prob:
        return base_reply, False

    chosen = None
    if keyword_emo:
        chosen = keyword_emo
    elif mood and MOOD_EMOJI.get(mood) and MOOD_EMOJI[mood] not in DISALLOWED_EMOJIS:
        chosen = MOOD_EMOJI[mood]
    else:
        safe_pool = [e for e in EMOJI_POOL if e not in DISALLOWED_EMOJIS]
        if safe_pool:
            chosen = random.choice(safe_pool)

    if not chosen:
        return base_reply, False
    new = (base_reply + " " + chosen).strip()
    return enforce_single_emoji(new), True

def is_mention_of_bot(message: dict, bot_user_id: str) -> bool:
    content = message.get('content', '') or ''
    if f"<@{bot_user_id}>" in content or f"<@!{bot_user_id}>" in content:
        return True
    for m in message.get('mentions', []):
        if m.get('id') == bot_user_id:
            return True
    return False

def get_referenced_bot_message_id(message: dict, bot_user_id: str):
    ref = message.get('referenced_message')
    if isinstance(ref, dict):
        ref_id = ref.get('id')
        author = (ref.get('author') or {})
        if author.get('id') == bot_user_id:
            return ref_id
        if ref_id and ref_id in OWN_IDS:
            return ref_id
    mref = message.get('message_reference')
    if isinstance(mref, dict):
        ref_id = mref.get('message_id')
        if ref_id and ref_id in OWN_IDS:
            return ref_id
    return None

def is_reply_to_bot(message: dict, bot_user_id: str) -> bool:
    return get_referenced_bot_message_id(message, bot_user_id) is not None

def is_reply_to_other_not_bot(message: dict, bot_user_id: str) -> bool:
    if message.get('type', 0) != 19:
        return False
    if is_reply_to_bot(message, bot_user_id):
        return False
    if is_mention_of_bot(message, bot_user_id):
        return False
    return True

# ------------------ Code-message handling ------------------
CODE_SIGNATURES = [
    r"```", r"\bfunction\b", r"\bconst\b", r"\blet\b", r"\bvar\b", r"\bimport\b", r"\bexport\b",
    r"\bclass\b", r"\bdef\b", r"\breturn\b", r"\bpragma\s+solidity\b", r"\bcontract\b",
    r"#include", r"\bpublic\s+static\s+void\b", r"\bCREATE\s+TABLE\b", r"\bSELECT\b", r"\bINSERT\b",
    r"\basync\b", r"\bawait\b", r"\bnpm\b", r"\byarn\b", r"\bpip\b", r"\bcurl\b",
    r"\bgo\s+run\b", r"\bnode\b", r"\bpython\b", r"<[a-zA-Z]+[^>]*>", r"0x[0-9a-fA-F]{6,}"
]

def is_code_message(s: str) -> bool:
    if not s or len(s) < 2:
        return False
    for pat in CODE_SIGNATURES:
        if re.search(pat, s, re.IGNORECASE | re.MULTILINE):
            return True
    symbols = "{}();<>[]=*/\\|`$"
    sym_count = sum(1 for ch in s if ch in symbols)
    return (sym_count >= 8)

CODE_AUTO_REPLY = "need ask team, stay active here and post in X"

# ------------------ AI Generation Logic ------------------
def _finalize_ai_text(raw_text: str, display_name: str, user_message: str) -> (str, bool):
    ai = sanitize_response(raw_text, user_message)
    ai = clamp_words(ai, MIN_WORDS, MAX_WORDS)
    ai = enforce_single_emoji(ai)
    ai, added = maybe_add_emoji(ai, user_message)
    ai = enforce_single_emoji(ai)
    if ai.lower().strip() == "good morning":
        ai = "morning, u around?"
    return ai[:300], added

def generate_ai_response(user_message, display_name, retry_count=0):
    max_retries = 2
    emojis_enabled = (os.getenv("EMOJIS_ENABLED", "y").lower() == "y")
    emoji_keywords = "shrimp, cow, moo, 🦐, 🐄"

    system_prompt = (
        "You are a casual, friendly Discord chat assistant. "
        "You are a casual, friendly Discord chat assistant with a light moderator vibe. "
        "Reply naturally like a human, without excessive formality. "
        "If you are asked about your condition, what are you doing, then you ask back because you are also a caring person. and you are a Singaporean."
        "Avoid time-based greetings unless the user did. "
        "Always answer in English. Keep it short: 4–10 words. "
        "Do NOT include the user's name in the reply. "
        "unless user text clearly references specific emoji keywords (shrimp, cow, moo, etc.)."
        "Emojis: at most one. If emojis are globally disabled, use none unless the user explicitly "
        f"mentions one of: {emoji_keywords} or clearly expresses emotion "
        "(laughter: lol/haha/lmao/😂; sadness: cry/tears/sad/😭; heartfelt: love/heart/thank you/"
        "appreciate/congrats/❤️). "
        "For whitelist/allowlist questions, prefer: 'Watch announcements; WL details posted there.' "
        "For 'how to get WL', prefer: 'Follow announcements, when Wl open, keep active here and X.' "
        "For 'how to contribute', prefer: 'keep active here,upload Art/meme, feedback, make active post on X.' "
        "If the user asks about your wellbeing, reply: 'Doing well, thanks for asking! How about you?'"
    )
    user_prompt = (
        f'Message: "{user_message}"\n'
        "Reply in English, casually and briefly (4–15 words). "
        "Do not include the user's name. "
        "Use at most one emoji only if it genuinely adds tone. "
    )

    # --- OpenRouter ---
    try:
        openrouter_key = None
        try:
            if os.path.exists("openrouter_key.txt"):
                with open("openrouter_key.txt", "r", encoding="utf-8") as f:
                    openrouter_key = f.readline().strip()
            else:
                openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        except Exception:
            openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

        if openrouter_key:
            url = "https://openrouter.ai/api/v1/chat/completions"
            payload = {
                "model": "openrouter/auto",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 100,
                "frequency_penalty": 0.2
            }
            headers = {"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"}
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                ai = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if ai:
                    final, added_emoji = _finalize_ai_text(ai, display_name, user_message)
                    return final, added_emoji
            elif resp.status_code == 429 and retry_count < max_retries:
                time.sleep(5)
                return generate_ai_response(user_message, display_name, retry_count + 1)
    except Exception:
        pass

    # --- OpenAI ---
    try:
        openai_key = None
        try:
            if os.path.exists("openai_key.txt"):
                with open("openai_key.txt", "r", encoding='utf-8') as f:
                    openai_key = f.readline().strip()
            else:
                openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        except Exception:
            openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        if openai_key:
            models_to_try = ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4o"]
            model_name = models_to_try[retry_count % len(models_to_try)]
            url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 100,
                "frequency_penalty": 0.2
            }
            headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                ai = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if ai:
                    final, added_emoji = _finalize_ai_text(ai, display_name, user_message)
                    return final, added_emoji
            elif resp.status_code == 429 and retry_count < max_retries:
                time.sleep(5)
                return generate_ai_response(user_message, display_name, retry_count + 1)
    except Exception:
        pass

    # --- Gemini fallback ---
    try:
        if os.path.exists("gemini_key.txt"):
            with open("gemini_key.txt", "r", encoding='utf-8') as f:
                gemini_key = f.readline().strip()
        else:
            gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

        if gemini_key:
            prompt = (
                "You are chatting casually in a Discord server. Reply naturally and briefly.\n"
                "Tone: relaxed and friendly. Avoid time-based greetings unless the user did.\n"
                "Answer in English only. 4–10 words.\n"
                "Do not include the user's name in the reply.\n"
                "Emojis: at most one; if globally disabled, don't use any unless the user references specific emoji keywords.\n\n"
                f"Message: \"{user_message}\"\n\n"
                "Your reply:"
            )
            models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
            model_name = models_to_try[retry_count % len(models_to_try)]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "topK": 20, "topP": 0.8, "maxOutputTokens": 100},
            }
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    cand = result['candidates'][0]
                    parts = cand.get('content', {}).get('parts', [])
                    if parts:
                        ai_text = parts[0].get('text', '').strip()
                        final, added_emoji = _finalize_ai_text(ai_text, display_name, user_message)
                        return final, added_emoji
            elif response.status_code == 429 and retry_count < max_retries:
                time.sleep(5)
                return generate_ai_response(user_message, display_name, retry_count + 1)
    except Exception:
        pass

    log_message("All AI attempts failed", "ERROR")
    return None, False

# ------------------ Discord HTTP helpers ------------------
def get_recent_messages(channel_id, headers, limit=50):
    try:
        url = f"{BASE_URL}/channels/{channel_id}/messages?limit={limit}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            log_message("Discord token is invalid or expired", "ERROR")
            return []
        elif response.status_code == 403:
            log_message("Bot doesn't have permission to read messages in this channel", "ERROR")
            return []
        elif response.status_code == 429:
            log_message("Discord rate limit hit - waiting", "WARNING")
            time.sleep(5)
            return []
        else:
            log_message(f"Failed to get messages: {response.status_code}", "ERROR")
            return []
    except requests.exceptions.RequestException as e:
        log_message(f"Network error getting messages: {str(e)}", "ERROR")
        return []
    except Exception as e:
        log_message(f"Error getting messages: {str(e)}", "ERROR")
        return []

def send_message(channel_id, content, headers, reply_to_message_id=None, retry_count=0):
    max_retries = 3
    try:
        payload = {'content': content, 'allowed_mentions': {'parse': []}}
        if reply_to_message_id:
            payload['message_reference'] = {'message_id': reply_to_message_id}

        response = requests.post(
            f"{BASE_URL}/channels/{channel_id}/messages",
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code in (200, 201):
            try:
                data = response.json()
                if data.get('id'):
                    record_own_message_id(data['id'])
                return data
            except Exception:
                return True
        elif response.status_code == 401:
            log_message("Discord token is invalid or expired", "ERROR")
            return False
        elif response.status_code == 403:
            log_message("Bot doesn't have permission to send messages in this channel", "ERROR")
            return False
        elif response.status_code == 429:
            if retry_count < max_retries:
                retry_after = response.headers.get('retry-after', '5')
                try:
                    wait_time = float(retry_after)
                except Exception:
                    wait_time = 5
                log_message(f"Rate limited - waiting {wait_time}s (attempt {retry_count + 1})", "WARNING")
                time.sleep(wait_time + 1)
                return send_message(channel_id, content, headers, reply_to_message_id, retry_count + 1)
            else:
                log_message("Max retries reached for rate limit", "ERROR")
                return False
        else:
            log_message(f"Failed to send message: {response.status_code} - {response.text[:100]}", "ERROR")
            return False
    except requests.exceptions.RequestException as e:
        log_message(f"Network error sending message: {str(e)}", "ERROR")
        return False
    except Exception as e:
        log_message(f"Error sending message: {str(e)}", "ERROR")
        return False

def natural_send(channel_id, headers, content, reply_to_id):
    delay = random.uniform(MIN_REPLY_DELAY, MAX_REPLY_DELAY)
    log_message(f"Replying in {delay:.1f} seconds...", "INFO")
    time.sleep(delay)
    res = send_message(channel_id, content, headers, reply_to_id)

    # NEW: cooldown global setelah kirim
    if res and POST_SEND_COOLDOWN > 0:
        log_message(f"Post-send cooldown {POST_SEND_COOLDOWN}s", "INFO")
        time.sleep(POST_SEND_COOLDOWN)

    return res

# ------------------ Scanning & Priorities ------------------
def partition_messages(messages, bot_user_id):
    high_priority, thread_other, normal = [], [], []
    for msg in messages:
        msg_id = msg.get('id')
        if not msg_id or msg_id in processed_messages:
            continue
        msg_type = msg.get('type', 0)
        if msg_type not in (0, 19):  # normal or reply
            add_processed(msg_id)
            continue
        author = msg.get('author', {}) or {}
        if author.get('id') == bot_user_id:
            add_processed(msg_id)
            continue
        content = msg.get('content') or ''
        if not content:
            add_processed(msg_id)
            continue
        if is_reply_to_bot(msg, bot_user_id) or is_mention_of_bot(msg, bot_user_id):
            high_priority.append(msg)
        elif is_reply_to_other_not_bot(msg, bot_user_id):
            thread_other.append(msg)
        else:
            normal.append(msg)
    return high_priority, thread_other, normal

# --------------------------- Worker (single token+channel) ---------------------------
def worker_main():
    # UI
    worker_silent = (os.getenv("WORKER_SILENT", "0") == "1")
    non_interactive = (os.getenv("NON_INTERACTIVE", "0") == "1")

    if not worker_silent and not HEADLESS:
        clear_screen()
        print_banner()

    # Channel & scan params
    try:
        channel_id = os.getenv("CHANNEL_ID")
        if not channel_id and not non_interactive and not HEADLESS:
            channel_id = input(Fore.CYAN + "Enter Channel ID: ").strip()
        if not channel_id or not channel_id.isdigit():
            log_message("Invalid Channel ID format", "ERROR")
            return

        process_count = int(os.getenv("PROCESS_COUNT") or ("50" if non_interactive or HEADLESS else input(Fore.CYAN + "How many recent messages to scan each check (1–100): ").strip()))
        if process_count < 1 or process_count > 100:
            log_message("Process count must be between 1 and 100", "ERROR")
            return

        reply_chance = float(os.getenv("REPLY_CHANCE") or ("0.25" if non_interactive or HEADLESS else input(Fore.CYAN + "Reply chance for normal messages (0–1): ").strip()))
        if not 0 <= reply_chance <= 1:
            log_message("Reply chance must be between 0 and 1", "ERROR")
            return

        thread_reply_chance_in = os.getenv("THREAD_REPLY_CHANCE") or ("" if non_interactive or HEADLESS else input(Fore.CYAN + "Reply chance for replies in threads to others (0–1) [0.35]: ").strip())
        thread_reply_chance = float(thread_reply_chance_in or "0.35")
        if not 0 <= thread_reply_chance <= 1:
            log_message("Thread reply chance must be between 0 and 1", "ERROR")
            return

        allow_time_greet = (os.getenv("ALLOW_TIME_GREET", "") or ("n" if (non_interactive or HEADLESS) else input(Fore.CYAN + "Allow time-based greetings? (y/n) [n]: ").strip())).lower()
        global ALLOW_TIME_GREETINGS
        ALLOW_TIME_GREETINGS = (allow_time_greet == 'y')

        global NAME_MENTION_PROB
        NAME_MENTION_PROB = float(os.getenv("NAME_MENTION_PROB") or ("0.25" if not (non_interactive or HEADLESS) else "0.0"))
        NAME_MENTION_PROB = max(0.0, min(1.0, NAME_MENTION_PROB))

        global MAX_THREAD_REPLIES, FOLLOWUP_CONTINUE_PROB
        MAX_THREAD_REPLIES = int(os.getenv("MAX_THREAD_REPLIES") or ("3" if (non_interactive or HEADLESS) else input(Fore.CYAN + "Max replies per thread (1–5) [3]: ").strip() or "3"))
        MAX_THREAD_REPLIES = max(1, min(5, MAX_THREAD_REPLIES))
        FOLLOWUP_CONTINUE_PROB = float(os.getenv("FOLLOWUP_CONTINUE_PROB") or ("0.60" if (non_interactive or HEADLESS) else input(Fore.CYAN + "Chance to continue follow-up (0–1) [0.60]: ").strip() or "0.60"))
        FOLLOWUP_CONTINUE_PROB = max(0.0, min(1.0, FOLLOWUP_CONTINUE_PROB))

        global MIN_REPLY_DELAY, MAX_REPLY_DELAY
        MIN_REPLY_DELAY = int(os.getenv("MIN_REPLY_DELAY") or ("3" if (non_interactive or HEADLESS) else input(Fore.CYAN + "Min typing delay before send (sec) [3]: ").strip() or "3"))
        MAX_REPLY_DELAY = int(os.getenv("MAX_REPLY_DELAY") or ("10" if (non_interactive or HEADLESS) else input(Fore.CYAN + "Max typing delay before send (sec) [10]: ").strip() or "10"))
        if MAX_REPLY_DELAY < MIN_REPLY_DELAY: MAX_REPLY_DELAY = MIN_REPLY_DELAY

        min_delay = int(os.getenv("MIN_DELAY") or ("45" if (non_interactive or HEADLESS) else input(Fore.CYAN + "Minimum delay between checks (seconds): ").strip()))
        max_delay = int(os.getenv("MAX_DELAY") or ("90" if (non_interactive or HEADLESS) else input(Fore.CYAN + "Maximum delay between checks (seconds): ").strip()))
        if min_delay < 1 or max_delay < min_delay:
            log_message("Invalid delay values", "ERROR")
            return

        # Emoji config from env
        global EMOJI_ALLOWED, EMOJI_PERCENT
        EMOJI_ALLOWED = (os.getenv("EMOJI_ALLOWED", "y").lower() == 'y')
        try:
            EMOJI_PERCENT = int(os.getenv("EMOJI_PERCENT", "25"))
        except Exception:
            EMOJI_PERCENT = 25
        EMOJI_PERCENT = max(0, min(100, EMOJI_PERCENT))

        # NEW: post-send cooldown from env
        global POST_SEND_COOLDOWN
        try:
            POST_SEND_COOLDOWN = int(os.getenv("POST_SEND_COOLDOWN", "30"))
        except Exception:
            POST_SEND_COOLDOWN = 30
        POST_SEND_COOLDOWN = max(0, POST_SEND_COOLDOWN)

    except ValueError:
        log_message("Invalid input format", "ERROR")
        return

    # ---- Token + headers (v9) ----
    try:
        authorization = os.getenv("TOKEN_VALUE", "").strip()

        if not authorization:
            token_file = os.getenv("TOKEN_FILE_PATH", "token.txt")
            first_line = ""
            with open(token_file, "r", encoding="utf-8") as f:
                for ln in f:
                    s = ln.strip()
                    if s and not s.startswith("#"):
                        first_line = s
                        break
            if not first_line:
                log_message("Discord token is empty", "ERROR")
                return
            if "|" in first_line:
                first_line = first_line.split("|", 1)[0].strip()
            authorization = first_line

        if not authorization:
            log_message("Discord token is empty", "ERROR")
            return

        log_message("Discord token loaded successfully", "SUCCESS")
        if not authorization.startswith("Bot "):
            log_message("Warning: token doesn't start with 'Bot '. Using user tokens is against Discord ToS (self-bot).", "WARNING")

    except FileNotFoundError:
        log_message("Discord token file 'token.txt' not found", "ERROR")
        return
    except Exception as e:
        log_message(f"Error reading Discord token: {str(e)}", "ERROR")
        return

    headers = {'Authorization': authorization, 'Content-Type': 'application/json', 'User-Agent': 'Discord Bot'}

    # Countdown & banner (non-headless)
    if not worker_silent and not HEADLESS:
        print(Fore.YELLOW + "\nStarting in:")
        for i in range(3, 0, -1):
            print(Fore.YELLOW + str(i))
            time.sleep(1)
        clear_screen()
        print_banner()

    # ---- Bot info ----
    try:
        bot_info = requests.get(f"{BASE_URL}/users/@me", headers=headers, timeout=10)
        if bot_info.status_code == 200:
            bot_data = bot_info.json()
            bot_user_id = bot_data['id']
            bot_username = bot_data.get('username') or bot_data.get('global_name') or 'Unknown'
            log_message(f"Bot started successfully! Bot: {bot_username} (ID: {bot_user_id})", "SUCCESS")
        else:
            log_message(
                f"Failed to get bot info. Status: {bot_info.status_code}. Check your token. Body: {bot_info.text}",
                "ERROR"
            )
            return
    except Exception as e:
        log_message(f"Error getting bot info: {str(e)}", "ERROR")
        return

    load_state()

    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            messages = get_recent_messages(channel_id, headers, limit=process_count)
            if not messages:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    log_message(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.", "ERROR")
                    break
            else:
                consecutive_errors = 0

                scan_list = list(reversed(messages[-process_count:]))

                high_priority, thread_other, normal = partition_messages(scan_list, bot_user_id)

                # -------- HIGH PRIORITY --------
                for message in high_priority:
                    message_id = message.get('id')
                    if not message_id or message_id in processed_messages:
                        continue

                    author = message.get('author', {}) or {}
                    author_name = author.get('display_name') or author.get('global_name') or author.get('username', 'Unknown')
                    content = message.get('content', '') or ''

                    must_reply = False
                    maybe_reply = False
                    thread_key = None

                    ref_bot_msg_id = get_referenced_bot_message_id(message, bot_user_id)
                    if ref_bot_msg_id:
                        thread_key = ref_bot_msg_id
                        count = THREAD_REPLY_COUNTS.get(thread_key, 0)
                        if count >= MAX_THREAD_REPLIES:
                            add_processed(message_id); continue
                        if count == 0: must_reply = True
                        else: maybe_reply = True
                    else:
                        if is_mention_of_bot(message, bot_user_id):
                            pass
                        must_reply = True

                    do_reply = must_reply or (maybe_reply and (random.random() < FOLLOWUP_CONTINUE_PROB))
                    if not do_reply:
                        add_processed(message_id); continue

                    if is_code_message(content):
                        ai_response = CODE_AUTO_REPLY
                    else:
                        ai_response, _ = generate_ai_response(content, author_name)
                        if ai_response is None:
                            add_processed(message_id); continue

                    sent = natural_send(channel_id, headers, ai_response, message_id)
                    if sent:
                        if ref_bot_msg_id:
                            THREAD_REPLY_COUNTS[thread_key] = THREAD_REPLY_COUNTS.get(thread_key, 0) + 1
                            save_state()
                        else:
                            if isinstance(sent, dict) and sent.get('id'):
                                THREAD_REPLY_COUNTS[sent['id']] = 1
                                save_state()
                    add_processed(message_id)

                # -------- THREAD replies to others --------
                for message in thread_other:
                    message_id = message.get('id')
                    if not message_id or message_id in processed_messages:
                        continue

                    author = message.get('author', {}) or {}
                    author_name = author.get('display_name') or author.get('global_name') or author.get('username', 'Unknown')
                    content = message.get('content', '') or ''

                    if random.random() <= thread_reply_chance:
                        # preflight priority re-check
                        pre = get_recent_messages(channel_id, headers, limit=process_count)
                        if pre:
                            hp2, _, _ = partition_messages(list(reversed(pre[-process_count:])), bot_user_id)
                            if hp2:
                                add_processed(message_id)
                                for hpmsg in hp2:
                                    hp_id = hpmsg.get('id')
                                    if not hp_id or hp_id in processed_messages:
                                        continue
                                    author2 = hpmsg.get('author', {}) or {}
                                    author2_name = author2.get('display_name') or author2.get('global_name') or author2.get('username', 'Unknown')
                                    content2 = hpmsg.get('content', '') or ''
                                    ref_id2 = get_referenced_bot_message_id(hpmsg, bot_user_id)
                                    must = (THREAD_REPLY_COUNTS.get(ref_id2, 0) == 0) if ref_id2 else True
                                    cont = (random.random() < FOLLOWUP_CONTINUE_PROB) if ref_id2 else False
                                    do = must or cont
                                    if not do:
                                        add_processed(hp_id); continue
                                    if is_code_message(content2):
                                        ai2 = CODE_AUTO_REPLY
                                    else:
                                        ai2, _ = generate_ai_response(content2, author2_name)
                                        if ai2 is None:
                                            add_processed(hp_id); continue
                                    sent2 = natural_send(channel_id, headers, ai2, hp_id)
                                    if sent2 and ref_id2:
                                        THREAD_REPLY_COUNTS[ref_id2] = THREAD_REPLY_COUNTS.get(ref_id2, 0) + 1
                                        save_state()
                                    add_processed(hp_id)
                                continue

                        if is_code_message(content):
                            ai_response = CODE_AUTO_REPLY
                        else:
                            ai_response, _ = generate_ai_response(content, author_name)
                            if ai_response is None:
                                add_processed(message_id); continue

                        natural_send(channel_id, headers, ai_response, message_id)

                    add_processed(message_id)

                # -------- NORMAL messages --------
                for message in normal:
                    message_id = message.get('id')
                    if not message_id or message_id in processed_messages:
                        continue

                    author = message.get('author', {}) or {}
                    author_name = author.get('display_name') or author.get('global_name') or author.get('username', 'Unknown')
                    content = message.get('content', '') or ''

                    if random.random() <= reply_chance:
                        pre = get_recent_messages(channel_id, headers, limit=process_count)
                        if pre:
                            hp2, _, _ = partition_messages(list(reversed(pre[-process_count:])), bot_user_id)
                            if hp2:
                                add_processed(message_id)
                                for hpmsg in hp2:
                                    hp_id = hpmsg.get('id')
                                    if not hp_id or hp_id in processed_messages:
                                        continue
                                    author2 = hpmsg.get('author', {}) or {}
                                    author2_name = author2.get('display_name') or author2.get('global_name') or author2.get('username', 'Unknown')
                                    content2 = hpmsg.get('content', '') or ''
                                    ref_id2 = get_referenced_bot_message_id(hpmsg, bot_user_id)
                                    must = (THREAD_REPLY_COUNTS.get(ref_id2, 0) == 0) if ref_id2 else True
                                    cont = (random.random() < FOLLOWUP_CONTINUE_PROB) if ref_id2 else False
                                    do = must or cont
                                    if not do:
                                        add_processed(hp_id); continue
                                    if is_code_message(content2):
                                        ai2 = CODE_AUTO_REPLY
                                    else:
                                        ai2, _ = generate_ai_response(content2, author2_name)
                                    if ai2 is None:
                                        add_processed(hp_id); continue
                                    sent2 = natural_send(channel_id, headers, ai2, hp_id)
                                    if sent2 and ref_id2:
                                        THREAD_REPLY_COUNTS[ref_id2] = THREAD_REPLY_COUNTS.get(ref_id2, 0) + 1
                                        save_state()
                                    add_processed(hp_id)
                                continue

                        if is_code_message(content):
                            ai_response = CODE_AUTO_REPLY
                        else:
                            ai_response, _ = generate_ai_response(content, author_name)
                            if ai_response is None:
                                add_processed(message_id); continue

                        natural_send(channel_id, headers, ai_response, message_id)

                    add_processed(message_id)

            delay_loop = random.uniform(max(min_delay, 30), max(max_delay, 60))
            log_message(f"Waiting {delay_loop:.1f} seconds before next check...", "INFO")
            time.sleep(delay_loop)

        except KeyboardInterrupt:
            save_state()
            log_message("Program stopped by user", "WARNING")
            break
        except Exception as e:
            save_state()
            log_message(f"An unexpected error occurred: {str(e)}", "ERROR")
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                save_state()
                log_message(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.", "ERROR")
                break
            time.sleep(10)

# --------------------------- Orchestrator helpers ---------------------------
def run_worker(env_overrides: dict):
    os.environ.update(env_overrides)
    try:
        worker_main()
    except KeyboardInterrupt:
        pass

def mask_token_display(token: str) -> str:
    t = token.replace("Bot ", "")
    if len(t) <= 10:
        return t
    return t[:4] + "..." + t[-6:]

def get_input(prompt_text: str, default: str = None):
    if default is not None and default != "":
        val = input(Fore.CYAN + f"{prompt_text} [{default}]: ").strip()
        return val if val != "" else default
    else:
        return input(Fore.CYAN + f"{prompt_text}: ").strip()

def prompt_scan_settings_once() -> dict:
    process_count = int(get_input("How many recent messages to scan each check (1–100)", "15"))
    if process_count < 1 or process_count > 100:
        raise ValueError("Process count must be between 1 and 100")

    reply_chance = float(get_input("Reply chance for normal messages (0–1)", "1"))
    thread_reply_chance = float(get_input("Reply chance for replies in threads to others (0–1)", "0.08"))
    allow_time_greet = get_input("Allow time-based greetings? (y/n)", "n").lower()
    name_mention_prob = float(get_input("Chance to mention user's name (0–1)", "0"))
    max_thread_replies = int(get_input("Max replies per thread (1–5)", "5"))
    followup_prob = float(get_input("Chance to continue follow-up (0–1)", "1"))
    min_typing = int(get_input("Min typing delay before send (sec)", "10"))
    max_typing = int(get_input("Max typing delay before send (sec)", "15"))
    min_loop = int(get_input("Minimum delay between checks (seconds)", "5"))
    max_loop = int(get_input("Maximum delay between checks (seconds)", "15"))
    post_send_cooldown = int(get_input("Post-send cooldown after sending (sec)", "20"))  

    if not 0 <= reply_chance <= 1: raise ValueError("Reply chance must be 0..1")
    if not 0 <= thread_reply_chance <= 1: raise ValueError("Thread reply chance must be 0..1")
    if not 0 <= name_mention_prob <= 1: raise ValueError("Name mention prob must be 0..1")
    if not 1 <= max_thread_replies <= 5: raise ValueError("Max thread replies must be 1..5")
    if not 0 <= followup_prob <= 1: raise ValueError("Follow-up prob must be 0..1")
    if max_typing < min_typing: max_typing = min_typing
    if min_loop < 1 or max_loop < min_loop: raise ValueError("Loop delays invalid")

    return {
        "PROCESS_COUNT": str(process_count),
        "REPLY_CHANCE": str(reply_chance),
        "THREAD_REPLY_CHANCE": str(thread_reply_chance),
        "ALLOW_TIME_GREET": "y" if allow_time_greet == "y" else "n",
        "NAME_MENTION_PROB": str(name_mention_prob),
        "MAX_THREAD_REPLIES": str(max_thread_replies),
        "FOLLOWUP_CONTINUE_PROB": str(followup_prob),
        "MIN_REPLY_DELAY": str(min_typing),
        "MAX_REPLY_DELAY": str(max_typing),
        "MIN_DELAY": str(min_loop),
        "MAX_DELAY": str(max_loop),
        "POST_SEND_COOLDOWN": str(post_send_cooldown),  # NEW
    }

def ask_emoji_for_account(label: str, default_allowed='n', default_percent='20'):
    use_emoji = get_input(f"Use emoji for {label}? (y/n)", default_allowed).lower()
    if use_emoji == 'y':
        pct_raw = get_input("chance emoji per message", default_percent)
        try:
            pct = int(pct_raw)
        except Exception:
            pct = 25
        pct = max(0, min(100, pct))
        return 'y', str(pct)
    else:
        return 'n', '0'

def load_tokens_with_inline_channels(path: str):
    """
    token.txt format per line:
      - 'Bot <token> | ch1,ch2'  (separator channel: ',' atau ';')
      - '<token> | ch1,ch2'
      - 'Bot <token>'
      - '<token>'
    """
    items = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                token = s
                ch_list = []
                if '|' in s:
                    tok, chs = [p.strip() for p in s.split('|', 1)]
                    token = tok
                    ch_list = [c.strip() for c in re.split(r"[;,]", chs) if c.strip().isdigit()]
                items.append((token, ch_list))
    except FileNotFoundError:
        log_message(f"Token file not found: {path}", "ERROR")
    except Exception as e:
        log_message(f"Error reading token file {path}: {e}", "ERROR")
    return items

def build_base_env_from_env():
    return {
        "PROCESS_COUNT": os.getenv("PROCESS_COUNT","30"),
        "REPLY_CHANCE": os.getenv("REPLY_CHANCE","1"),
        "THREAD_REPLY_CHANCE": os.getenv("THREAD_REPLY_CHANCE","0.35"),
        "ALLOW_TIME_GREET": os.getenv("ALLOW_TIME_GREET","n"),
        "NAME_MENTION_PROB": os.getenv("NAME_MENTION_PROB","0"),
        "MAX_THREAD_REPLIES": os.getenv("MAX_THREAD_REPLIES","5"),
        "FOLLOWUP_CONTINUE_PROB": os.getenv("FOLLOWUP_CONTINUE_PROB","1"),
        "MIN_REPLY_DELAY": os.getenv("MIN_REPLY_DELAY","3"),
        "MAX_REPLY_DELAY": os.getenv("MAX_REPLY_DELAY","10"),
        "MIN_DELAY": os.getenv("MIN_DELAY","5"),
        "MAX_DELAY": os.getenv("MAX_DELAY","9"),
        "POST_SEND_COOLDOWN": os.getenv("POST_SEND_COOLDOWN","30"),  # NEW
    }

# --------------------------- Orchestrator (input dulu semua ➜ launch bareng) ---------------------------
if __name__ == "__main__":
    if not HEADLESS:
        clear_screen()
        print_banner()

    token_path = os.getenv("TOKEN_PATH", "token.txt")
    token_items = load_tokens_with_inline_channels(token_path)
    if not token_items:
        log_message("No tokens found. Fill token.txt with 'Bot <token> | ch1,ch2' or '<token> | ch1,ch2'", "ERROR")
        raise SystemExit(1)

    # HEADLESS: no prompts, use mapping from token.txt and env
    if HEADLESS:
        base_env = build_base_env_from_env()
        procs = []
        for ti, (token, mapped) in enumerate(token_items, start=1):
            chs = mapped
            if not chs:
                log_message(f"Skip ACCOUNT{ti} ({mask_token_display(token)}) — no channels.", "WARNING")
                continue
            for ch in chs:
                env = dict(base_env); env.update({
                    "TOKEN_VALUE": token,
                    "CHANNEL_ID": ch,
                    "STATE_FILE": f"state_t{ti}_{ch}.json",
                    "EMOJI_ALLOWED": os.getenv("EMOJI_ALLOWED","y"),
                    "EMOJI_PERCENT": os.getenv("EMOJI_PERCENT","25"),
                    "WORKER_SILENT": "1",
                    "NON_INTERACTIVE": "1",
                })
                log_message(f"READY ➜ ACCOUNT{ti} token={mask_token_display(token)} channel={ch}", "INFO")
                p = Process(target=run_worker, args=(env,), daemon=False)
                p.start(); procs.append(p); time.sleep(0.2)
        try:
            for p in procs:
                p.join()
        except KeyboardInterrupt:
            log_message("Stopping all workers...", "WARNING")
            for p in procs:
                p.terminate()
        raise SystemExit(0)

    # ======= MENU: Single / Multi =======
    print(Fore.CYAN + "Mode:")
    print("  1) Single Account (pilih 1 token, bebas tentukan channel)")
    print("  2) Multi Account  (pakai mapping dari token.txt, bisa edit per akun)")
    choice = (input(Fore.CYAN + "Choose [1/2]: ").strip() or "2")

    # ======= Tanya setting scan SEKALI untuk semua worker =======
    try:
        base_env = prompt_scan_settings_once()
    except Exception as e:
        log_message(f"Invalid input: {e}", "ERROR")
        raise SystemExit(1)

    launch_plan = []  # list of env dicts

    if choice == "1":
        # ---- SINGLE ACCOUNT ----
        print(Fore.YELLOW + "\nAvailable tokens:")
        for i, (tok, chs) in enumerate(token_items, start=1):
            mapped = ",".join(chs) if chs else "-"
            print(f"  {i}) {mask_token_display(tok)}  | mapped channels: {mapped}")
        idx = input(Fore.CYAN + "Pick token index: ").strip()
        try:
            idx = int(idx)
            if not (1 <= idx <= len(token_items)): raise ValueError()
        except Exception:
            log_message("Invalid index.", "ERROR")
            raise SystemExit(1)

        token, mapped = token_items[idx-1]
        default_map = ",".join(mapped) if mapped else ""
        channels_raw = get_input("Enter Channel ID ACCOUNT1", default_map)
        channels = [c.strip() for c in re.split(r"[,\s]+", channels_raw) if c.strip().isdigit()]
        if not channels:
            log_message("No channels provided.", "ERROR")
            raise SystemExit(1)

        # emoji per account
        allow_e, pct_e = ask_emoji_for_account("ACCOUNT1", default_allowed='y', default_percent='25')

        for ch in channels:
            env = dict(base_env); env.update({
                "TOKEN_VALUE": token,
                "CHANNEL_ID": ch,
                "STATE_FILE": f"state_single_{ch}.json",
                "EMOJI_ALLOWED": allow_e,
                "EMOJI_PERCENT": pct_e,
                "WORKER_SILENT": "0",
                "NON_INTERACTIVE": "1",
            })
            launch_plan.append(("ACCOUNT1", token, ch, env))

    else:
        # ---- MULTI ACCOUNT ----
        print(Fore.YELLOW + "\nConfig per akun. Default channel ngikut mapping di token.txt (kalau ada).")
        for i, (token, mapped) in enumerate(token_items, start=1):
            token_label = f"ACCOUNT{i}"
            default_map = ",".join(mapped) if mapped else ""
            prompt_text = f"Enter Channel ID {token_label}"
            channels_raw = get_input(prompt_text, default_map) if default_map else get_input(prompt_text)
            channels = [c.strip() for c in re.split(r"[,\s]+", channels_raw) if c.strip().isdigit()]
            if not channels:
                log_message(f"Skip {token_label} ({mask_token_display(token)}) — no channels.", "WARNING")
                continue

            allow_e, pct_e = ask_emoji_for_account(token_label, default_allowed='y', default_percent='25')

            for ch in channels:
                env = dict(base_env); env.update({
                    "TOKEN_VALUE": token,
                    "CHANNEL_ID": ch,
                    "STATE_FILE": f"state_t{i}_{ch}.json",
                    "EMOJI_ALLOWED": allow_e,
                    "EMOJI_PERCENT": pct_e,
                    "WORKER_SILENT": "1",
                    "NON_INTERACTIVE": "1",
                })
                launch_plan.append((token_label, token, ch, env))

    # ======= Ringkasan & Launch Bareng =======
    print(Fore.YELLOW + "\nLaunch plan:")
    for label, token, ch, _env in launch_plan:
        print(f"  {label}  token={mask_token_display(token)}  channel={ch}")
    input(Fore.CYAN + "Press Enter to START all...")

    procs = []
    for label, token, ch, env in launch_plan:
        log_message(f"LAUNCH ➜ {label} token={mask_token_display(token)} channel={ch}", "INFO")
        p = Process(target=run_worker, args=(env,), daemon=False)
        p.start(); procs.append(p); time.sleep(0.2)

    try:
        for p in procs:
            p.join()
    except KeyboardInterrupt:
        log_message("Stopping all workers...", "WARNING")
        for p in procs:
            p.terminate()
