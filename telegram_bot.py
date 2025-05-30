import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import json
import os
import asyncio # Added for to_thread
import requests
import paramiko

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation handler
ADD_PANEL_DOMAIN, ADD_PANEL_PORT, ADD_PANEL_USERNAME, ADD_PANEL_PASSWORD, ADD_PANEL_HTTPS, CHOOSE_PANEL_FOR_NODE, ADD_NODE_IP, ADD_NODE_PORT, ADD_NODE_USER, ADD_NODE_PASSWORD, ADD_NODE_TO_PANEL_CONFIRM = range(11)

# File to store panel data
PANEL_DATA_FILE = "marzban_panels.json"

# Helper function to load panel data
def load_panel_data():
    if os.path.exists(PANEL_DATA_FILE):
        with open(PANEL_DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

# Helper function to save panel data
def save_panel_data(data):
    with open(PANEL_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"سلام {user.mention_html()}! به ربات مدیریت نود مرزبان خوش آمدید.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        "برای شروع، یکی از دستورات زیر را انتخاب کنید:\n"
        "/add_panel - افزودن پنل مرزبان جدید\n"
        "/add_node - افزودن نود به پنل موجود\n"
        "/list_panels - نمایش پنل‌های ذخیره شده\n"
        "/cancel - لغو عملیات فعلی"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the current conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text(
        "عملیات لغو شد.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# --- Add Panel Conversation --- #
async def add_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to add a new Marzban panel."""
    await update.message.reply_text(
        "لطفاً دامنه یا IP پنل مرزبان خود را وارد کنید:"
    )
    return ADD_PANEL_DOMAIN

async def add_panel_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the panel domain and asks for the port."""
    context.user_data['panel_domain'] = update.message.text
    await update.message.reply_text(
        "لطفاً پورت پنل مرزبان را وارد کنید (مثال: 443):"
    )
    return ADD_PANEL_PORT

async def add_panel_port(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the panel port and asks for the username."""
    context.user_data['panel_port'] = update.message.text
    await update.message.reply_text(
        "لطفاً نام کاربری پنل مرزبان را وارد کنید:"
    )
    return ADD_PANEL_USERNAME

async def add_panel_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the panel username and asks for the password."""
    context.user_data['panel_username'] = update.message.text
    await update.message.reply_text(
        "لطفاً رمز عبور پنل مرزبان را وارد کنید:"
    )
    return ADD_PANEL_PASSWORD

async def add_panel_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the panel password and asks if HTTPS is used."""
    context.user_data['panel_password'] = update.message.text
    reply_keyboard = [['بله (HTTPS)'], ['خیر (HTTP)']]
    await update.message.reply_text(
        "آیا پنل شما از HTTPS استفاده می‌کند؟",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return ADD_PANEL_HTTPS

async def add_panel_https(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores HTTPS preference and saves the panel."""
    text = update.message.text
    context.user_data['panel_https'] = True if text == 'بله (HTTPS)' else False

    panel_name = f"{context.user_data['panel_domain']}:{context.user_data['panel_port']}"
    panels = load_panel_data()
    panels[panel_name] = {
        "domain": context.user_data['panel_domain'],
        "port": context.user_data['panel_port'],
        "username": context.user_data['panel_username'],
        "password": context.user_data['panel_password'],
        "https": context.user_data['panel_https']
    }
    save_panel_data(panels)

    await update.message.reply_text(
        f"پنل {panel_name} با موفقیت ذخیره شد.",
        reply_markup=ReplyKeyboardRemove(),
    )
    logger.info(f"Panel {panel_name} added by user {update.effective_user.id}")
    context.user_data.clear()
    return ConversationHandler.END

# --- List Panels --- #
async def list_panels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all saved Marzban panels."""
    panels = load_panel_data()
    if not panels:
        await update.message.reply_text("هیچ پنل مرزبانی ذخیره نشده است. با /add_panel یک پنل اضافه کنید.")
        return

    message = "پنل‌های ذخیره شده:\n"
    for name, data in panels.items():
        protocol = "HTTPS" if data.get('https', True) else "HTTP"
        message += f"- نام: {name} (پروتکل: {protocol})\n"
    
    await update.message.reply_text(message)


# --- Marzban API and SSH Logic (adapted from curlscript.py) --- #
async def get_marzban_access_token(panel_info: dict):
    """Gets access token from Marzban panel."""
    use_protocol = 'https' if panel_info['https'] else 'http'
    url = f"{use_protocol}://{panel_info['domain']}:{panel_info['port']}/api/admin/token"
    data = {
        'username': panel_info['username'],
        'password': panel_info['password']
    }
    try:
        # Run blocking requests call in a separate thread
        response = await asyncio.to_thread(requests.post, url, data=data, timeout=10)
        response.raise_for_status()
        access_token = response.json()['access_token']
        logger.info(f"Successfully obtained access token for {panel_info['domain']}")
        return access_token
    except requests.exceptions.RequestException as e:
        logger.error(f'Error obtaining access token for {panel_info["domain"]}: {e}')
        return None

async def get_marzban_cert(panel_info: dict, access_token: str):
    """Gets certificate from Marzban panel."""
    use_protocol = 'https' if panel_info['https'] else 'http'
    url = f"{use_protocol}://{panel_info['domain']}:{panel_info['port']}/api/node/settings"
    headers = {
        'accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    try:
        response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        response.raise_for_status()
        cert = response.json()["certificate"]
        logger.info(f"Successfully retrieved certificate from {panel_info['domain']}")
        return cert
    except requests.exceptions.RequestException as e:
        logger.error(f'Error retrieving certificate from {panel_info["domain"]}: {e}')
        return None

async def add_marzban_node_api(panel_info: dict, access_token: str, node_ip: str, add_as_host: bool = True):
    """Adds a node to the Marzban panel via API."""
    use_protocol = 'https' if panel_info['https'] else 'http'
    url = f"{use_protocol}://{panel_info['domain']}:{panel_info['port']}/api/node"
    node_information = {
        "name": f"{node_ip}",
        "address": f"{node_ip}",
        "port": 62050, # Default Marzban-node port
        "api_port": 62051, # Default Marzban-node API port
        "add_as_new_host": add_as_host,
        "usage_coefficient": 1
    }
    headers = {
        'accept': 'application/json',
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    try:
        response = await asyncio.to_thread(requests.post, url, json=node_information, headers=headers, timeout=15)
        response.raise_for_status()
        logger.info(f"Node {node_ip} added successfully to panel {panel_info['domain']}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f'Error adding node {node_ip} to panel {panel_info["domain"]}: {e}')
        return False

async def execute_ssh_commands_on_node(node_details: dict, cert_info: str):
    """Connects to a node via SSH and executes setup commands."""
    commands = [
        'sudo ufw disable',
        'curl -fsSL https://get.docker.com | sh',
        '[ -d Marzban-node ] && sudo rm -rf Marzban-node', # Added sudo for rm -rf
        'git clone https://github.com/Gozargah/Marzban-node',
        'cd Marzban-node && docker compose up -d && docker compose down && sudo rm docker-compose.yml', # Added sudo for rm
        # Ensure the directory exists and user has write permission, or use sudo tee
        f'echo "{cert_info}" | sudo tee /var/lib/marzban-node/ssl_client_cert.pem > /dev/null',
        'cd Marzban-node && echo \'services:\n  marzban-node:\n    image: gozargah/marzban-node:latest\n    restart: always\n    network_mode: host\n    environment:\n      SSL_CERT_FILE: "/var/lib/marzban-node/ssl_cert.pem"\n      SSL_KEY_FILE: "/var/lib/marzban-node/ssl_key.pem"\n      SSL_CLIENT_CERT_FILE: "/var/lib/marzban-node/ssl_client_cert.pem"\n    volumes:\n      - /var/lib/marzban-node:/var/lib/marzban-node\' | sudo tee docker-compose.yml > /dev/null && sudo docker compose up -d'
    ]

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    command_output = []
    try:
        def connect_and_exec():
            client.connect(node_details['ip'], port=int(node_details['port']), username=node_details['user'], password=node_details['password'], timeout=10)
            for command in commands:
                logger.info(f"Executing on {node_details['ip']}: {command}")
                stdin, stdout, stderr = client.exec_command(command, get_pty=True) # get_pty for sudo
                # Wait for command completion
                exit_status = stdout.channel.recv_exit_status()
                cmd_out = stdout.read().decode()
                cmd_err = stderr.read().decode()
                log_msg = f"CMD: {command}\nEXIT_STATUS: {exit_status}\nSTDOUT: {cmd_out}\nSTDERR: {cmd_err}"
                logger.info(log_msg)
                command_output.append(log_msg)
                if exit_status != 0:
                    logger.error(f"Command '{command}' failed on {node_details['ip']} with exit status {exit_status}.")
                    # raise Exception(f"Command failed: {command}. Error: {cmd_err}") # Optionally raise to stop further execution
                    return False # Indicate failure
            return True # Indicate success
        
        success = await asyncio.to_thread(connect_and_exec)
        return success, "\n".join(command_output)

    except Exception as e:
        logger.error(f"SSH connection or command execution failed for {node_details['ip']}: {e}")
        command_output.append(f"Error: {str(e)}")
        return False, "\n".join(command_output)
    finally:
        client.close()

# --- Add Node Conversation --- # 
async def add_node_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to add a new node to a panel."""
    panels = load_panel_data()
    if not panels:
        await update.message.reply_text(
            "ابتدا باید یک پنل مرزبان اضافه کنید. از دستور /add_panel استفاده کنید.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    reply_keyboard = [[name] for name in panels.keys()]
    await update.message.reply_text(
        "لطفاً پنلی را که می‌خواهید نود به آن اضافه شود انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return CHOOSE_PANEL_FOR_NODE

async def choose_panel_for_node(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the chosen panel and asks for node IP."""
    chosen_panel_name = update.message.text
    panels = load_panel_data()
    if chosen_panel_name not in panels:
        await update.message.reply_text(
            "پنل انتخاب شده معتبر نیست. لطفاً دوباره تلاش کنید یا عملیات را لغو کنید.",
            reply_markup=ReplyKeyboardRemove(),
        )
        # Potentially restart this step or end conversation
        return CHOOSE_PANEL_FOR_NODE # Or ConversationHandler.END
    
    context.user_data['chosen_panel'] = panels[chosen_panel_name]
    context.user_data['chosen_panel_name'] = chosen_panel_name
    await update.message.reply_text(
        f"شما پنل '{chosen_panel_name}' را انتخاب کردید.\n"
        "لطفاً IP سرور نود را وارد کنید:"
    )
    return ADD_NODE_IP

async def add_node_ip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['node_ip'] = update.message.text
    await update.message.reply_text("لطفاً پورت SSH سرور نود را وارد کنید (پیش‌فرض: 22):")
    return ADD_NODE_PORT

async def add_node_port(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    port_text = update.message.text
    context.user_data['node_port'] = port_text if port_text else '22'
    await update.message.reply_text("لطفاً نام کاربری سرور نود را وارد کنید (پیش‌فرض: root):")
    return ADD_NODE_USER

async def add_node_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_text = update.message.text
    context.user_data['node_user'] = user_text if user_text else 'root'
    await update.message.reply_text("لطفاً رمز عبور سرور نود را وارد کنید:")
    return ADD_NODE_PASSWORD

async def add_node_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['node_password'] = update.message.text
    panel_info = context.user_data['chosen_panel']
    node_details = {
        'ip': context.user_data['node_ip'],
        'port': context.user_data['node_port'],
        'user': context.user_data['node_user'],
        'password': context.user_data['node_password']
    }

    await update.message.reply_text(
        f"درحال پردازش درخواست شما برای افزودن نود {node_details['ip']} به پنل {context.user_data['chosen_panel_name']}... این عملیات ممکن است چند دقیقه طول بکشد."
    )

    # 1. Get Marzban access token
    access_token = await get_marzban_access_token(panel_info)
    if not access_token:
        await update.message.reply_text("خطا: امکان دریافت توکن دسترسی از پنل مرزبان وجود ندارد. لطفاً اطلاعات پنل را بررسی کنید.")
        context.user_data.clear()
        return ConversationHandler.END

    # 2. Get Marzban certificate
    cert_info = await get_marzban_cert(panel_info, access_token)
    if not cert_info:
        await update.message.reply_text("خطا: امکان دریافت گواهی از پنل مرزبان وجود ندارد.")
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text("گواهی با موفقیت از پنل دریافت شد. در حال اجرای دستورات روی سرور نود...")

    # 3. Execute SSH commands on the node server
    # Assuming ADD_AS_HOST is always True for simplicity, or get it from user_data if needed
    ssh_success, ssh_output = await execute_ssh_commands_on_node(node_details, cert_info)
    
    logger.info(f"SSH Execution Output for {node_details['ip']}:\n{ssh_output}")
    # You might want to send parts of ssh_output to the user for debugging or progress
    # await update.message.reply_text(f"خروجی اجرای دستورات SSH:\n```\n{ssh_output[:1000]}...\n```") # Be careful with message length

    if not ssh_success:
        await update.message.reply_text(
            f"خطا در هنگام اجرای دستورات روی سرور نود {node_details['ip']}. لطفاً لاگ‌ها را بررسی کنید.\n{ssh_output[-500:]}"
        )
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text(f"دستورات روی سرور نود {node_details['ip']} با موفقیت اجرا شدند. در حال افزودن نود به پنل مرزبان...")

    # 4. Add node to Marzban panel via API
    # Determine ADD_AS_HOST, for now, let's assume True or get from user input earlier
    add_as_host_preference = panel_info.get('add_as_new_host', True) # Example, ideally ask user or have a default
    node_added_successfully = await add_marzban_node_api(panel_info, access_token, node_details['ip'], add_as_host_preference)

    if node_added_successfully:
        await update.message.reply_text(
            f"نود {node_details['ip']} با موفقیت به پنل {context.user_data['chosen_panel_name']} اضافه شد."
        )
    else:
        await update.message.reply_text(
            f"خطا در افزودن نود {node_details['ip']} به پنل مرزبان. ممکن است سرور نود به درستی کانفیگ نشده باشد یا مشکلی در ارتباط با پنل وجود داشته باشد."
        )

    logger.info(f"Node addition process completed for {node_details['ip']} to panel {context.user_data['chosen_panel_name']}")
    context.user_data.clear()
    return ConversationHandler.END

def main() -> None:
    """Start the bot."""
    # Get the token from environment variable or replace with your bot token
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
        print("لطفاً توکن ربات تلگرام خود را در متغیر محیطی TELEGRAM_BOT_TOKEN قرار دهید.")
        return

    application = Application.builder().token(bot_token).build()

    # Conversation handler for adding a panel
    add_panel_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add_panel", add_panel_start)],
        states={
            ADD_PANEL_DOMAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_panel_domain)],
            ADD_PANEL_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_panel_port)],
            ADD_PANEL_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_panel_username)],
            ADD_PANEL_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_panel_password)],
            ADD_PANEL_HTTPS: [MessageHandler(filters.Regex('^(بله \(HTTPS\)|خیر \(HTTP\))$'), add_panel_https)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Conversation handler for adding a node
    add_node_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add_node", add_node_start)],
        states={
            CHOOSE_PANEL_FOR_NODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_panel_for_node)],
            ADD_NODE_IP: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_node_ip)],
            ADD_NODE_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_node_port)],
            ADD_NODE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_node_user)],
            ADD_NODE_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_node_password)],
            # ADD_NODE_TO_PANEL_CONFIRM will be handled after actual logic is integrated
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("list_panels", list_panels))
    application.add_handler(add_panel_conv_handler)
    application.add_handler(add_node_conv_handler)

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()