import requests
import random
import time
import os
import json
import re
from datetime import datetime
from colorama import Fore, init
import sys

# ================== Defaults (can be overridden by input) ==================
MIN_WORDS = 3
MAX_WORDS = 15

# Greetings & style (will be overridden from input)
ALLOW_TIME_GREETINGS = True      # allow "good morning/afternoon/evening"
NAME_MENTION_PROB = 0.25         # default 25% to prefix with user's name (if clean)
EMOJI_BASE_PROB = 0.30           # chance to add ONE emoji if user had none
EMOJI_IF_USER_USED = 0.60        # chance to add ONE emoji if user used emoji

# High-priority reply policy (can be overridden from input)
MAX_THREAD_REPLIES = 3           # total replies per bot-thread (including the first)
FOLLOWUP_CONTINUE_PROB = 0.60    # probability for 2nd/3rd follow-up replies

# Natural typing pause before sending
MIN_REPLY_DELAY = 3
MAX_REPLY_DELAY = 10

# Persistence
STATE_FILE = "bot_state.json"     # holds thread counts, processed IDs, and our own message IDs
MAX_PROCESSED_MEMORY = 5000
MAX_OWN_IDS_MEMORY = 5000
# ===========================================================================

# In-memory state (will be loaded/saved)
THREAD_REPLY_COUNTS = {}          # { bot_message_id: count }
_processed_ids_list = []          # ordered list of processed message IDs
processed_messages = set()        # set for O(1) membership
_own_ids_list = []                # ordered list of our own message IDs
OWN_IDS = set()                   # set for quick membership

# Initialize colorama
init(autoreset=True)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    try:
        width = os.get_terminal_size().columns
    except Exception:
        width = 60
    banner_lines = [
        "=" * width,
        Fore.CYAN + "===================  AI AUTO REPLY BOT  ====================",
        Fore.MAGENTA + "================= @AirdropJP_JawaPride =====================",
        Fore.YELLOW + "=============== https://x.com/JAWAPRIDE_ID =================",
        Fore.RED + "============= https://linktr.ee/Jawa_Pride_ID ==============",
        Fore.WHITE + "=" * width
    ]
    for line in banner_lines:
        print(line)

def log_message(message, status="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = {
        "INFO": Fore.WHITE,
        "SUCCESS": Fore.GREEN,
        "ERROR": Fore.RED,
        "WARNING": Fore.YELLOW
    }.get(status, Fore.WHITE)
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
    if msg_id in processed_messages:
        return
    _processed_ids_list.append(str(msg_id))
    processed_messages.add(str(msg_id))
    while len(_processed_ids_list) > MAX_PROCESSED_MEMORY:
        old = _processed_ids_list.pop(0)
        processed_messages.discard(old)
    save_state()

def record_own_message_id(msg_id: str):
    if msg_id in OWN_IDS:
        return
    _own_ids_list.append(str(msg_id))
    OWN_IDS.add(str(msg_id))
    while len(_own_ids_list) > MAX_OWN_IDS_MEMORY:
        old = _own_ids_list.pop(0)
        OWN_IDS.discard(old)
    save_state()

# ----------------------- Emoji & Text Helpers -----------------------
# Wide, varied emoji pool (max ONE will be used per reply)
EMOJI_POOL = [
    "🙂","😉","😄","😁","😊","😌","😎","🤝","👍","🆗","✅","🔥","✨","🎯","🚀","🌟","🙌","👏",
    "😅","😂","😆","🤣","😜","🤗","🥳","🤩","😇","😺","😸","😻",
    "😐","🤔","😮","😲","😯","😴","🥱","😪","😬","😳","😌",
    "☀️","🌞","🌈","🌊","🌱","🍀","🍻","☕","🍵","🍕","🍩",
    "💪","🧠","🫶","🤝","🫡","🙏","📈","🛠️","🧰","📝"
]

BANNED_GREETINGS = [
    "good morning", "good afternoon", "good evening",
    "selamat pagi", "selamat siang", "selamat malam"
]

