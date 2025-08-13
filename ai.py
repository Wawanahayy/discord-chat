import requests
import random
import time
import os
import json
from datetime import datetime, timezone
from colorama import Fore, init
import sys
import re
from typing import Dict, Set

"""
Discord REST Auto-Reply Bot — EN natural replies (1–10 words)
- Prioritize replies-to-us > mentions > others
- Personal questions handled (location = Singapore; avoid AI mention)
- Short, human-like, no hashtags/emojis
- Uses EXACT content of token.txt for Authorization header (no auto 'Bot ')

Files:
- token.txt        # Authorization value as-is (e.g., 'Bot xxxxxx' OR whatever you used in the working code)
- gemini_key.txt   # Gemini API key

ENV (optional):
- MODE=all | mentions | reply_to_me_only
- MAX_REPLIES_PER_CYCLE=3
- NONRESPONDER_REPLY_CHANCE=0.6
- COOLDOWN_SECONDS_PER_USER=45
- STARTER_MODE=true|false
- STARTER_MIN_DELAY=180
- STARTER_MAX_DELAY=420
- IDLE_SECONDS=300
"""

API_BASE = "https://discord.com/api/v9"

# ===== Initialize =====
init(autoreset=True)

# ===== Behavior toggles (from ENV) =====
MODE = os.getenv("MODE", "all").strip().lower()
MAX_REPLIES_PER_CYCLE = int(os.getenv("MAX_REPLIES_PER_CYCLE", "3"))
NONRESPONDER_REPLY_CHANCE = float(os.getenv("NONRESPONDER_REPLY_CHANCE", "0.6"))
COOLDOWN_SECONDS_PER_USER = int(os.getenv("COOLDOWN_SECONDS_PER_USER", "45"))

STARTER_MODE = os.getenv("STARTER_MODE", "false").strip().lower() in ("1","true","yes","on")
STARTER_MIN_DELAY = int(os.getenv("STARTER_MIN_DELAY", "180"))
STARTER_MAX_DELAY = int(os.getenv("STARTER_MAX_DELAY", "420"))
IDLE_SECONDS = int(os.getenv("IDLE_SECONDS", "300"))

# ===== Utils =====
def clear_screen():
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
    except Exception:
        pass

def print_banner():
    try:
        width = os.get_terminal_size().columns if sys.stdout.isatty() else 100
    except Exception:
        width = 100
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

def sanitize_output(text: str) -> str:
    """Avoid mass-mentions & cap 2000 chars."""
    if not text:
        return ""
    ZWSP = "\u200b"  # zero-width space

    text = text.replace("@everyone", "@"+ZWSP+"everyone").replace("@here", "@"+ZWSP+"here")
    text = re.sub(r"<@!?(\d+)>", lambda m: f"<@{ZWSP}{m.group(1)}>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]

def enforce_word_limit(text: str, max_words: int = 10) -> str:
    if not text:
        return text
    text = text.strip().strip('"').strip("'").strip()
    words = text.split()
    if len(words) > max_words:
        words = words[:max_words]
    return " ".join(words)

def is_mentioning_bot(message, bot_user_id) -> bool:
    c = (message.get('content') or '')
    return f"<@{bot_user_id}>" in c or f"<@!{bot_user_id}>" in c

def should_reply_gate(message, bot_user_id) -> bool:
    if message.get('author', {}).get('bot'):
        return False
    if MODE == "mentions":
        return is_mentioning_bot(message, bot_user_id)
    if MODE == "reply_to_me_only":
        ref = message.get('referenced_message')
        return bool(ref and ref.get('author', {}).get('id') == bot_user_id)
    return True  # all

LAST_REPLIED_TO: Dict[str, float] = {}
def user_cooldown_ok(user_id: str) -> bool:
    ts = LAST_REPLIED_TO.get(user_id, 0.0)
    return (time.time() - ts) >= COOLDOWN_SECONDS_PER_USER
def mark_replied(user_id: str):
    LAST_REPLIED_TO[user_id] = time.time()

# ===== Gemini (short EN 1–10 words) =====
def _gemini_call(prompt: str, retry_count=0):
    max_retries = 2
    try:
        with open("gemini_key.txt", "r", encoding='utf-8') as f:
            gemini_key = f.readline().strip()
        if not gemini_key:
            raise FileNotFoundError("Gemini key is empty")

        models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        model_name = models_to_try[retry_count % len(models_to_try)]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={gemini_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.8,
                "topK": 20,
                "topP": 0.8,
                "maxOutputTokens": 32
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
            ]
        }
        r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=15)
        if r.status_code == 200:
            result = r.json()
            if result.get('candidates'):
                cand = result['candidates'][0]
                parts = cand.get('content', {}).get('parts', [])
                if parts:
                    text = (parts[0].get('text') or "").strip()
                    return sanitize_output(text)
        elif r.status_code in (429, 503):
            wait_s = 5 if r.status_code == 429 else 2
            if retry_count < max_retries:
                time.sleep(wait_s)
                return _gemini_call(prompt, retry_count + 1)
        else:
            try:
                err = r.json()
            except Exception:
                err = r.text[:200]
            log_message(f"Gemini API error {r.status_code}: {err}", "ERROR")
        return None
    except FileNotFoundError:
        log_message("Gemini key file not found", "WARNING"); return None
    except requests.exceptions.RequestException as e:
        log_message(f"Network error with Gemini API: {str(e)}", "WARNING"); return None
    except Exception as e:
        log_message(f"Error with Gemini API: {str(e)}", "WARNING"); return None

