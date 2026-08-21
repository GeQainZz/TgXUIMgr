import asyncio
import hashlib
from datetime import datetime, timedelta, date
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from functools import wraps
import config
from query_logic import query_user_data
from xui_api import XUIApi
from database import (
    get_daily_stats, get_panel_daily_stats, get_user_daily_stats,
    get_top_users, get_latest_snapshot, get_date_range,
    get_panel_user_list, init_db,
    record_query_log, get_query_logs,
)
from notify import notify_admins

app = Flask(__name__)
# Stable secret shared by all Gunicorn workers.
try:
    app.secret_key = hashlib.sha256((config.get_config().get("bot_token", "") or "tgxui-default-secret").encode("utf-8")).hexdigest()
except Exception:
    app.secret_key = "tgxui-fallback-secret-key"

init_db()

failed_web_attempts = {}
blocked_ips = {}


def is_admin_login() -> bool:
    return session.get("is_admin", False)


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_admin_login():
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapper


# --- Pages ---

@app.route('/')
def index():
    panels = config.get_all_panels()
    active_names = [n for n, c in panels.items() if not c.get("disabled", False)]
    return render_template('index.html', panel_names=active_names)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        admin_password = config.get_web_admin_password()
        if not admin_password:
            error = "管理后台密码未配置，请在 config.yml 的 web.admin_password 中设置。"
        elif password == admin_password:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = "密码错误。"
    return render_template('login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))


@app.route('/admin')
@require_admin
def admin_dashboard():
    return render_template('admin.html')


# --- Admin API: Panels ---

@app.route('/api/admin/panels', methods=['GET'])
@require_admin
def admin_get_panels():
    panels = config.get_all_panels()
    result = []
    for name, pconf in panels.items():
        result.append({
            "name": name,
            "url": pconf.get("url", ""),
            "username": pconf.get("username", ""),
            "reset_day": pconf.get("reset_day", 1),
            "disabled": bool(pconf.get("disabled", False)),
        })
    return jsonify(result)


@app.route('/api/admin/panels', methods=['POST'])
@require_admin
def admin_add_panel():
    data = request.get_json()
    name = (data or {}).get("name", "").strip()
    url = (data or {}).get("url", "").strip()
    username = (data or {}).get("username", "").strip()
    password = (data or {}).get("password", "").strip()
    reset_day = (data or {}).get("reset_day", 1)
    keep_password = (data or {}).get("keep_password", False)
    original_name = (data or {}).get("original_name", "")

    if not name or not url or not username:
        return jsonify({"error": "面板名、URL、用户名不能为空"}), 400
    if not isinstance(reset_day, int) or reset_day < 1 or reset_day > 28:
        reset_day = 1

    if keep_password and not password:
        existing = config.get_panel_config(name)
        if not existing and original_name:
            existing = config.get_panel_config(original_name)
        if existing:
            password = existing.get("password", "")
        else:
            return jsonify({"error": "新面板必须填写密码"}), 400

    if not password:
        return jsonify({"error": "密码不能为空"}), 400

    config.add_or_update_panel(name, url, username, password, reset_day=reset_day)
    return jsonify({"ok": True, "message": f"面板 '{name}' 已保存。"})


@app.route('/api/admin/panels/<name>', methods=['DELETE'])
@require_admin
def admin_delete_panel(name):
    if config.delete_panel(name):
        return jsonify({"ok": True, "message": f"面板 '{name}' 已删除。"})
    return jsonify({"error": f"未找到面板 '{name}'"}), 404


@app.route('/api/admin/panels/<name>/test', methods=['POST'])
@require_admin
def admin_test_panel(name):
    pconf = config.get_panel_config(name)
    if not pconf:
        return jsonify({"error": f"未找到面板 '{name}'"}), 404
    try:
        async def _test():
            async with XUIApi(pconf["url"], pconf["username"], pconf["password"]) as api:
                ok = await api.login()
                status = None
                if ok:
                    status = await api.get_server_status()
            return ok, status
        ok, status = asyncio.run(_test())
    except Exception as e:
        return jsonify({"error": f"连接失败: {e}"}), 500
    if ok:
        return jsonify({"ok": True, "message": "连接成功！", "status": status})
    return jsonify({"error": "连接失败，请检查凭证和面板地址。"}), 500


@app.route('/api/admin/panels/<name>/reset', methods=['POST'])
@require_admin
def admin_reset_panel(name):
    pconf = config.get_panel_config(name)
    if not pconf:
        return jsonify({"error": f"未找到面板 '{name}'"}), 404
    try:
        async def _reset():
            async with XUIApi(pconf["url"], pconf["username"], pconf["password"]) as api:
                return await api.reset_all_client_traffic()
        ok = asyncio.run(_reset())
    except Exception as e:
        return jsonify({"error": f"重置失败: {e}"}), 500
    if ok:
        notify_admins(f"✅ **{name}**: 流量重置成功！(手动重置，由 Web 后台触发)")
        return jsonify({"ok": True, "message": f"面板 '{name}' 流量已重置。"})
    notify_admins(f"❌ **{name}**: 流量重置失败！(手动重置，由 Web 后台触发)")
    return jsonify({"error": "重置失败。"}), 500


# --- Admin API: Users ---

@app.route('/api/admin/panels/<name>/disable', methods=['POST'])
@require_admin
def admin_disable_panel(name):
    if not config.get_panel_config(name):
        return jsonify({"error": f"未找到面板 '{name}'"}), 404
    config.set_panel_disabled(name, True)
    return jsonify({"ok": True, "message": f"面板 '{name}' 已禁用。"})


@app.route('/api/admin/panels/<name>/enable', methods=['POST'])
@require_admin
def admin_enable_panel(name):
    if not config.get_panel_config(name):
        return jsonify({"error": f"未找到面板 '{name}'"}), 404
    config.set_panel_disabled(name, False)
    return jsonify({"ok": True, "message": f"面板 '{name}' 已启用。"})

@app.route('/api/admin/users', methods=['GET'])
@require_admin
def admin_get_users():
    return jsonify({
        "admin_users": config.get_admin_users(),
        "normal_users": config.get_normal_users(),
    })


@app.route('/api/admin/users', methods=['POST'])
@require_admin
def admin_add_user():
    data = request.get_json()
    uid_str = str((data or {}).get("user_id", "")).strip()
    if not uid_str or not uid_str.isdigit():
        return jsonify({"error": "用户ID必须是数字"}), 400
    uid = int(uid_str)
    if config.add_normal_user(uid):
        return jsonify({"ok": True, "message": f"用户 {uid} 已添加。"})
    return jsonify({"error": f"用户 {uid} 已存在。"}), 400


@app.route('/api/admin/users/<int:uid>', methods=['DELETE'])
@require_admin
def admin_delete_user(uid):
    if config.del_normal_user(uid):
        return jsonify({"ok": True, "message": f"用户 {uid} 已删除。"})
    return jsonify({"error": f"用户 {uid} 不存在。"}), 404


# --- Admin API: Settings ---

@app.route('/api/admin/settings', methods=['GET'])
@require_admin
def admin_get_settings():
    cfg = config.get_config()
    return jsonify({
        "monthly_reset": cfg.get("monthly_reset", {}),
        "traffic": cfg.get("traffic", {"accounting_mode": "unidirectional"}),
        "daily_report": cfg.get("daily_report", {}),
        "web": {"admin_password_set": bool(cfg.get("web", {}).get("admin_password", ""))},
    })


@app.route('/api/admin/settings/monthly_reset', methods=['POST'])
@require_admin
def admin_set_monthly_reset():
    data = request.get_json()
    enabled = bool((data or {}).get("enable", False))
    cfg = config.get_config()
    cfg.setdefault("monthly_reset", {})["enable"] = enabled
    config.save_config(cfg)
    return jsonify({"ok": True, "message": f"月度重置已{'开启' if enabled else '关闭'}。"})


@app.route('/api/admin/settings/daily_report', methods=['POST'])
@require_admin
def admin_set_daily_report():
    data = request.get_json()
    enabled = bool((data or {}).get("enable", False))
    hour = int((data or {}).get("hour", 8))
    if hour < 0 or hour > 23:
        hour = 8
    cfg = config.get_config()
    cfg["daily_report"] = {"enable": enabled, "hour": hour}
    config.save_config(cfg)
    return jsonify({"ok": True, "message": "日报设置已保存。"})


@app.route("/api/admin/settings/accounting_mode", methods=["POST"])
@require_admin
def admin_set_accounting_mode():
    data = request.get_json()
    mode = (data or {}).get("mode", "unidirectional")
    if mode not in ("unidirectional", "bidirectional"):
        mode = "unidirectional"
    cfg = config.get_config()
    cfg["traffic"] = {"accounting_mode": mode}
    config.save_config(cfg)
    return jsonify({"ok": True, "message": f"统计方式已设为 {mode}。"})


# --- Admin API: Stats ---

def _date_range_for(period: str, anchor: date = None) -> tuple:
    anchor = anchor or date.today()
    if period == "day":
        start = end = anchor
    elif period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
    elif period == "month":
        start = anchor.replace(day=1)
        next_month = (anchor.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
    else:
        start = anchor - timedelta(days=29)
        end = anchor
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


@app.route('/api/admin/stats/overview')
@require_admin
def admin_stats_overview():
    end = date.today().strftime("%Y-%m-%d")
    start_30 = (date.today() - timedelta(days=29)).strftime("%Y-%m-%d")
    daily = get_daily_stats(start_30, end)
    panel_daily = get_panel_daily_stats(start_30, end)
    snapshots = get_latest_snapshot()
    panel_users = {}
    for s in snapshots:
        pn = s["panel_name"]
        if pn not in panel_users:
            panel_users[pn] = {"total_users": 0, "total_used": 0, "total_limit": 0}
        panel_users[pn]["total_users"] += 1
        panel_users[pn]["total_used"] += s["upload"] + s["download"]
        panel_users[pn]["total_limit"] += s["total_bytes"]
    db_range = get_date_range()
    return jsonify({
        "daily": daily,
        "panel_daily": panel_daily,
        "panel_summary": panel_users,
        "date_range": {"start": db_range[0] if db_range else None,
                        "end": db_range[1] if db_range else None},
    })


@app.route('/api/admin/stats/<period>')
@require_admin
def admin_stats_period(period):
    if period not in ("day", "week", "month"):
        return jsonify({"error": "统计周期无效"}), 400

    db_range = get_date_range()
    selected_date = request.args.get("date")
    if selected_date:
        try:
            anchor = date.fromisoformat(selected_date)
        except ValueError:
            return jsonify({"error": "日期格式无效，请使用 YYYY-MM-DD"}), 400
    else:
        selected_date = db_range[1] if db_range else date.today().isoformat()
        anchor = date.fromisoformat(selected_date)

    start, end = _date_range_for(period, anchor)
    daily = get_daily_stats(start, end)
    panel_daily = get_panel_daily_stats(start, end)
    panel_name = request.args.get("panel", "").strip() or None
    if panel_name:
        top = get_top_users(start, end, panel_name=panel_name, limit=20)
    else:
        top = get_top_users(start, end, limit=20)
    return jsonify({
        "selected_date": selected_date,
        "selected_panel": panel_name,
        "start": start,
        "end": end,
        "available_range": {
            "start": db_range[0] if db_range else None,
            "end": db_range[1] if db_range else None,
        },
        "daily": daily,
        "panel_daily": panel_daily,
        "top_users": top,
    })


@app.route('/api/admin/stats/panel/<name>')
@require_admin
def admin_stats_panel(name):
    period = request.args.get("period", "month")
    start, end = _date_range_for(period)
    daily = get_daily_stats(start, end, panel_name=name)
    top = get_top_users(start, end, panel_name=name, limit=20)
    user_daily = get_user_daily_stats(start, end, name, limit=500)
    return jsonify({"panel_name": name, "start": start, "end": end, "daily": daily, "top_users": top, "user_daily": user_daily})



# --- Admin Query Logs ---

@app.route('/api/admin/query_logs')
@require_admin
def admin_query_logs():
    limit = request.args.get("limit", 200, type=int)
    if limit < 1 or limit > 1000:
        limit = 200
    return jsonify(get_query_logs(limit=limit))


# --- User Query API ---

@app.route('/api/query', methods=['POST'])
def api_query():
    ip_address = request.remote_addr
    if ip_address in blocked_ips:
        unblock_time = blocked_ips[ip_address]
        if datetime.now() < unblock_time:
            remaining = unblock_time - datetime.now()
            return jsonify({"error": f"您因查询过于频繁已被暂时封禁，请在 {int(remaining.total_seconds() / 60)} 分钟后再试。"}), 429
        else:
            del blocked_ips[ip_address]
            if ip_address in failed_web_attempts:
                del failed_web_attempts[ip_address]

    data = request.get_json()
    if not data or 'panel_name' not in data or 'email' not in data:
        return jsonify({"error": "请求缺少 panel_name 或 email"}), 400

    panel_name = data['panel_name']
    email = data['email']

    try:
        success, result = asyncio.run(query_user_data(panel_name, email))
        try:
            record_query_log("web", ip_address, panel_name, email, success)
        except Exception:
            pass
        if success:
            if ip_address in failed_web_attempts:
                del failed_web_attempts[ip_address]
            return jsonify(result)
        else:
            now = datetime.now()
            if ip_address not in failed_web_attempts:
                failed_web_attempts[ip_address] = []
            failed_web_attempts[ip_address].append(now)
            five_minutes_ago = now - timedelta(minutes=5)
            failed_web_attempts[ip_address] = [
                t for t in failed_web_attempts[ip_address] if t > five_minutes_ago
            ]
            if len(failed_web_attempts[ip_address]) >= 5:
                block_duration = timedelta(hours=2)
                blocked_ips[ip_address] = now + block_duration
                del failed_web_attempts[ip_address]
                return jsonify({"error": "您因查询不存在的用户过于频繁，已被封禁2小时。"}), 429
            return jsonify({"error": result}), 404
    except Exception as e:
        print(f"Web API error: {e}")
        return jsonify({"error": "服务器内部错误，请联系管理员。"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
