# 笔记融合项目

## 项目目标

将三个笔记平台的内容融会贯通：
- **印象笔记**：晨间日记
- **Get笔记**：录音卡绑定的语音对话 + 自我反思
- **Flomo**：学习笔记

实现：(a) 行为分析——分析过去一周表现；(b) 知识链接——跨平台关联，打造第二大脑。

## 技术栈

- Python 3.11（印象笔记 SDK 使用了 `inspect.getargspec`，Python 3.14 已移除该函数）
- 印象笔记：Evernote SDK（中国版）+ 图片 OCR（winocr，Windows 内置 OCR）
- Get笔记：REST API（openapi.biji.com）
- Flomo：MCP API（flomoapp.com/mcp）

### Python 依赖

```
pip install evernote3 python-oauth2 winocr Pillow
```

- `winocr`：Windows 内置 OCR 的 Python 封装，用于识别印象笔记截图中的文字（依赖 `winrt-*`，pip 自动安装）

## 文件结构

```
02 笔记融合/
├── CLAUDE.md                 # 本文件
├── config.json               # 平台凭证配置（不入 git）
├── fetch_notes.py            # 统一数据拉取脚本（含图片 OCR）
├── analyze.py                # 行为分析 + 知识链接脚本
├── read_week_diary.py        # 读取印象笔记上周晨间日记
├── save_weekly_to_evernote.py # 将周记保存到印象笔记
├── 笔记融合需求.txt            # 原始需求文档
└── output/                   # 分析报告输出目录（不入 git）
    ├── notes_YYYYMMDD.json     # 拉取的原始数据
    ├── report_YYYYMMDD.md      # 分析报告
    ├── last_week_diaries.json  # 上周日记原始数据
    └── weekly_YYYYMMDD.md      # 周记
```

## 使用方式

### 拉取数据

```bash
# Python 3.11 环境
python fetch_notes.py --days 7
```

输出：`output/notes_YYYYMMDD.json`

### 分析数据

```bash
python analyze.py --input output/notes_YYYYMMDD.json
```

输出：`output/report_YYYYMMDD.md`

### 快捷方式

用户说"帮我分析这周表现"时：
1. 运行 `fetch_notes.py` 拉取数据
2. 运行 `analyze.py` 或直接用 Claude 分析
3. 输出报告

### 周记生成

用户说"帮我写周记"或"汇总上周日记"时：
1. 运行 `python3.11 read_week_diary.py` 读取上周晨间日记
2. Claude 根据日记内容汇总周记
3. 运行 `python3.11 save_weekly_to_evernote.py` 保存到印象笔记

## 数据格式

### 拉取数据（notes_YYYYMMDD.json）

```json
{
  "fetch_time": "2026-05-10T...",
  "days": 7,
  "total_notes": 208,
  "platforms": {"yinxiang": 8, "getnote": 180, "flomo": 20},
  "notes": [
    {
      "source": "yinxiang|getnote|flomo",
      "date": "2026-05-10",
      "title": "...",
      "content": "...",
      "tags": ["..."],
      "note_id": "..."
    }
  ]
}
```

印象笔记的 `content` 字段末尾可能包含 `[图片文字]` 标记，后跟 OCR 识别的图片文字。

### 分析报告（report_YYYYMMDD.md）

报告结构：
1. **执行率分析** — 从晨间日记提取工作事项，匹配 Get笔记/Flomo 中的完成记录
2. **时间分配分析** — 会议/沟通、学习/思考、健康、生活四个维度
3. **关键洞察** — 主题聚类（6类）、反复出现的问题、思维突破
4. **下周建议** — 基于执行率、时间分配、跨平台知识链接

## API 限流注意

- Get笔记：QPS 限制（错误码 10202），频繁请求会被限流
- Flomo：每分钟 60 次
- 印象笔记：无明确限制，但避免过于频繁；拉取图片资源会增加请求量

## 图片 OCR

印象笔记晨间日记中包含截图（天气、地理位置等），`fetch_notes.py` 会自动：
1. 获取笔记中的图片资源（`withResourcesData=True`）
2. 用 Windows 内置 OCR（`winocr` 包）识别中文文字
3. 将 OCR 结果追加到笔记 `content` 末尾，以 `[图片文字]` 标记分隔

首次使用需确保 Windows OCR 中文语言包已安装（Win11 通常自带）。

## 编码处理

Windows bash 终端执行 Python 脚本输出中文时会乱码，脚本中需设置：
```python
os.environ['PYTHONIOENCODING'] = 'utf-8'
# 或
sys.stdout.reconfigure(encoding='utf-8')
```

## 凭证管理

凭证存储在 `config.json`（已加入 .gitignore），不要提交到 git。
