"""批量保存所有年记到印象笔记 + 获取缺失年份日记数据

功能：
1. 检查印象笔记中已有哪些年记
2. 将本地已有但印象笔记中没有的年记保存过去
3. 获取 2023/2024 年日记数据供后续生成年记
"""
import sys, os, json, inspect, time, ssl, re
from datetime import datetime

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec
ssl._create_default_https_context = ssl._create_unverified_context

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from weekly_journal import (
    load_config, get_token, get_evernote_connection, find_notebook,
    retry_on_rate_limit, md_to_enml, get_or_create_tag
)
from evernote.edam.notestore import NoteStore
from evernote.edam.type.ttypes import Note as EvernoteNote

def wait_for_rate_limit(seconds=600):
    """主动等待限流冷却"""
    print(f"  等待 {seconds} 秒让限流冷却...")
    time.sleep(seconds)


def load_checkpoint(json_path):
    """加载已有数据，返回 (diaries列表, 已获取的GUID集合)"""
    diaries = []
    existing_guids = set()
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                diaries = json.load(f)
            existing_guids = {d.get('guid', '') for d in diaries}
            print(f"    加载断点: 已有 {len(diaries)} 条")
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"    断点文件损坏，从头开始")
            diaries = []
            existing_guids = set()
    return diaries, existing_guids


def save_checkpoint(json_path, diaries):
    """保存当前进度到 JSON 文件"""
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(diaries, f, ensure_ascii=False, indent=2)

