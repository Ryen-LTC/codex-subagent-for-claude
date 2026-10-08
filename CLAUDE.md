# codex-subagent-for-claude —— 维护者说明

Claude Code 通过 MCP 把任务派给 Codex，Codex 后台并行执行，结果由 hook 推回派出它的会话。
仅依赖 Python 3 标准库和已登录的 Codex。面向用户的安装与使用见 [README.md](README.md)。

## 组成

```
Claude Code ──stdio MCP──> server.py ──stdio JSON-RPC──> codex app-server（本工具自己拉起的常驻子进程）
                              └ 任务状态写 %LOCALAPPDATA%\codex-sub\session-<claude pid>.json
Claude Code ──hook──> hook.py：读状态文件，注入完成结果 / Stop 时拦截
```

- `server.py`：MCP 服务，六个工具。每个任务一个 app-server thread，状态来自事件流。app-server 在首次调用时拉起并常驻（约 150 MB），Claude 会话结束时随之退出。
- `hook.py`：`UserPromptSubmit` / `PostToolUse` 把未送达的完成结果注入为 `additionalContext`；`Stop` 时有未送达结果则阻止结束并附结果，有未 `detach` 的任务在跑则阻止结束并要求 `codex_wait`（每任务最多拦 3 次）。
- 会话归属：状态文件以 Claude 进程 pid（MCP 服务的父进程）命名，hook 沿自己的祖先链找第一个存在且 MCP 服务还活着的文件。只认直接父进程，不做更深层回退——Claude Desktop 下所有会话共用同一个祖父进程，回退会串会话。
- 结果只送一次：通过工具返回过的终态结果标 `reported`，hook 不再注入；hook 注入过的记进 `.ack.json`。 并行工具调用会同时触发多个 hook 进程，用 `.lock` 文件互斥，抢不到锁的直接放弃本次。
- 判定状态文件所属 MCP 服务是否存活：pid 存在、是 python、且父进程等于文件名里的 Claude pid（防 pid 复用）。
- 启动时清理 MCP 服务已死的旧会话文件，并杀掉它们残留的 app-server（Claude 被强杀时 `finally` 不会执行）。
- 服务端发来的审批/追问按各方法的应答格式一律拒绝（`_DECLINE_REPLIES`），无人值守不会挂起。

## 工具

| 工具 | 作用 |
|---|---|
| `codex_spawn(prompt, cwd, wait_s, thread_id, persist, sandbox, model, effort, worktree, detach)` | 派任务，立即返回 id；`wait_s>0` 先等，等到即返回结果；`thread_id` 续问 |
| `codex_review(scope, value, cwd, wait_s)` | Codex 内置代码审查模式（`review/start`，只读、找缺陷）：`uncommitted` / `base_branch` / `commit` / `custom` |
| `codex_wait(ids, timeout, mode)` | 等待，`mode=any` 任一完成即返回；每 10s 发进度心跳；超时只返回状态，不杀任务 |
| `codex_status(ids, full)` | 不传 ids 列出全部任务；传 ids 看详情（运行中：最近动作、改动文件、输出预览；已结束：结果，超 6000 字截断，`full=true` 看全文） |
| `codex_steer(id, prompt)` | 运行中追加/修正指令 |
| `codex_interrupt(id)` | 中断，保留已产出部分 |

- thread 默认临时（不进 `~/.codex`、不进 Codex 历史），同一 Claude 会话内可续问；跨会话续问需 `persist=true`。
- `worktree=true`：在 `<仓库>.codex-sub/<id>/` 建 worktree，分支 `codex-sub/<id>`，合并与清理由调用方负责。
- `detach=true`：Stop 时不因它拦截。
- initialize 返回 `instructions`（何时派、prompt 怎么写、结果怎么处理），Claude Code 会注入系统提示。
- 续问时该 thread 上不能有未结束的任务；`worktree` 与 `thread_id` 不能同用。
- 子代理加载的是 `~/.codex` 里的全部技能与插件（`skills/list` 可见，含系统技能 `review-agent`、`openai-docs` 等），在 prompt 里写 `$技能名` 或按描述提及即可触发。
- 模型参数独立于 `~/.codex/config.toml`：默认 `gpt-6.1-sol` / effort `high` / 服务档 `default`（标准档，不用 Fast）。config.toml 的 `service_tier = "priority"` 只作用于桌面聊天，子代理不继承。每个任务可用 `model` / `effort` 覆盖；`model` 限定为 `gpt-6.1-sol` / `gpt-6-astra` / `gpt-6-sol` / `gpt-6-luna`（界面名 GPT-6.1 Sol / GPT-6 Astra / GPT-6 Sol / GPT-6 Luna），Luna 不支持 `ultra`。