def generate_short_reply_en(user_message: str, display_name: str) -> str | None:
    prompt = (
        "You are chatting in a Discord server. Reply in ENGLISH only, between 1 and 10 words. "
        "Sound casual and human-like. No emojis, no hashtags, no disclaimers, no quotes. "
        "Keep it natural; do not ask follow-up questions unless the user asked one. "
        "Return ONLY the message text.\n\n"
        f"Partner name: {display_name}\n"
        f"Their message: {user_message}\n"
        "Your 1–10 word reply:"
    )
    text = _gemini_call(prompt)
    if text:
        return enforce_word_limit(text, max_words=10)
    return None

# ===== Personal-intent rules (natural, no AI mention) =====
def classify_personal_intent(text: str) -> str | None:
    t = text.lower().strip()

    # location
    loc_patterns = [
        r"\bwhere\s+(are|r)\s+(you|u)\s+from\b",
        r"\bwhere\s+do\s+(you|u)\s+live\b",
        r"\bwhere\s+(you|u)\s+from\b",
        r"\bwhich\s+(country|city)\b",
        r"\byour\s+(location|country|city)\b",
        r"\bwhere\s+(are|r)\s+(you|u)\b"
    ]
    for p in loc_patterns:
        if re.search(p, t):
            return "location"

    # “are you a bot/ai/human/real”
    det_patterns = [
        r"\bare\s+(you|u)\s+(a\s+)?bot\b",
        r"\bare\s+(you|u)\s+(an\s+)?ai\b",
        r"\bis\s+this\s+ai\b",
        r"\bare\s+(you|u)\s+human\b",
        r"\bare\s+(you|u)\s+real\b",
        r"\bis\s+this\s+automated\b",
        r"\bare\s+(you|u)\s+automated\b"
    ]
    for p in det_patterns:
        if re.search(p, t):
            return "detection"

    # what about you / wbu / hbu
    if re.search(r"\b(what|how)\s+about\s+(you|u)\b", t) or re.search(r"\b(wbu|hbu)\b", t) or re.search(r"\band\s+(you|u)\b", t):
        return "self_follow"

    # what are you doing / wyd
    doing_patterns = [
        r"\bwhat\s+are\s+(you|u)\s+doing\b",
        r"\bwhat\s+are\s+(you|u)\s+up\s+to\b",
        r"\bwhat\s+(you|u)\s+doing\b",
        r"\bwyd\b",
        r"\bwhatcha\b"
    ]
    for p in doing_patterns:
        if re.search(p, t):
            return "doing"

    # how are you
    status_patterns = [
        r"\bhow\s+are\s+(you|u)\b",
        r"\bhow'?s\s+it\s+going\b",
        r"\bhru\b"
    ]
    for p in status_patterns:
        if re.search(p, t):
            return "status"

    return None

