import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
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
ADD_PANEL_DOMAIN, ADD_PANEL_PORT, ADD_PANEL_USERNAME, ADD_PANEL_PASSWORD, ADD_PANEL_HTTPS, CHOOSE_PANEL_FOR_NODE, ADD_NODE_IP, ADD_NODE_PORT, ADD_NODE_USER, ADD_NODE_PASSWORD, ADD_NODE_TO_PANEL_CONFIRM, EDIT_PANEL_CHOICE, EDIT_PANEL_FIELD, EDIT_PANEL_NEW_VALUE, DELETE_NODE_PANEL_CHOICE, DELETE_NODE_CHOICE = range(16) # Added new states

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

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str = "عملیات با موفقیت انجام شد. گزینه مورد نظر را انتخاب کنید:"):
    """Displays the main menu with inline keyboard."""
    keyboard = [
        [InlineKeyboardButton("افزودن پنل جدید", callback_data='add_panel')],
        [InlineKeyboardButton("افزودن نود جدید", callback_data='add_node')],
        [InlineKeyboardButton("لیست پنل‌ها", callback_data='list_panels')],
        # [InlineKeyboardButton("ویرایش پنل", callback_data='edit_panel_start')], # Placeholder for future
        # [InlineKeyboardButton("حذف نود", callback_data='delete_node_start')], # Placeholder for future
        [InlineKeyboardButton("لغو", callback_data='cancel_operation')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query: # If called from a callback query, edit the message
        await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup)
    else: # If called from a command, send a new message
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued and shows the main menu."""
    user = update.effective_user
    await update.message.reply_html(
        rf"سلام {user.mention_html()}! به ربات مدیریت نود مرزبان خوش آمدید.",
        reply_markup=ReplyKeyboardRemove(), # Remove any previous reply keyboard
    )
    await show_main_menu(update, context, "گزینه مورد نظر را انتخاب کنید:")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the current conversation and shows the main menu."""
    user = update.effective_user
    logger.info("User %s canceled the conversation.", user.first_name)
    
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text="عملیات لغو شد.")
    else:
        await update.message.reply_text(
            "عملیات لغو شد.", reply_markup=ReplyKeyboardRemove()
        )
    
    # Show main menu after cancellation
    # We need a way to send a new message if the original message for the menu was from a command
    # For now, let's assume we always want to send a new message for the menu after cancel
    # This might need adjustment based on how `show_main_menu` is called from `cancel`
    # A simple way is to just call start again, or a dedicated function to show menu via new message
    
    # To avoid issues with context when cancelling from different states, 
    # we send a new message for the main menu.
    # A new update object is simulated for show_main_menu to send a new message.
    class MockMessage:
        async def reply_text(self, text, reply_markup):
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
    
    class MockUpdate:
        def __init__(self, effective_chat):
            self.message = MockMessage()
            self.callback_query = None # Ensure it sends a new message
            self.effective_chat = effective_chat

    mock_update = MockUpdate(update.effective_chat)
    await show_main_menu(mock_update, context, "گزینه مورد نظر را انتخاب کنید:")

    context.user_data.clear()
    return ConversationHandler.END

# --- Add Panel Conversation --- #
async def add_panel_start_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text="لطفاً دامنه یا IP پنل مرزبان خود را وارد کنید:")
    else:
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
    await show_main_menu(update, context) # Show main menu
    return ConversationHandler.END

