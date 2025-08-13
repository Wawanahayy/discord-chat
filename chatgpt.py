import requests
import random
import time
import os
import json
import re
from datetime import datetime
from colorama import Fore, init
import pyfiglet
import sys


MIN_WORDS = 3
MAX_WORDS = 15



init(autoreset=True)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    width = os.get_terminal_size().columns  # Get terminal width
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

# ----------------------- Helpers -----------------------
BANNED_GREETINGS = [
    "good morning", "good afternoon", "good evening",
    "selamat pagi", "selamat siang", "selamat malam"
]

def strip_greetings(text: str) -> str:
    t = text.strip()
    low = t.lower()
    for g in BANNED_GREETINGS:
        if low.startswith(g):
            # remove the greeting at start only
            t = t[len(g):].lstrip(" ,.-!?")
            break
    return t

def sanitize_response(text: str) -> str:
    t = text.replace('\n', ' ').strip().strip('"').strip("'")
    t = re.sub(r"\s+", " ", t)
    if t.endswith('.'):
        t = t[:-1]
    t = strip_greetings(t)
    return t

def clamp_words(text: str, min_w: int = MIN_WORDS, max_w: int = MAX_WORDS) -> str:
    words = [w for w in text.split() if w.strip()]
    if len(words) > max_w:
        words = words[:max_w]
    # If too short, add a soft, friendly closer
    if len(words) < min_w:
        fillers = ["thoughts?", "okay?", "agree?", "what do you think?"]
        while len(words) < min_w:
            words.append(random.choice(fillers))
    return " ".join(words)

# ------------------ AI Generation Logic ------------------

def generate_ai_response(user_message, display_name, retry_count=0):
    """
    Generate AI response. Tries OpenAI (ChatGPT) first, then falls back to Gemini.
    Enforces 3–15 words and a casual, friendly tone — in English only.
    """
    max_retries = 2

    # ------- Try OpenAI (ChatGPT) -------
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

            system_prompt = (
                "You are a casual, friendly Discord chat assistant. "
                "Reply naturally like a human, without excessive formality. "
                "Avoid time-based greetings (e.g., 'good morning'). "
                "Always answer in English. "
                "Keep it short: 3–15 words. "
                "No emojis unless the user used one first."
            )

            user_prompt = (
                f"Partner name: {display_name}. "
                f"Message: \"{user_message}\" "
                "Reply in English, casually and briefly, 3–15 words."
            )

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
                    ai = sanitize_response(ai)
                    ai = clamp_words(ai, MIN_WORDS, MAX_WORDS)
                    log_message(f"AI response generated with OpenAI {model_name}", "SUCCESS")
                    return ai[:300]
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

    # ------- Fallback: Google Gemini (English-only prompt) -------
    try:
        with open("gemini_key.txt", "r", encoding='utf-8') as f:
            gemini_key = f.readline().strip()
        if not gemini_key:
            raise FileNotFoundError("Gemini key is empty")

        log_message(f"Using Gemini API (attempt {retry_count + 1})", "INFO")

        prompt = (
            "You are chatting casually in a Discord server. Reply naturally and briefly.\n"
            "Tone: relaxed and friendly. Avoid time-based greetings.\n"
            "Answer in English only. 3–15 words.\n"
            f"Partner: {display_name}\n\n"
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
                    ai_response = sanitize_response(ai_response)
                    ai_response = clamp_words(ai_response, MIN_WORDS, MAX_WORDS)
                    log_message(f"AI response generated with {model_name}", "SUCCESS")
                    return ai_response[:300]
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

    # If all attempts failed
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
    """Send a message to the channel with retry logic for rate limits"""
    max_retries = 3

    try:
        payload = {'content': content}

        # If replying to a specific message
        if reply_to_message_id:
            payload['message_reference'] = {
                'message_id': reply_to_message_id
            }

        response = requests.post(
            f"https://discord.com/api/v9/channels/{channel_id}/messages",
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
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

        reply_chance_input = input(Fore.CYAN + "Reply chance (0.1 = 10%, 0.3 = 30%): ").strip()
        reply_chance = float(reply_chance_input)
        if not 0 <= reply_chance <= 1:
            log_message("Reply chance must be between 0 and 1", "ERROR")
            return

        min_delay = int(input(Fore.CYAN + "Minimum delay between checks (seconds): "))
        max_delay = int(input(Fore.CYAN + "Maximum delay between checks (seconds): "))

        if min_delay < 1 or max_delay < min_delay:
            log_message("Invalid delay values", "ERROR")
            return

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

        # Heads up if it's not a Bot token (Discord ToS)
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

    processed_messages = set()  # Track processed messages
    consecutive_errors = 0
    max_consecutive_errors = 5

    # Main loop
    while True:
        try:
            # Get recent messages
            messages = get_recent_messages(channel_id, headers)

            if messages:
                consecutive_errors = 0  # Reset error counter on success

                # Process messages (newest first)
                for message in reversed(messages[-10:]):  # Check last 10 messages
                    message_id = message['id']
                    author_id = message['author']['id']
                    author_username = message['author']['username']
                    # Use display_name if available, otherwise use username
                    author_name = message['author'].get('display_name') or message['author'].get('global_name') or author_username
                    content = message['content']

                    # Skip if already processed or if it's from the bot itself
                    if message_id in processed_messages or author_id == bot_user_id:
                        continue

                    # Skip empty messages or system messages
                    if not content or message['type'] != 0:
                        processed_messages.add(message_id)
                        continue

                    # Random chance to reply
                    if random.random() <= reply_chance:
                        log_message(f"Found message from {author_name}: {content[:50]}...", "INFO")

                        # Generate AI response
                        ai_response = generate_ai_response(content, author_name)

                        # Skip if AI failed completely
                        if ai_response is None:
                            log_message(f"Skipping message from {author_name} - AI failed", "WARNING")
                            processed_messages.add(message_id)
                            continue

                        # Add small delay before replying to seem natural
                        reply_delay = random.uniform(3, 10)  # natural pause
                        log_message(f"Generating reply in {reply_delay:.1f} seconds...", "INFO")
                        time.sleep(reply_delay)

                        # Send reply to the specific message
                        if send_message(channel_id, ai_response, headers, message_id):
                            log_message(f"Replied to {author_name}: {ai_response}", "SUCCESS")
                        else:
                            log_message(f"Failed to send reply to {author_name}", "ERROR")

                    processed_messages.add(message_id)

                    # Keep only recent message IDs in memory (prevent memory leak)
                    if len(processed_messages) > 1000:
                        processed_messages = set(list(processed_messages)[-500:])
            else:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    log_message(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.", "ERROR")
                    break

            # Wait before next check (longer to avoid rate limits)
            delay = random.uniform(max(min_delay, 30), max(max_delay, 60))  # Minimum 30s delay
            log_message(f"Waiting {delay:.1f} seconds before next check...", "INFO")
            time.sleep(delay)

        except KeyboardInterrupt:
            log_message("Program stopped by user", "WARNING")
            break
        except Exception as e:
            log_message(f"An unexpected error occurred: {str(e)}", "ERROR")
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                log_message(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.", "ERROR")
                break
            time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_message("\nProgram stopped by user", "WARNING")
    except Exception as e:
        log_message(f"Critical error: {str(e)}", "ERROR")
