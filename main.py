import logging
from functools import wraps
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)

import config
from xui_api import XUIApi

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Rate Limiting ---
failed_query_attempts = {}
blocked_users = {}



# --- Helper Functions ---
def _format_bytes(size: int) -> str:
    """Helper function to format bytes into KB, MB, GB, etc."""
    if size is None: return "N/A"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power and n < len(power_labels) -1:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"


# --- Decorators ---
def authorized(func):
    """Decorator to check if a user is authorized."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not config.is_authorized(update.effective_user.id):
            await update.message.reply_text("抱歉，您没有权限使用此机器人。")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def admin_only(func):
    """Decorator to check if a user is an admin."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not config.is_admin(update.effective_user.id):
            await update.message.reply_text("抱歉，此命令仅限管理员使用。")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


# --- Bot Handlers ---
@authorized
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message."""
    user = update.effective_user
    await update.message.reply_html(
        rf"你好, {user.mention_html()}! "
        f"欢迎使用 3x-ui 面板管理机器人。请使用 /help 查看可用命令。",
    )

@authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the help message based on user role."""
    if config.is_admin(update.effective_user.id):
        help_text = (
            "**✨ 管理员命令:**\n"
            "/start - 🚀 开始与机器人交互\n"
            "/help - ℹ️ 显示此帮助信息\n"
            "/setting - ⚙️ 新增或更新面板\n"
            "/delpanel <名称> - 🗑️ 删除指定名称的面板\n"
            "/listpanels - 📋 列出所有已配置的面板\n"
            "/status <名称> - 📊 查看指定面板的状态 (不带名称则看全部)\n"
            "/adduser <ID> - ✅ 添加普通用户\n"
            "/deluser <ID> - ❌ 删除普通用户\n"
            "/listusers - 👥 列出所有授权用户"
        )
    else:
        help_text = (
            "**👋 用户命令:**\n"
            "/start - 🚀 开始与机器人交互\n"
            "/help - ℹ️ 显示此帮助信息\n"
            "/query <面板名> <用户名> - 🔍 查询节点信息"
        )
    await update.message.reply_text(help_text, parse_mode='Markdown')

