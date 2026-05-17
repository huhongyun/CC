# 年记批量生成 — 进度追踪

## 当前进度

| 年份 | 日记数 | 本地年记 | 印象笔记 |
|------|--------|---------|---------|
| 2019 | 148 | `journal_2019.md` | ✅ 已保存 |
| 2020 | 124 | `journal_2020.md` | ✅ 已保存 |
| 2021 | 47 | `journal_2021.md` | ✅ 已保存 |
| 2022 | 368 | `journal_2022.md` | ✅ 已保存 |
| 2023 | ~457 | `journal_2023.md` | ✅ 已保存 |
| 2024 | ~365+ | `journal_2024.md` | ✅ 已保存 |
| 2025 | 365 | `journal_2025.md` | ✅ 已保存 |
| 2026 | WIP | `journal_2026.md` | ⚠️ 进行中 |

## 恢复操作

### 批量保存已有年记

```bash
cd "C:/hhy/08 Claude/01 Claude Code/02 笔记融合"
# 预览模式
PYTHONIOENCODING=utf-8 python3.11 save_all_annual.py --all --dry-run
# 实际保存
PYTHONIOENCODING=utf-8 python3.11 save_all_annual.py --all --no-fetch
```

### 拉取缺失年份日记数据（含断点续传）

```bash
PYTHONIOENCODING=utf-8 python3.11 save_all_annual.py --year 2023 2024
```

### 单独保存某年年记

```bash
PYTHONIOENCODING=utf-8 python3.11 weekly_journal.py save --title "2023~年记" --file output/journal_2023.md
PYTHONIOENCODING=utf-8 python3.11 weekly_journal.py save --title "2024~年记" --file output/journal_2024.md
```

标签根据标题中的 `~年记` 自动添加。

## 关键文件

- `save_all_annual.py` — 批量保存年记 + 获取日记数据（CLI 参数化，含断点续传）
- `weekly_journal.py` — 读取/保存工具（含 `resolve` 日期计算、`retry_on_rate_limit`、`md_to_enml`）
- `output/diaries_YYYY.json` — 原始日记数据

## 已知问题

- Evernote China API 的 `created:` 搜索语法不可靠，已改用 `findNotes` + Python 时间戳过滤
- 每次约 220 次 `getNote` 调用后限流 ~60 分钟，脚本内置自动重试
- 拉取全年日记数据需 2-3 轮限流等待
