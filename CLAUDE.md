## Windows终端UTF-8编码处理
在Windows bash终端中执行Python脚本输出中文时，会出现乱码。解决方案：
- 方法1：在Python脚本开头设置 `os.environ['PYTHONIOENCODING'] = 'utf-8'`
- 方法2：使用`sys.stdout.reconfigure(encoding='utf-8')`重新配置标准输出
- 方法3：将结果写入文件，用Read工具读取（避免终端编码问题）
- 注意：`chcp 65001`在bash中不可用，仅适用于Windows CMD/PowerShell

## Get笔记API使用注意事项
- **凭证位置**：在 `~/.openclaw/openclaw.json` 的 `skills.entries.Get笔记` 下，apiKey 对应 Authorization，env.GETNOTE_CLIENT_ID 对应 X-Client-ID。不是系统环境变量，不要用 `os.environ` 读取
- **必须翻页**：API默认每页返回20条记录，查询笔记数量时必须翻页获取完整数据
- **翻页方法**：使用`cursor`参数，将响应中的`cursor`字段传入下次请求
- **统计逻辑**：遍历所有页面，按日期筛选目标笔记并计数
- **限流注意**：API有QPS限制（错误码10202），频繁请求会被限流

## Python环境注意事项
- **印象笔记脚本必须用 Python 3.11**（Windows Store 版），Python 3.14 移除了 `inspect.getargspec` 导致 evernote SDK 不兼容
- 运行印象笔记脚本时加 `PYTHONIOENCODING=utf-8` 避免 Windows 终端编码问题
- evernote SDK 需要额外安装 `python-oauth2` 依赖：`pip install evernote3 python-oauth2`

## Git & GitHub 环境
- **Git 版本**：2.54.0
- **user.name**：huhongyunks
- **user.email**：13511632960@163.com
- **GitHub 账号**：huhongyun
- **SSH Key**：ed25519，路径 `~/.ssh/id_ed25519`，已绑定 GitHub
- **gh CLI**：v2.92.0，路径 `/c/Program Files/GitHub CLI`（需手动加 PATH）
- **远程仓库**：`git@github.com:huhongyun/CC.git`（SSH 协议，2026-05-10 创建）

## 自动化计划任务

| 任务名 | 触发时间 | 脚本 | 说明 |
|--------|---------|------|------|
| 晨间日记自动创建 | 每天 06:00 | `01 晨间日记自动创建/create_diary.py` | 在印象笔记"04-10 晨间日记"中创建次日日记 |

管理：`powershell.exe -NoProfile -Command "Get-ScheduledTask -TaskName '<任务名>'"`

## 已配置的笔记 Skills

| Skill | 读取方式 | 写入方式 | 备注 |
|-------|---------|---------|------|
| flomo | MCP API（flomoapp.com/mcp） | Webhook API | 读取需 MCP Token，配置在 `02 笔记融合/config.json` |
| Get笔记 | REST API | REST API | 需 API Key + Client ID |
| 印象笔记 | evernote SDK + 图片 OCR | evernote SDK | 中国版需 `china=True`，Python 3.11，OCR 用 `winocr`（Windows 内置） |

## 已安装的 Skills

| Skill | 位置 | 说明 |
|-------|------|------|
| birthday-poem | `~/.claude/skills/birthday-poem/` | 生日祝福藏头诗生成，支持保存到 Get笔记「生日祝福」知识库 |
| lark-* (24个) | `~/.agents/skills/lark-*/` | 飞书官方 Skill，覆盖日历、消息、文档、表格、任务、邮箱等飞书业务域 |

## API 调用编码规范

Windows bash 环境下调用含中文的 REST API 时：
- **禁止用 curl**：curl 在 Windows bash 下发送中文 JSON 会乱码
- **必须用 Python**：`urllib.request` + `json.dumps(data, ensure_ascii=False).encode('utf-8')`
- 参考：`06 生日祝福` 项目中保存到 Get笔记的实际实现

## 飞书 lark-cli 配置

- **版本**：1.0.31，全局安装（`npm install -g @larksuite/cli`）
- **应用 ID**：`cli_aa8c0508b43a1cce`（品牌：feishu）
- **授权用户**：胡宏运（`ou_d7da6606af109ae4328e759cf9f72be3`）
- **Token 有效期**：access token 约 2 小时，refresh token 7 天，过期后需重新 `lark-cli auth login --recommend`
- **已授权业务域**：日历、消息、文档、表格、云盘、任务、知识库、多维表格、幻灯片、白板、会议、邮箱、审批、通讯录、妙记
- **注意事项**：
  - `--recommend` 参数会请求全部常用权限，浏览器授权页面需批准所有权限开关
  - 消息发送需额外 scope `im:message.send_as_user`，`--recommend` 未包含，需单独授权
  - 命令格式：`lark-cli <domain> +<action> [flags]`，如 `lark-cli calendar +agenda --start 2026-05-15`