@admin_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays the server status."""
    panel_name = context.args[0] if context.args else None
    
    if not panel_name:
        all_panels = config.get_all_panels()
        if not all_panels:
            await update.message.reply_text("未配置任何面板，请使用 /setting 命令进行配置。")
            return
        
        status_messages = ["**所有面板状态概览:**"]
        for name, panel_config in all_panels.items():
            api = XUIApi(panel_config["url"], panel_config["username"], panel_config["password"])
            status = await api.get_server_status()
            if status and 'xray' in status:
                xray_status = status['xray'].get('state', 'N/A')
                status_messages.append(f"- **{name}**: {xray_status.capitalize()}")
            else:
                status_messages.append(f"- **{name}**: `连接失败`")
        
        await update.message.reply_text("\n".join(status_messages), parse_mode='Markdown')
        return

    panel_config = config.get_panel_config(panel_name)
    if not panel_config:
        await update.message.reply_text(f"未找到名为 '{panel_name}' 的面板配置。")
        return

    api = XUIApi(panel_config["url"], panel_config["username"], panel_config["password"])
    await update.message.reply_text(f"正在获取 '{panel_name}' 的服务器状态，请稍候...")
    
    status = await api.get_server_status()
    if status and 'cpu' in status and 'mem' in status and 'disk' in status:
        # ... (rest of the status formatting is the same)
        # CPU
        cpu_percent = status.get('cpu', 0)

        # Memory
        mem = status.get('mem', {})
        mem_current = mem.get('current', 0)
        mem_total = mem.get('total', 0)
        mem_percent = (mem_current / mem_total * 100) if mem_total > 0 else 0

        # Disk
        disk = status.get('disk', {})
        disk_current = disk.get('current', 0)
        disk_total = disk.get('total', 0)
        disk_percent = (disk_current / disk_total * 100) if disk_total > 0 else 0

        # Network Traffic
        net_traffic = status.get('netTraffic', {})
        net_sent = net_traffic.get('sent', 0)
        net_recv = net_traffic.get('recv', 0)

        # Uptime
        uptime_seconds = status.get('uptime', 0)
        uptime_delta = timedelta(seconds=uptime_seconds)
        days = uptime_delta.days
        hours, rem = divmod(uptime_delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        uptime_str = f"{days}天 {hours}小时 {minutes}分钟"

        # Xray status
        xray = status.get('xray', {})
        xray_status = xray.get('state', 'N/A')
        xray_version = xray.get('version', 'N/A')

        status_text = (
            f"**面板 {panel_name} 状态**\n"
            f"- Xray 版本: `{xray_version}`\n"
            f"- Xray 状态: **{xray_status.capitalize()}**\n\n"
            f"**服务器状态**\n"
            f"- CPU: {cpu_percent:.2f}%\n"
            f"- 内存: {_format_bytes(mem_current)} / {_format_bytes(mem_total)} ({mem_percent:.2f}%)\n"
            f"- 硬盘: {_format_bytes(disk_current)} / {_format_bytes(disk_total)} ({disk_percent:.2f}%)\n"
            f"- 运行时间: {uptime_str}\n\n"
            f"**网络状态**\n"
            f"- 上传流量: {_format_bytes(net_sent)}\n"
            f"- 下载流量: {_format_bytes(net_recv)}"
        )
        await update.message.reply_text(status_text, parse_mode='Markdown')
    else:
        await update.message.reply_text(f"无法获取 '{panel_name}' 的完整服务器状态，请检查面板连接或稍后再试。")


@authorized
async def query_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows users to query their inbound status by username (email)."""
    user_id = update.effective_user.id

    # Check if user is blocked
    if user_id in blocked_users:
        unblock_time = blocked_users[user_id]
        if datetime.now() < unblock_time:
            remaining_time = unblock_time - datetime.now()
            await update.message.reply_text(f"您因查询过于频繁已被暂时封禁，请在 {int(remaining_time.total_seconds() / 60)} 分钟后再试。")
            return
        else:
            # Unblock user if time is up
            del blocked_users[user_id]
            if user_id in failed_query_attempts:
                del failed_query_attempts[user_id]

    if len(context.args) < 2:
        await update.message.reply_text("请提供面板名称和用户名进行查询，格式: /query <面板名> <用户名>")
        return

    panel_name, query_user = context.args[0], context.args[1]
    panel_config = config.get_panel_config(panel_name)
    if not panel_config:
        await update.message.reply_text(f"未找到名为 '{panel_name}' 的面板配置。")
        return

    api = XUIApi(panel_config["url"], panel_config["username"], panel_config["password"])
    await update.message.reply_text(f"正在在 '{panel_name}' 上查询中，请稍候...")
    
    inbounds_data = await api.get_inbounds()
    if not inbounds_data or not inbounds_data.get("success"):
        await update.message.reply_text("无法从面板获取数据，请稍后再试。")
        return

    found_inbound = None
    for inbound in inbounds_data.get("obj", []):
        clients = inbound.get("clientStats", [])
        for client in clients:
            if client.get("email") == query_user:
                found_inbound = client
                found_inbound.update({
                    'total': client.get('total', inbound.get('total', 0)),
                    'expiryTime': client.get('expiryTime', inbound.get('expiryTime', 0))
                })
                break
        if found_inbound:
            break

    if found_inbound:
        if user_id in failed_query_attempts:
            del failed_query_attempts[user_id]
        used_gb = (found_inbound.get("up", 0) + found_inbound.get("down", 0)) / (1024**3)
        total_gb = found_inbound.get("total", 0) / (1024**3)
        expiry_ts = found_inbound.get("expiryTime", 0)
        expiry_date = datetime.fromtimestamp(expiry_ts / 1000).strftime('%Y-%m-%d') if expiry_ts > 0 else "永不过期"

        used_gb_double = float(used_gb) * 2
        total_gb_double = float(total_gb) * 2
        reply_text = (
            f"**用户 {query_user} 在 '{panel_name}' 的节点信息:**\n"
            f"- 流量: {used_gb_double:.2f} GB / {total_gb_double:.2f} GB\n"
            f"- 到期时间: {expiry_date}"
        )
        await update.message.reply_text(reply_text, parse_mode='Markdown')
    else:
        await update.message.reply_text(f"在 '{panel_name}' 上未找到用户名为 '{query_user}' 的节点。")
        now = datetime.now()
        if user_id not in failed_query_attempts:
            failed_query_attempts[user_id] = []

        failed_query_attempts[user_id].append(now)
        five_minutes_ago = now - timedelta(minutes=5)
        failed_query_attempts[user_id] = [
            t for t in failed_query_attempts[user_id] if t > five_minutes_ago
        ]

        if len(failed_query_attempts[user_id]) >= 5:
            block_duration = timedelta(hours=2)
            blocked_users[user_id] = now + block_duration
            await update.message.reply_text("您因查询不存在的用户过于频繁，已被封禁2小时。")
            del failed_query_attempts[user_id]

