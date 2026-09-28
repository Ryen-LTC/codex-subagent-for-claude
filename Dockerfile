# 仅用于目录站（如 Glama）的启动/自省检查：服务能起来、能应答 initialize 和 tools/list。
# 实际派任务需要本机已登录的 Codex，且目前只在 Windows 上验证。
FROM python:3.12-slim
WORKDIR /app
COPY server.py hook.py ./
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "server.py"]