TIME_GREETINGS_RE = re.compile(
    r"\b(good morning|good afternoon|good evening)\b",
    re.IGNORECASE
)

EMOJI_RE = re.compile(
    "["                     # common emoji blocks
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002600-\U000026FF"
    "]", flags=re.UNICODE
)

def contains_emoji(text: str) -> bool:
    return bool(EMOJI_RE.search(text or ""))

def has_risky_chars(text: str) -> bool:
    return any(c in (":", "@", "#", "<", ">", "|", "`") for c in (text or ""))

def strip_greetings(text: str) -> str:
    t = text.strip()
    low = t.lower()
    for g in BANNED_GREETINGS:
        if low.startswith(g):
            t = t[len(g):].lstrip(" ,.-!?")
            break
    return t

def sanitize_response(text: str) -> str:
    t = text.replace('\n', ' ').strip().strip('"').strip("'")
    t = re.sub(r"\s+", " ", t)
    if not ALLOW_TIME_GREETINGS:
        t = TIME_GREETINGS_RE.sub("", t)
        t = re.sub(r"\s{2,}", " ", t).strip(" ,.-!?")
        t = strip_greetings(t)
    if t.endswith('.'):
        t = t[:-1]
    return t

def clamp_words(text: str, min_w: int = MIN_WORDS, max_w: int = MAX_WORDS) -> str:
    words = [w for w in text.split() if w.strip()]
    if len(words) > max_w:
        words = words[:max_w]
    if len(words) < min_w:
        fillers = ["thoughts?", "okay?", "agree?", "what do you think?"]
        while len(words) < min_w:
            words.append(random.choice(fillers))
    return " ".join(words)

def maybe_prefix_name(name: str) -> str:
    """Return 'Name, ' with probability, unless name has emoji or risky chars."""
    if not name or contains_emoji(name) or has_risky_chars(name):
        return ""
    if random.random() < NAME_MENTION_PROB:
        return f"{name}, "
    return ""

def maybe_add_emoji(reply: str, user_message: str) -> str:
    """Append at most ONE emoji based on probability."""
    user_used = contains_emoji(user_message)
    prob = EMOJI_IF_USER_USED if user_used else EMOJI_BASE_PROB
    if random.random() < prob:
        return (reply + " " + random.choice(EMOJI_POOL)).strip()
    return reply

def enforce_single_emoji(text: str) -> str:
    """Ensure there is at most ONE emoji in the final reply."""
    emojis = EMOJI_RE.findall(text or "")
    if len(emojis) <= 1:
        return text
    no_emoji = EMOJI_RE.sub("", text).strip()
    return (no_emoji + " " + emojis[0]).strip()

# ----------------------- Bot mention / reply detection -----------------------
def is_mention_of_bot(message: dict, bot_user_id: str) -> bool:
    content = message.get('content', '') or ''
    if f"<@{bot_user_id}>" in content or f"<@!{bot_user_id}>" in content:
        return True
    for m in message.get('mentions', []):
        if m.get('id') == bot_user_id:
            return True
    return False

def get_referenced_bot_message_id(message: dict, bot_user_id: str):
    """
    Return the bot's message ID that this message is replying to.
    Works even if 'referenced_message' is missing by checking message_reference.
    """
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

# ------------------ AI Generation Logic ------------------
def _finalize_ai_text(raw_text: str, display_name: str, user_message: str) -> str:
    """Sanitize, clamp, maybe prefix name, and maybe add emoji (max 1)."""
    ai = sanitize_response(raw_text)
    ai = clamp_words(ai, MIN_WORDS, MAX_WORDS)
    ai = enforce_single_emoji(ai)
    # Name prefix is optional probability:
    prefix = maybe_prefix_name(display_name)
    ai = (prefix + ai).strip()
    # Only add emoji if there isn't one yet:
    if not contains_emoji(ai):
        ai = maybe_add_emoji(ai, user_message)
    ai = enforce_single_emoji(ai)
    return ai[:300]