@admin_only
async def adduser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a normal user."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("使用格式: /adduser <用户ID>")
        return
    
    user_id_to_add = int(context.args[0])
    current_config = config.get_config()

    # Ensure normal_users is a list before access
    if current_config.get("users") is None:
        current_config["users"] = {}
    if current_config["users"].get("normal_users") is None:
        current_config["users"]["normal_users"] = []
    
    if user_id_to_add in current_config["users"]["normal_users"]:
        await update.message.reply_text(f"用户 {user_id_to_add} 已经存在。")
        return
        
    current_config["users"]["normal_users"].append(user_id_to_add)
    config.save_config(current_config)
    await update.message.reply_text(f"✅ 普通用户 {user_id_to_add} 添加成功！")

@admin_only
async def deluser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes a normal user."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("使用格式: /deluser <用户ID>")
        return
        
    user_id_to_del = int(context.args[0])
    current_config = config.get_config()

    # Ensure normal_users is a list before access
    if current_config.get("users") is None:
        current_config["users"] = {}
    if current_config["users"].get("normal_users") is None:
        current_config["users"]["normal_users"] = []
    
    if user_id_to_del not in current_config["users"]["normal_users"]:
        await update.message.reply_text(f"用户 {user_id_to_del} 不存在。")
        return
        
    current_config["users"]["normal_users"].remove(user_id_to_del)
    config.save_config(current_config)
    await update.message.reply_text(f"🗑️ 普通用户 {user_id_to_del} 已删除。")

@admin_only
async def listusers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all authorized users."""
    admin_users = config.get_admin_users()
    normal_users = config.get_normal_users()
    
    message = "**授权用户列表**\n\n"
    message += "**管理员:**\n"
    for user_id in admin_users:
        message += f"- `{user_id}`\n"
    
    message += "\n**普通用户:**\n"
    if not normal_users:
        message += "无"
    else:
        for user_id in normal_users:
            message += f"- `{user_id}`\n"
            
    await update.message.reply_text(message, parse_mode='Markdown')

@admin_only
async def delpanel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes a panel configuration."""
    if not context.args:
        await update.message.reply_text("使用格式: /delpanel <面板名>")
        return

    panel_name = context.args[0]
    if config.delete_panel(panel_name):
        await update.message.reply_text(f"🗑️ 面板 '{panel_name}' 已被成功删除。")
    else:
        await update.message.reply_text(f"未找到名为 '{panel_name}' 的面板。")

@admin_only
async def listpanels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all configured panels."""
    all_panels = config.get_all_panels()
    if not all_panels:
        await update.message.reply_text("当前未配置任何面板。")
        return

    message = "**已配置的面板列表:**\n\n"
    for name, panel_config in all_panels.items():
        message += f"- **{name}**: `{panel_config['url']}`\n"

    await update.message.reply_text(message, parse_mode='Markdown')


# --- Settings Conversation ---
# ...
# In main():
# application.add_handler(CommandHandler("adduser", adduser_command))
# application.add_handler(CommandHandler("deluser", deluser_command))
# application.add_handler(CommandHandler("listusers", listusers_command))

SET_NAME, SET_URL, SET_USERNAME, SET_PASSWORD = range(4)

@admin_only
async def setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to set panel config."""
    await update.message.reply_text("请输入要添加或更新的面板名称:")
    return SET_NAME

