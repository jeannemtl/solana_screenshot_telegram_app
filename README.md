# Daily Screenshot NFT on Solana

Automatically creates daily NFTs from screenshots using AI summaries on Solana blockchain.

## Requirements

- macOS with Python 3.8+
- Anthropic API key for AI summaries
- Internet connection

## Installation

### 1. Setup Environment

```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Install Solana CLI

```bash
# Install Solana CLI
sh -c "$(curl -sSfL https://release.solana.com/v1.18.4/install)"

# Add to PATH
echo 'export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Verify installation
solana --version
```

### 3. Create Solana Wallet

```bash
# Generate wallet
solana-keygen new --outfile config/wallet-keypair.json

# Save the seed phrase that appears

# Configure for devnet
solana config set --keypair config/wallet-keypair.json
solana config set --url devnet

# Get free devnet SOL
solana airdrop 2
solana balance
```

### 4. Configure Environment

Create `config/.env`:

```bash
# Anthropic AI (required)
ANTHROPIC_API_KEY=your_api_key_from_console.anthropic.com

# Solana settings
SOLANA_RPC_URL=https://api.devnet.solana.com
WALLET_KEYPAIR_PATH=config/wallet-keypair.json

# Screenshot directory
SCREENSHOTS_DIR=/Users/yourusername/Desktop

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### 5. Get Anthropic API Key

1. Go to https://console.anthropic.com/
2. Sign up and create API key
3. Add to `config/.env` file

## Running

### Test Installation

```bash
# Test system components
python3 test_setup.py

# Should show "4/4 tests passed"

# Test core functionality
python3 src/simple_solana_client.py
```

### Start Monitoring

```bash
# Start screenshot monitor
python3 screenshot_monitor_solana.py

# Take a screenshot (Cmd+Shift+3 or Cmd+Shift+4)
# Watch console for processing messages
```

## How It Works

1. System monitors Desktop for new screenshots
2. AI analyzes screenshot content and generates summary
3. Summary stored in daily NFT on Solana devnet
4. Each day creates new NFT that evolves with screenshots
5. Cost: ~$0.0001 per screenshot on devnet

## File Structure

```
solana_screenshot_telegram_app/
├── config/
│   ├── .env                     # Configuration
│   └── wallet-keypair.json      # Solana wallet
├── src/
│   └── simple_solana_client.py  # Core system
├── screenshot_monitor_solana.py  # Main script
├── test_setup.py               # System test
└── requirements.txt            # Dependencies
```

## Daily Usage

```bash
# Activate environment
source venv/bin/activate

# Start monitoring
python3 screenshot_monitor_solana.py

# Take screenshots throughout day
# Each screenshot gets added to today's NFT
```

## Troubleshooting

### Common Issues

**Import errors:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Wallet errors:**
```bash
solana-keygen new --outfile config/wallet-keypair.json --force
solana airdrop 2
```

**API key missing:**
```bash
# Check config/.env has valid ANTHROPIC_API_KEY
cat config/.env
```

**File not found:**
```bash
# Check screenshot directory in config/.env
# Default: /Users/yourusername/Desktop
```

### Testing Components

```bash
# Test Solana connection
solana config get
solana balance

# Test Python imports
python3 -c "from src.simple_solana_client import SimpleSolanaScreenshotNFT; print('OK')"

# View today's NFT metadata
python3 -c "from src.simple_solana_client import SimpleSolanaScreenshotNFT; nft = SimpleSolanaScreenshotNFT(); print(nft.get_metadata_json())"
```

## Configuration Options

### Environment Variables

- `ANTHROPIC_API_KEY`: Required for AI summaries
- `SOLANA_RPC_URL`: Solana network endpoint
- `WALLET_KEYPAIR_PATH`: Path to wallet file
- `SCREENSHOTS_DIR`: Directory to monitor
- `TELEGRAM_BOT_TOKEN`: Optional notifications
- `TELEGRAM_CHAT_ID`: Optional notifications

### Screenshot Detection

Automatically detects files containing:
- "screenshot" in filename
- "Screen Shot" in filename
- Files starting with "Screenshot"
- PNG, JPG, JPEG formats

## Commands Reference

```bash
# Daily operations
source venv/bin/activate
python3 screenshot_monitor_solana.py

# System checks
python3 test_setup.py
solana balance
solana config get

# View NFT data
python3 src/simple_solana_client.py
```