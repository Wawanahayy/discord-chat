import requests
import random
import time
import os
import json
from datetime import datetime
from colorama import Fore, init
import pyfiglet
import sys

# Initialize colorama
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

def generate_ai_response(user_message, display_name, retry_count=0):
    """
    Generate AI response using Google Gemini API with retry logic
    """
    max_retries = 2
    
    try:
        # Try to load Gemini API key
        try:
            with open("gemini_key.txt", "r", encoding='utf-8') as f:
                gemini_key = f.readline().strip()
            
            if not gemini_key:
                raise FileNotFoundError("Gemini key is empty")
                
            log_message(f"Using Gemini API (attempt {retry_count + 1})", "INFO")
            
            # Create a natural conversation prompt
            prompt = f"""You are chatting casually in a Discord server. Reply naturally and briefly like a normal person would. 
Keep responses short (1-2 sentences max). Be friendly but not overly enthusiastic.
The person you're talking to is named {display_name}.

Their message: "{user_message}"

Your reply:"""
            
            # Try multiple model endpoints
            models_to_try = [
                "gemini-1.5-flash",
                "gemini-1.5-pro",
                "gemini-pro"
            ]
            
            model_name = models_to_try[retry_count % len(models_to_try)]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.8,
                    "topK": 20,
                    "topP": 0.8,
                    "maxOutputTokens": 100,
                    "stopSequences": []
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    }
                ]
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Extract the response text from Gemini's response format
                if 'candidates' in result and len(result['candidates']) > 0:
                    candidate = result['candidates'][0]
                    
                    # Check if the candidate has content
                    if 'content' in candidate and 'parts' in candidate['content']:
                        ai_response = candidate['content']['parts'][0]['text'].strip()
                        
                        # Clean up the response
                        ai_response = ai_response.replace('"', '').strip()
                        if ai_response.endswith('.'):
                            ai_response = ai_response[:-1]
                        
                        log_message(f"AI response generated with {model_name}", "SUCCESS")
                        return ai_response[:300]
                    else:
                        log_message("No content in Gemini response", "WARNING")
                else:
                    log_message("No valid candidates in Gemini response", "WARNING")
            
            elif response.status_code == 400:
                error_detail = response.json() if response.content else {"error": "Bad request"}
                log_message(f"Gemini API bad request: {error_detail}", "ERROR")
            elif response.status_code == 401:
                log_message("Gemini API key invalid or unauthorized", "ERROR")
            elif response.status_code == 403:
                log_message("Gemini API access forbidden - check API key permissions", "ERROR")
            elif response.status_code == 429:
                log_message("Gemini API rate limit - waiting 5s", "WARNING")
                if retry_count < max_retries:
                    time.sleep(5)
                    return generate_ai_response(user_message, display_name, retry_count + 1)
            elif response.status_code == 503:
                log_message(f"Gemini API overloaded (model: {model_name})", "WARNING")
                if retry_count < max_retries:
                    time.sleep(2)
                    return generate_ai_response(user_message, display_name, retry_count + 1)
            else:
                log_message(f"Gemini API error: {response.status_code}", "WARNING")
                try:
                    error_detail = response.json()
                    log_message(f"Error detail: {error_detail}", "ERROR")
                except:
                    log_message(f"Response text: {response.text[:200]}...", "ERROR")
                
        except FileNotFoundError:
            log_message("Gemini key file not found", "WARNING")
        except requests.exceptions.RequestException as e:
            log_message(f"Network error with Gemini API: {str(e)}", "WARNING")
        except Exception as e:
            log_message(f"Error with Gemini API: {str(e)}", "WARNING")
        
        # Return None if all attempts failed
        log_message("All AI attempts failed", "ERROR")
        return None
        
    except Exception as e:
        log_message(f"Error generating AI response: {str(e)}", "ERROR")
        return None

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
                # Get retry-after from headers
                retry_after = response.headers.get('retry-after', '5')
                try:
                    wait_time = float(retry_after)
                except:
                    wait_time = 5
                
                log_message(f"Rate limited - waiting {wait_time}s (attempt {retry_count + 1})", "WARNING")
                time.sleep(wait_time + 1)  # Add 1 second buffer
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
            bot_username = bot_data['username']
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
                        reply_delay = random.uniform(3, 10)  # Increased delay
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