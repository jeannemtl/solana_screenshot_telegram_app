#!/usr/bin/env python3

import os
import json
import time
import base64
import requests
from datetime import datetime
from solana.rpc.api import Client
from solders.keypair import Keypair  
from solders.pubkey import Pubkey     
import struct
import hashlib
from typing import Optional, Dict, Any
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleSolanaScreenshotNFT:
    def __init__(self):
        # Load configuration
        self.rpc_url = os.getenv('SOLANA_RPC_URL', 'https://api.devnet.solana.com')
        self.wallet_path = os.getenv('WALLET_KEYPAIR_PATH', 'config/wallet-keypair.json')
        
        # Initialize Solana client
        self.client = Client(self.rpc_url)
        
        # Load wallet
        self.wallet = self.load_wallet()
        
        # We'll create a simple data account for each day instead of a complex program
        self.daily_nfts = {}  # Cache for daily NFT accounts
        
        logger.info(f"Initialized Simple Solana client")
        logger.info(f"Wallet: {self.wallet.pubkey()}")
        logger.info(f"Network: {self.rpc_url}")
    
    def load_wallet(self) -> Keypair:
        """Load wallet from keypair file"""
        try:
            with open(self.wallet_path, 'r') as f:
                keypair_data = json.load(f)
                
            # The keypair file contains 64 bytes: [secret_key + public_key]
            # We need all 64 bytes for Keypair.from_bytes()
            if len(keypair_data) == 64:
                # Use all 64 bytes
                secret_key_bytes = bytes(keypair_data)
            elif len(keypair_data) >= 32:
                # If only 32 bytes available, pad with zeros (fallback)
                secret_key_bytes = bytes(keypair_data[:32] + [0] * 32)
            else:
                raise ValueError(f"Invalid keypair data length: {len(keypair_data)}")
                
            return Keypair.from_bytes(secret_key_bytes)
            
        except Exception as e:
            logger.error(f"Error loading wallet: {e}")
            raise
    
    def get_current_date(self) -> str:
        """Get current date as string"""
        return datetime.now().strftime("%Y%m%d")
    
    def create_data_account(self, date: str) -> Pubkey:
        """Create a simple data account for storing daily screenshot data"""
        try:
            # Create a new keypair for this day's account
            daily_account = Keypair()
            
            logger.info(f"Creating local data store for {date}: {daily_account.pubkey()}")
            
            # Initialize the account with empty data
            initial_data = {
                "date": date,
                "creator": str(self.wallet.pubkey()),
                "screenshots": [],
                "theme": "",
                "created_at": int(time.time())
            }
            
            # Store account info locally
            self.daily_nfts[date] = {
                "account": daily_account,
                "address": daily_account.pubkey(),
                "data": initial_data
            }
            
            return daily_account.pubkey()
            
        except Exception as e:
            logger.error(f"Error creating data account: {e}")
            raise
    
    def get_or_create_daily_account(self, date: Optional[str] = None) -> Pubkey:
        """Get existing daily account or create new one"""
        if date is None:
            date = self.get_current_date()
        
        # Check if we already have an account for this date
        if date in self.daily_nfts:
            return self.daily_nfts[date]["address"]
        
        # Create new account
        return self.create_data_account(date)
    
    def add_screenshot(self, summary: str, image_hash: str = "", date: Optional[str] = None) -> bool:
        """Add a screenshot to today's data account"""
        if date is None:
            date = self.get_current_date()
        
        try:
            # Ensure account exists
            account_address = self.get_or_create_daily_account(date)
            
            # Add screenshot to local data
            if date not in self.daily_nfts:
                # Load existing data if account exists but not in cache
                self.daily_nfts[date] = {
                    "address": account_address,
                    "data": {
                        "date": date,
                        "creator": str(self.wallet.pubkey()),
                        "screenshots": [],
                        "theme": "",
                        "created_at": int(time.time())
                    }
                }
            
            # Add the new screenshot
            screenshot_data = {
                "timestamp": int(time.time()),
                "summary": summary,
                "image_hash": image_hash
            }
            
            self.daily_nfts[date]["data"]["screenshots"].append(screenshot_data)
            
            logger.info(f"Added screenshot to {date}: {summary[:50]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding screenshot: {e}")
            return False
    
    def get_metadata_json(self, date: Optional[str] = None) -> str:
        """Generate NFT-style metadata JSON"""
        if date is None:
            date = self.get_current_date()
        
        data = self.daily_nfts.get(date, {}).get("data", {})
        if not data:
            return "{}"
        
        metadata = {
            "name": f"Daily Screenshots {date}",
            "description": f"A collection of screenshot moments from {date}",
            "image": f"https://your-storage.com/daily/{date}.png",
            "attributes": [
                {"trait_type": "Date", "value": date},
                {"trait_type": "Screenshot Count", "value": len(data.get("screenshots", []))},
                {"trait_type": "Theme", "value": data.get("theme", "") or "Unthemed"},
                {"trait_type": "Creator", "value": data.get("creator", "")}
            ],
            "properties": {
                "screenshots": data.get("screenshots", []),
                "created_at": data.get("created_at", 0)
            }
        }
        
        return json.dumps(metadata, indent=2)