def generate_ai_response(user_message, display_name, retry_count=0):
    """
    Generate AI response. Try OpenRouter → OpenAI → Gemini.
    English-only, casual & friendly, 3–15 words. Do NOT include user name yourself.
    """
    max_retries = 2

    system_prompt = (
        "You are a casual, friendly Discord chat assistant. "
        "Reply naturally like a human, without excessive formality. "
        "You may use normal greetings like 'good morning' when appropriate. "
        "Always answer in English. Keep it short: 3–15 words. "
        "Do NOT include the user's name in the reply. "
        "Use at most one emoji, and only if it fits the tone."
    )
    user_prompt = (
        f"Message: \"{user_message}\"\n"
        "Reply in English, casually and briefly, 3–15 words. "
        "Do not include the user's name."
    )

    # ------- Try OpenRouter -------
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
            log_message(f"Using OpenRouter API (attempt {retry_count + 1})", "INFO")
            url = "https://openrouter.ai/api/v1/chat/completions"
            payload = {
                "model": "openrouter/auto",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.8,
                "max_tokens": 100,
                "frequency_penalty": 0.2
            }
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                ai = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if ai:
                    final = _finalize_ai_text(ai, display_name, user_message)
                    log_message("AI response generated with OpenRouter", "SUCCESS")
                    return final
                else:
                    log_message("OpenRouter returned empty content", "WARNING")
            elif resp.status_code == 429:
                log_message("OpenRouter rate limit. Waiting 5s then retry.", "WARNING")
                if retry_count < max_retries:
                    time.sleep(5)
                    return generate_ai_response(user_message, display_name, retry_count + 1)
            else:
                log_message(f"OpenRouter error {resp.status_code}: {resp.text[:200]}", "WARNING")
        else:
            log_message("OpenRouter key not set (openrouter_key.txt or OPENROUTER_API_KEY). Skipping.", "WARNING")
    except requests.exceptions.RequestException as e:
        log_message(f"Network error with OpenRouter API: {str(e)}", "WARNING")
    except Exception as e:
        log_message(f"Error with OpenRouter API: {str(e)}", "WARNING")

    # ------- Try OpenAI -------
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
            log_message(f"Using OpenAI ChatGPT API (attempt {retry_count + 1})", "INFO")
            models_to_try = ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4o"]
            model_name = models_to_try[retry_count % len(models_to_try)]
            url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.8,
                "max_tokens": 100,
                "frequency_penalty": 0.2
            }
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                ai = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if ai:
                    final = _finalize_ai_text(ai, display_name, user_message)
                    log_message(f"AI response generated with OpenAI {model_name}", "SUCCESS")
                    return final
                else:
                    log_message("OpenAI returned empty content", "WARNING")
            elif resp.status_code in (401, 403):
                log_message("OpenAI key invalid/forbidden. Check API key & billing.", "ERROR")
            elif resp.status_code == 429:
                log_message("OpenAI rate limit. Waiting 5s then retry.", "WARNING")
                if retry_count < max_retries:
                    time.sleep(5)
                    return generate_ai_response(user_message, display_name, retry_count + 1)
            else:
                log_message(f"OpenAI error {resp.status_code}: {resp.text[:200]}", "WARNING")
        else:
            log_message("OpenAI key not set (openai_key.txt or OPENAI_API_KEY). Skipping OpenAI.", "WARNING")
    except requests.exceptions.RequestException as e:
        log_message(f"Network error with OpenAI API: {str(e)}", "WARNING")
    except Exception as e:
        log_message(f"Error with OpenAI API: {str(e)}", "WARNING")

    # ------- Fallback: Gemini -------
    try:
        with open("gemini_key.txt", "r", encoding='utf-8') as f:
            gemini_key = f.readline().strip()
        if not gemini_key:
            raise FileNotFoundError("Gemini key is empty")

        log_message(f"Using Gemini API (attempt {retry_count + 1})", "INFO")

        prompt = (
            "You are chatting casually in a Discord server. Reply naturally and briefly.\n"
            "Tone: relaxed and friendly. You may use normal greetings.\n"
            "Answer in English only. 3–15 words.\n"
            "Do not include the user's name in the reply.\n\n"
            f"Message: \"{user_message}\"\n\n"
            "Your reply:"
        )

        models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        model_name = models_to_try[retry_count % len(models_to_try)]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.8,
                "topK": 20,
                "topP": 0.8,
                "maxOutputTokens": 100,
                "stopSequences": []
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
            ]
        }

        headers = {"Content-Type": "application/json"}
        response = requests.post(url, headers=headers, json=payload, timeout=12)

        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    ai_response = candidate['content']['parts'][0].get('text', '').strip()
                    final = _finalize_ai_text(ai_response, display_name, user_message)
                    log_message(f"AI response generated with {model_name}", "SUCCESS")
                    return final
                else:
                    log_message("No content in Gemini response", "WARNING")
            else:
                log_message("No valid candidates in Gemini response", "WARNING")
        elif response.status_code == 429:
            log_message("Gemini API rate limit - waiting 5s", "WARNING")
            if retry_count < max_retries:
                time.sleep(5)
                return generate_ai_response(user_message, display_name, retry_count + 1)
        else:
            log_message(f"Gemini API error: {response.status_code}", "WARNING")
            try:
                error_detail = response.json()
                log_message(f"Error detail: {error_detail}", "ERROR")
            except Exception:
                log_message(f"Response text: {response.text[:200]}...", "ERROR")

    except FileNotFoundError:
        log_message("Gemini key file not found (gemini_key.txt)", "WARNING")
    except requests.exceptions.RequestException as e:
        log_message(f"Network error with Gemini API: {str(e)}", "WARNING")
    except Exception as e:
        log_message(f"Error with Gemini API: {str(e)}", "WARNING")

    log_message("All AI attempts failed", "ERROR")
    return None

