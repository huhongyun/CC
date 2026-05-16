# 生成周记

从印象笔记晨间日记中读取本周（或指定周）的日记，生成周记并保存到印象笔记。

## 参数

- `$ARGUMENTS` — 可选，指定周的起止日期，格式 `YYYY-MM-DD~YYYY-MM-DD`。不指定则自动取上周（周一~周日）。

## 执行步骤

### 1. 确定日期范围

如果用户提供了 `$ARGUMENTS`，解析为 `--start` 和 `--end`。

如果没有提供，自动计算**上周**的日期范围：
- 找到上周一和上周日的日期
- 用 Python 计算：`python3.11 -c "from datetime import date, timedelta; today=date.today(); start=today - timedelta(days=today.weekday()+7); end=start+timedelta(days=6); print(f'{start} {end}'  )"`

### 2. 读取日记

```bash
PYTHONIOENCODING=utf-8 python3.11 "C:/hhy/08 Claude/01 Claude Code/02 笔记融合/weekly_journal.py" read --start <START> --end <END>
```

输出文件在 `output/weekly_YYYYMMDD.txt`。

### 3. 生成周记

读取输出的日记文件，按以下格式生成周记 Markdown：

```markdown
# 周记 | YYYY/MM/DD~MM/DD

## 一、本周概览

（用 2-3 句话概括本周主线：工作、家庭、个人成长各一句）

---

## 二、每日回顾

### 周一（M/D）| 主题标签
（当天核心事件，2-3 句话）

### 周二（M/D）| 主题标签
...

（以此类推，跳过无日记的日期）

---

## 三、本周关键主题

### 1. 主题名称
（从日记中提炼的 2-3 个贯穿全周的主题，每个 2-3 句话）

### 2. 主题名称
...

---

## 四、成长轨迹

### 认知升级
（本周在认知/学习方面的收获）

### 身体管理
（运动、健康、养生方面的记录）

### 工作推进
（项目进展、团队管理、技术突破）

### 家庭关系
（与家人互动、情感变化）

---

## 五、下周关注

1. **关注点1**
2. **关注点2**
3. **关注点3**
```

**写作要求**：
- 基于日记原文事实，不添加虚构内容
- 用具体事件和细节代替笼统概括
- 保留日记中的关键对话、情感表达
- 每日回顾提炼一个主题标签（用 `|` 分隔）

### 4. 保存到印象笔记

将生成的 Markdown 写入 `output/journal_YYYYMMDD~MMDD.md`，然后运行：

```bash
PYTHONIOENCODING=utf-8 python3.11 "C:/hhy/08 Claude/01 Claude Code/02 笔记融合/weekly_journal.py" save --title "YYYYMMDD~MMDD-周记" --file "C:/hhy/08 Claude/01 Claude Code/02 笔记融合/output/journal_YYYYMMDD~MMDD.md"
```

标签会根据标题自动添加（含"周记"自动加 `周记` 标签）。

### 5. 输出结果

告知用户：
- 读取了多少篇日记
- 周记保存的位置和印象笔记 GUID
- 本周的核心主题（一句话）