async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['panel_name'] = update.message.text.strip()
    await update.message.reply_text("请输入您的 3x-ui 面板 URL:")
    return SET_URL

async def set_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['panel_url'] = update.message.text.strip()
    await update.message.reply_text("请输入面板登录用户名:")
    return SET_USERNAME

async def set_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['panel_username'] = update.message.text.strip()
    await update.message.reply_text("请输入面板登录密码:")
    return SET_PASSWORD

async def set_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['panel_password'] = update.message.text.strip()
    
    name, url, username, password = context.user_data['panel_name'], context.user_data['panel_url'], context.user_data['panel_username'], context.user_data['panel_password']
    await update.message.reply_text("正在尝试连接面板...")

    api = XUIApi(url, username, password)
    if await api.login():
        current_config = config.get_config()
        if 'panels' not in current_config:
            current_config['panels'] = {}
        current_config['panels'][name] = {"url": url, "username": username, "password": password}
        config.save_config(current_config)
        await update.message.reply_text(f"✅ 面板 '{name}' 连接成功！配置已保存。")
    else:
        await update.message.reply_text("❌ 连接失败！请检查凭证后使用 /setting 重试。")
    return ConversationHandler.END

async def cancel_setting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("设置已取消。")
    return ConversationHandler.END


# --- Scheduled Jobs ---
async def check_inbounds_job(context: ContextTypes.DEFAULT_TYPE):
    """A recurring job to check for expiring inbounds and panel status."""
    logger.info("Running scheduled job: check_inbounds_job")
    all_panels = config.get_all_panels()
    if not all_panels:
        logger.warning("Job skipped: No panels are configured.")
        return

    admin_users = config.get_admin_users()

    for name, panel_config in all_panels.items():
        logger.info(f"Checking panel: {name}")
        api = XUIApi(panel_config["url"], panel_config["username"], panel_config["password"])

        if not await api.login():
            logger.error(f"Panel '{name}' connection failed. Sending alert.")
            for user_id in admin_users:
                await context.bot.send_message(chat_id=user_id, text=f"🚨 **面板 '{name}' 离线告警**", parse_mode='Markdown')
            continue # Skip to the next panel

        inbounds_data = await api.get_inbounds()
        if inbounds_data and inbounds_data.get("success"):
            three_days_later = (datetime.now() + timedelta(days=3)).timestamp() * 1000
            for inbound in inbounds_data.get("obj", []):
                expiry_ts = inbound.get("expiryTime", 0)
                if 0 < expiry_ts < three_days_later:
                    expiry_date = datetime.fromtimestamp(expiry_ts / 1000).strftime('%Y-%m-%d')
                    message = f"🔔 **入站到期提醒 ({name})** 🔔\n- 备注: {inbound.get('remark', 'N/A')}\n- 将于: {expiry_date} 到期"
                    for user_id in admin_users:
                        await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')



def main() -> None:
    """Start the bot."""
    bot_token = config.get_bot_token()
    if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("Bot token not configured in config.yml.")
        return

    application = Application.builder().token(bot_token).build()

    # --- Job Queue ---
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_inbounds_job, interval=timedelta(hours=6), first=timedelta(seconds=10))
    else:
        logger.warning("JobQueue not initialized. Periodic checks will not run. "
                       "Install with 'pip install \"python-telegram-bot[job-queue]\"' to enable.")

    # --- Handlers ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("setting", setting_start)],
        states={
            SET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name)],
            SET_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_url)],
            SET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_username)],
            SET_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel_setting)],
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("query", query_command))
    application.add_handler(CommandHandler("adduser", adduser_command))
    application.add_handler(CommandHandler("deluser", deluser_command))
    application.add_handler(CommandHandler("listusers", listusers_command))
    application.add_handler(CommandHandler("delpanel", delpanel_command))
    application.add_handler(CommandHandler("listpanels", listpanels_command))


    logger.info("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
