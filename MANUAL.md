# 3x-ui Telegram 机器人操作手册 (V2)

## 1. 概述

本机器人旨在帮助您通过 Telegram 轻松管理和监控 **多个** 3x-ui 面板。它支持多用户、多面板管理，并提供丰富的管理员功能和自动化任务。

- **管理员**: 拥有完全控制权，可以配置机器人、管理所有面板和用户，并接收自动告警。
- **普通用户**: 只能查询授权面板上，与其用户名（email）关联的节点信息。

## 2. 运行环境

- **Python**: 3.8 或更高版本
- **依赖**: 通过 `pip` 安装的所有 `requirements.txt` 中的包

## 3. 准备工作

### 3.1 获取 Telegram Bot Token

1.  在 Telegram 中搜索 `BotFather` 并开始对话。
2.  发送 `/newbot` 命令，按照提示创建一个新的机器人。
3.  创建成功后，BotFather 会提供一个 **Token**，请务必复制并妥善保管。

### 3.2 获取您的 Telegram User ID

1.  在 Telegram 中搜索 `userinfobot` 并开始对话。
2.  机器人会自动返回您的个人信息，其中包含 `Id`，这就是您的 User ID。

## 4. 首次配置 (管理员)

### 4.1 配置文件

在项目根目录手动创建 `config.yml` 文件，并参照以下格式填入您的配置：

```yaml
# 1. Telegram Bot Token，从 BotFather 获取
bot_token: "YOUR_TELEGRAM_BOT_TOKEN"

# 2. 授权用户列表
users:
  # 第一个 admin_user 将被视为超级管理员
  admin_users:
    - 123456789  # 替换为您的管理员 User ID
  # 普通用户列表 (可选)
  normal_users:
    - 987654321

# 3. 3x-ui 面板列表 (核心配置)
# 您可以在这里预先配置好所有需要管理的面板
panels:
  # "自定义面板名称": { ... }
  # 例如:
  # "我的新加坡节点":
  #   url: "http://your-panel-url.com:port"
  #   username: "your_username"
  #   password: "your_password"
  # "备用服务器":
  #   url: "http://another-panel.com:port"
  #   username: "admin"
  #   password: "password123"

```

**注意**: 旧版的 `panel_config` 字段已被废弃，请使用 `panels` 字段来管理您的面板。

### 4.2 安装依赖

```bash
pip install -r requirements.txt
```

### 4.3 运行机器人

直接在前台运行（用于调试）：
```bash
python main.py
```

为了让机器人长期稳定运行，建议使用 `nohup` 或 `tmux`/`screen` 等工具在后台运行：
```bash
nohup python main.py &
```

## 5. 功能使用

### 5.1 管理员命令

| 命令 | 参数 | 描述 |
| :--- | :--- | :--- |
| `/setting` | 无 | 通过对话式交互，新增或更新一个面板配置。 |
| `/listpanels`| 无 | 列出所有已在 `config.yml` 中配置的面板。 |
| `/delpanel` | `<面板名>` | 从配置中删除一个指定的面板。 |
| `/status` | `[面板名]` | 查看面板状态。若提供面板名，则显示该面板的详细服务器状态；否则，显示所有面板的在线状态摘要。 |
| `/adduser` | `<用户ID>` | 添加一个普通用户，授权其使用查询功能。 |
| `/deluser` | `<用户ID>` | 移除一个普通用户的授权。 |
| `/listusers` | 无 | 列出所有管理员和普通用户。 |
| `/help` | 无 | 显示帮助信息。 |

### 5.2 普通用户命令

| 命令 | 参数 | 描述 |
| :--- | :--- | :--- |
| `/query` | `<面板名> <用户名>` | 查询指定面板上，与该用户名（email）关联节点的流量使用情况和到期时间。 |
| `/help` | 无 | 显示帮助信息。 |


## 6. 自动化功能 (管理员)

机器人内置了强大的自动化任务，无需手动触发：

- **面板离线告警**: 机器人会周期性（默认为6小时）检查所有已配置面板的在线状态。如果某个面板无法连接，将立即向所有管理员发送告警信息。
- **入站到期提醒**: 机器人会自动扫描所有面板的入站列表。如果某个入站将在 **3天内** 到期，将自动向所有管理员发送提醒。

## 7. 常见问题 (FAQ)

**Q: 为什么我发送 `/query myuser` 无法查询？**
A: 因为机器人现在支持多面板管理，查询时必须明确指定要查询哪个面板。请使用正确的格式：`/query <面板名> <用户名>`。例如：`/query 我的新加坡节点 myuser`。

**Q: 机器人提示我“查询过于频繁已被暂时封禁”，这是为什么？**
A: 为了防止恶意查询和滥用，当您在短时间内（5分钟内）连续查询 **不存在的用户** 达到5次时，系统会将您暂时封禁（默认为2小时）。请检查您的用户名和面板名是否正确，然后耐心等待。

**Q: 如何让机器人一直在后台运行，即使我关闭了SSH终端？**
A: 请使用 `nohup` 命令，如 `nohup python main.py &`。或者使用 `tmux` 或 `screen` 等终端复用工具来创建一个持久化的会话。

---

*技术支持: 本手册由 Claude V2 生成并完善。*


## 8. Docker 部署 (推荐)

使用 Docker 可以极大地简化部署流程，并确保环境一致性。

### 8.1 准备工作

1.  确保您的服务器上已经安装了 [Docker](https://docs.docker.com/engine/install/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。
2.  将项目代码克隆或下载到您的服务器上。

### 8.2 配置

像手动部署一样，您需要先创建并配置 `config.yml` 文件。请参考 **[4.1 配置文件](#41-配置文件)** 部分完成配置。

### 8.3 启动机器人

在项目根目录下，执行以下命令来构建镜像并以守护进程模式（在后台）启动容器：

```bash
docker-compose up -d --build
```

### 8.4 管理机器人

-   **查看日志**:
    ```bash
    docker-compose logs -f
    ```

-   **停止并移除容器**:
    ```bash
    docker-compose down
    ```

-   **更新代码后重新部署**:
    1.  先停止旧的容器: `docker-compose down`
    2.  拉取最新的代码: `git pull`
    3.  重新构建并启动: `docker-compose up -d --build`

