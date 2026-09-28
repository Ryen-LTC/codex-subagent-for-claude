#!/usr/bin/env python3
"""
不依赖 Codex 的握手测试：启动 server.py，验证 initialize / tools/list / ping 能正常应答。
用于 CI 和目录站的自省检查；真实派发见 smoke.py。
"""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    env = dict(os.environ, CODEX_SUB_STATE_DIR=tempfile.mkdtemp())
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py")],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "ci", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    ]
    out, _ = p.communicate("\n".join(json.dumps(r) for r in reqs).encode() + b"\n", timeout=30)
    replies = {m["id"]: m for m in (json.loads(l) for l in out.decode("utf-8").splitlines() if l.strip())}
    assert replies[1]["result"]["serverInfo"]["name"] == "codex-sub", replies[1]
    assert replies[1]["result"].get("instructions"), "initialize 应返回 instructions"
    tools = {t["name"] for t in replies[2]["result"]["tools"]}
    expected = {"codex_spawn", "codex_review", "codex_wait", "codex_status", "codex_steer", "codex_interrupt"}
    assert tools == expected, tools ^ expected
    assert replies[3]["result"] == {}, replies[3]
    assert p.returncode == 0, p.returncode
    print("handshake ok:", len(tools), "tools")


if __name__ == "__main__":
    main()