# ------------------ Discord HTTP helpers ------------------
def get_recent_messages(channel_id, headers, limit=50):
    """Get recent messages from the channel"""
    try:
        url = f"https://discord.com/api/v9/channels/{channel_id}/messages?limit={limit}"
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
    """Send a message; returns JSON (with 'id') on success, otherwise False."""
    max_retries = 3
    try:
        payload = {'content': content}
        if reply_to_message_id:
            payload['message_reference'] = {'message_id': reply_to_message_id}

        response = requests.post(
            f"https://discord.com/api/v9/channels/{channel_id}/messages",
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
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

# --------------------------- Input helpers ---------------------------
def ask_float(prompt, default, lo, hi):
    s = input(Fore.CYAN + f"{prompt} [{default}]: ").strip()
    if s == "":
        return default
    try:
        v = float(s)
        if lo <= v <= hi:
            return v
    except Exception:
        pass
    log_message(f"Invalid value; using default {default}", "WARNING")
    return default

def ask_int(prompt, default, lo, hi):
    s = input(Fore.CYAN + f"{prompt} [{default}]: ").strip()
    if s == "":
        return default
    try:
        v = int(s)
        if lo <= v <= hi:
            return v
    except Exception:
        pass
    log_message(f"Invalid value; using default {default}", "WARNING")
    return default

def ask_bool(prompt, default_true=True):
    default_txt = "y" if default_true else "n"
    s = input(Fore.CYAN + f"{prompt} [y/n, default {default_txt}]: ").strip().lower()
    if s == "":
        return default_true
    if s in ("y", "yes"):
        return True
    if s in ("n", "no"):
        return False
    log_message(f"Invalid value; using default {default_txt}", "WARNING")
    return default_true

# --------------------------- Main ---------------------------
def main():
    clear_screen()
    print_banner()

    # Get user inputs with validation
    try:
        channel_id = input(Fore.CYAN + "Enter Channel ID: ").strip()
        if not channel_id.isdigit():
            log_message("Invalid Channel ID format", "ERROR")
            return

        process_count = ask_int("How many recent messages to scan each check (1–100)", 50, 1, 100)
        reply_chance = ask_float("Reply chance for normal messages (0.0–1.0)", 0.3, 0.0, 1.0)

        # Style knobs
        global NAME_MENTION_PROB, EMOJI_BASE_PROB, EMOJI_IF_USER_USED, ALLOW_TIME_GREETINGS
        NAME_MENTION_PROB = ask_float("Chance to prefix username (0.0–1.0)", NAME_MENTION_PROB, 0.0, 1.0)
        EMOJI_BASE_PROB = ask_float("Emoji chance if user used NONE (0.0–1.0)", EMOJI_BASE_PROB, 0.0, 1.0)
        EMOJI_IF_USER_USED = ask_float("Emoji chance if user USED emoji (0.0–1.0)", EMOJI_IF_USER_USED, 0.0, 1.0)
        ALLOW_TIME_GREETINGS = ask_bool("Allow time-based greetings (good morning/afternoon/evening)?", True)

        # Thread policy knobs
        global MAX_THREAD_REPLIES, FOLLOWUP_CONTINUE_PROB
        MAX_THREAD_REPLIES = ask_int("Max follow-ups per thread (1–5)", MAX_THREAD_REPLIES, 1, 5)
        FOLLOWUP_CONTINUE_PROB = ask_float("Follow-up continue probability (0.0–1.0)", FOLLOWUP_CONTINUE_PROB, 0.0, 1.0)

        min_delay = ask_int("Minimum delay between checks (seconds)", 30, 1, 3600)
        max_delay = ask_int("Maximum delay between checks (seconds)", 60, min_delay, 7200)

    except ValueError:
        log_message("Invalid input format", "ERROR")
        return

    # Countdown
    print(Fore.YELLOW + "\nStarting in:")
    for i in range(3, 0, -1):
        print(Fore.YELLOW + str(i))
        time.sleep(1)

    clear_screen()
    print_banner()

    # Read Discord token
    try:
        with open("token.txt", "r", encoding='utf-8') as f:
            authorization = f.readline().strip()

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

    headers = {
        'Authorization': authorization,
        'Content-Type': 'application/json',
        'User-Agent': 'Discord Bot'
    }

    # Get bot user info
    try:
        bot_info = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=10)
        if bot_info.status_code == 200:
            bot_data = bot_info.json()
            bot_user_id = bot_data['id']
            bot_username = bot_data.get('username') or bot_data.get('global_name') or 'Unknown'
            log_message(f"Bot started successfully! Bot: {bot_username} (ID: {bot_user_id})", "SUCCESS")
        else:
            log_message(f"Failed to get bot info. Status: {bot_info.status_code}. Check your token.", "ERROR")
            return
    except Exception as e:
        log_message(f"Error getting bot info: {str(e)}", "ERROR")
        return

    # Load persisted state
    load_state()

    consecutive_errors = 0
    max_consecutive_errors = 5

    # Main loop
    while True:
        try:
            messages = get_recent_messages(channel_id, headers, limit=process_count)

            if messages:
                consecutive_errors = 0

                # Newest last
                scan_list = list(reversed(messages[-process_count:]))

                # First pass: split high-priority (reply/mention) vs normal
                high_priority = []
                normal = []
                for msg in scan_list:
                    msg_id = msg.get('id')
                    if not msg_id or msg_id in processed_messages:
                        continue

                    msg_type = msg.get('type', 0)
                    # Accept normal (0) and reply (19); skip others
                    if msg_type not in (0, 19):
                        add_processed(msg_id)
                        continue

                    author_id = msg['author']['id']
                    if author_id == bot_user_id:
                        add_processed(msg_id)
                        continue

                    content = msg.get('content', '') or ''
                    if not content:
                        add_processed(msg_id)
                        continue

                    if is_reply_to_bot(msg, bot_user_id) or is_mention_of_bot(msg, bot_user_id):
                        high_priority.append(msg)
                    else:
                        normal.append(msg)

                # 1) Handle high-priority first
                for message in high_priority:
                    message_id = message['id']
                    if message_id in processed_messages:
                        continue

                    author_username = message['author']['username']
                    author_name = message['author'].get('display_name') or message['author'].get('global_name') or author_username
                    content = message['content']

                    must_reply = False
                    maybe_reply = False
                    thread_key = None

                    ref_bot_msg_id = get_referenced_bot_message_id(message, bot_user_id)
                    if ref_bot_msg_id:
                        thread_key = ref_bot_msg_id
                        log_message(f"(PRIORITY DETECTED) Reply to our msg {ref_bot_msg_id}", "INFO")
                        count = THREAD_REPLY_COUNTS.get(thread_key, 0)
                        if count >= MAX_THREAD_REPLIES:
                            add_processed(message_id)
                            continue
                        if count == 0:
                            must_reply = True
                        else:
                            maybe_reply = True
                    else:
                        if is_mention_of_bot(message, bot_user_id):
                            log_message("(PRIORITY DETECTED) Mentioned us", "INFO")
                        must_reply = True  # mention: reply once

                    do_reply = must_reply or (maybe_reply and (random.random() < FOLLOWUP_CONTINUE_PROB))
                    if not do_reply:
                        add_processed(message_id)
                        continue

                    log_message(f"(PRIORITY) From {author_name}: {content[:120]}", "INFO")

                    ai_response = generate_ai_response(content, author_name)
                    if ai_response is None:
                        log_message(f"Skipping priority message from {author_name} - AI failed", "WARNING")
                        add_processed(message_id)
                        continue

                    reply_delay = random.uniform(MIN_REPLY_DELAY, MAX_REPLY_DELAY)
                    log_message(f"Replying in {reply_delay:.1f} seconds...", "INFO")
                    time.sleep(reply_delay)

                    sent = send_message(channel_id, ai_response, headers, message_id)
                    if sent:
                        if ref_bot_msg_id:
                            THREAD_REPLY_COUNTS[thread_key] = THREAD_REPLY_COUNTS.get(thread_key, 0) + 1
                            save_state()
                        else:
                            if isinstance(sent, dict) and sent.get('id'):
                                THREAD_REPLY_COUNTS[sent['id']] = 1
                                save_state()
                        log_message(f"Replied (priority) to {author_name}: {ai_response}", "SUCCESS")
                    else:
                        log_message(f"Failed to send priority reply to {author_name}", "ERROR")

                    add_processed(message_id)

                # 2) Handle normal messages
                for message in normal:
                    message_id = message['id']
                    if message_id in processed_messages:
                        continue

                    author_username = message['author']['username']
                    author_name = message['author'].get('display_name') or message['author'].get('global_name') or author_username
                    content = message['content']

                    if random.random() <= reply_chance:
                        log_message(f"From {author_name}: {content[:120]}", "INFO")

                        ai_response = generate_ai_response(content, author_name)
                        if ai_response is None:
                            log_message(f"Skipping message from {author_name} - AI failed", "WARNING")
                            add_processed(message_id)
                            continue

                        reply_delay = random.uniform(MIN_REPLY_DELAY, MAX_REPLY_DELAY)
                        log_message(f"Replying in {reply_delay:.1f} seconds...", "INFO")
                        time.sleep(reply_delay)

                        sent = send_message(channel_id, ai_response, headers, message_id)
                        if sent:
                            log_message(f"Replied to {author_name}: {ai_response}", "SUCCESS")
                        else:
                            log_message(f"Failed to send reply to {author_name}", "ERROR")

                    add_processed(message_id)

            else:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    log_message(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.", "ERROR")
                    break

            delay = random.uniform(max(min_delay, 30), max(max_delay, 60))
            log_message(f"Waiting {delay:.1f} seconds before next check...", "INFO")
            time.sleep(delay)

        except KeyboardInterrupt:
            save_state()
            log_message("Program stopped by user", "WARNING")
            break
        except Exception as e:
            log_message(f"An unexpected error occurred: {str(e)}", "ERROR")
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                save_state()
                log_message(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.", "ERROR")
                break
            time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        save_state()
        log_message("\nProgram stopped by user", "WARNING")
    except Exception as e:
        save_state()
        log_message(f"Critical error: {str(e)}", "ERROR")
