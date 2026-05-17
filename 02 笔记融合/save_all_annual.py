"""批量保存年记到印象笔记 + 获取缺失年份日记数据

功能：
1. 检查印象笔记中已有哪些年记
2. 将本地已有但印象笔记中没有的年记保存过去
3. 获取指定年份日记数据供后续生成年记

用法:
    python save_all_annual.py --year 2023 2024 2026   # 处理指定年份
    python save_all_annual.py --all                     # 自动检测所有有本地年记的年份
    python save_all_annual.py --year 2025 --dry-run    # 预览模式
    python save_all_annual.py --year 2025 --no-fetch   # 仅保存已有年记，不拉取日记
    python save_all_annual.py --year 2025 --notebook "04-10 晨间日记"
"""
import sys, os, json, inspect, time, ssl, re, argparse, glob as glob_module
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


def detect_local_years(output_dir):
    """自动检测所有有本地年记文件的年份"""
    years = set()
    for fname in os.listdir(output_dir):
        m = re.match(r'journal_(\d{4})\.md$', fname)
        if m:
            years.add(int(m.group(1)))
    return sorted(years)


def check_existing_annuals(note_store, token, nb_guid):
    """检查印象笔记中已有的年记，返回标题集合"""
    nf = NoteStore.NoteFilter()
    nf.notebookGuid = nb_guid
    nf.words = 'intitle:年记'
    result = retry_on_rate_limit(note_store.findNotes, token, nf, 0, 50)
    return {n.title for n in result.notes}


def save_one_annual(note_store, token, nb_guid, year, local_path, dry_run=False):
    """保存单条年记到印象笔记。返回 True 表示成功保存，False 表示已存在或跳过。"""
    title = f"{year}~年记"

    if dry_run:
        print(f"  [dry-run] 将保存: {title} (来源: {os.path.basename(local_path)})")
        return True

    with open(local_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    print(f"  保存 {title}...")
    try:
        enml_content = md_to_enml(md_content)
        note = EvernoteNote()
        note.title = title
        note.content = enml_content
        note.notebookGuid = nb_guid

        tag_guid = get_or_create_tag(note_store, token, '年记')
        note.tagGuids = [tag_guid]

        created = retry_on_rate_limit(note_store.createNote, token, note)
        print(f"    -> GUID: {created.guid}")
        return True
    except Exception as e:
        print(f"    -> 失败: {e}")
        if hasattr(e, 'errorCode') and e.errorCode == 19:
            wait = getattr(e, 'rateLimitDuration', 60)
            print(f"    限流，等待 {wait} 秒后重试...")
            time.sleep(wait)
            try:
                created = retry_on_rate_limit(note_store.createNote, token, note)
                print(f"    -> 重试成功 GUID: {created.guid}")
                return True
            except Exception as e2:
                print(f"    -> 重试失败: {e2}")
        return False


def fetch_year_diaries(note_store, token, nb_guid, year, output_dir):
    """获取指定年份的全部日记数据"""
    json_path = os.path.join(output_dir, f'diaries_{year}.json')

    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if len(data) > 0:
                print(f"    {year}年: 断点文件有 {len(data)} 条，将从断点续传")
            else:
                print(f"    {year}年: 断点文件为空，重新获取")
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"    {year}年: 断点文件损坏，重新获取")
            os.remove(json_path)

    print(f"  获取 {year}年日记...")
    nf_year = NoteStore.NoteFilter()
    nf_year.notebookGuid = nb_guid
    nf_year.order = 1  # CREATED
    nf_year.ascending = True

    start_ts = int(datetime(year, 1, 1).timestamp() * 1000)
    end_ts = int(datetime(year, 12, 31, 23, 59, 59).timestamp() * 1000)

    # Paginate through all notes
    all_notes = []
    offset = 0
    page_size = 100
    while True:
        result = retry_on_rate_limit(note_store.findNotes, token, nf_year, offset, page_size)
        for note in result.notes:
            if note.created and start_ts <= note.created <= end_ts:
                all_notes.append(note)
        scanned = min(offset + page_size, result.totalNotes) if hasattr(result, 'totalNotes') else (offset + len(result.notes))
        print(f"    已扫描 {scanned}/{getattr(result, 'totalNotes', '?')} 条，匹配 {len(all_notes)} 条")
        if offset + page_size >= getattr(result, 'totalNotes', 0):
            break
        offset += page_size

    print(f"  {year}年共找到 {len(all_notes)} 条日记")

    # Fetch full content (with checkpoint/resume)
    diaries, existing_guids = load_checkpoint(json_path)
    newly_fetched = 0

    for note_meta in all_notes:
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

        if newly_fetched % 5 == 0:
            save_checkpoint(json_path, diaries)

        if newly_fetched % 20 == 0:
            done = len(existing_guids)
            print(f"    已获取 {done}/{len(all_notes)} 条")

    save_checkpoint(json_path, diaries)
    print(f"  {year}年: 已保存 {len(diaries)} 条日记到 {os.path.basename(json_path)}")


