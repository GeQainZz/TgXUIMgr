# 3x-ui Telegram 机器人操作手册

## 1. 概述

本机器人旨在帮助您通过 Telegram 轻松管理和监控 3x-ui 面板。它分为两种用户角色：

- **管理员**: 拥有完全控制权，可以配置机器人、管理面板和用户。
- **普通用户**: 只能查询与其用户名（email）关联的节点信息。

## 2. 准备工作

### 2.1 获取 Telegram Bot Token

1.  在 Telegram 中搜索 `BotFather` 并开始对话。
2.  发送 `/newbot` 命令，按照提示？创建一个新的机器人。
3.  创建成功后，BotFather 会提供一个 **Token**，请务必复制并妥善保管它。

### 2.2 获取您的 Telegram User ID

1.  在 Telegram 中搜索 `userinfobot` 并开始对话。
2.  机器人会自动返回您的个人信息，其中包含 `Id`，这就是您的 User ID。

## 3. 首次配置 (管理员)

### 3.1 配置文件

项目需要一个 `config.yml` 文件来存储核心配置。请在项目根目录手动创建此文件，并填入以下内容：

```yaml
# Telegram Bot Token，从 BotFather 获取
bot_token: "YOUR_TELEGRAM_BOT_TOKEN"

# 授权用户列表
# admin_users 中填写的第一个用户 ID 将被视为超级管理员
users:
  admin_users:
    - 123456789  # 替换为您的管理员 User ID
  
  # 普通用户列表 (可选)
  # normal_users:
  #   - 987654321

# 3x-ui 面板连接配置 (首次运行时可留空)
panel_config:
  url: ""
  username: ""
  password: ""
```

### 3.2 安装依赖

在您的服务器或本地环境中，运行以下命令安装所需的 Python 包：

```bash
pip install -r requirements.txt
```

### 3.3 运行机器人

```bash
python main.py
```

### 3.4 配置面板连接

1.  在 Telegram 中找到您的机器人并开始对话。
2.  作为管理员，您会看到一个“设置面板”的按钮，或者可以发送 `/setting` 命令。
3.  按照机器人的引导，依次输入 3x-ui 面板的 **URL**、**用户名**和**密码**。
4.  配置完成后，机器人将尝试连接面板并确认状态。

## 4. 功能使用

### 4.1 管理员命令

- `/start` - 初始化机器人并显示主菜单。
- `/help` - 获取帮助信息。
- `/setting` - 进入设置菜单，配置面板连接。
- `/status` - 查看服务器和面板的实时状态。
- `/adduser <UserID>` - 添加一个普通用户。
- `/deluser <UserID>` - 删除一个普通用户。
- `/listusers` - 列出所有已授权的用户。

### 4.2 如何授权普通用户

1.  让需要被授权的用户在 Telegram 中搜索 `userinfobot`，获取他自己的 **User ID**。
2.  管理员向机器人发送命令: `/adduser <用户的User ID>` (例如: `/adduser 987654321`)。
3.  添加成功后，该用户即可开始使用机器人的查询功能。

### 4.3 普通用户命令
- `/start` - 初始化机器人并显示主菜单。
- `/help` - 获取帮助信息。
- `/query <用户名>` - 查询与指定用户名（即入站 `email`）关联的节点信息，例如：`/query myuser`。机器人将返回该节点的剩余流量和到期时间。

---

*技术支持: 本手册由 Claude 生成。*
