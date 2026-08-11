import logging
import subprocess
import sys
from functools import wraps
from datetime import datetime, timedelta, time
from telegram import Update, BotCommand
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
from database import init_db, batch_record_traffic, get_daily_stats, get_panel_daily_stats, get_top_users

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Init database on startup
init_db()

# --- Rate Limiting ---
failed_query_attempts = {}
blocked_users = {}


# --- Helper Functions ---
def _format_bytes(size: int) -> str:
    if size is None:
        return "N/A"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power and n < len(power_labels) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"


def _bytes_to_gb(size: int) -> float:
    return round(size / (1024 ** 3), 2)


# --- Decorators ---
def authorized(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not config.is_authorized(update.effective_user.id):
            await update.message.reply_text("抱歉，您没有权限使用此机器人。")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def admin_only(func):
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
    user = update.effective_user
    await update.message.reply_html(
        rf"你好, {user.mention_html()}! "
        f"欢迎使用 3x-ui 面板管理机器人。请使用 /help 查看可用命令。",
    )


@authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if config.is_admin(update.effective_user.id):
        help_text = (
            "**✨ 管理员命令:**\n"
            "/start - 🚀 开始与机器人交互\n"
            "/help - ℹ️ 显示此帮助信息\n"
            "/setting - ⚙️ 新增或更新面板\n"
            "/delpanel <名称> - 🗑️ 删除指定名称的面板\n"
            "/listpanels - 📋 列出所有已配置的面板\n"
            "/status <名称> - 📊 查看面板状态 (不带名称则看全部)\n"
            "/adduser <ID> - ✅ 添加普通用户\n"
            "/deluser <ID> - ❌ 删除普通用户\n"
            "/listusers - 👥 列出所有授权用户\n"
            "/setresetday <面板名> <日期> - 🔧 设置面板流量重置日(1-28)\n"
            "/report - 📈 立即发送今日日报\n"
            "/resetpanel <面板名> - ⚡️ 立即重置指定面板流量"
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
    panel_name = context.args[0] if context.args else None

    if not panel_name:
        all_panels = config.get_all_panels()
        if not all_panels:
            await update.message.reply_text("未配置任何面板，请使用 /setting 命令进行配置。")
            return

        status_messages = ["**所有面板状态概览:**"]
        for name, panel_config in all_panels.items():
            if panel_config.get("disabled", False):
                status_messages.append(f"- **{name}**: `已禁用`")
                continue
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
        cpu_percent = status.get('cpu', 0)
        mem = status.get('mem', {})
        mem_current = mem.get('current', 0)
        mem_total = mem.get('total', 0)
        mem_percent = (mem_current / mem_total * 100) if mem_total > 0 else 0
        disk = status.get('disk', {})
        disk_current = disk.get('current', 0)
        disk_total = disk.get('total', 0)
        disk_percent = (disk_current / disk_total * 100) if disk_total > 0 else 0
        net_traffic = status.get('netTraffic', {})
        net_sent = net_traffic.get('sent', 0)
        net_recv = net_traffic.get('recv', 0)
        uptime_seconds = status.get('uptime', 0)
        uptime_delta = timedelta(seconds=uptime_seconds)
        days = uptime_delta.days
        hours, rem = divmod(uptime_delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        uptime_str = f"{days}天 {hours}小时 {minutes}分钟"
        xray = status.get('xray', {})
        xray_status = xray.get('state', 'N/A')
        xray_version = xray.get('version', 'N/A')

        reset_day = config.get_panel_reset_day(panel_name)
        reset_info = f"- 流量重置日: 每月{reset_day}号" if reset_day else "- 流量重置日: 每月1号 (默认)"

        status_text = (
            f"**面板 {panel_name} 状态**\n"
            f"- Xray 版本: `{xray_version}`\n"
            f"- Xray 状态: **{xray_status.capitalize()}**\n\n"
            f"**服务器状态**\n"
            f"- CPU: {cpu_percent:.2f}%\n"
            f"- 内存: {_format_bytes(mem_current)} / {_format_bytes(mem_total)} ({mem_percent:.2f}%)\n"
            f"- 硬盘: {_format_bytes(disk_current)} / {_format_bytes(disk_total)} ({disk_percent:.2f}%)\n"
            f"- 运行时间: {uptime_str}\n"
            f"{reset_info}\n\n"
            f"**网络状态**\n"
            f"- 上传流量: {_format_bytes(net_sent)}\n"
            f"- 下载流量: {_format_bytes(net_recv)}"
        )
        await update.message.reply_text(status_text, parse_mode='Markdown')
    else:
        await update.message.reply_text(f"无法获取 '{panel_name}' 的完整服务器状态，请检查面板连接或稍后再试。")


from query_logic import query_user_data


@authorized
async def query_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if user_id in blocked_users:
        unblock_time = blocked_users[user_id]
        if datetime.now() < unblock_time:
            remaining_time = unblock_time - datetime.now()
            await update.message.reply_text(
                f"您因查询过于频繁已被暂时封禁，请在 {int(remaining_time.total_seconds() / 60)} 分钟后再试。")
            return
        else:
            del blocked_users[user_id]
            if user_id in failed_query_attempts:
                del failed_query_attempts[user_id]

    if len(context.args) < 2:
        await update.message.reply_text("请提供面板名称和用户名进行查询，格式: /query <面板名> <用户名>")
        return

    panel_name, query_user = context.args[0], context.args[1]
    await update.message.reply_text(f"正在在 '{panel_name}' 上查询中，请稍候...")

    success, result = await query_user_data(panel_name, query_user)

    if success:
        if user_id in failed_query_attempts:
            del failed_query_attempts[user_id]
        accounting_mode = config.get_accounting_mode()
        used_gb = result['used_gb']
        total_gb = result['total_gb']
        if accounting_mode == "bidirectional":
            try:
                used_gb = float(used_gb) * 2
                total_gb = float(total_gb) * 2
            except (ValueError, TypeError):
                pass
        try:
            used_gb_formatted = f"{float(used_gb):.2f}"
            total_gb_formatted = f"{float(total_gb):.2f}"
        except (ValueError, TypeError):
            used_gb_formatted = used_gb
            total_gb_formatted = total_gb

        reply_text = (
            f"**用户 {result['email']} 在 '{result['panel_name']}' 的节点信息:**\n"
            f"- 流量: {used_gb_formatted} GB / {total_gb_formatted} GB\n"
            f"- 到期时间: {result['expiry_date']}"
        )
        await update.message.reply_text(reply_text, parse_mode='Markdown')
    else:
        await update.message.reply_text(result)
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
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("使用格式: /adduser <用户ID>")
        return
    user_id_to_add = int(context.args[0])
    if config.add_normal_user(user_id_to_add):
        await update.message.reply_text(f"✅ 普通用户 {user_id_to_add} 添加成功！")
    else:
        await update.message.reply_text(f"用户 {user_id_to_add} 已经存在。")


@admin_only
async def deluser_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("使用格式: /deluser <用户ID>")
        return
    user_id_to_del = int(context.args[0])
    if config.del_normal_user(user_id_to_del):
        await update.message.reply_text(f"🗑️ 普通用户 {user_id_to_del} 已删除。")
    else:
        await update.message.reply_text(f"用户 {user_id_to_del} 不存在。")


@admin_only
async def listusers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_users = config.get_admin_users()
    normal_users = config.get_normal_users()
    message = "**授权用户列表**\n\n**管理员:**\n"
    for uid in admin_users:
        message += f"- `{uid}`\n"
    message += "\n**普通用户:**\n"
    if not normal_users:
        message += "无"
    else:
        for uid in normal_users:
            message += f"- `{uid}`\n"
    await update.message.reply_text(message, parse_mode='Markdown')


@admin_only
async def delpanel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    all_panels = config.get_all_panels()
    if not all_panels:
        await update.message.reply_text("当前未配置任何面板。")
        return
    message = "**已配置的面板列表:**\n\n"
    for name, pconf in all_panels.items():
        reset_day = pconf.get("reset_day", "1 (默认)")
        disabled_tag = " ⛔已禁用" if pconf.get("disabled", False) else ""
        message += f"- **{name}**{disabled_tag}: `{pconf['url']}`\n  重置日: 每月{reset_day}号\n"
    await update.message.reply_text(message, parse_mode='Markdown')


@admin_only
async def setresetday_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set per-panel traffic reset day."""
    if len(context.args) < 2:
        await update.message.reply_text("使用格式: /setresetday <面板名> <日期(1-28)>")
        return
    panel_name = context.args[0]
    try:
        day = int(context.args[1])
    except ValueError:
        await update.message.reply_text("日期必须是1-28之间的整数。")
        return
    if day < 1 or day > 28:
        await update.message.reply_text("日期必须在1到28之间。")
        return
    panel_config = config.get_panel_config(panel_name)
    if not panel_config:
        await update.message.reply_text(f"未找到面板 '{panel_name}'。")
        return
    config.add_or_update_panel(
        panel_name, panel_config["url"], panel_config["username"],
        panel_config["password"], reset_day=day
    )
    await update.message.reply_text(f"✅ 面板 '{panel_name}' 的流量重置日已设为每月{day}号。")


@admin_only
async def resetpanel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually reset traffic for a specific panel."""
    if not context.args:
        await update.message.reply_text("使用格式: /resetpanel <面板名>")
        return
    panel_name = context.args[0]
    panel_config = config.get_panel_config(panel_name)
    if not panel_config:
        await update.message.reply_text(f"未找到面板 '{panel_name}'。")
        return
    await update.message.reply_text(f"正在重置 '{panel_name}' 的流量...")
    api = XUIApi(panel_config["url"], panel_config["username"], panel_config["password"])
    initiator = update.effective_user
    init_name = initiator.full_name or initiator.username or str(initiator.id)
    success = await api.reset_all_client_traffic()
    if success:
        await update.message.reply_text(f"✅ 面板 '{panel_name}' 流量重置成功！")
        msg = f"✅ **{panel_name}**: 流量重置成功！(手动重置，由 {init_name} 触发)"
    else:
        await update.message.reply_text(f"❌ 面板 '{panel_name}' 流量重置失败！")
        msg = f"❌ **{panel_name}**: 流量重置失败！(手动重置，由 {init_name} 触发)"
    # Broadcast the result to other admins (the issuer already got the reply above)
    for uid in config.get_admin_users():
        if uid == update.effective_user.id:
            continue
        try:
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to notify admin {uid}: {e}")


# --- Settings Conversation ---
SET_NAME, SET_URL, SET_USERNAME, SET_PASSWORD = range(4)


@admin_only
async def setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    name = context.user_data['panel_name']
    url = context.user_data['panel_url']
    username = context.user_data['panel_username']
    password = context.user_data['panel_password']
    await update.message.reply_text("正在尝试连接面板...")

    api = XUIApi(url, username, password)
    if await api.login():
        config.add_or_update_panel(name, url, username, password)
        await update.message.reply_text(f"✅ 面板 '{name}' 连接成功！配置已保存。")
    else:
        await update.message.reply_text("❌ 连接失败！请检查凭证后使用 /setting 重试。")
    return ConversationHandler.END


async def cancel_setting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("设置已取消。")
    return ConversationHandler.END


# --- Scheduled Jobs ---
async def record_traffic_job(context: ContextTypes.DEFAULT_TYPE):
    """Daily job: snapshot all panels' client traffic into the database."""
    logger.info("Running scheduled job: record_traffic_job")
    all_panels = config.get_all_panels()
    if not all_panels:
        logger.warning("record_traffic_job skipped: no panels configured.")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    records = []
    for name, pconf in all_panels.items():
        if pconf.get("disabled", False):
            continue
        api = XUIApi(pconf["url"], pconf["username"], pconf["password"])
        clients = await api.get_all_clients()
        for c in clients:
            if not c["email"]:
                continue
            records.append((name, c["email"], c["up"], c["down"],
                            c["total"], c["expiryTime"], today))
    batch_record_traffic(records)
    logger.info(f"Recorded {len(records)} traffic entries for {today}.")


async def _generate_daily_report_text() -> str:
    """Build the daily traffic report message from the database."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    # Use yesterday's data for the report (full day)
    stats = get_daily_stats(yesterday, yesterday)
    panel_stats = get_panel_daily_stats(yesterday, yesterday)
    top_users = get_top_users(yesterday, yesterday, limit=10)

    total_upload = sum(s["total_upload"] for s in stats)
    total_download = sum(s["total_download"] for s in stats)
    total_traffic = total_upload + total_download

    lines = [
        f"📊 **每日流量日报 ({yesterday})**\n",
        f"**总用量**: {_bytes_to_gb(total_traffic)} GB",
        f"  - 上传: {_bytes_to_gb(total_upload)} GB",
        f"  - 下载: {_bytes_to_gb(total_download)} GB\n",
    ]

    if panel_stats:
        lines.append("**各面板用量:**")
        for ps in panel_stats:
            lines.append(f"  - {ps['panel_name']}: {_bytes_to_gb(ps['daily_total'])} GB")
        lines.append("")

    if top_users:
        lines.append("**Top 10 用户:**")
        for i, u in enumerate(top_users, 1):
            lines.append(f"  {i}. {u['email']} ({u['panel_name']}): {_bytes_to_gb(u['total_usage'])} GB")

    return "\n".join(lines)


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    """Send a daily traffic report to all admins."""
    logger.info("Running scheduled job: daily_report_job")
    if not config.is_daily_report_enabled():
        logger.info("Daily report is disabled, skipping.")
        return

    report_text = await _generate_daily_report_text()
    admin_users = config.get_admin_users()
    for uid in admin_users:
        try:
            await context.bot.send_message(chat_id=uid, text=report_text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send report to {uid}: {e}")


@admin_only
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger a daily report."""
    report_text = await _generate_daily_report_text()
    await update.message.reply_text(report_text, parse_mode='Markdown')


async def check_inbounds_job(context: ContextTypes.DEFAULT_TYPE):
    """Check for expiring inbounds and panel status."""
    logger.info("Running scheduled job: check_inbounds_job")
    all_panels = config.get_all_panels()
    if not all_panels:
        logger.warning("Job skipped: No panels are configured.")
        return
    admin_users = config.get_admin_users()
    for name, pconf in all_panels.items():
        if pconf.get("disabled", False):
            continue
        api = XUIApi(pconf["url"], pconf["username"], pconf["password"])
        if not await api.login():
            logger.error(f"Panel '{name}' connection failed. Sending alert.")
            for uid in admin_users:
                await context.bot.send_message(chat_id=uid, text=f"🚨 **面板 '{name}' 离线告警**", parse_mode='Markdown')
            continue
        inbounds_data = await api.get_inbounds()
        if inbounds_data and inbounds_data.get("success"):
            three_days_later = (datetime.now() + timedelta(days=3)).timestamp() * 1000
            for inbound in inbounds_data.get("obj", []):
                expiry_ts = inbound.get("expiryTime", 0)
                if 0 < expiry_ts < three_days_later:
                    expiry_date = datetime.fromtimestamp(expiry_ts / 1000).strftime('%Y-%m-%d')
                    message = f"🔔 **入站到期提醒 ({name})** 🔔\n- 备注: {inbound.get('remark', 'N/A')}\n- 将于: {expiry_date} 到期"
                    for uid in admin_users:
                        await context.bot.send_message(chat_id=uid, text=message, parse_mode='Markdown')


async def traffic_reset_job(context: ContextTypes.DEFAULT_TYPE):
    """Check each panel individually for its reset day and reset if needed."""
    logger.info("Running scheduled job: traffic_reset_job")
    all_panels = config.get_all_panels()
    if not all_panels:
        return
    admin_users = config.get_admin_users()
    today = datetime.now()
    for name, pconf in all_panels.items():
        if pconf.get("disabled", False):
            continue
        reset_day = config.get_panel_reset_day(name)
        if reset_day is None:
            # global monthly reset check
            if not config.is_monthly_reset_enabled():
                continue
            reset_day = 1
        if today.day != reset_day:
            continue
        logger.info(f"Resetting traffic for panel '{name}' on day {reset_day}.")
        api = XUIApi(pconf["url"], pconf["username"], pconf["password"])
        if await api.reset_all_client_traffic():
            msg = f"✅ **{name}**: 流量重置成功！(重置日: {reset_day}号)"
            logger.info(f"Successfully reset traffic for panel: {name}")
        else:
            msg = f"❌ **{name}**: 流量重置失败！"
            logger.error(f"Failed to reset traffic for panel: {name}")
        for uid in admin_users:
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode='Markdown')


async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "🚀 开始与机器人交互"),
        BotCommand("help", "ℹ️ 获取帮助信息"),
        BotCommand("query", "🔍 查询节点信息 (用户)"),
        BotCommand("setting", "⚙️ 新增或更新面板 (管理员)"),
        BotCommand("status", "📊 查看面板状态 (管理员)"),
        BotCommand("listpanels", "📋 列出所有面板 (管理员)"),
        BotCommand("delpanel", "🗑️ 删除指定面板 (管理员)"),
        BotCommand("adduser", "✅ 添加普通用户 (管理员)"),
        BotCommand("deluser", "❌ 删除普通用户 (管理员)"),
        BotCommand("listusers", "👥 列出所有用户 (管理员)"),
        BotCommand("setresetday", "🔧 设置面板重置日 (管理员)"),
        BotCommand("resetpanel", "⚡️ 重置面板流量 (管理员)"),
        BotCommand("report", "📈 发送今日日报 (管理员)"),
    ]
    await application.bot.set_my_commands(commands)


