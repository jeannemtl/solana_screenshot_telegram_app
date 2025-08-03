#!/usr/bin/env python3

import os
import time
import base64
import requests
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image
import subprocess
import tempfile
from datetime import datetime

class ScreenshotSummarizer:
    def __init__(self, api_key, telegram_bot_token=None, telegram_chat_id=None, screenshots_dir=None):
        self.api_key = api_key
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        # macOS default screenshot location
        self.screenshots_dir = screenshots_dir or os.path.expanduser('~/Desktop')
        self.processed_files = set()
        
    def summarize_image(self, image_path):
        """Send image to Claude for summarization"""
        try:
            # Read and encode image
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Get image media type
            if image_path.lower().endswith('.png'):
                media_type = "image/png"
            elif image_path.lower().endswith(('.jpg', '.jpeg')):
                media_type = "image/jpeg"
            else:
                media_type = "image/png"  # Default
            
            # Anthropic Claude API call
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 200,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Provide a concise summary of what's shown in this screenshot. Focus on the main content, key information, or purpose."
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_data
                                    }
                                }
                            ]
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                return response.json()['content'][0]['text']
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing image: {str(e)}"
    
    def send_telegram_message(self, message):
        """Send message to Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Telegram not configured - skipping message")
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                print("Message sent to Telegram")
                return True
            else:
                print(f"Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Failed to send Telegram message: {str(e)}")
            return False
    
    def send_telegram_photo_with_summary(self, image_path, summary):
        """Send photo and summary to Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Telegram not configured - skipping photo")
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendPhoto"
            
            # Format the caption nicely
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            caption = f"*Screenshot Summary*\n\n{summary}\n\n_Captured: {timestamp}_"
            
            with open(image_path, 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': self.telegram_chat_id,
                    'caption': caption,
                    'parse_mode': 'Markdown'
                }
                
                response = requests.post(url, files=files, data=data, timeout=30)
            
            if response.status_code == 200:
                print("Photo and summary sent to Telegram")
                return True
            else:
                print(f"Telegram photo API error: {response.status_code} - {response.text}")
                # Fallback to text-only message
                return self.send_telegram_message(f"📸 *Screenshot Summary*\n\n{summary}")
                
        except Exception as e:
            print(f"Failed to send photo to Telegram: {str(e)}")
            # Fallback to text-only message
            return self.send_telegram_message(f"📸 *Screenshot Summary*\n\n{summary}")
    
    def show_notification(self, title, message):
        """Show macOS notification (optional fallback)"""
        try:
            # Clean the message to avoid AppleScript issues
            clean_message = message.replace('"', "'").replace('\n', ' ').replace('\r', ' ')
            # Limit message length
            if len(clean_message) > 100:
                clean_message = clean_message[:97] + "..."
            
            script = f'display notification "{clean_message}" with title "{title}"'
            subprocess.run(['osascript', '-e', script], check=True)
        except subprocess.CalledProcessError as e:
            print(f" Notification failed: {e}")
            # Fallback to just printing
            print(f"{title}: {message}")
    
    def save_summary(self, image_path, summary):
        """Save summary to a text file next to the image"""
        base_name = os.path.splitext(image_path)[0]
        summary_path = f"{base_name}_summary.txt"
        
        with open(summary_path, 'w') as f:
            f.write(f"Screenshot: {os.path.basename(image_path)}\n")
            f.write(f"Processed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Summary: {summary}\n")
        
        return summary_path