def main():
    parser = argparse.ArgumentParser(description='批量保存年记到印象笔记并获取日记数据')
    parser.add_argument('--year', type=int, nargs='*',
                        help='要处理的年份（可指定多个）')
    parser.add_argument('--all', action='store_true',
                        help='自动检测所有有本地年记文件的年份')
    parser.add_argument('--notebook', '-n', default='04-10 晨间日记',
                        help='笔记本名称（默认: 04-10 晨间日记）')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅预览，不实际写入印象笔记')
    parser.add_argument('--no-fetch', dest='fetch', action='store_false',
                        help='仅保存年记，不拉取日记数据')
    parser.add_argument('--fetch', dest='fetch', action='store_true', default=True,
                        help='同时拉取日记数据（默认）')
    parser.add_argument('--token', help='印象笔记 token（覆盖 config.json）')
    args = parser.parse_args()

    # 确定要处理的年份
    output_dir = os.path.join(SCRIPT_DIR, 'output')

    if args.all:
        years = detect_local_years(output_dir)
        if not years:
            print("错误: 没有找到本地年记文件（journal_YYYY.md）")
            sys.exit(1)
        print(f"自动检测到年份: {years}")
    elif args.year:
        years = args.year
    else:
        print("错误: 请指定 --year 或 --all")
        print("示例: python save_all_annual.py --year 2025")
        print("      python save_all_annual.py --all")
        sys.exit(1)

    config = load_config()
    token = args.token if args.token else get_token(config)
    note_store = get_evernote_connection(token)
    notebook_name = args.notebook
    nb = find_notebook(note_store, name=notebook_name)
    print(f"笔记本: {nb.name} ({nb.guid})")

    # Step 1: Check existing annual journals in Evernote
    print("\n=== Step 1: 检查已有年记 ===")
    existing_titles = check_existing_annuals(note_store, token, nb.guid)
    print(f"印象笔记中已有 {len(existing_titles)} 条年记:")
    for title in sorted(existing_titles):
        print(f"  {title}")

    # Build local journal map
    local_journals = {}
    for fname in os.listdir(output_dir):
        m = re.match(r'journal_(\d{4})\.md$', fname)
        if m:
            year = int(m.group(1))
            if year in years:
                local_journals[year] = os.path.join(output_dir, fname)

    print(f"\n本地年记文件:")
    for year in sorted(local_journals):
        print(f"  {year}: {os.path.basename(local_journals[year])}")

    # Step 2: Save missing journals to Evernote
    print(f"\n=== Step 2: 保存缺失的年记到印象笔记{' [dry-run]' if args.dry_run else ''} ===")
    saved = 0
    for year in sorted(years):
        if year not in local_journals:
            print(f"  {year}年: 本地没有年记文件，跳过")
            continue

        title = f"{year}~年记"
        if title in existing_titles:
            print(f"  {title} 已存在，跳过")
            continue

        ok = save_one_annual(note_store, token, nb.guid, year,
                             local_journals[year], dry_run=args.dry_run)
        if ok:
            saved += 1
            if not args.dry_run:
                time.sleep(2)  # Small delay between saves

    print(f"\n共{'将' if args.dry_run else ''}保存 {saved} 条新年记")

    # Step 3: Fetch diary data for specified years
    if args.fetch:
        print(f"\n=== Step 3: 获取日记数据 ===")
        for year in sorted(years):
            fetch_year_diaries(note_store, token, nb.guid, year, output_dir)

    print("\n=== 完成 ===")


if __name__ == '__main__':
    main()
