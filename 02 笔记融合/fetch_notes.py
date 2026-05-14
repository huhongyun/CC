#!/usr/bin/env python3
"""统一拉取三个平台笔记数据"""

import os
import sys
import json
import inspect
import ssl
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Windows 终端 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Python 3.11+ 兼容性修复
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

# SSL 证书验证修复
ssl._create_default_https_context = ssl._create_unverified_context

# 脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'config.json')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')


def load_config() -> dict:
    """加载配置文件"""
    if not os.path.exists(CONFIG_PATH):
        print(f"错误: 配置文件不存在: {CONFIG_PATH}")
        print("请先创建 config.json，参考 CLAUDE.md 中的格式")
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def ensure_output_dir():
    """确保输出目录存在"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# 印象笔记
# ============================================================

def ocr_image(image_bytes: bytes) -> str:
    """对图片执行 OCR 识别（Windows 内置 OCR）"""
    try:
        from winocr import recognize_pil_sync
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_bytes))
        result = recognize_pil_sync(img, 'zh-CN')
        text = result.get('text', '')
        return text.strip()
    except ImportError:
        return ''
    except Exception as e:
        return ''


def fetch_yinxiang(token: str, notebook_name: str, days: int) -> List[Dict]:
    """从印象笔记拉取晨间日记（含图片 OCR）"""
    print(f"[印象笔记] 正在拉取 '{notebook_name}' 最近 {days} 天的笔记...")

    try:
        from evernote.api.client import EvernoteClient
        from evernote.edam.notestore.ttypes import NoteFilter
    except ImportError:
        print("错误: 请安装 evernote SDK: pip install evernote3 python-oauth2")
        return []

    client = EvernoteClient(token=token, sandbox=False, china=True)
    note_store = client.get_note_store()

    # 查找笔记本
    notebooks = note_store.listNotebooks()
    target_notebook = None
    for nb in notebooks:
        if nb.name == notebook_name:
            target_notebook = nb
            break

    if not target_notebook:
        print(f"警告: 未找到笔记本 '{notebook_name}'")
        return []

    # 搜索笔记
    note_filter = NoteFilter()
    note_filter.notebookGuid = target_notebook.guid

    result = note_store.findNotes(token, note_filter, 0, 100)

    # 计算日期边界
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_timestamp = int(cutoff_date.timestamp() * 1000)

    notes = []
    ocr_count = 0
    for note in result.notes:
        # 按创建时间筛选
        if note.created and note.created >= cutoff_timestamp:
            # 获取笔记内容和资源（图片）
            full_note = note_store.getNote(token, note.guid, True, True, False, False)

            # 提取纯文本内容（去除 ENML 标签）
            content = full_note.content or ''
            content = re.sub(r'<[^>]+>', '', content)
            content = re.sub(r'&nbsp;', ' ', content)
            content = re.sub(r'&amp;', '&', content)
            content = re.sub(r'&lt;', '<', content)
            content = re.sub(r'&gt;', '>', content)
            content = content.strip()

            # OCR 提取图片中的文字
            ocr_texts = []
            if full_note.resources:
                for res in full_note.resources:
                    mime = res.mime or ''
                    if mime.startswith('image/') and res.data and res.data.body:
                        ocr_text = ocr_image(res.data.body)
                        if ocr_text and len(ocr_text) > 5:
                            ocr_texts.append(ocr_text)
                            ocr_count += 1

            # 将 OCR 文字追加到内容后面
            if ocr_texts:
                content += '\n\n[图片文字]\n' + '\n'.join(ocr_texts)

            created_dt = datetime.fromtimestamp(note.created / 1000)

            notes.append({
                'source': 'yinxiang',
                'date': created_dt.strftime('%Y-%m-%d'),
                'title': note.title or '',
                'content': content,
                'tags': note.tagNames or [],
                'note_id': note.guid
            })

    print(f"[印象笔记] 拉取到 {len(notes)} 条笔记，OCR 识别 {ocr_count} 张图片")
    return notes


# ============================================================
# Get笔记
# ============================================================

def fetch_getnote(api_key: str, client_id: str, days: int) -> List[Dict]:
    """从 Get笔记拉取笔记"""
    import urllib.request
    import urllib.error

    print(f"[Get笔记] 正在拉取最近 {days} 天的笔记...")

    base_url = "https://openapi.biji.com/open/api/v1/resource/note/list"
    headers = {
        'Authorization': api_key,
        'X-Client-ID': client_id,
        'Content-Type': 'application/json'
    }

    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_date.strftime('%Y-%m-%d')

    all_notes = []
    cursor = None
    page_count = 0

    while True:
        url = base_url
        if cursor:
            url = f"{base_url}?cursor={cursor}"

        req = urllib.request.Request(url, headers=headers, method='GET')

        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            print(f"[Get笔记] API 错误: {e.code} - {error_body}")
            break
        except Exception as e:
            print(f"[Get笔记] 请求失败: {e}")
            break

        if not data.get('success'):
            print(f"[Get笔记] API 返回失败: {data}")
            break

        notes = data.get('data', {}).get('notes', [])
        if not notes:
            break

        page_count += 1
        reached_cutoff = False

        for note in notes:
            created_at = note.get('created_at', '')
            if not created_at:
                continue

            # 解析日期
            note_date = created_at[:10]  # YYYY-MM-DD

            if note_date < cutoff_str:
                reached_cutoff = True
                break

            # 提取标签
            tags = []
            for tag in note.get('tags', []):
                if isinstance(tag, dict):
                    tags.append(tag.get('name', ''))
                elif isinstance(tag, str):
                    tags.append(tag)

            all_notes.append({
                'source': 'getnote',
                'date': note_date,
                'title': note.get('title', ''),
                'content': note.get('content', ''),
                'tags': tags,
                'note_id': note.get('note_id', str(note.get('id', '')))
            })

        # 翻页
        has_more = data.get('data', {}).get('has_more', False)
        cursor = data.get('data', {}).get('cursor')

        if not has_more or not cursor or reached_cutoff:
            break

    print(f"[Get笔记] 拉取到 {len(all_notes)} 条笔记（{page_count} 页）")
    return all_notes


# ============================================================
# Flomo
# ============================================================

def fetch_flomo(mcp_token: str, days: int) -> List[Dict]:
    """从 Flomo 拉取笔记"""
    import urllib.request
    import urllib.error

    print(f"[Flomo] 正在拉取最近 {days} 天的笔记...")

    # Flomo MCP endpoint
    mcp_url = "https://flomoapp.com/mcp"

    # 计算日期范围
    cutoff_date = datetime.now() - timedelta(days=days)

    headers = {
        'Authorization': f'Bearer {mcp_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream'
    }

    # MCP 请求：使用 memo_search 工具（不带参数获取所有笔记）
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "memo_search",
            "arguments": {}
        }
    }

    req = urllib.request.Request(
        mcp_url,
        data=json.dumps(mcp_request).encode('utf-8'),
        headers=headers,
        method='POST'
    )

    notes = []
    try:
        with urllib.request.urlopen(req) as response:
            raw_response = response.read().decode('utf-8')

        # 解析 SSE 格式响应
        result = None
        for line in raw_response.split('\n'):
            if line.startswith('data: '):
                try:
                    result = json.loads(line[6:])
                    break
                except json.JSONDecodeError:
                    continue

        if result and 'result' in result:
            content = result['result'].get('content', [])
            for item in content:
                if item.get('type') == 'text':
                    text = item.get('text', '')
                    # 尝试解析为 JSON
                    try:
                        data = json.loads(text)
                        memos = data.get('memos', [])
                        if isinstance(memos, list):
                            for memo in memos:
                                created_at = memo.get('created_at', '')
                                if created_at:
                                    # 解析日期并筛选
                                    try:
                                        note_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                        if note_date.replace(tzinfo=None) >= cutoff_date:
                                            # 提取标签
                                            tags = memo.get('tags', [])
                                            if not isinstance(tags, list):
                                                tags = []

                                            notes.append({
                                                'source': 'flomo',
                                                'date': note_date.strftime('%Y-%m-%d'),
                                                'title': '',  # Flomo 笔记通常没有标题
                                                'content': memo.get('content', ''),
                                                'tags': tags,
                                                'note_id': memo.get('id', '')
                                            })
                                    except (ValueError, AttributeError):
                                        # 日期解析失败，跳过
                                        pass
                    except json.JSONDecodeError:
                        # 如果不是 JSON，跳过
                        pass

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"[Flomo] API 错误: {e.code} - {error_body}")

    except Exception as e:
        print(f"[Flomo] 请求失败: {e}")

    print(f"[Flomo] 拉取到 {len(notes)} 条笔记")
    return notes


def write_flomo(webhook_url: str, content: str, tags: List[str] = None) -> bool:
    """通过 Webhook API 写入 Flomo 笔记"""
    import urllib.request
    import urllib.error

    if not webhook_url:
        print("[Flomo] 未配置 webhook_url，跳过写入")
        return False

    # 去除空行，保留单个换行
    content = re.sub(r'\n\s*\n', '\n', content).strip()

    payload = {'content': content}
    if tags:
        payload['tags'] = tags

    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get('code') == 0:
                print("[Flomo] 写入成功")
                return True
            else:
                print(f"[Flomo] 写入失败: {result.get('message', '未知错误')}")
                return False
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"[Flomo] API 错误: {e.code} - {error_body}")
        return False
    except Exception as e:
        print(f"[Flomo] 请求失败: {e}")
        return False


# ============================================================
# 主程序
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='统一拉取三个平台笔记数据')
    parser.add_argument('--days', type=int, default=7, help='拉取最近 N 天的笔记（默认 7）')
    parser.add_argument('--output', type=str, help='输出文件路径（默认 auto）')
    parser.add_argument('--platforms', type=str, default='all',
                        help='拉取的平台，逗号分隔：yinxiang,getnote,flomo（默认 all）')

    args = parser.parse_args()

    # 加载配置
    config = load_config()
    ensure_output_dir()

    # 确定要拉取的平台
    platforms = args.platforms.split(',') if args.platforms != 'all' else ['yinxiang', 'getnote', 'flomo']

    all_notes = []

    # 拉取各平台数据
    if 'yinxiang' in platforms:
        yx_config = config.get('yinxiang', {})
        if yx_config.get('token'):
            notes = fetch_yinxiang(yx_config['token'], yx_config.get('notebook', '04-10 晨间日记'), args.days)
            all_notes.extend(notes)
        else:
            print("[印象笔记] 未配置 token，跳过")

    if 'getnote' in platforms:
        gn_config = config.get('getnote', {})
        if gn_config.get('api_key') and gn_config.get('client_id'):
            notes = fetch_getnote(gn_config['api_key'], gn_config['client_id'], args.days)
            all_notes.extend(notes)
        else:
            print("[Get笔记] 未配置凭证，跳过")

    if 'flomo' in platforms:
        flomo_config = config.get('flomo', {})
        if flomo_config.get('mcp_token'):
            notes = fetch_flomo(flomo_config['mcp_token'], args.days)
            all_notes.extend(notes)
        else:
            print("[Flomo] 未配置 token，跳过")

    # 按日期排序
    all_notes.sort(key=lambda x: x.get('date', ''), reverse=True)

    # 构建输出
    output = {
        'fetch_time': datetime.now().isoformat(),
        'days': args.days,
        'total_notes': len(all_notes),
        'platforms': {
            'yinxiang': len([n for n in all_notes if n['source'] == 'yinxiang']),
            'getnote': len([n for n in all_notes if n['source'] == 'getnote']),
            'flomo': len([n for n in all_notes if n['source'] == 'flomo'])
        },
        'notes': all_notes
    }

    # 确定输出路径
    if args.output:
        output_path = args.output
    else:
        date_str = datetime.now().strftime('%Y%m%d')
        output_path = os.path.join(OUTPUT_DIR, f'notes_{date_str}.json')

    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成! 共拉取 {len(all_notes)} 条笔记")
    print(f"  印象笔记: {output['platforms']['yinxiang']} 条")
    print(f"  Get笔记: {output['platforms']['getnote']} 条")
    print(f"  Flomo: {output['platforms']['flomo']} 条")
    print(f"\n输出文件: {output_path}")


if __name__ == "__main__":
    main()
