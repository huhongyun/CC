# 生成月记

从印象笔记晨间日记中读取指定月份的日记，生成月记并保存到印象笔记。

## 参数

- `$ARGUMENTS` — 可选，指定月份，格式 `YYYY-MM`。不指定则自动取上个月。

## 执行步骤

### 1. 确定月份和日期范围

如果用户提供了 `$ARGUMENTS`，解析为年月。

如果没有提供，自动计算**上个月**：
- 用 Python 计算：`python3.11 -c "from datetime import date; today=date.today(); month=today.month-1 or 12; year=today.year if month!=12 else today.year-1; import calendar; last_day=calendar.monthrange(year,month)[1]; print(f'{year}-{month:02d}-01 {year}-{month:02d}-{last_day}')"`

### 2. 读取整月日记

```bash
PYTHONIOENCODING=utf-8 python3.11 "C:/hhy/08 Claude/01 Claude Code/02 笔记融合/weekly_journal.py" read --start <YYYY-MM-01> --end <YYYY-MM-DD>
```

输出文件在 `output/weekly_YYYYMM01.txt`。

### 3. 生成月记

读取输出的日记文件，按以下格式生成月记 Markdown：

```markdown
# 月记 | YYYY年M月

## 一、月度概览

（用 3-4 句话概括本月主线：家庭、工作、个人成长、人际关系各一句）

---

## 二、每周回顾

### 第N周（M/D~M/D）| 主题标签
（本周核心事件，3-4 句话，覆盖关键对话和情感）

### 第N周（M/D~M/D）| 主题标签
...

---

## 三、月度关键主题

### 1. 主题名称
（从日记中提炼的 3 个贯穿全月的核心主题，每个 3-5 句话）

### 2. 主题名称
...

### 3. 主题名称
...

---

## 四、成长轨迹

### 认知升级
（本月在认知/学习/哲学方面的收获和突破）

### 身体管理
（运动、健康、养生方面的记录和变化）

### 工作推进
（项目进展、团队管理、技术突破、客户沟通）

### 家庭关系
（与家人互动、情感变化、重要事件）

---

## 五、下月关注

1. **关注点1**
2. **关注点2**
3. **关注点3**
4. **关注点4**
5. **关注点5**
```

**写作要求**：
- 基于日记原文事实，不添加虚构内容
- 每周提炼一个主题标签，用具体事件支撑
- 月度关键主题应是贯穿全月的线索，而非孤立事件
- 保留日记中的关键对话、情感表达、反思
- 下月关注从日记末尾暴露的未完结线索中提取

### 4. 保存到印象笔记

将生成的 Markdown 写入 `output/journal_YYYYMM.md`，然后运行：

```bash
PYTHONIOENCODING=utf-8 python3.11 "C:/hhy/08 Claude/01 Claude Code/02 笔记融合/weekly_journal.py" save --title "YYYYMM~月记" --file "C:/hhy/08 Claude/01 Claude Code/02 笔记融合/output/journal_YYYYMM.md"
```

标签会根据标题自动添加（含"月记"自动加 `月记` 标签）。

### 5. 输出结果

告知用户：
- 读取了多少篇日记
- 月记保存的位置和印象笔记 GUID
- 本月的 3 个核心主题（一句话）
