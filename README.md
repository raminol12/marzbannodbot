# MarzbanNode

اسکریپتی برای افزودن آسان سرورها به عنوان نود در پنل مرزبان تنها با یک دستور ساده!

## راه‌اندازی ربات تلگرام

این پروژه اکنون به عنوان یک ربات تلگرام برای مدیریت آسان‌تر نودهای مرزبان شما عمل می‌کند.

### پیش‌نیازها

- پایتون 3.8 یا بالاتر
- توکن ربات تلگرام (از BotFather دریافت کنید)

### مراحل نصب و اجرا

1.  **کلون کردن پروژه (در صورت نیاز):**
    ```bash
    git clone https://github.com/raminol12/marzbannodbot.git
    cd marzbannodbot
    ```

2.  **نصب وابستگی‌ها:**
    فایل `requirements.txt` شامل تمام کتابخانه‌های پایتون مورد نیاز است. آن‌ها را با دستور زیر نصب کنید:
    ```bash
    pip install -r requirements.txt
    ```

3.  **تنظیم توکن ربات:**
    توکن ربات تلگرام خود را به عنوان یک متغیر محیطی با نام `TELEGRAM_BOT_TOKEN` تنظیم کنید. برای مثال در لینوکس یا macOS:
    ```bash
    export TELEGRAM_BOT_TOKEN="YOUR_ACTUAL_BOT_TOKEN"
    ```
    در ویندوز (Command Prompt):
    ```cmd
    set TELEGRAM_BOT_TOKEN=YOUR_ACTUAL_BOT_TOKEN
    ```
    یا در PowerShell:
    ```powershell
    $env:TELEGRAM_BOT_TOKEN="YOUR_ACTUAL_BOT_TOKEN"
    ```
    **مهم:** `YOUR_ACTUAL_BOT_TOKEN` را با توکن واقعی ربات خود جایگزین کنید.

4.  **اجرای ربات:**
    پس از تنظیم توکن، ربات را با دستور زیر اجرا کنید:
    ```bash
    python telegram_bot.py
    ```

پس از اجرا، می‌توانید با ربات خود در تلگرام تعامل داشته باشید و از دستورات `/start`، `/add_panel` و `/add_node` استفاده کنید.

## حمایت مالی

اگر این پروژه برای شما مفید بوده است، می‌توانید از طریق آدرس‌های زیر از ما حمایت کنید:

- تتر (TRC20): `TKqV6MWsdcrGPXVK5DL2eTYz339Psp3Zwp`
- بیتکوین (BSC BEP20): `0x4f19f5071bc49833c4cd9c1e646c03db195c9ffe`
