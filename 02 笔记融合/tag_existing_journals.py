"""为已有的周记/月记/年记批量添加标签

用法:
    python tag_existing_journals.py [--dry-run]
"""
import os, sys, inspect, ssl, argparse, time

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

ssl._create_default_https_context = ssl._create_unverified_context

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def retry_on_rate_limit(func, *args, max_retries=5, **kwargs):
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

def load_config():
    import json
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

def main():
    parser = argparse.ArgumentParser(description='为已有周记/月记/年记添加标签')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际修改')
    args = parser.parse_args()

    config = load_config()
    token = get_token(config)

    from evernote.api.client import EvernoteClient
    client = EvernoteClient(token=token, sandbox=False, china=True)
    note_store = client.get_note_store()

    from evernote.edam.notestore.ttypes import NoteFilter, NotesMetadataResultSpec

    # 找到笔记本
    notebooks = retry_on_rate_limit(note_store.listNotebooks)
    nb_guid = None
    for nb in notebooks:
        if nb.name == '04-10 晨间日记':
            nb_guid = nb.guid
            break
    if not nb_guid:
        print("错误: 未找到笔记本 '04-10 晨间日记'")
        sys.exit(1)

    # 搜索所有笔记（不限日期范围，找周记/月记/年记）
    note_filter = NoteFilter()
    note_filter.notebookGuid = nb_guid
    note_filter.order = 1
    note_filter.ascending = True

    result_spec = NotesMetadataResultSpec()
    result_spec.includeTitle = True
    result_spec.includeTagGuids = True

    all_notes = []
    offset = 0
    while True:
        result = retry_on_rate_limit(note_store.findNotesMetadata, token, note_filter, offset, 100, result_spec)
        all_notes.extend(result.notes)
        offset += len(result.notes)
        if offset >= result.totalNotes:
            break

    print(f"笔记本共 {len(all_notes)} 条笔记")

    # 过滤出周记/月记/年记
    target_notes = []
    for note_meta in all_notes:
        title = note_meta.title or ''
        if '周记' in title or '月记' in title or '年记' in title:
            target_notes.append(note_meta)

    print(f"找到 {len(target_notes)} 条需要打标签的笔记\n")

    # 获取或创建标签
    tags_cache = {}
    existing_tags = retry_on_rate_limit(note_store.listTags)
    for tag in existing_tags:
        tags_cache[tag.name] = tag.guid

    def get_or_create_tag(tag_name):
        if tag_name in tags_cache:
            return tags_cache[tag_name]
        if args.dry_run:
            print(f"  [dry-run] 将创建标签: {tag_name}")
            return f"fake-{tag_name}"
        from evernote.edam.type.ttypes import Tag
        tag = Tag()
        tag.name = tag_name
        created = retry_on_rate_limit(note_store.createTag, token, tag)
        tags_cache[tag_name] = created.guid
        print(f"  创建标签: {tag_name} ({created.guid})")
        return created.guid

    # 逐个处理
    updated = 0
    skipped = 0
    for note_meta in target_notes:
        title = note_meta.title
        existing_guids = note_meta.tagGuids or []

        # 确定需要的标签
        tag_name = None
        if '年记' in title:
            tag_name = '年记'
        elif '月记' in title:
            tag_name = '月记'
        elif '周记' in title:
            tag_name = '周记'

        if not tag_name:
            continue

        tag_guid = get_or_create_tag(tag_name)

        # 检查是否已有该标签
        if tag_guid in existing_guids:
            print(f"  跳过（已有标签）: {title}")
            skipped += 1
            continue

        if args.dry_run:
            print(f"  [dry-run] 将添加标签 '{tag_name}': {title}")
            updated += 1
            continue

        # 获取完整笔记并更新标签
        full_note = retry_on_rate_limit(note_store.getNote, note_meta.guid, False, False, False, False)
        full_note.tagGuids = list(set(existing_guids + [tag_guid]))
        retry_on_rate_limit(note_store.updateNote, token, full_note)
        print(f"  ✓ {tag_name}: {title}")
        updated += 1

    print(f"\n完成: {updated} 条更新, {skipped} 条跳过")

if __name__ == '__main__':
    main()
