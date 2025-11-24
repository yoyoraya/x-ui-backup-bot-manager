#!/bin/bash

# --- تنظیمات پروژه ---
GITHUB_REPO="https://github.com/yoyoraya/x-ui-backup-bot-manager.git"
INSTALL_DIR="/opt/xui-backup"
SERVICE_NAME="xui-backup"
SCRIPT_NAME="xuibackup.py"

# --- رنگ‌ها ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --- چک کردن دسترسی روت ---
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root (sudo).${NC}"
  exit
fi

clear
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}     X-UI BACKUP BOT - INSTALLER        ${NC}"
echo -e "${BLUE}========================================${NC}"

# 1. آپدیت و نصب پیش‌نیازها
echo -e "${YELLOW}[+] Updating system and installing dependencies...${NC}"
apt update -qq
apt install -y python3 python3-pip git -qq

# 2. دریافت فایل‌ها از گیت‌هاب
# اگر پوشه قبلا بود، پاکش میکنه و از اول میریزه که فایل‌ها تازه باشه
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}[!] Removing old directory...${NC}"
    rm -rf $INSTALL_DIR
fi

echo -e "${YELLOW}[+] Cloning repository from GitHub...${NC}"
git clone $GITHUB_REPO $INSTALL_DIR

cd $INSTALL_DIR

# --- تغییر نام فایل اصلی (طبق خواسته شما) ---
if [ -f "main.py" ]; then
    mv main.py $SCRIPT_NAME
fi

# 3. نصب کتابخانه‌های پایتون
echo -e "${YELLOW}[+] Installing Python libraries...${NC}"
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt

# 4. کانفیگ امنیتی
echo -e "${BLUE}========================================${NC}"
if [ ! -f "config.py" ]; then
    echo -e "${GREEN}Configuring Secure Bot:${NC}"
    read -p "Bot Token: " USER_TOKEN
    read -p "Admin ID: " USER_ID

    # تولید کلید رمزنگاری با پایتون
    echo -e "${YELLOW}[+] Generating Encryption Key...${NC}"
    ENC_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    cat > config.py <<EOF
BOT_TOKEN = "${USER_TOKEN}"
ADMIN_ID = ${USER_ID}
ENCRYPTION_KEY = "${ENC_KEY}"
EOF
    
    chmod 600 config.py
    echo -e "${GREEN}Config saved securely.${NC}"
else
    # اگر فایل کانفیگ هست، چک کن کلید داره یا نه. اگر نداشت اضافه کن (برای آپدیت)
    if ! grep -q "ENCRYPTION_KEY" config.py; then
        echo -e "${YELLOW}[+] Updating config with new encryption key...${NC}"
        ENC_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
        echo "" >> config.py
        echo "ENCRYPTION_KEY = \"${ENC_KEY}\"" >> config.py
    fi
    echo -e "${GREEN}Config updated.${NC}"
fi
# 5. ساخت سرویس Systemd با نام جدید
echo -e "${YELLOW}[+] Creating system service ($SERVICE_NAME)...${NC}"
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=X-UI Backup Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $SCRIPT_NAME
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# فعال‌سازی سرویس
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ INSTALLATION COMPLETE!${NC}"
echo -e "Service Name: ${YELLOW}$SERVICE_NAME${NC}"
echo -e "Folder Path:  ${YELLOW}$INSTALL_DIR${NC}"
echo -e "Main File:    ${YELLOW}$SCRIPT_NAME${NC}"
echo -e ""
echo -e "To check status: ${YELLOW}systemctl status $SERVICE_NAME${NC}"
echo -e "${BLUE}========================================${NC}"