class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, summarizer):
        self.summarizer = summarizer
        super().__init__()
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        filepath = event.src_path
        filename = os.path.basename(filepath)
        
        # Debug: print all new files with their actual path
        print(f"🔍 New file detected: {filename}")
        print(f"📁 Full path: {repr(filepath)}")  # Show the actual characters
        
        # Check if it's a macOS screenshot - be more flexible with detection
        is_screenshot = (
            filename.lower().endswith(('.png', '.jpg', '.jpeg')) and 
            (
                'screenshot' in filename.lower() or 
                'screen shot' in filename.lower() or
                filename.startswith('Screenshot') or 
                filename.startswith('Screen Shot') or
                'CleanShot' in filename or
                # macOS default pattern: "Screenshot 2025-07-21 at..."
                (filename.startswith('.Screenshot') and 'at' in filename)
            )
        )
        
        if is_screenshot and filepath not in self.summarizer.processed_files:
            self.summarizer.processed_files.add(filepath)
            print(f"Identified as screenshot, processing...")
            # Wait for file to be written
            time.sleep(2)
            self.process_screenshot(filepath)
    
    def process_screenshot(self, filepath):
        """Process a new screenshot"""
        print(f"📸 Processing screenshot: {os.path.basename(filepath)}")
        
        # Try to find the actual file - sometimes Unicode characters cause issues
        directory = os.path.dirname(filepath)
        filename = os.path.basename(filepath)
        
        # List all files in the directory and find the closest match
        try:
            all_files = os.listdir(directory)
            matching_files = [f for f in all_files if 'Screenshot' in f and f.endswith('.png')]
            
            if matching_files:
                # Sort by modification time, get the most recent
                matching_files.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)
                actual_filepath = os.path.join(directory, matching_files[0])
                print(f"Using actual file: {matching_files[0]}")
            else:
                actual_filepath = filepath
                
        except Exception as e:
            print(f"Error finding file: {e}")
            actual_filepath = filepath
        
        # Check if file actually exists and wait if needed
        max_retries = 3
        for i in range(max_retries):
            if os.path.exists(actual_filepath) and os.path.getsize(actual_filepath) > 0:
                break
            print(f"Waiting for file to be ready... ({i+1}/{max_retries})")
            time.sleep(1)
        
        if not os.path.exists(actual_filepath):
            print(f"File not found: {actual_filepath}")
            return
            
        # Get summary from Claude
        summary = self.summarizer.summarize_image(actual_filepath)
        
        # Send to Telegram (with photo) or fallback to notification
        if not summary.startswith("Error"):
            # Try to send photo with summary to Telegram
            telegram_sent = self.summarizer.send_telegram_photo_with_summary(actual_filepath, summary)
            
            # If Telegram failed or not configured, show local notification
            if not telegram_sent:
                self.summarizer.show_notification(
                    "Screenshot Summarized", 
                    summary[:100] + "..." if len(summary) > 100 else summary
                )
        else:
            print(f"{summary}")
            # Send error to Telegram too
            self.summarizer.send_telegram_message(f"*Screenshot Processing Error*\n\n{summary}")
        
        # Save summary to file
        summary_path = self.summarizer.save_summary(actual_filepath, summary)
        print(f"Summary saved to: {os.path.basename(summary_path)}")
        print(f"Summary: {summary}\n")

def load_env_file():
    """Load environment variables from .env file if it exists"""
    env_file = '.env'
    if os.path.exists(env_file):
        print(f"Loading environment from {env_file}")
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def main():
    print("🖥️  macOS Screenshot Summarizer with Telegram")
    print("=" * 45)
    
    # Load .env file if it exists
    load_env_file()
    
    # Get credentials from environment variables
    API_KEY = os.getenv('ANTHROPIC_API_KEY')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    
    # If not in environment, prompt for them
    if not API_KEY:
        API_KEY = input("Enter your Anthropic API key: ").strip()
        if not API_KEY:
            print("Anthropic API key is required!")
            print("Get one at: https://console.anthropic.com/")
            return
    else:
        print("Anthropic API key loaded from environment")
    
    if not TELEGRAM_BOT_TOKEN:
        print("\n📱 Telegram Configuration:")
        TELEGRAM_BOT_TOKEN = input("Enter your Telegram Bot Token: ").strip() or None
    else:
        print("Telegram Bot Token loaded from environment")
        
    if not TELEGRAM_CHAT_ID:
        TELEGRAM_CHAT_ID = input("Enter your Telegram Chat ID: ").strip() or None
    else:
        print("Telegram Chat ID loaded from environment")
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("Telegram configured - summaries will be sent to your Telegram")
        # Test Telegram connection
        test_summarizer = ScreenshotSummarizer(API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        if test_summarizer.send_telegram_message("🤖 *Screenshot Summarizer Started*\n\nI'm now monitoring for screenshots!"):
            print("Telegram test message sent successfully")
        else:
            print("Telegram test failed - please check your bot token and chat ID")
    else:
        print("Telegram not configured - will use macOS notifications")
    
    # Check if Desktop exists
    screenshots_dir = os.path.expanduser('~/Desktop')
    if not os.path.exists(screenshots_dir):
        screenshots_dir = os.path.expanduser('~/')
        print(f"Desktop not found, monitoring home directory: {screenshots_dir}")
    
    print(f"\nMonitoring: {screenshots_dir}")
    print("Take a screenshot (⌘+Shift+3, ⌘+Shift+4, or ⌘+Shift+5) to test!")
    print("Press Ctrl+C to stop.\n")
    
    # Create summarizer and start monitoring
    summarizer = ScreenshotSummarizer(API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, screenshots_dir)
    
    observer = Observer()
    observer.schedule(
        ScreenshotHandler(summarizer), 
        screenshots_dir, 
        recursive=False
    )
    
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n Stopping screenshot monitor...")
        
        # Send goodbye message to Telegram
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            summarizer.send_telegram_message("👋 *Screenshot Summarizer Stopped*\n\nNo longer monitoring for screenshots.")
        
        print("👋 Goodbye!")
    
    observer.join()

if __name__ == "__main__":
    main()