def run_web_app():
    logger.info("Starting web application with Gunicorn...")
    command = ["gunicorn", "--workers", "2", "--timeout", "120", "--bind", "0.0.0.0:5000", "webapp:app"]
    try:
        subprocess.Popen(command)
        logger.info("Web application started successfully.")
    except FileNotFoundError:
        logger.error("Gunicorn not found.")
        sys.exit(1)


def main() -> None:
    bot_token = config.get_bot_token()
    if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("Bot token not configured in config.yml.")
        return

    application = Application.builder().token(bot_token).build()
    application.post_init = post_init

    run_web_app()

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_inbounds_job, interval=timedelta(hours=6), first=timedelta(seconds=10))
        job_queue.run_daily(record_traffic_job, time=time(hour=23, minute=50))
        report_hour = config.get_daily_report_hour()
        job_queue.run_daily(daily_report_job, time=time(hour=report_hour, minute=0))
        job_queue.run_daily(traffic_reset_job, time=time(hour=0, minute=5))
    else:
        logger.warning("JobQueue not initialized.")

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
    application.add_handler(CommandHandler("setresetday", setresetday_command))
    application.add_handler(CommandHandler("resetpanel", resetpanel_command))
    application.add_handler(CommandHandler("report", report_command))

    logger.info("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