# --- List Panels --- #
async def list_panels_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
    
    panels = load_panel_data()
    if not panels:
        message_text = "هیچ پنل مرزبانی ذخیره نشده است. با دکمه 'افزودن پنل جدید' یک پنل اضافه کنید."
        if query:
            await query.edit_message_text(text=message_text)
        else:
            await update.message.reply_text(message_text)
        await show_main_menu(update, context, "گزینه مورد نظر را انتخاب کنید:") # Show main menu even if no panels
        return

    message = "پنل‌های ذخیره شده:\n"
    for name, data in panels.items():
        protocol = "HTTPS" if data.get('https', True) else "HTTP"
        message += f"- نام: {name} (پروتکل: {protocol})\n"
    
    if query:
        await query.edit_message_text(text=message)
    else:
        await update.message.reply_text(message)
    await show_main_menu(update, context, "گزینه مورد نظر را انتخاب کنید:") # Show main menu


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
        'sudo apt-get update && sudo apt-get install -y curl git', # Ensure curl and git are installed
        # Check if docker group exists, if not create it. Then add user to docker group.
        # This might require a session restart for the group changes to take effect for non-sudo docker commands.
        # However, we will continue to use sudo for docker commands to ensure they run.
        f"getent group docker || sudo groupadd docker",
        f"sudo usermod -aG docker {node_details['user']}", 
        # The following command attempts to apply group changes immediately for the current session.
        # This is shell-specific and might not work as expected in all environments or with paramiko.
        # 'newgrp docker || true', # This command replaces the current shell, which can be problematic.
                                 # It's safer to rely on sudo for docker commands throughout the script.

        'curl -fsSL https://get.docker.com | sudo sh', # Ensure Docker is installed with sudo
        # Ensure Marzban-node directory can be removed and re-cloned
        'cd /tmp && sudo rm -rf Marzban-node', # Operate in /tmp to avoid permission issues in home dir, and ensure sudo for rm
        'cd /tmp && git clone https://github.com/Gozargah/Marzban-node',
        'cd /tmp/Marzban-node && sudo docker compose up -d && sudo docker compose down && sudo rm -f docker-compose.yml', # Ensure sudo for docker and rm
        # Ensure the directory exists and user has write permission, or use sudo tee
        'sudo mkdir -p /var/lib/marzban-node', # Ensure directory exists
        f'echo "{cert_info}" | sudo tee /var/lib/marzban-node/ssl_client_cert.pem > /dev/null',
        'cd /tmp/Marzban-node && echo \'services:\n  marzban-node:\n    image: gozargah/marzban-node:latest\n    restart: always\n    network_mode: host\n    environment:\n      SSL_CERT_FILE: "/var/lib/marzban-node/ssl_cert.pem"\n      SSL_KEY_FILE: "/var/lib/marzban-node/ssl_key.pem"\n      SSL_CLIENT_CERT_FILE: "/var/lib/marzban-node/ssl_client_cert.pem"\n    volumes:\n      - /var/lib/marzban-node:/var/lib/marzban-node\' | sudo tee docker-compose.yml > /dev/null && sudo docker compose up -d'
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
async def add_node_start_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()

    panels = load_panel_data()
    if not panels:
        message_text = "ابتدا باید یک پنل مرزبان اضافه کنید. از دکمه 'افزودن پنل جدید' استفاده کنید."
        if query:
            await query.edit_message_text(text=message_text, reply_markup=None) # Remove keyboard if any
        else:
            await update.message.reply_text(message_text, reply_markup=ReplyKeyboardRemove())
        await show_main_menu(update, context, "گزینه مورد نظر را انتخاب کنید:")
        return ConversationHandler.END

    # Using InlineKeyboardMarkup for panel selection
    keyboard = [[InlineKeyboardButton(name, callback_data=f"select_panel_for_node_{name}")] for name in panels.keys()]
    keyboard.append([InlineKeyboardButton("لغو", callback_data='cancel_operation')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "لطفاً پنلی را که می‌خواهید نود به آن اضافه شود انتخاب کنید:"
    if query:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    return CHOOSE_PANEL_FOR_NODE

async def choose_panel_for_node(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the chosen panel and asks for node IP."""
    query = update.callback_query
    await query.answer()
    
    chosen_panel_name = query.data.replace("select_panel_for_node_", "")
    panels = load_panel_data()

    if chosen_panel_name not in panels:
        await query.edit_message_text(
            text="پنل انتخاب شده معتبر نیست. لطفاً دوباره تلاش کنید."
        )
        # Go back to panel selection or show main menu
        # For simplicity, let's reshow panel selection
        keyboard = [[InlineKeyboardButton(name, callback_data=f"select_panel_for_node_{name}")] for name in panels.keys()]
        keyboard.append([InlineKeyboardButton("لغو", callback_data='cancel_operation')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("لطفاً پنلی را که می‌خواهید نود به آن اضافه شود انتخاب کنید:", reply_markup=reply_markup)
        return CHOOSE_PANEL_FOR_NODE
    
    context.user_data['chosen_panel'] = panels[chosen_panel_name]
    context.user_data['chosen_panel_name'] = chosen_panel_name
    await query.edit_message_text(
        text=f"شما پنل '{chosen_panel_name}' را انتخاب کردید.\n"
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


# --- Main Application Setup --- #
def main() -> None:
    """Start the bot.""" # Check if TELEGRAM_BOT_TOKEN is set
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("متغیر محیطی TELEGRAM_BOT_TOKEN تنظیم نشده است!")
        return

    application = Application.builder().token(bot_token).build()

    # Conversation handler for adding a panel
    add_panel_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_panel_start_wrapper, pattern='^add_panel$'), CommandHandler("add_panel", add_panel_start_wrapper)],
        states={
            ADD_PANEL_DOMAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_panel_domain)],
            ADD_PANEL_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_panel_port)],
            ADD_PANEL_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_panel_username)],
            ADD_PANEL_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_panel_password)],
            ADD_PANEL_HTTPS: [MessageHandler(filters.Regex('^(بله \(HTTPS\)|خیر \(HTTP\))$'), add_panel_https)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(cancel, pattern='^cancel_operation$')],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END # Propagate END to parent if nested
        }
    )

    # Conversation handler for adding a node
    add_node_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_node_start_wrapper, pattern='^add_node$'), CommandHandler("add_node", add_node_start_wrapper)],
        states={
            CHOOSE_PANEL_FOR_NODE: [CallbackQueryHandler(choose_panel_for_node, pattern='^select_panel_for_node_.*$')],
            ADD_NODE_IP: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_node_ip)],
            ADD_NODE_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_node_port)],
            ADD_NODE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_node_user)],
            ADD_NODE_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_node_password)],
            ADD_NODE_TO_PANEL_CONFIRM: [MessageHandler(filters.Regex('^(بله|خیر|yes|no)$'), add_node_to_panel_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(cancel, pattern='^cancel_operation$')],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END
        }
    )
    
    # Main conversation handler to manage top-level menu and sub-conversations
    # This is a simplified approach. For complex menus, a different structure might be better.
    # For now, we'll use individual handlers for commands/callbacks from the main menu.

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start)) # Alias help to start
    application.add_handler(CallbackQueryHandler(cancel, pattern='^cancel_operation$')) # General cancel from inline kbd

    application.add_handler(add_panel_conv_handler)
    application.add_handler(add_node_conv_handler)
    application.add_handler(CallbackQueryHandler(list_panels_wrapper, pattern='^list_panels$'))
    application.add_handler(CommandHandler("list_panels", list_panels_wrapper))

    # Fallback for unknown commands/callbacks if needed
    # application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    # application.add_handler(CallbackQueryHandler(unknown_callback))

    logger.info("Bot started and polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