def main():
    config = load_config()
    token = get_token(config)
    note_store = get_evernote_connection(token)
    nb = find_notebook(note_store)
    print(f"笔记本: {nb.name} ({nb.guid})")

    # Step 1: Check existing annual journals in Evernote
    print("\n=== Step 1: 检查已有年记 ===")
    nf = NoteStore.NoteFilter()
    nf.notebookGuid = nb.guid
    nf.words = 'intitle:年记'
    result = retry_on_rate_limit(note_store.findNotes, token, nf, 0, 50)
    existing = {n.title: n.guid for n in result.notes}
    print(f"印象笔记中已有 {len(existing)} 条年记:")
    for title, guid in existing.items():
        print(f"  {title}")

    # Step 2: Check local journal files
    output_dir = os.path.join(SCRIPT_DIR, 'output')
    local_journals = {}
    for fname in os.listdir(output_dir):
        if fname.startswith('journal_') and fname.endswith('.md') and '年记' not in fname:
            # Extract year from filename
            m = re.match(r'journal_(\d{4})\.md$', fname)
            if m:
                year = m.group(1)
                local_journals[year] = os.path.join(output_dir, fname)

    print(f"\n本地年记文件:")
    for year, path in sorted(local_journals.items()):
        print(f"  {year}: {os.path.basename(path)}")

    # Step 3: Save missing journals to Evernote
    print("\n=== Step 2: 保存缺失的年记到印象笔记 ===")
    saved = 0
    for year in sorted(local_journals.keys()):
        title = f"{year}~年记"
        evernote_title = f"{year}年记"  # Evernote title format
        if evernote_title in existing:
            print(f"  {evernote_title} 已存在，跳过")
            continue

        # Read local file
        with open(local_journals[year], 'r', encoding='utf-8') as f:
            md_content = f.read()

        # Save to Evernote
        print(f"  保存 {evernote_title}...")
        try:
            enml_content = md_to_enml(md_content)
            note = EvernoteNote()
            note.title = evernote_title
            note.content = enml_content
            note.notebookGuid = nb.guid

            # Add tag
            tag_guid = get_or_create_tag(note_store, token, '年记')
            note.tagGuids = [tag_guid]

            created = retry_on_rate_limit(note_store.createNote, token, note)
            print(f"    -> GUID: {created.guid}")
            saved += 1
            time.sleep(2)  # Small delay between saves
        except Exception as e:
            print(f"    -> 失败: {e}")
            if hasattr(e, 'errorCode') and e.errorCode == 19:
                wait = getattr(e, 'rateLimitDuration', 60)
                print(f"    限流，等待 {wait} 秒...")
                time.sleep(wait)
                # Retry once
                try:
                    created = retry_on_rate_limit(note_store.createNote, token, note)
                    print(f"    -> 重试成功 GUID: {created.guid}")
                    saved += 1
                except Exception as e2:
                    print(f"    -> 重试失败: {e2}")

    print(f"\n共保存 {saved} 条新年记")

    # Step 4: Fetch 2023 and 2024 diary data
    print("\n=== Step 3: 获取 2023/2024 年日记数据 ===")

    for year in [2023, 2024]:
        json_path = os.path.join(output_dir, f'diaries_{year}.json')
        total_needed = None  # Will be set after pagination
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if len(data) > 0:
                    print(f"  {year}年: 断点文件有 {len(data)} 条，将从断点续传")
                else:
                    print(f"  {year}年: 断点文件为空，重新获取")
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"  {year}年: 断点文件损坏，重新获取")
                os.remove(json_path)

        print(f"  获取 {year}年日记...")
        # Use findNotes + Python date filtering (Evernote China created: search unreliable)
        nf_year = NoteStore.NoteFilter()
        nf_year.notebookGuid = nb.guid
        nf_year.order = 1  # CREATED
        nf_year.ascending = True

        # Calculate year boundaries in milliseconds
        start_dt = datetime(year, 1, 1)
        end_dt = datetime(year, 12, 31, 23, 59, 59)
        start_ts = int(start_dt.timestamp() * 1000)
        end_ts = int(end_dt.timestamp() * 1000)

        # Paginate through all notes
        all_notes = []
        offset = 0
        page_size = 100
        while True:
            result = retry_on_rate_limit(note_store.findNotes, token, nf_year, offset, page_size)
            for note in result.notes:
                if note.created and start_ts <= note.created <= end_ts:
                    all_notes.append(note)
            print(f"    已扫描 {offset + len(result.notes)}/{result.totalNotes} 条，匹配 {len(all_notes)} 条")
            if offset + page_size >= result.totalNotes:
                break
            offset += page_size

        print(f"  {year}年共找到 {len(all_notes)} 条日记")

        # Fetch full content (with checkpoint/resume)
        diaries, existing_guids = load_checkpoint(json_path)
        newly_fetched = 0  # Track new entries for periodic checkpoint

        for i, note_meta in enumerate(all_notes):
            if note_meta.guid in existing_guids:
                continue

            try:
                note = retry_on_rate_limit(note_store.getNote, token, note_meta.guid, True, False, False, False)
                content = note.content or ''
                content = re.sub(r'<[^>]+>', '', content)
                content = content.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
                content = re.sub(r'\n\s*\n', '\n\n', content).strip()
                diaries.append({
                    'guid': note_meta.guid,
                    'title': note.title,
                    'content': content,
                    'created': note.created
                })
                existing_guids.add(note_meta.guid)
                newly_fetched += 1
            except Exception as e:
                print(f"    获取 {note_meta.guid} 失败: {e}")
                if hasattr(e, 'errorCode') and e.errorCode == 19:
                    wait = getattr(e, 'rateLimitDuration', 60)
                    print(f"    限流，等待 {wait} 秒...")
                    time.sleep(wait)
                continue

            # Save checkpoint every 5 newly-fetched notes
            if newly_fetched % 5 == 0:
                save_checkpoint(json_path, diaries)

            if newly_fetched % 20 == 0:
                done = len(existing_guids)
                print(f"    已获取 {done}/{len(all_notes)} 条")

        # Final save
        save_checkpoint(json_path, diaries)
        print(f"  {year}年: 已保存 {len(diaries)} 条日记到 {os.path.basename(json_path)}")

    print("\n=== 完成 ===")

if __name__ == '__main__':
    main()
