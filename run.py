import requests
import random
import time
import os
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
        Fore.CYAN + "=======================  J.W.P.A  ==========================",
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

def main():
    clear_screen()
    print_banner()
    
    # Get user inputs
    channel_id = input(Fore.CYAN + "Enter Channel ID: ")
    send_delay_min = int(input(Fore.CYAN + "Set Minimum Message Send Delay (seconds): "))
    send_delay_max = int(input(Fore.CYAN + "Set Maximum Message Send Delay (seconds): "))
    
    # Countdown
    print(Fore.YELLOW + "\nStarting in:")
    for i in range(3, 0, -1):
        print(Fore.YELLOW + str(i))
        time.sleep(1)
    
    clear_screen()
    print_banner()
    
    # Read messages and token
    try:
        with open("messages.txt", "r", encoding='utf-8') as f:
            words = f.readlines()
        with open("token.txt", "r", encoding='utf-8') as f:
            authorization = f.readline().strip()
    except FileNotFoundError as e:
        log_message(f"File not found: {str(e)}", "ERROR")
        return
    
    # Main loop
    while True:
        try:
            # Send message
            payload = {
                'content': random.choice(words).strip()
            }
            headers = {
                'Authorization': authorization
            }
            
            r = requests.post(
                f"https://discord.com/api/v9/channels/{channel_id}/messages",
                data=payload,
                headers=headers
            )
            
            if r.status_code == 200:
                log_message(f"Message sent: {payload['content']}", "SUCCESS")
            else:
                log_message(f"Failed to send message: {r.status_code}", "ERROR")
            
            # Random delay before next message
            delay = random.uniform(send_delay_min, send_delay_max)
            log_message(f"Waiting {delay:.1f} seconds before next message", "INFO")
            time.sleep(delay)
            
        except Exception as e:
            log_message(f"An error occurred: {str(e)}", "ERROR")
            time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_message("\nProgram stopped by user", "WARNING")
