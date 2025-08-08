from flask import Flask, render_template, request, jsonify
import asyncio
from datetime import datetime, timedelta
from query_logic import query_user_data

app = Flask(__name__)

# --- Web Rate Limiting ---
# 注意: 在多 worker 环境下，这个内存中的状态不是共享的。
# 对于简单的防刷，这通常足够了。
# 对于更严格的速率限制，需要使用 Redis 或 Memcached 等外部存储。
failed_web_attempts = {}
blocked_ips = {}

@app.route('/')
def index():
    """渲染主查询页面"""
    return render_template('index.html')

@app.route('/api/query', methods=['POST'])
def api_query():
    """处理来自 Web 的流量查询请求"""
    ip_address = request.remote_addr

    # 1. 检查 IP 是否被封禁
    if ip_address in blocked_ips:
        unblock_time = blocked_ips[ip_address]
        if datetime.now() < unblock_time:
            remaining_time = unblock_time - datetime.now()
            return jsonify({"error": f"您因查询过于频繁已被暂时封禁，请在 {int(remaining_time.total_seconds() / 60)} 分钟后再试。"}), 429
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
        
        if success:
            # 2. 查询成功，清除错误记录
            if ip_address in failed_web_attempts:
                del failed_web_attempts[ip_address]
            return jsonify(result)
        else:
            # 3. 查询失败，记录错误并检查是否需要封禁
            now = datetime.now()
            if ip_address not in failed_web_attempts:
                failed_web_attempts[ip_address] = []
            
            failed_web_attempts[ip_address].append(now)
            
            # 清理5分钟前的旧记录
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
        print(f"Web API 查询时发生错误: {e}")
        return jsonify({"error": "服务器内部错误，请联系管理员。"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)


