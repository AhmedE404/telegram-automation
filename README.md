# Telegram Automation Suite

A modular Python automation framework that monitors Telegram channels and executes automated browser actions upon receiving targeted messages.

---

## Prerequisites

- Python 3.10+
- Telegram account
- Telegram API credentials (`API_ID`, `API_HASH`)
- Google Chrome installed

---

## Obtaining Telegram API Credentials

This is a one-time configuration for the project:

1. Log in to [my.telegram.org](https://my.telegram.org) using your phone number.
2. Navigate to **API development tools**.
3. Create a new application by specifying an **App title** and **Short name**.
4. Copy the generated credentials:
   - `App api_id` (Integer)
   - `App api_hash` (String)

> Important: Keep these credentials private. Never commit them to version control.

---

## Installation and Configuration

### 1. Environment Variables

Create a `.env` file from the provided template:

```bash
cp .env.example .env
```

Define the required parameters in `.env`:

```env
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
```

Refer to `.env.example` for all optional configuration options.

### 2. Set Up Virtual Environment (Recommended)

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows (Command Prompt / PowerShell)
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Running the Application

Launch the application:

```bash
python3 main.py
```

By default (`APP_MODE=production`), running `python3 main.py` immediately starts the configured automations (`link_sniper`) automatically in unattended mode.

### Execution Modes and CLI Flags

- **Automatic Mode (`APP_MODE=production`, default):** Running `python3 main.py` connects and starts listening for events immediately without prompts.
- **Interactive Menu (`APP_MODE=local` or `--menu`):** Running `python3 main.py --menu` displays the interactive selection menu.

Available CLI commands:

```bash
python3 main.py            # Automatically start Link Sniper (default)
python3 main.py --menu     # Open the interactive selection menu
python3 main.py --login    # Open Google Account authentication tool directly
python3 main.py --sniper   # Start Link Sniper directly
```

---

## Google Account Authentication (One-time Setup)

To allow browser automations to operate with your authenticated Google account:

1. Run `python3 main.py --login` (or select Option 2 from the menu).
2. A Chrome browser window will open at `accounts.google.com`.
3. Complete the login process, including any two-factor authentication (2FA).
4. Return to the terminal and press `Enter`.
5. Session data and cookies will be stored persistently in `browser_profile/`.

All subsequent runs of `main.py` will automatically reuse this authenticated profile.

---

## Telegram Session Authentication

On the initial run of `main.py --sniper`, the Telethon client will prompt for your phone number:

```text
Please enter your phone (or bot token):
```

Enter your phone number using the standard international format without spaces or dashes:

```text
+[country code][full phone number]
```

Examples:
- Egypt: `+201012345678`
- Saudi Arabia: `+966501234567`
- UAE: `+971501234567`

After providing your phone number, enter the verification code sent via Telegram. The session is saved to `session/` and will not require re-authentication.

---

## Project Structure

```text
telegram-automation/
├── .env                          # Local environment variables (not committed)
├── .env.example                  # Environment configuration template
├── requirements.txt              # Project dependencies
├── main.py                       # Application entry point and CLI runner
├── README.md                     # Technical documentation
│
├── tools/
│   ├── __init__.py
│   └── login_google.py           # Interactive Google authentication helper
│
├── config/
│   └── settings.py               # Centralized configuration and environment loader
│
├── core/
│   ├── client.py                 # Telethon client instance (singleton)
│   └── logger.py                 # Standardized logging configuration
│
├── integrations/
│   └── browser.py                # Chromium/DrissionPage driver and resilience engine
│
├── automations/
│   └── link_sniper/              # Google subscription link sniping module
│       ├── __init__.py
│       ├── config.py             # Channel IDs, regex patterns, and selectors
│       └── handler.py            # Event listener and claim logic
│
├── browser_profile/              # Persistent browser profile and cookies (gitignored)
└── session/                      # Persistent Telethon session data (gitignored)
```

---

## Adding a New Automation

1. Create a module directory under `automations/`:
   ```text
   automations/my_automation/
   ├── __init__.py
   ├── config.py
   └── handler.py
   ```

2. Implement the standard interface in `handler.py`:
   ```python
   from telethon import TelegramClient, events

   async def on_startup(client: TelegramClient) -> None:
       """Optional coroutine executed once after the client connects."""
       pass

   def register(client: TelegramClient) -> None:
       """Registers Telethon event handlers."""
       @client.on(events.NewMessage(...))
       async def _handler(event):
           pass
   ```

3. Register the automation in `main.py`:
   ```python
   from automations.my_automation import handler as my_automation

   AUTOMATION_REGISTRY = {
       "link_sniper": link_sniper,
       "my_automation": my_automation,
   }
   ```
   Add its name to `ACTIVE_AUTOMATIONS` in `.env` (e.g. `ACTIVE_AUTOMATIONS=link_sniper,my_automation`) to have it run automatically in production mode.

---

## Best Practices and Operational Guidelines

- **Testing:** Verify automation logic on private test channels prior to production deployment.
- **Channel Targeting:** Set `TARGET_CHANNEL` in `.env`. Supports private channel IDs with `-100` prefix (e.g., `-1001234567890`) or public usernames (e.g., `@channel_username`).
- **Bot Detection:** Maintain `BROWSER_HEADLESS=false` when interacting with Google services to minimize anti-automation flags.
- **Data Persistence:** Do not remove the `session/` or `browser_profile/` directories while processes are active.