## 权限

- Claude 侧：工具名 `mcp__codex-sub__codex_*`。未在 `permissions.allow` 放行 `mcp__codex-sub` 时每次调用弹确认。
- Codex 侧：默认 `sandbox=danger-full-access`（无沙箱）、`approvalPolicy=never`，Codex 发来的审批/追问一律拒绝。`codex_review` 用同样的默认沙箱——审查模式本身不改文件，但要跑 `git` 等命令。默认沙箱由 `CODEX_SUB_SANDBOX` 改。
- `read-only` 不可用：它和 `workspace-write` 一样会启用 Codex 的 Windows 沙箱，沙箱里任何命令都起不来（`exec_command failed: … setup refresh had errors`），`git`、`python` 全部失败。参数保留只为完整性，工具描述里已标明。
- 不用 `workspace-write` 的原因：Codex 的 Windows 沙箱（`[windows] sandbox = "elevated"`）用受限账户跑命令，读不到用户目录下安装的工具（`AppData\Local` 里的 Python、pnpm、uv、npm 全局包在沙箱内都不存在），子代理无法运行测试；官方只提供交互式 `/sandbox-add-read-dir`，无法从 app-server 配置。`workspace-write` 下命令能否联网另由 `[sandbox_workspace_write] network_access` 决定。
- Codex 内置网页工具在任何 `web_search` 模式、任何沙箱下都经过 OpenAI 服务端抓取层，同一 URL 短时间内返回同一快照，带参数的 URL 和冷门站点拿不到；要真正实时抓取需让子代理跑 `curl`。

## 接入

- MCP：`~/.claude.json` user 级 `codex-sub`（`claude mcp add codex-sub -s user -- python "<安装目录>\server.py"`）。
- hook：`~/.claude/settings.json` 的 `hooks` 里三条 `python "<安装目录>\hook.py" <事件>`。
- 临时试用不改全局配置：`claude --plugin-dir "<安装目录>"`，不能同时加 `--strict-mcp-config`（会屏蔽插件 MCP）；工具名前缀变为 `mcp__plugin_codex-sub_codex-sub__`。
- 环境变量：`CODEX_SUB_BIN` 指定 codex 可执行文件；`CODEX_SUB_STATE_DIR` 状态目录；`CODEX_SUB_SANDBOX` 默认沙箱；`CODEX_SUB_MODEL` / `CODEX_SUB_EFFORT` / `CODEX_SUB_SERVICE_TIER` 模型默认值。
- 日志：`%LOCALAPPDATA%\codex-sub\server.log`、`app-server.stderr`。

## 约束

- 常见两份 codex：npm 的 `%APPDATA%\npm\codex.cmd`（手动更新）和桌面应用的 `%LOCALAPPDATA%\OpenAI\Codex\bin\<hash>\codex.exe`（随应用更新，`bin\` 可能残留空的旧 hash 目录）。共用 `~/.codex` 登录态与 `config.toml`；旧版可能解析不了新版写出的 `config.toml`。`find_codex()` 优先桌面版最新 `codex.exe`，其次 PATH。
- `codex app-server daemon` 是共享后台进程（套接字在 `~/.codex/app-server-control/`），本工具不连它，自己拉独立 `app-server`，随 Claude 会话生灭。
- 新版 Codex 无 `codex mcp-server` 子命令，程序化入口只有 `app-server`。
- 若走 npm 的 `codex.cmd`，须用 `node codex.js` 直接调用：`CreateProcess` 找不到 `.cmd`，cmd.exe 会破坏含换行的 prompt。
- 子进程 stdin 一律 `DEVNULL`：Windows 下 git 继承 MCP 的 stdin 管道会挂死。
- MCP 的 stdin/stdout 强制 UTF-8，默认 GBK 会打坏中文。
- Claude 桌面应用是 MSIX 包，它及其子进程对 `AppData\Local` / `AppData\Roaming` 的写入会被重定向到 `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\`，普通终端看不到。因此状态目录在桌面会话和终端 CLI 会话里是两份（各自自洽，不会串）；在桌面会话里 `npm install -g` 装的东西终端里不存在，全局安装要在普通终端做。`%LOCALAPPDATA%\OpenAI\Codexin` 由 Codex 应用写入，不受此影响，`find_codex()` 两种会话都能找到。

## 测试

- `python tests/smoke.py`：协议层冒烟测试，真实调用 Codex，用临时目录。改动核心逻辑后必跑。