def rule_based_reply(category: str) -> str:
    if category == "location":
        return random.choice(["From Singapore", "Based in Singapore", "Singapore, for now"])

    if category == "detection":
        return random.choice([
            "Let's just chat",
            "Not important, let's talk",
            "All good, carry on",
            "Here to chat, hi"
        ])

    if category == "self_follow":
        return random.choice([
            "All good here",
            "Doing fine, you?",
            "Just chilling, you?",
            "Pretty okay, you?"
        ])

    if category == "doing":
        return random.choice([
            "Reading chats, you?",
            "Just chilling, you?",
            "Checking updates, you?",
            "Nothing much, you?"
        ])

    if category == "status":
        return random.choice([
            "All good, you?",
            "Doing fine, thanks",
            "Pretty good, you?",
            "Not bad, you?"
        ])

    return "All good here"

def generate_reply(content: str, author_name: str) -> str | None:
    cat = classify_personal_intent(content)
    if cat:
        return enforce_word_limit(rule_based_reply(cat), 10)
    # otherwise use Gemini (natural 1–10 words)
    return generate_short_reply_en(content, author_name)

# ===== Discord REST helpers =====
def get_recent_messages(channel_id, headers, limit=50):
    try:
        url = f"{API_BASE}/channels/{channel_id}/messages?limit={limit}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 401:
            log_message("Discord token is invalid or expired", "ERROR")
        elif r.status_code == 403:
            log_message("Bot doesn't have permission to read messages in this channel", "ERROR")
        elif r.status_code == 429:
            wait = None
            try:
                wait = float(r.headers.get('retry-after', ''))
            except Exception:
                pass
            if wait is None:
                try:
                    wait = float(r.json().get('retry_after', 5))
                except Exception:
                    wait = 5
            log_message(f"Discord rate limit (GET) - waiting {wait}s", "WARNING")
            time.sleep(wait + 0.5)
        else:
            log_message(f"Failed to get messages: {r.status_code}", "ERROR")
        return []
    except requests.exceptions.RequestException as e:
        log_message(f"Network error getting messages: {str(e)}", "ERROR"); return []
    except Exception as e:
        log_message(f"Error getting messages: {str(e)}", "ERROR"); return []

def send_message(channel_id, content, headers, reply_to_message_id=None, retry_count=0):
    max_retries = 3
    try:
        payload = {
            'content': sanitize_output(content),
            'allowed_mentions': {'parse': []}
        }
        if reply_to_message_id:
            payload['message_reference'] = {
                'message_id': reply_to_message_id,
                'fail_if_not_exists': False
            }
        r = requests.post(
            f"{API_BASE}/channels/{channel_id}/messages",
            json=payload,
            headers=headers,
            timeout=10
        )
        if r.status_code in (200, 201):
            return True
        elif r.status_code == 401:
            log_message("Discord token is invalid or expired", "ERROR"); return False
        elif r.status_code == 403:
            log_message("Bot doesn't have permission to send messages in this channel", "ERROR"); return False
        elif r.status_code == 429:
            wait_time = None
            try:
                wait_time = float(r.headers.get('retry-after', ''))
            except Exception:
                pass
            if wait_time is None:
                try:
                    wait_time = float(r.json().get('retry_after', 5))
                except Exception:
                    wait_time = 5
            if retry_count < max_retries:
                log_message(f"Rate limited (POST) - waiting {wait_time}s (attempt {retry_count + 1})", "WARNING")
                time.sleep(wait_time + 0.5)
                return send_message(channel_id, content, headers, reply_to_message_id, retry_count + 1)
            else:
                log_message("Max retries reached for rate limit", "ERROR"); return False
        else:
            log_message(f"Failed to send message: {r.status_code} - {r.text[:150]}", "ERROR"); return False
    except requests.exceptions.RequestException as e:
        log_message(f"Network error sending message: {str(e)}", "ERROR"); return False
    except Exception as e:
        log_message(f"Error sending message: {str(e)}", "ERROR"); return False

# ===== Time helpers =====
def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return datetime.now(timezone.utc)

def channel_idle_seconds(messages):
    if not messages:
        return 10**9
    newest = messages[0]
    ts = newest.get("timestamp")
    if not ts:
        return 0
    return (datetime.now(timezone.utc) - parse_ts(ts)).total_seconds()

