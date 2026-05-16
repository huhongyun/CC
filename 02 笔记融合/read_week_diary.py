"""读取印象笔记中上周（周一→周日）的晨间日记，输出到文件"""
import os, sys, json, re, inspect, ssl
from datetime import datetime, timedelta

# 修补: evernote SDK 使用了已移除的 inspect.getargspec
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

# SSL 证书验证修复（中国版印象笔记需要）
ssl._create_default_https_context = ssl._create_unverified_context

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

# 加载凭证
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# 优先使用 create_diary.py 中的 token（config.json 的可能已过期）
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '01 晨间日记自动创建'))
    from create_diary import DEFAULT_TOKEN
    TOKEN = DEFAULT_TOKEN
except Exception:
    TOKEN = config['yinxiang']['token']

if not TOKEN:
    print("错误: 未找到有效的印象笔记 token")
    sys.exit(1)
NOTEBOOK_NAME = config['yinxiang']['notebook']

# 计算上一周的日期范围（周一→周日）
today = datetime.now()
# 找到上周一
days_since_monday = today.weekday()  # 0=Monday
last_monday = today - timedelta(days=days_since_monday + 7)
last_sunday = last_monday + timedelta(days=6)

start_date = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
end_date = last_sunday.replace(hour=23, minute=59, second=59, microsecond=0)

print(f"目标日期范围: {start_date.strftime('%Y-%m-%d')} (周一) → {end_date.strftime('%Y-%m-%d')} (周日)")

# 连接印象笔记
try:
    from evernote.api.client import EvernoteClient
    from evernote.edam.notestore.ttypes import NoteFilter
except ImportError:
    print("错误: 请安装 evernote SDK: pip install evernote3 python-oauth2")
    sys.exit(1)

client = EvernoteClient(token=TOKEN, sandbox=False, china=True)
note_store = client.get_note_store()

# 查找笔记本
notebooks = note_store.listNotebooks()
target_notebook = None
for nb in notebooks:
    if nb.name == NOTEBOOK_NAME:
        target_notebook = nb
        break

if not target_notebook:
    print(f"错误: 未找到笔记本 '{NOTEBOOK_NAME}'")
    sys.exit(1)

print(f"找到笔记本: {target_notebook.name} (guid: {target_notebook.guid})")

# 搜索笔记（用 created 时间过滤）
note_filter = NoteFilter()
note_filter.notebookGuid = target_notebook.guid
result = note_store.findNotes(TOKEN, note_filter, 0, 100)

print(f"笔记本中共 {result.totalNotes} 条笔记")

# 按日期筛选
start_ts = int(start_date.timestamp() * 1000)
end_ts = int(end_date.timestamp() * 1000)

DIARY_PATTERN = re.compile(r'^(\d{8})-([A-Za-z]+)-(\d+)→(\d+)W$')
matched_notes = []

for note in result.notes:
    if note.created and start_ts <= note.created <= end_ts:
        matched_notes.append(note)
    # 也通过标题匹配确认
    m = DIARY_PATTERN.match(note.title)
    if m:
        date_str = m.group(1)
        try:
            note_date = datetime.strptime(date_str, "%Y%m%d")
            if start_date.date() <= note_date.date() <= end_date.date():
                # 避免重复
                if note.guid not in [n.guid for n in matched_notes]:
                    matched_notes.append(note)
        except ValueError:
            pass

# 按日期排序
matched_notes.sort(key=lambda n: n.created or 0)

print(f"\n找到 {len(matched_notes)} 条上周日记:")
for note in matched_notes:
    created = datetime.fromtimestamp(note.created / 1000).strftime('%Y-%m-%d %H:%M')
    print(f"  - {note.title} ({created})")

# 读取每条笔记的完整内容
all_diaries = []
for note in matched_notes:
    full_note = note_store.getNote(TOKEN, note.guid, True, False, False, False)
    content = full_note.content or ''
    # ENML → 纯文本
    content = re.sub(r'<[^>]+>', '', content)
    content = re.sub(r'&nbsp;', ' ', content)
    content = re.sub(r'&amp;', '&', content)
    content = re.sub(r'&lt;', '<', content)
    content = re.sub(r'&gt;', '>', content)
    content = content.strip()

    all_diaries.append({
        'title': note.title,
        'created': datetime.fromtimestamp(note.created / 1000).strftime('%Y-%m-%d %H:%M'),
        'content': content
    })

# 输出到文件
output_path = os.path.join(os.path.dirname(__file__), 'output', 'last_week_diaries.json')
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump({
        'week_range': f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}",
        'diary_count': len(all_diaries),
        'diaries': all_diaries
    }, f, ensure_ascii=False, indent=2)

print(f"\n日记内容已保存到: {output_path}")

# 同时输出到文本文件方便阅读
txt_path = os.path.join(os.path.dirname(__file__), 'output', 'last_week_diaries.txt')
with open(txt_path, 'w', encoding='utf-8') as f:
    f.write(f"上周晨间日记汇总 ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})\n")
    f.write("=" * 60 + "\n\n")
    for d in all_diaries:
        f.write(f"【{d['title']}】 {d['created']}\n")
        f.write("-" * 40 + "\n")
        f.write(d['content'])
        f.write("\n\n")

print(f"文本版本已保存到: {txt_path}")
