## ✨ 主要功能

- **多面板管理**: 在一个机器人中管理您所有的 3x-ui 面板。
- **状态监控**: 随时查看服务器状态、流量和 Xray 核心状态。
- **多渠道查询**: 支持通过 **Telegram 机器人** 和 **Web 浏览器** 两种方式进行自助查询。
- **自动化任务**:
    - 面板离线自动告警。
    - 入站节点到期自动提醒。
    - 每月自动重置所有用户流量。
- **安全可靠**: 基于角色的权限管理，区分管理员和普通用户。

---

## 🚀 快速开始 (Docker 部署 - 推荐)

这是最简单、最推荐的部署方式，只需三步即可让您的机器人运行起来。

### 第 1 步：准备环境

确保您的服务器上已经安装了 [Docker](https://docs.docker.com/engine/install/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。

### 第 2 步：下载并配置项目

1.  **克隆项目代码到您的服务器：**
    ```bash
    git clone https://github.com/GeQainZz/TgXUIMgr.git
    cd TgXUIMgr
    ```

2.  **创建并编辑配置文件：**
    复制配置文件模板：
    ```bash
    cp config.yml.example config.yml
    ```
    然后，使用 `vim` 或任何文本编辑器打开 `config.yml` 文件，填入您的信息。

    **`config.yml` 文件详解:**
    ```yaml
    # 1. Telegram Bot Token (必填)
    # 从 Telegram 的 @BotFather 获取
    bot_token: "YOUR_TELEGRAM_BOT_TOKEN"

    # 2. 授权用户 (必填)
    users:
      # 管理员的用户 ID 列表，第一个将被视为超级管理员
      admin_users:
        - 123456789  # 替换为您的 Telegram User ID

      # 普通用户的用户 ID 列表 (可选)
      normal_users:
        - 987654321

    # 3. 您的 3x-ui 面板列表 (可选，可后续通过机器人添加)
    # "自定义面板名称": { ... }
    panels:
      "我的新加坡节点":
        url: "http://your-panel-url.com:port"
        username: "your_username"
        password: "your_password"
      "备用服务器":
        url: "http://another-panel.com:port"
        username: "admin"
        password: "password123"
    ```
    > **如何获取 Telegram User ID?**
    > 在 Telegram 中搜索 `@userinfobot` 并开始对话，它会立即返回您的 User ID。

### 第 3 步：启动机器人！

在项目根目录下，执行以下命令：

```bash
docker-compose up -d --build
```

恭喜您！您的机器人和 Web 服务现在已经成功运行在后台了。

---

## 📖 使用指南

在您的服务成功运行后，您的用户可以通过以下两种方式与它交互。

### 方式一：Web 页面查询 (推荐)

这是最方便的方式，无需安装任何应用，推荐给所有用户。

1.  打开浏览器，访问 `http://<您的服务器IP>:5000`。
2.  在页面中输入“面板名称”和您的“用户名 (Email)”。
3.  点击查询，即可看到最新的流量数据。

### 方式二：Telegram Bot 查询

如果您是 Telegram 用户，可以直接与机器人对话。

#### 管理员命令

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

#### 普通用户命令

| 命令 | 参数 | 描述 |
| :--- | :--- | :--- |
| `/query` | `<面板名> <用户名>` | 查询指定面板上，与该用户名（email）关联节点的流量使用情况和到期时间。 |
| `/help` | 无 | 显示帮助信息。 |

---

## 🔧 Docker 管理

一些常用的 Docker 命令，用于管理您的机器人。

-   **查看实时日志**:
    ```bash
    docker-compose logs -f
    ```

-   **停止并移除容器**:
    ```bash
    docker-compose down
    ```

-   **更新项目后重新部署**:
    1.  先停止旧的容器: `docker-compose down`
    2.  拉取最新的代码: `git pull`
    3.  重新构建并启动: `docker-compose up -d --build`

---

## ⚙️ 手动部署 (高级)

如果您不想使用 Docker，也可以按照以下步骤手动部署。

1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **配置 `config.yml`**:
    参考上面的 Docker 部署部分，创建并配置 `config.yml` 文件。
3.  **运行机器人**:
    为了让机器人长期稳定运行，建议使用 `nohup` 或 `tmux`/`screen` 等工具在后台运行：
    ```bash
    nohup python main.py &
    ```

---

## ⁉️ 常见问题 (FAQ)

**Q: 我该如何获取我的 Telegram User ID？**
A: 在 Telegram 中搜索 `@userinfobot` 并开始对话，它会立即返回您的 User ID。

**Q: 为什么普通用户发送 `/query myuser` 无法查询？**
A: 因为机器人现在支持多面板管理，查询时必须明确指定要查询哪个面板。请使用正确的格式：`/query <面板名> <用户名>`。例如：`/query 我的新加坡节点 myuser`。

**Q: 机器人提示我“查询过于频繁已被暂时封禁”，这是为什么？**
A: 为了防止恶意查询和滥用，当您在短时间内（5分钟内）连续查询 **不存在的用户** 达到5次时，系统会将您暂时封禁（默认为2小时）。请检查您的用户名和面板名是否正确，然后耐心等待。

**Q: Web 查询页面的防刷机制是怎样的？**
A: Web 查询页面同样有防刷保护。系统会基于访客的 **IP 地址** 进行识别。如果同一个 IP 在 5 分钟内错误查询达到 5 次，该 IP 将被封禁 2 小时，以防止接口被恶意攻击。

