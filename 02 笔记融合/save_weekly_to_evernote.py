"""将周记保存到印象笔记"""
import os, sys, json, inspect, re, ssl

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

# 修补: evernote SDK 使用了已移除的 inspect.getargspec
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

# SSL 证书验证修复（中国版印象笔记需要）
ssl._create_default_https_context = ssl._create_unverified_context

# 使用 create_diary.py 中的 token
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '01 晨间日记自动创建'))
from create_diary import DEFAULT_TOKEN

NOTEBOOK_NAME = '04-10 晨间日记'
TITLE = '20260504~0510-周记'

# 读取周记内容
weekly_path = os.path.join(os.path.dirname(__file__), 'output', 'weekly_20260504.md')
with open(weekly_path, 'r', encoding='utf-8') as f:
    md_content = f.read()

# 连接印象笔记
from evernote.api.client import EvernoteClient
from evernote.edam.notestore.ttypes import NoteFilter

client = EvernoteClient(token=DEFAULT_TOKEN, sandbox=False, china=True)
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

print(f"目标笔记本: {target_notebook.name}")

# Markdown → ENML 转换（简化版）
def md_to_enml(md_text):
    """将 Markdown 转为 ENML"""
    lines = md_text.split('\n')
    enml_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # 空行
        if not stripped:
            if in_list:
                enml_parts.append('</en-media>')
                in_list = False
            enml_parts.append('<br/>')
            continue

        # 标题 → 加粗
        if stripped.startswith('# '):
            text = stripped[2:]
            enml_parts.append(f'<b>{escape_xml(text)}</b><br/>')
            continue
        if stripped.startswith('## '):
            text = stripped[3:]
            enml_parts.append(f'<b>{escape_xml(text)}</b><br/>')
            continue
        if stripped.startswith('### '):
            text = stripped[4:]
            enml_parts.append(f'<b>{escape_xml(text)}</b><br/>')
            continue

        # 分隔线
        if stripped == '---':
            enml_parts.append('<br/>----------------------------------------<br/>')
            continue

        # 无序列表
        if stripped.startswith('- '):
            text = stripped[2:]
            enml_parts.append(f'• {format_inline(text)}<br/>')
            continue

        # 有序列表
        if len(stripped) > 2 and stripped[0].isdigit() and '. ' in stripped[:5]:
            text = stripped.split('. ', 1)[1] if '. ' in stripped else stripped
            enml_parts.append(f'{format_inline(text)}<br/>')
            continue

        # 普通段落
        enml_parts.append(f'{format_inline(stripped)}<br/>')

    body = '\n'.join(enml_parts)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">
<en-note>{body}</en-note>'''

def escape_xml(text):
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text

def format_inline(text):
    """处理行内格式：**bold** → <b>"""
    text = escape_xml(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    return text

enml_content = md_to_enml(md_content)

# 创建笔记
from evernote.edam.type.ttypes import Note, Notebook

note = Note()
note.title = TITLE
note.content = enml_content
note.notebookGuid = target_notebook.guid

try:
    created_note = note_store.createNote(DEFAULT_TOKEN, note)
    print(f"周记已保存到印象笔记！")
    print(f"  标题: {created_note.title}")
    print(f"  GUID: {created_note.guid}")
    print(f"  笔记本: {NOTEBOOK_NAME}")
except Exception as e:
    print(f"保存失败: {e}")
    sys.exit(1)
