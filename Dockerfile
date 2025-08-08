# 使用官方 Python 运行时作为父镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
# 如果你的 Python 包需要编译，可以在这里添加 build-essential
# RUN apt-get update && apt-get install -y build-essential

# 复制依赖文件到工作目录
COPY requirements.txt .

# 安装项目依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有项目文件到工作目录
COPY . .

# 容器启动时执行的命令
CMD ["python", "main.py"]
