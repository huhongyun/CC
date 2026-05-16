#!/usr/bin/env python3
"""笔记融合分析：从三个平台的笔记中提取洞察，生成综合分析报告

报告结构：
1. 执行率分析（计划 vs 实际）
2. 时间分配分析
3. 关键洞察（主题聚类 + 反复问题 + 思维突破）
4. 下周建议
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict

# Windows 终端 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')


# ============================================================
# 晨间日记结构化提取
# ============================================================

def parse_diary(content: str, date: str) -> Dict:
    """从晨间日记中提取结构化信息"""
    result = {
        'date': date,
        'work': [],
        'exercise': '',
        'diet': '',
        'health': '',
        'sleep': '',
        'gratitude': [],
        'strengths': '',
        'improvements': '',
        'adjustments': '',
        'highlights': '',
    }

    # 工作：🐸 工作 到 健康与饮食 之间
    work_match = re.search(r'🐸\s*工作\s*(.*?)(?=健康与饮食|今日活动|$)', content, re.DOTALL)
    if work_match:
        work_text = work_match.group(1).strip()
        if work_text:
            result['work'] = [w.strip() for w in re.split(r'[；;、\n]', work_text) if w.strip()]

    # 锻炼
    m = re.search(r'今日锻炼[：:]\s*(.*?)(?=今日饮食|$)', content, re.DOTALL)
    if m:
        result['exercise'] = m.group(1).strip()

    # 饮食
    m = re.search(r'今日饮食[：:]\s*(.*?)(?=今日健康|$)', content, re.DOTALL)
    if m:
        result['diet'] = m.group(1).strip()

    # 健康
    m = re.search(r'今日健康[：:]\s*(.*?)(?=其他|$)', content, re.DOTALL)
    if m:
        result['health'] = m.group(1).strip()

    # 睡眠（起床/睡觉时间）
    wake = re.search(r'起床[：:]?\s*([\d.]+)', content)
    sleep_time = re.search(r'睡觉[：:]?\s*([\d.]+)', content)
    parts = []
    if wake:
        parts.append(f"起床 {wake.group(1)}")
    if sleep_time:
        parts.append(f"睡觉 {sleep_time.group(1)}")
    result['sleep'] = ' / '.join(parts)

    # 感恩
    m = re.search(r'感恩\s*(.*?)(?=表达善意|$)', content, re.DOTALL)
    if m:
        grat_text = m.group(1).strip()
        items = [g.strip() for g in re.split(r'感恩|，|。|\n', grat_text) if g.strip() and len(g.strip()) > 3]
        result['gratitude'] = items

    # 优点
    m = re.search(r'优点[：:]\s*(.*?)(?=改进点|$)', content, re.DOTALL)
    if m:
        result['strengths'] = m.group(1).strip()

    # 改进点
    m = re.search(r'改进点[：:]\s*(.*?)(?=调整|$)', content, re.DOTALL)
    if m:
        result['improvements'] = m.group(1).strip()

    # 调整（只取到第一个句号或换行）
    m = re.search(r'调整[：:]\s*(.+?)(?:。|\n|$)', content, re.DOTALL)
    if m:
        result['adjustments'] = m.group(1).strip()

    # 日记亮点（"我在"之后的自由文本）
    m = re.search(r'我在(.+)', content, re.DOTALL)
    if m:
        result['highlights'] = m.group(1).strip()

    return result


# ============================================================
# Get笔记分类
# ============================================================

def classify_getnote(note: Dict) -> str:
    """将 Get笔记分为：meeting / reflection / daily"""
    title = note.get('title', '')
    content = note.get('content', '')
    combined = title + ' ' + content

    meeting_kw = ['会议', '讨论', '沟通', '对接', '协调', '洽谈', '汇报', '对齐', '评审', '复盘', '电话会']
    reflection_kw = ['反思', '感悟', '觉察', '领悟', '顿悟', '思考', '认知', '意识到', '我发现', '理解了',
                     '焦虑', '正念', '当下', '五蕴', '哲学', '活在', '接受']

    meeting_score = sum(1 for kw in meeting_kw if kw in combined)
    reflection_score = sum(1 for kw in reflection_kw if kw in combined)

    if meeting_score >= 2:
        return 'meeting'
    if reflection_score >= 1 and meeting_score == 0:
        return 'reflection'
    return 'daily'


# ============================================================
# 主题聚类
# ============================================================

THEME_KEYWORDS = {
    'AI与技术': ['AI', 'LLM', 'Agent', 'Prompt', '大模型', '神经网络', '机器学习',
                 'Claude', 'GPT', '上下文', '模型', '算法', '特征工程', '提示词',
                 'RAG', '知识库', '向量', 'embedding', 'context engineering',
                 '最小知识集', '边界性掌握'],
    '工作管理': ['项目', '进度', '采购', '图纸', '模具', '设备', '生产', '加工',
                 '报价', '供应商', '客户', '订单', '验收', '调试', '安装',
                 '自动化', '机构设计', '机械', '工程', 'BOM', '外包', '降本',
                 '核心技术', '利润', '供应链'],
    '哲思与正念': ['正念', '当下', '五蕴', '无常', '因果', '修行', '觉察',
                  '臣服', '小我', '控制', '焦虑', '恐惧', '死亡', '存在',
                  '卡巴金', '克里希那穆提', '修心', '活在', '接受',
                  '特修斯', '哲学', '刹那'],
    '家庭与教育': ['女儿', '丫头', '爸爸', '家庭', '教育', '孩子', '学校',
                  '爷爷', '家人', '车站', '聊天', '遗传学', '实验',
                  '动物实验', '南京', '就诊'],
    '学习与阅读': ['阅读', '读书', '笔记', '学习', '课程', '书', '知识',
                  '概念', '理论', '框架', '思维', '认知', 'Flomo', '笔记法',
                  'Zettelkasten', '发芽', 'getseed', '费曼', '输出'],
    '健康与生活': ['锻炼', '运动', '八段锦', '睡眠', '饮食', '健康', '身体',
                  '膏药', '医院', '体检', '腰', '疼痛', '站立办公',
                  '站立式办公', '疲劳'],
}


def classify_theme(note: Dict) -> List[str]:
    """为一条笔记分配主题标签（最多2个）"""
    content = note.get('content', '')
    tags = note.get('tags', [])
    combined = content + ' ' + ' '.join(tags)

    themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score >= 1:
            themes.append((theme, score))

    themes.sort(key=lambda x: -x[1])
    return [t[0] for t in themes[:2]]


# ============================================================
# 分析引擎
# ============================================================

def analyze_execution_rate(diaries: List[Dict], getnotes: List[Dict], flomos: List[Dict]) -> Dict:
    """分析计划执行率：晨间日记中的工作事项 vs Get笔记/Flomo中的完成记录"""
    result = {
        'diary_plans': [],
        'completed': [],
        'not_completed': [],
        'partial': [],
    }

    # 从晨间日记提取工作内容作为计划
    for diary in diaries:
        date = diary['date']
        for item in diary.get('work', []):
            if item and len(item) > 2:
                result['diary_plans'].append({'date': date, 'plan': item})

    # 构建活动索引
    activity_notes = []
    for gn in getnotes:
        activity_notes.append({'date': gn['date'], 'content': gn['content'], 'title': gn['title']})
    for fm in flomos:
        activity_notes.append({'date': fm['date'], 'content': fm['content'], 'title': ''})

    done_kw = ['搞定', '完成', '做好', '弄好', '结束', '交付', '确认', '通过', '解决了', '搞定']

    for plan_item in result['diary_plans']:
        plan_date = plan_item['date']
        plan_text = plan_item['plan']
        plan_keywords = [w for w in re.split(r'[，,、：:\s]+', plan_text) if len(w) >= 2]

        # 如果关键词太少（如"远程办公"），放宽到只要1个匹配
        min_match = 1 if len(plan_keywords) <= 2 else 2

        found = False
        for note in activity_notes:
            if note['date'] < plan_date:
                continue
            note_text = note['title'] + ' ' + note['content']
            match_count = sum(1 for kw in plan_keywords if kw in note_text)
            if match_count >= min_match:
                if any(kw in note_text for kw in done_kw):
                    result['completed'].append(plan_item)
                else:
                    result['partial'].append(plan_item)
                found = True
                break

        if not found:
            result['not_completed'].append(plan_item)

    return result


def analyze_time_allocation(diaries: List[Dict], getnotes: List[Dict], flomos: List[Dict]) -> Dict:
    """分析时间分配"""
    allocation = {
        'work': {'meetings': [], 'other': []},
        'learning': [],
        'health': [],
        'life': [],
    }

    for gn in getnotes:
        category = classify_getnote(gn)
        entry = {'date': gn['date'], 'title': gn['title'][:60]}
        if category == 'meeting':
            allocation['work']['meetings'].append(entry)
        elif category == 'reflection':
            allocation['learning'].append({'date': gn['date'], 'type': '反思', 'title': gn['title'][:50]})
        else:
            allocation['work']['other'].append(entry)

    for fm in flomos:
        themes = classify_theme(fm)
        if 'AI与技术' in themes or '学习与阅读' in themes:
            allocation['learning'].append({'date': fm['date'], 'type': '学习', 'title': fm['content'][:50]})
        elif '哲思与正念' in themes:
            allocation['learning'].append({'date': fm['date'], 'type': '思考', 'title': fm['content'][:50]})
        elif '家庭与教育' in themes:
            allocation['life'].append({'date': fm['date'], 'content': fm['content'][:80]})
        elif '健康与生活' in themes:
            allocation['health'].append({'date': fm['date'], 'info': fm['content'][:50]})

    for d in diaries:
        if d.get('health'):
            allocation['health'].append({'date': d['date'], 'info': d['health'][:50]})
        if d.get('exercise'):
            allocation['health'].append({'date': d['date'], 'info': '锻炼: ' + d['exercise'][:40]})

    return allocation


def clean_snippet(text: str, max_len: int = 80) -> str:
    """清理笔记摘要，提取有效内容"""
    # Get笔记结构：📑 智能总结 → 录音信息（元数据）→ 录音总结（正文）
    # 优先提取"录音总结"之后的内容
    m = re.search(r'录音总结\s*(.+)', text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        # 去掉常见前缀噪音
        text = re.sub(r'📑\s*智能总结\s*', '', text)
        text = re.sub(r'####?\s*录音信息\s*', '', text)
        text = re.sub(r'####?\s*录音总结\s*', '', text)

    # 去掉残留的元数据行
    text = re.sub(r'\*?\*?录音时间\*?\*?\s*[：:]\s*[\d\-: ]+~?[\d\-: ]*', '', text)
    text = re.sub(r'\*?\*?时长\*?\*?\s*[：:]\s*约?\s*[\d小时分秒]+', '', text)
    text = re.sub(r'\*?\*?参与人数\*?\*?\s*[：:]\s*约?\s*\d+\s*人', '', text)
    text = re.sub(r'\*?\*?内容类型\*?\*?\s*[：:]\s*[^\n]*', '', text)

    # 去掉多余空白和标点
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^[，。、\-\*\s]+', '', text)
    return text[:max_len]


def build_theme_clusters(all_notes: List[Dict]) -> Dict[str, List[Dict]]:
    """主题聚类"""
    clusters = defaultdict(list)
    for note in all_notes:
        themes = classify_theme(note)
        for theme in themes:
            snippet = clean_snippet(note['content'])
            if snippet and len(snippet) > 10:
                clusters[theme].append({
                    'source': note['source'],
                    'date': note['date'],
                    'snippet': snippet,
                })
    return dict(clusters)


def extract_key_insights(diaries: List[Dict], flomos: List[Dict]) -> Dict:
    """提取关键洞察"""
    insights = {'breakthroughs': [], 'recurring_issues': []}

    for d in diaries:
        if d.get('improvements') and len(d['improvements']) > 5:
            adj = d.get('adjustments', '')
            # 去掉明显不属于调整方案的内容（后续diary文本泄漏）
            for noise in ['Claude', 'claude', 'chrome', 'Chrome', '小红书', 'surface',
                          '早晨', '今天我', '昨晚也']:
                idx = adj.find(noise)
                if idx > 0:
                    adj = adj[:idx].strip()
            # 去掉尾部逗号
            adj = adj.rstrip('，,。')
            insights['recurring_issues'].append({
                'date': d['date'],
                'issue': d['improvements'][:60],
                'adjustment': adj[:50] if adj else '',
            })
        if d.get('highlights') and len(d['highlights']) > 20:
            insights['breakthroughs'].append({
                'date': d['date'],
                'insight': d['highlights'][:120],
            })

    breakthrough_kw = ['意识到', '理解了', '感悟', '顿悟', '突然', '明白了', '发现', '原来']
    for fm in flomos:
        if any(kw in fm['content'] for kw in breakthrough_kw):
            insights['breakthroughs'].append({
                'date': fm['date'],
                'insight': fm['content'][:120],
            })

    return insights


# ============================================================
# 报告生成
# ============================================================

def generate_report(data: Dict) -> str:
    """生成结构化分析报告"""
    notes = data.get('notes', [])
    days = data.get('days', 7)

    # 按来源分类
    yinxiang = [n for n in notes if n['source'] == 'yinxiang']
    getnotes = [n for n in notes if n['source'] == 'getnote']
    flomos = [n for n in notes if n['source'] == 'flomo']

    # 解析晨间日记
    diaries = [parse_diary(n['content'], n['date']) for n in yinxiang]

    # 日期范围
    dates = sorted(set(n['date'] for n in notes))
    start_date = dates[0] if dates else '?'
    end_date = dates[-1] if dates else '?'

    # 执行分析
    execution = analyze_execution_rate(diaries, getnotes, flomos)
    time_alloc = analyze_time_allocation(diaries, getnotes, flomos)
    theme_clusters = build_theme_clusters(notes)
    insights = extract_key_insights(diaries, flomos)

    # ---- 组装报告 ----
    L = []
    L.append(f'# 本周回顾：{start_date} ~ {end_date}')
    L.append('')
    L.append(f'> 数据来源：印象笔记 {len(yinxiang)} 条 / Get笔记 {len(getnotes)} 条 / Flomo {len(flomos)} 条')
    L.append(f'> 分析时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}')
    L.append('')

    # ---- 一、执行率 ----
    L.append('---')
    L.append('')
    L.append('## 一、执行率分析（计划 vs 实际）')
    L.append('')

    L.append('### 晨间日记中的工作事项')
    L.append('')
    if execution['diary_plans']:
        cur_date = ''
        for p in execution['diary_plans']:
            if p['date'] != cur_date:
                L.append(f"**{p['date']}**")
                cur_date = p['date']
            L.append(f"- {p['plan']}")
        L.append('')
    else:
        L.append('本周晨间日记中未提取到明确的工作计划。')
        L.append('')

    L.append('### 执行情况')
    L.append('')
    total = len(execution['diary_plans'])
    done = len(execution['completed'])
    partial = len(execution['partial'])
    missed = len(execution['not_completed'])

    if execution['completed']:
        L.append('**已完成：**')
        for c in execution['completed']:
            L.append(f"- ✅ {c['plan']} ({c['date']})")
        L.append('')
    if execution['partial']:
        L.append('**进行中/部分完成：**')
        for p in execution['partial']:
            L.append(f"- 🔄 {p['plan']} ({p['date']})")
        L.append('')
    if execution['not_completed']:
        L.append('**未找到完成记录：**')
        for n in execution['not_completed']:
            L.append(f"- ❌ {n['plan']} ({n['date']})")
        L.append('')

    if total > 0:
        rate = (done + partial * 0.5) / total * 100
        L.append(f'**执行率：** {total} 项计划中，完成 {done} 项，部分完成 {partial} 项，执行率 {rate:.0f}%')
    else:
        rate = None
        L.append('**执行率：** 本周晨间日记未记录具体工作计划，无法计算执行率。')
    L.append('')

    # ---- 二、时间分配 ----
    L.append('---')
    L.append('')
    L.append('## 二、时间分配分析')
    L.append('')

    # 工作
    L.append('### 工作')
    L.append('')
    meetings = time_alloc['work']['meetings']
    other_work = time_alloc['work']['other']
    if meetings:
        L.append(f'**会议/沟通：** {len(meetings)} 次')
        # 只展示最近3天的代表性会议
        by_date = defaultdict(list)
        for m in meetings:
            by_date[m['date']].append(m)
        recent_dates = sorted(by_date.keys(), reverse=True)[:3]
        for d in recent_dates:
            items = by_date[d]
            L.append(f"- {d}（{len(items)} 次）: {items[0]['title']}")
            if len(items) > 1:
                L.append(f"  等共 {len(items)} 次会议/沟通")
        if len(by_date) > 3:
            L.append(f"  更早的日期还有 {sum(len(v) for k, v in by_date.items() if k not in recent_dates)} 次")
        L.append('')
    if other_work:
        L.append(f'**其他工作：** {len(other_work)} 项')
        for w in other_work[:5]:
            L.append(f"- {w['date']} {w['title']}")
        if len(other_work) > 5:
            L.append(f"  ...及其他 {len(other_work) - 5} 项")
        L.append('')
    if not meetings and not other_work:
        L.append('本周无明确的工作记录。')
        L.append('')

    # 学习
    L.append('### 学习与思考')
    L.append('')
    learning = time_alloc['learning']
    if learning:
        by_type = defaultdict(list)
        for l in learning:
            by_type[l.get('type', '学习')].append(l)
        for ltype, items in by_type.items():
            L.append(f'**{ltype}：** {len(items)} 条')
            for item in items[:3]:
                title = clean_snippet(item['title'], 50)
                L.append(f"- {item['date']} {title}")
            if len(items) > 3:
                L.append(f"  ...及其他 {len(items) - 3} 条")
            L.append('')
    else:
        L.append('本周无明确的学习/思考记录。')
        L.append('')

    # 健康
    L.append('### 健康')
    L.append('')
    health = time_alloc['health']
    if health:
        seen = set()
        for h in health:
            key = h.get('info', '') or h.get('content', '')
            if key and key not in seen:
                seen.add(key)
                L.append(f"- {h['date']}: {key}")
        L.append('')
    else:
        L.append('本周无明确的健康记录。')
        L.append('')

    # 生活
    L.append('### 生活')
    L.append('')
    life = time_alloc['life']
    if life:
        for l in life:
            snippet = l.get('content', '') or l.get('info', '')
            L.append(f"- {l['date']}: {snippet[:60]}")
        L.append('')
    else:
        L.append('本周无明确的生活记录。')
        L.append('')

    # ---- 三、关键洞察 ----
    L.append('---')
    L.append('')
    L.append('## 三、关键洞察')
    L.append('')

    # 主题分布
    L.append('### 本周主题分布')
    L.append('')
    if theme_clusters:
        sorted_themes = sorted(theme_clusters.items(), key=lambda x: -len(x[1]))
        for theme, items in sorted_themes:
            sources = defaultdict(int)
            for item in items:
                sources[item['source']] += 1
            source_str = ' / '.join(f'{k} {v}条' for k, v in sources.items())
            L.append(f'**{theme}**（{len(items)} 条：{source_str}）')
            shown = 0
            for item in items:
                if shown >= 3:
                    break
                snippet = item['snippet']
                if len(snippet) > 15:
                    L.append(f"  - [{item['date']}] {snippet[:70]}")
                    shown += 1
            L.append('')
    else:
        L.append('无法自动聚类主题。')
        L.append('')

    # 反复出现的问题
    if insights['recurring_issues']:
        L.append('### 反复出现的问题')
        L.append('')
        for issue in insights['recurring_issues']:
            issue_text = issue['issue']
            if len(issue_text) > 50:
                issue_text = issue_text[:50] + '...'
            L.append(f"- **{issue['date']}** 问题：{issue_text}")
            if issue['adjustment']:
                adj_text = issue['adjustment']
                if len(adj_text) > 40:
                    adj_text = adj_text[:40] + '...'
                L.append(f"  调整：{adj_text}")
        L.append('')

    # 思维突破
    if insights['breakthroughs']:
        L.append('### 思维突破')
        L.append('')
        seen_keys = []
        for bp in insights['breakthroughs']:
            snippet = clean_snippet(bp['insight'], 120)
            # 用前30字做近似去重
            key = snippet[:30]
            is_dup = False
            for sk in seen_keys:
                # 检查是否包含共同子串（处理偏移情况）
                # 取较短的key的前15字作为子串去匹配
                substr = key[:15] if len(key) >= 15 else key
                if substr in sk or sk[:15] in key:
                    is_dup = True
                    break
            if not is_dup and len(snippet) > 15:
                seen_keys.append(key)
                L.append(f"- [{bp['date']}] {snippet}")
        L.append('')

    # ---- 四、下周建议 ----
    L.append('---')
    L.append('')
    L.append('## 四、下周建议')
    L.append('')

    # 基于执行率
    L.append('### 基于执行率')
    L.append('')
    if rate is not None:
        if rate < 60:
            L.append('- 本周执行率偏低，建议：')
            L.append('  - 晨间日记只写 1-3 件最重要的事，不要列太多')
            L.append('  - 晚间回顾时对照检查，逐步提高执行率')
        elif rate < 80:
            L.append('- 本周执行率尚可，但仍有提升空间：')
            L.append('  - 区分"必须做"和"想做"，优先保证必须项')
        else:
            L.append('- 本周执行率不错，继续保持。')
    else:
        L.append('- 本周晨间日记没有明确的工作计划，建议：')
        L.append('  - 每天早晨花 3 分钟写下当天最重要的 1-3 件事')
        L.append('  - 具体、可衡量（如"完成XX图纸"而非"处理工作"）')
    L.append('')

    # 基于时间分配
    L.append('### 基于时间分配')
    L.append('')
    if len(meetings) > 5:
        L.append(f'- 本周会议 {len(meetings)} 次，较频繁。建议：')
        L.append('  - 评估哪些会议可以异步沟通或缩短时长')
        L.append('  - 为深度工作预留不被打断的时间块')
    if len(learning) == 0:
        L.append('- 本周缺少学习/思考记录。建议：')
        L.append('  - 每天花 15 分钟阅读或学习，记一条 Flomo')
        L.append('  - 不需要长篇大论，一两句话的感悟就够了')
    elif len(learning) > 0:
        L.append(f'- 本周有 {len(learning)} 条学习/思考记录，覆盖良好。')
    L.append('')

    # 基于知识链接
    L.append('### 基于知识链接')
    L.append('')
    if theme_clusters:
        cross_platform = []
        for theme, items in theme_clusters.items():
            sources = set(item['source'] for item in items)
            if len(sources) >= 2:
                cross_platform.append((theme, sources))
        if cross_platform:
            L.append('- 以下主题在多个平台出现，值得深入关联：')
            for theme, sources in cross_platform:
                L.append(f'  - **{theme}**（{" + ".join(sources)}）')
        else:
            L.append('- 本周各平台笔记主题较独立，建议：')
            L.append('  - 在 Flomo 中对 Get笔记/印象笔记的要点做二次整理和链接')
            L.append('  - 用标签或双向链接建立跨平台知识网络')
    L.append('')

    # 睡眠提醒
    sleep_issues = [d for d in diaries if d.get('improvements') and ('睡' in d['improvements'] or '短视频' in d['improvements'])]
    if sleep_issues:
        L.append('### 睡眠与作息')
        L.append('')
        L.append('- 本周有日记提到睡眠问题，注意：')
        for si in sleep_issues:
            L.append(f"  - {si['date']}：{si['improvements'][:60]}")
        L.append('')

    return '\n'.join(L)


# ============================================================
# 主程序
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='笔记融合分析')
    parser.add_argument('--input', type=str, help='输入 JSON 文件路径')
    parser.add_argument('--output', type=str, help='输出报告路径（默认 auto）')

    args = parser.parse_args()

    # 找到输入文件
    if args.input:
        input_path = args.input
    else:
        import glob
        pattern = os.path.join(OUTPUT_DIR, 'notes_*.json')
        files = sorted(glob.glob(pattern))
        if not files:
            print("错误: 未找到数据文件。请先运行 fetch_notes.py")
            sys.exit(1)
        input_path = files[-1]

    if not os.path.exists(input_path):
        print(f"错误: 输入文件不存在: {input_path}")
        sys.exit(1)

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"读取数据: {data.get('total_notes', '?')} 条笔记")

    report = generate_report(data)

    # 输出
    if args.output:
        output_path = args.output
    else:
        date_str = datetime.now().strftime('%Y%m%d')
        output_path = os.path.join(OUTPUT_DIR, f'report_{date_str}.md')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"报告已生成: {output_path}")


if __name__ == "__main__":
    main()
