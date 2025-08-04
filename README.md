 # Screenshot Summarizer

Automatically summarizes macOS screenshots using Claude AI and sends them to Telegram.

## Features

- **Auto-detects** new screenshots on macOS
- **AI-powered summaries** using Claude 3.5 Sonnet
- **Telegram integration** - sends screenshot + summary to your chat
- **Local backup** - saves summaries as text files
- **Real-time monitoring** of Desktop folder

## Setup

### 1. Install Dependencies

```bash
pip install requests watchdog Pillow beautifulsoup4 easyocr
```

### 2. Get API Keys

- **Anthropic API Key**: Get from [console.anthropic.com](https://console.anthropic.com/)
- **Telegram Bot**: 
  1. Message @BotFather on Telegram
  2. Send `/newbot` and follow prompts
  3. Save the bot token
- **Chat ID**: 
  1. Message your bot first
  2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
  3. Find your chat ID in the response

### 3. Configure Environment

```bash
# Copy example file
cp .env.example .env

# Edit .env with your actual API keys
nano .env
```

### 4. Run

```bash
# Load environment variables
source .env

# Start the summarizer
python3 screenshot_tg.py
```

## Usage

1. **Start the script** - it will monitor your Desktop folder
2. **Take a screenshot** (⌘+Shift+3, ⌘+Shift+4, or ⌘+Shift+5)
3. **Receive summary** in your Telegram chat with the screenshot image
4. **Stop with** Ctrl+C

## Files

- `screenshot_summarizer.py` - Main script
- `.env` - Your API keys (not committed to git)
- `.env.example` - Template for environment variables
- `*_summary.txt` - Local backup of summaries

## Security

- API keys are stored in `.env` file (excluded from git)
- Never commit real API keys to version control
- Copy `.env.example` to `.env` and add your real keys

## Requirements

- macOS (for screenshot detection)
- Python 3.6+
- Telegram account
- Anthropic API access