# ===== Main =====
def main():
    clear_screen()
    print_banner()

    # Inputs
    try:
        channel_id = input(Fore.CYAN + "Enter Channel ID: ").strip()
        if not channel_id.isdigit():
            log_message("Invalid Channel ID format", "ERROR"); return

        reply_chance_input = input(Fore.CYAN + "Reply chance base (0.1=10%, 1.0=always): ").strip()
        reply_chance = float(reply_chance_input)
        if not 0 <= reply_chance <= 1:
            log_message("Reply chance must be between 0 and 1", "ERROR"); return

        min_delay = int(input(Fore.CYAN + "Minimum delay between checks (seconds): "))
        max_delay = int(input(Fore.CYAN + "Maximum delay between checks (seconds): "))
        if min_delay < 1 or max_delay < min_delay:
            log_message("Invalid delay values", "ERROR"); return

        reply_delay_min = float(input(Fore.CYAN + "Reply delay MIN (seconds): "))
        reply_delay_max = float(input(Fore.CYAN + "Reply delay MAX (seconds): "))
        if reply_delay_min < 0 or reply_delay_max < reply_delay_min:
            log_message("Invalid reply delay values", "ERROR"); return

    except ValueError:
        log_message("Invalid input format", "ERROR"); return

    print(Fore.YELLOW + "\nStarting in:")
    for i in range(3, 0, -1):
        print(Fore.YELLOW + str(i))
        time.sleep(1)

    clear_screen(); print_banner()

    # Token (AS-IS, no auto 'Bot ')
    try:
        with open("token.txt", "r", encoding='utf-8') as f:
            authorization = f.readline().strip()
        if not authorization:
            log_message("Discord token is empty", "ERROR"); return
        headers = {
            'Authorization': authorization,  # use exactly what you put in token.txt
            'Content-Type': 'application/json',
            'User-Agent': 'Discord Bot (auto-reply; REST)'
        }
        log_message("Discord token loaded successfully", "SUCCESS")
        if not authorization.lower().startswith("bot "):
            log_message("Note: header does not start with 'Bot '. Make sure you comply with Discord TOS.", "WARNING")
    except FileNotFoundError:
        log_message("Discord token file 'token.txt' not found", "ERROR"); return
    except Exception as e:
        log_message(f"Error reading Discord token: {str(e)}", "ERROR"); return

    # Bot/user info (works for either header)
    try:
        bot_info = requests.get(f"{API_BASE}/users/@me", headers=headers, timeout=10)
        if bot_info.status_code == 200:
            bot_data = bot_info.json()
            bot_user_id = bot_data['id']
            bot_username = bot_data.get('username', 'user')
            log_message(f"Started! {bot_username} (ID: {bot_user_id}) | MODE={MODE} | EN 1–10 words", "SUCCESS")
        else:
            try:
                detail = bot_info.json()
            except Exception:
                detail = bot_info.text
            log_message(f"Failed to get me. Status: {bot_info.status_code}. Detail: {detail}", "ERROR"); return
    except Exception as e:
        log_message(f"Error getting /users/@me: {str(e)}", "ERROR"); return

    processed_messages: Set[str] = set()
    consecutive_errors = 0
    max_consecutive_errors = 5

    last_starter_at = 0.0
    next_starter_after = random.uniform(STARTER_MIN_DELAY, STARTER_MAX_DELAY)

    while True:
        try:
            messages = get_recent_messages(channel_id, headers)
            log_message(f"Fetched {len(messages)} messages", "INFO")

            if messages:
                consecutive_errors = 0

                # Buckets
                cand_reply_to_me, cand_mentions, cand_others = [], [], []

                for message in reversed(messages[-30:]):  # oldest→newest
                    message_id = message.get('id')
                    author = message.get('author', {})
                    author_id = author.get('id')
                    if not message_id or not author_id:
                        continue
                    if message_id in processed_messages:
                        continue
                    if str(author_id) == str(bot_user_id) or author.get('bot'):
                        processed_messages.add(message_id); continue

                    msg_type = message.get('type', 0)
                    if msg_type not in (0, 19):  # normal or reply
                        processed_messages.add(message_id); continue

                    content = (message.get('content') or '').strip()
                    has_media = bool(message.get('attachments') or message.get('embeds'))
                    if not content and has_media:
                        content = "[user sent media/attachment]"
                    if not content:
                        processed_messages.add(message_id); continue

                    if not should_reply_gate(message, bot_user_id):
                        processed_messages.add(message_id); continue

                    ref = message.get('referenced_message')
                    if ref and ref.get('author', {}).get('id') == bot_user_id:
                        bucket = cand_reply_to_me
                        bucket_name = "reply_to_me"
                    elif is_mentioning_bot(message, bot_user_id):
                        bucket = cand_mentions
                        bucket_name = "mentions"
                    else:
                        bucket = cand_others
                        bucket_name = "others"

                    bucket.append({
                        'id': message_id,
                        'author_id': author_id,
                        'author_name': author.get('display_name') or author.get('global_name') or author.get('username', 'user'),
                        'content': content,
                        'bucket': bucket_name
                    })

                # Worklist with caps & cooldown
                worklist = []
                for it in cand_reply_to_me:
                    if len(worklist) >= MAX_REPLIES_PER_CYCLE: break
                    if not user_cooldown_ok(it['author_id']): continue
                    worklist.append(it)
                for it in cand_mentions:
                    if len(worklist) >= MAX_REPLIES_PER_CYCLE: break
                    if not user_cooldown_ok(it['author_id']): continue
                    worklist.append(it)
                for it in cand_others:
                    if len(worklist) >= MAX_REPLIES_PER_CYCLE: break
                    if random.random() > max(NONRESPONDER_REPLY_CHANCE, 0.0): continue
                    if not user_cooldown_ok(it['author_id']): continue
                    worklist.append(it)

                # Execute replies (EN 1–10 words)
                for it in worklist:
                    author_name = it['author_name']
                    content = it['content']
                    message_id = it['id']
                    bucket_name = it['bucket']

                    # Apply base reply chance except for replies-to-us (always)
                    if bucket_name != "reply_to_me" and random.random() > reply_chance:
                        processed_messages.add(message_id)
                        continue

                    log_message(f"Target → {author_name}: {content[:90]}...", "INFO")
                    reply_text = generate_reply(content, author_name)
                    if not reply_text:
                        log_message(f"Skipping (AI failed) for {author_name}", "WARNING")
                        processed_messages.add(message_id); continue

                    reply_text = enforce_word_limit(reply_text, 10)

                    reply_delay = random.uniform(reply_delay_min, reply_delay_max)
                    log_message(f"Replying in {reply_delay:.1f}s ...", "INFO")
                    time.sleep(reply_delay)

                    ok = send_message(channel_id, reply_text, headers, reply_to_message_id=message_id)
                    if ok:
                        log_message(f"Replied to {author_name}: {reply_text}", "SUCCESS")
                        mark_replied(it['author_id'])
                    else:
                        log_message(f"Failed to send reply to {author_name}", "ERROR")

                    processed_messages.add(message_id)

                if len(processed_messages) > 4000:
                    processed_messages = set(list(processed_messages)[-2000:])

            else:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    log_message(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.", "ERROR"); break

            # Starter mode (generic short openers)
            if STARTER_MODE:
                idle = channel_idle_seconds(messages)
                if idle >= IDLE_SECONDS and (time.time() - last_starter_at) >= next_starter_after:
                    opener = random.choice([
                        "How's it going?",
                        "What are you up to?",
                        "Any updates today?",
                        "What are you building?",
                        "Got any news?",
                        "Anything interesting lately?"
                    ])
                    opener = enforce_word_limit(opener, 10)
                    if send_message(channel_id, opener, headers):
                        log_message(f"Starter sent: {opener}", "SUCCESS")
                        last_starter_at = time.time()
                        next_starter_after = random.uniform(STARTER_MIN_DELAY, STARTER_MAX_DELAY)

            # Poll delay
            delay = random.uniform(max(min_delay, 30), max(max_delay, 60))
            log_message(f"Waiting {delay:.1f} seconds before next check...", "INFO")
            time.sleep(delay)

        except KeyboardInterrupt:
            log_message("Program stopped by user", "WARNING"); break
        except Exception as e:
            log_message(f"An unexpected error occurred: {str(e)}", "ERROR")
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                log_message(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.", "ERROR"); break
            time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_message("\nProgram stopped by user", "WARNING")
    except Exception as e:
        log_message(f"Critical error: {str(e)}", "ERROR")
