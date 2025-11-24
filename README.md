# 🛡️ Smart X-UI Backup Bot Manager

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

A professional, secure, and intelligent Telegram bot to manage backups for multiple **X-UI panels**.
It runs on your external server, connects to your panels (Sanaei, Alireza, Official, etc.) via API, and sends the backup files directly to your Telegram.

## ✨ Key Features

- 🚀 **Quick Installer:** One-line installation command.
- 🧠 **Smart Auto-Discovery:** Automatically detects the correct database path (`/server/getDb`, `/panel/api/...`, etc.) regardless of the X-UI version.
- 🔒 **Secure:** Restricted to the Admin's Telegram ID only. Configuration file is protected.
- 🌍 **Multi-Server:** Manage unlimited servers from a single bot.
- 🛠️ **No SSH Required:** Connects via the web panel port (HTTP/HTTPS).

---

## 📥 Quick Installation (Recommended)

Run this command on your **VPS (Ubuntu/Debian)**. The script will install Python, dependencies, and set up the system service automatically.

```bash
bash <(curl -Ls [https://raw.githubusercontent.com/yoyoraya/x-ui-backup-bot-manager/main/install.sh](https://raw.githubusercontent.com/yoyoraya/x-ui-backup-bot-manager/main/install.sh))
