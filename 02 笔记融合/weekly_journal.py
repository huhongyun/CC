"""周记工具：读取印象笔记晨间日记 / 保存周记到印象笔记 / 日期解析

用法:
    python weekly_journal.py resolve --type week               # 上周范围
    python weekly_journal.py resolve --type week --date 2026-04-01  # 指定周的周一~周日
    python weekly_journal.py resolve --type month              # 上月范围
    python weekly_journal.py resolve --type month --date 2026-04  # 指定月起止日
    python weekly_journal.py resolve --type year               # 去年
    python weekly_journal.py resolve --type year --date 2025   # 指定年
    python weekly_journal.py read --start 2026-04-01 --end 2026-04-07 [--output path] [--notebook NAME] [--no-ocr]
    python weekly_journal.py save --title "20260330~0405-周记" --file output/journal.md [--notebook NAME]
"""
import os, sys, json, inspect, re, ssl, argparse, html, time, calendar
from datetime import datetime, timedelta, date

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

# 修补: evernote SDK 使用了已移除的 inspect.getargspec
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

# SSL 证书验证修复（中国版印象笔记需要）
ssl._create_default_https_context = ssl._create_unverified_context

# ─── 限流重试 ───────────────────────────────────────────────

def retry_on_rate_limit(func, *args, max_retries=5, **kwargs):
    """调用 Evernote API 时自动处理限流重试"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if hasattr(e, 'errorCode') and e.errorCode == 19:
                wait = getattr(e, 'rateLimitDuration', 60)
                print(f"  限流，等待 {wait} 秒后重试（第 {attempt+1}/{max_retries} 次）...")
                time.sleep(wait)
            else:
                raise
    raise Exception(f"重试 {max_retries} 次后仍被限流")

# ─── 配置加载 ───────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_config():
    config_path = os.path.join(SCRIPT_DIR, 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_token(config):
    token = config['yinxiang']['token']
    if not token:
        try:
            sys.path.insert(0, os.path.join(SCRIPT_DIR, '..', '01 晨间日记自动创建'))
            from create_diary import DEFAULT_TOKEN
            token = DEFAULT_TOKEN
        except Exception:
            print("错误: 未找到有效的印象笔记 token")
            sys.exit(1)
    return token

def get_evernote_connection(token):
    from evernote.api.client import EvernoteClient
    client = EvernoteClient(token=token, sandbox=False, china=True)
    note_store = client.get_note_store()
    return note_store

def find_notebook(note_store, name='04-10 晨间日记'):
    notebooks = retry_on_rate_limit(note_store.listNotebooks)
    for nb in notebooks:
        if nb.name == name:
            return nb
    print(f"错误: 未找到笔记本 '{name}'")
    sys.exit(1)

# ─── 读取日记 ───────────────────────────────────────────────

def strip_enml(enml_content):
    """从 ENML 中提取纯文本，保留基本结构"""
    text = enml_content
    # 移除 XML 声明和 DOCTYPE
    text = re.sub(r'<\?xml[^?]*\?>', '', text)
    text = re.sub(r'<!DOCTYPE[^>]*>', '', text)
    # 移除 en-note 标签
    text = re.sub(r'</?en-note[^>]*>', '', text)
    # <br/> / <br> → 换行
    text = re.sub(r'<br\s*/?>', '\n', text)
    # <en-media .../> → [图片]
    text = re.sub(r'<en-media[^/]*/>', '[图片]', text)
    # <div> → 换行
    text = re.sub(r'<div[^>]*>', '\n', text)
    text = re.sub(r'</div>', '', text)
    # 保留加粗/斜体标记
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<i>(.*?)</i>', r'*\1*', text, flags=re.DOTALL)
    # <span> 等内联标签直接移除
    text = re.sub(r'</?span[^>]*>', '', text)
    text = re.sub(r'</?en-todo[^>]*/?>', '', text)
    # 移除其余 HTML/ENML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 合并连续空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def read_diaries(note_store, token, nb_guid, start_date, end_date, skip_ocr=False):
    """读取指定日期范围内的晨间日记"""
    from evernote.edam.notestore.ttypes import NoteFilter, NotesMetadataResultSpec

    start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()

    note_filter = NoteFilter()
    note_filter.notebookGuid = nb_guid
    note_filter.order = 1  # CREATED, ascending
    note_filter.ascending = True

    result_spec = NotesMetadataResultSpec()
    result_spec.includeTitle = True
    result_spec.includeCreated = True

    all_notes = []
    offset = 0
    while True:
        result = retry_on_rate_limit(note_store.findNotesMetadata, token, note_filter, offset, 100, result_spec)
        for note_meta in result.notes:
            if note_meta.created is not None:
                created_date = datetime.fromtimestamp(note_meta.created / 1000).date()
                if start_dt <= created_date <= end_dt:
                    all_notes.append(note_meta)
                elif created_date > end_dt:
                    # 已超过结束日期，后续都是更晚的，可以停止
                    break
        offset += len(result.notes)
        if offset >= result.totalNotes:
            break

    print(f"找到 {len(all_notes)} 条日记（{start_date} ~ {end_date}）")

    diaries = []
    for note_meta in all_notes:
        full_note = retry_on_rate_limit(note_store.getNote, note_meta.guid, True, False, False, False)
        content_text = strip_enml(full_note.content)
        # 尝试获取 OCR 文字
        if not skip_ocr:
            ocr_text = ''
            if full_note.resources:
                for res in full_note.resources:
                    if res.mime and 'image' in res.mime:
                        try:
                            import winocr
                            img_data = res.data.body
                            from PIL import Image
                            import io
                            img = Image.open(io.BytesIO(img_data))
                            result = winocr.recognize_pil(img, 'zh-CN')
                            if result and result.text:
                                ocr_text += result.text + '\n'
                        except Exception:
                            pass
            if ocr_text:
                content_text += '\n[图片文字]\n' + ocr_text

        diaries.append({
            'title': note_meta.title,
            'guid': note_meta.guid,
            'created': datetime.fromtimestamp(note_meta.created / 1000).strftime('%Y-%m-%d'),
            'content': content_text,
        })

    return diaries

# ─── Markdown → ENML 转换 ──────────────────────────────────

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

def md_to_enml(md_text):
    """将 Markdown 转为 ENML"""
    lines = md_text.split('\n')
    enml_parts = []

    for line in lines:
        stripped = line.strip()

        # 空行
        if not stripped:
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

# ─── 保存到印象笔记 ─────────────────────────────────────────

def get_or_create_tag(note_store, token, tag_name):
    """获取或创建标签，返回 tag GUID"""
    tags = retry_on_rate_limit(note_store.listTags)
    for tag in tags:
        if tag.name == tag_name:
            return tag.guid
    # 不存在则创建
    from evernote.edam.type.ttypes import Tag
    tag = Tag()
    tag.name = tag_name
    created = retry_on_rate_limit(note_store.createTag, token, tag)
    print(f"  创建标签: {tag_name} ({created.guid})")
    return created.guid

def save_to_evernote(note_store, token, notebook_guid, title, md_content, tags=None):
    from evernote.edam.type.ttypes import Note

    enml_content = md_to_enml(md_content)
    note = Note()
    note.title = title
    note.content = enml_content
    note.notebookGuid = notebook_guid

    # 自动检测标签（从标题推断，要求 ~ 或 - 前缀避免误匹配）
    if tags is None:
        tags = []
        m = re.search(r'[~-](周记|月记|年记)', title)
        if m:
            tags.append(m.group(1))

    # 设置标签
    if tags:
        tag_guids = []
        for tag_name in tags:
            tag_guid = get_or_create_tag(note_store, token, tag_name)
            tag_guids.append(tag_guid)
        note.tagGuids = tag_guids

    created_note = retry_on_rate_limit(note_store.createNote, token, note)
    print(f"已保存到印象笔记！")
    print(f"  标题: {created_note.title}")
    print(f"  GUID: {created_note.guid}")
    if tags:
        print(f"  标签: {', '.join(tags)}")
    return created_note

# ─── resolve 命令：统一日期计算入口 ────────────────────────

def _resolve_week(ref_date_str=None):
    """计算周一~周日日期范围。不传则返回上周。"""
    today = date.today()
    if ref_date_str:
        ref_date = datetime.strptime(ref_date_str, '%Y-%m-%d').date()
        monday = ref_date - timedelta(days=ref_date.weekday())
    else:
        monday = today - timedelta(days=today.weekday() + 7)
    sunday = monday + timedelta(days=6)
    return monday, sunday

def _resolve_month(ref_date_str=None):
    """计算月份起止日。不传则返回上月。"""
    if ref_date_str:
        parts = ref_date_str.split('-')
        year, month = int(parts[0]), int(parts[1])
    else:
        first_of_this = date(date.today().year, date.today().month, 1)
        last_day = first_of_this - timedelta(days=1)
        year, month = last_day.year, last_day.month
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)

def cmd_resolve(args):
    """统一日期计算入口，供 Skill 调用"""
    if args.type == 'week':
        monday, sunday = _resolve_week(args.date)
        print(f"{monday} {sunday}")
    elif args.type == 'month':
        start, end = _resolve_month(args.date)
        print(f"{start} {end}")
    elif args.type == 'year':
        if args.date:
            print(args.date)
        else:
            print(str(date.today().year - 1))

# ─── CLI ────────────────────────────────────────────────────

def _detect_output_name(start_date, end_date):
    """根据日期跨度自动选择输出文件名"""
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    span_days = (end_dt - start_dt).days
    start_compact = start_date.replace('-', '')

    if span_days <= 7:
        return f'weekly_{start_compact}.txt'
    elif span_days <= 32:
        # 按月命名
        return f'diary_{start_date[:7].replace("-", "")}.txt'
    else:
        # 自定义范围
        end_compact = end_date.replace('-', '')
        return f'diary_{start_compact}_{end_compact}.txt'

def cmd_read(args):
    config = load_config()
    token = args.token if args.token else get_token(config)
    note_store = get_evernote_connection(token)
    notebook_name = args.notebook or '04-10 晨间日记'
    notebook = find_notebook(note_store, name=notebook_name)

    diaries = read_diaries(note_store, token, notebook.guid, args.start, args.end, skip_ocr=args.no_ocr)

    # 输出
    output_dir = os.path.join(SCRIPT_DIR, 'output')
    os.makedirs(output_dir, exist_ok=True)

    if args.output:
        output_path = args.output
    else:
        fname = _detect_output_name(args.start, args.end)
        output_path = os.path.join(output_dir, fname)

    with open(output_path, 'w', encoding='utf-8') as f:
        for d in diaries:
            f.write(f"=== {d['title']} ({d['created']}) ===\n")
            f.write(d['content'])
            f.write('\n\n')

    print(f"输出: {output_path}")
    return output_path

def cmd_save(args):
    config = load_config()
    token = args.token if args.token else get_token(config)
    note_store = get_evernote_connection(token)
    notebook_name = args.notebook or '04-10 晨间日记'
    notebook = find_notebook(note_store, name=notebook_name)

    with open(args.file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    save_to_evernote(note_store, token, notebook.guid, args.title, md_content)

def main():
    parser = argparse.ArgumentParser(description='周记工具')
    sub = parser.add_subparsers(dest='command', required=True)

    # resolve 子命令
    p_resolve = sub.add_parser('resolve', help='计算日期范围（供 Skill 调用）')
    p_resolve.add_argument('--type', required=True, choices=['week', 'month', 'year'],
                           help='日期类型')
    p_resolve.add_argument('--date', help='参考日期（周: YYYY-MM-DD, 月: YYYY-MM, 年: YYYY）')

    # read 子命令
    p_read = sub.add_parser('read', help='读取指定日期范围的晨间日记')
    p_read.add_argument('--start', required=True, help='开始日期 YYYY-MM-DD')
    p_read.add_argument('--end', required=True, help='结束日期 YYYY-MM-DD')
    p_read.add_argument('--output', help='输出文件路径')
    p_read.add_argument('--notebook', '-n', help='笔记本名称（默认: 04-10 晨间日记）')
    p_read.add_argument('--no-ocr', action='store_true', help='跳过图片 OCR')
    p_read.add_argument('--token', help='印象笔记 token（覆盖 config.json）')

    # save 子命令
    p_save = sub.add_parser('save', help='将 Markdown 周记/月记/年记保存到印象笔记')
    p_save.add_argument('--title', required=True, help='笔记标题')
    p_save.add_argument('--file', required=True, help='Markdown 文件路径')
    p_save.add_argument('--notebook', '-n', help='笔记本名称（默认: 04-10 晨间日记）')
    p_save.add_argument('--token', help='印象笔记 token（覆盖 config.json）')

    args = parser.parse_args()

    if args.command == 'resolve':
        cmd_resolve(args)
    elif args.command == 'read':
        cmd_read(args)
    elif args.command == 'save':
        cmd_save(args)

if __name__ == '__main__':
    main()
