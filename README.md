# 🛡️ Smart X-UI Backup Bot Manager

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)
![backubx-ui](https://github.com/user-attachments/assets/6d674eb5-16e2-496c-82ec-2b1a709a78da)

A professional, secure, and intelligent Telegram bot to manage backups for multiple **X-UI panels**.
It runs on your external server, connects to your panels (Sanaei, Alireza, Official, etc.) via API, and sends the backup files directly to your Telegram.

## 📥 Quick Installation (Recommended)

Run this command on your **VPS (Ubuntu/Debian)**. The script will install Python, dependencies, and set up the system service automatically.

```bash
bash <(curl -Ls https://raw.githubusercontent.com/yoyoraya/x-ui-backup-bot-manager/main/install.sh) 
```
Paste the command and press Enter.

Enter your Telegram Bot Token (from @BotFather).

Enter your Numeric Chat ID (from @userinfobot).

Done! The bot is now running in the background.

## ✨ Key Features

- 🚀 **Quick Installer:** One-line installation command.
- 🧠 **Smart Auto-Discovery:** Automatically detects the correct database path (`/server/getDb`, `/panel/api/...`, etc.) regardless of the X-UI version.
- 🔒 **Secure:** Restricted to the Admin's Telegram ID only. Configuration file is protected.
- 🌍 **Multi-Server:** Manage unlimited servers from a single bot.
- 🔄 **Smart Retry:** Auto-retries failed connections (3 attempts with delay) to handle network instability.
- 🛠️ **No SSH Required:** Connects via the web panel port (HTTP/HTTPS).
-  ⏱ **Dynamic Scheduler:** Change backup intervals directly from the Bot UI (Supports **1 min** to **24 hours**).
- 🔒 **AES Encryption:** All server passwords are automatically encrypted in `servers.json` using Fernet/AES.
- ⚡ **Non-Blocking Core:** Built with `AsyncIO`. The bot never freezes, even when handling 100+ servers or connection timeouts.
- - ✏️ **Edit Server:** Update username/password easily without deleting the server.
- ⚡ **Anti-Freeze Core:** Smart timeout system prevents the bot from locking up on unresponsive servers.
- 🛡️ **HTML Protection:** Verifies SQLite header to ensure only valid database files are downloaded (prevents Login Page HTML download).

---
## 🤖 Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Show the main menu and welcome message. |
| `/add` | Add a new X-UI server (Interactive wizard). |

##Dashboard Buttons:
➕ Add Server: Add a new X-UI panel (supports Auto-Discovery).

📋 Monitoring: Check the health status (CPU/RAM/Online) of all servers.

⏱ Schedule: Change the automatic backup interval (e.g., Every 1 Hour).

🚀 Instant Backup: Trigger an immediate backup for all servers.

## ⚙️ How It Works (Smart Logic)
When you add a server using 

The bot attempts to Login using the provided credentials.

If successful, it scans multiple known API endpoints (e.g., `/server/getDb`, `/panel/api/server/getDb`, etc.).

Once it finds the correct path that returns a valid SQLite file, it saves that path for future use.

This ensures compatibility with almost all X-UI forks (Sanaei, Vaxilu, FranzKafkaYu, etc.).

## Disclaimer
This project is for educational and server management purposes. Use it responsibly.