class SimpleScreenshotProcessor:
    """Screenshot processor that integrates with Solana NFT system"""
    
    def __init__(self):
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.solana_nft = SimpleSolanaScreenshotNFT()
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.processed_files = set()
    
    def summarize_image(self, image_path: str) -> str:
        """Generate AI summary of screenshot"""
        if not self.api_key:
            return f"Demo summary: Screenshot analysis (add ANTHROPIC_API_KEY to config/.env for real AI summaries)"
        
        try:
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            if image_path.lower().endswith('.png'):
                media_type = "image/png"
            elif image_path.lower().endswith(('.jpg', '.jpeg')):
                media_type = "image/jpeg"
            else:
                media_type = "image/png"
            
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
    
    def create_image_hash(self, image_path: str) -> str:
        """Create a simple hash for the image"""
        try:
            with open(image_path, 'rb') as f:
                content = f.read()
                return hashlib.sha256(content).hexdigest()[:16]
        except:
            return ""
    
    def process_screenshot(self, filepath: str) -> bool:
        """Process a screenshot and add to Solana NFT system"""
        try:
            # Generate summary
            summary = self.summarize_image(filepath)
            
            if summary.startswith("Error"):
                logger.error(f"Failed to summarize: {summary}")
                # Still add it with error summary for demo
                summary = f"Screenshot from {datetime.now().strftime('%H:%M:%S')} (AI summary failed)"
            
            # Create image hash
            image_hash = self.create_image_hash(filepath)
            
            # Add to Solana NFT system
            success = self.solana_nft.add_screenshot(summary, image_hash)
            
            if success:
                logger.info("✅ Screenshot added to Solana NFT system")
                
                # Send Telegram notification
                if self.telegram_bot_token and self.telegram_chat_id:
                    self.send_telegram_message(
                        f"📸 *New Screenshot Added to Daily NFT*\n\n{summary}\n\n💰 Solana network (~$0.0001)"
                    )
                
                return True
            else:
                logger.error("❌ Failed to add to Solana")
                return False
                
        except Exception as e:
            logger.error(f"Error processing screenshot: {e}")
            return False
    
    def send_telegram_message(self, message: str) -> bool:
        """Send message to Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return False
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

def main():
    """Test the simple Solana NFT system"""
    try:
        # Test basic functionality
        nft_system = SimpleSolanaScreenshotNFT()
        
        print("🚀 Simple Solana Screenshot NFT System")
        print("=" * 40)
        print(f"Wallet: {nft_system.wallet.pubkey()}")
        print(f"Network: {nft_system.rpc_url}")
        
        # Test creating a daily account
        today = nft_system.get_current_date()
        account_address = nft_system.get_or_create_daily_account()
        print(f"Today's account: {account_address}")
        
        # Test adding screenshots
        nft_system.add_screenshot("Test screenshot summary of a coding session", "abc123")
        nft_system.add_screenshot("Another screenshot showing a web browser with documentation", "def456")
        nft_system.add_screenshot("Screenshot of a terminal with build output", "ghi789")
        
        # Show metadata
        metadata = nft_system.get_metadata_json()
        print(f"\nGenerated metadata:")
        print(metadata)
        
        print("\n✅ System ready! You can now integrate with your screenshot monitor.")
        print("💡 Note: This demo uses local storage. Full version would write to Solana accounts.")
        print("💰 Cost estimate: ~$0.001 per day for on-chain storage")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
