#!/usr/bin/env python3
"""
Maple Barrel — Static Site Builder (Исправленная версия)
Сайт: journalists.ca
"""

import json
import os
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime

# ── НАСТРОЙКИ ──────────────────────────────────────────
BASE_URL = "https://journalists.ca"
SITE_DIR = "site"
DATA_DIR = "Data"  # Папка с большой буквы, как в твоем репозитории
POSTS_PER_PAGE = 25
TG_CHANNEL = "https://t.me/maplebarrel"

MATERIAL_SRCS = {
    'macleans.ca', 'theatlantic.com', 'thehub.ca', 'spectator.com',
    'westernstandard.news', 'financialpost.com', 'nytimes.com',
    'nationalpost.com', 'torontosun.com', 'theglobeandmail.com', 'cbc.ca'
}
LONGREAD_MARKERS = [
    'огромный материал', 'зацените оригинал', 'прекрасно оформлен',
    'обязательно зацените', 'кучу данн', 'большой текст', 'лонгрид'
]

# Списки тегов и персон из твоего оригинального скрипта
TOP_TAGS = [
    'тарифы', 'иммиграция', 'жильё', 'выборы', 'экономика',
    'энергетика', 'преступность', 'Онтарио', 'Квебек',
    'Торонто', 'Арктика', 'IRCC', 'США–Канада', 'Украина'
]
TOP_PERSONS = [
    'Марк Карни', 'Пьер Полиев', 'Даг Форд', 'Джастин Трюдо', 
    'Дональд Трамп', 'Мелани Жоли', 'Христя Фриланд', 'Марк Миллер'
]

# ── СТИЛИ (CSS) ────────────────────────────────────────
COMMON_CSS = """
:root {
    --bg: #ffffff;
    --text-main: #1a1a1a;
    --text-muted: #666666;
    --accent: #c53030;
    --border: #eeeeee;
    --bg-alt: #f9f9f9;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { 
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
    line-height: 1.6; color: var(--text-main); background: var(--bg); 
}
a { color: inherit; text-decoration: none; }
header { 
    background: #fff; border-bottom: 1px solid var(--border); 
    padding: 1.2rem 0; position: sticky; top: 0; z-index: 1000;
}
.header-content { 
    max-width: 800px; margin: 0 auto; padding: 0 20px;
    display: flex; justify-content: space-between; align-items: center;
}
.logo { font-size: 1.4rem; font-weight: 900; letter-spacing: -0.03em; color: var(--accent); }
.nav-menu { display: flex; gap: 1.2rem; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; }
.nav-menu a:hover { color: var(--accent); }
.container { max-width: 800px; margin: 2.5rem auto; padding: 0 20px; }
.post-card { margin-bottom: 4rem; padding-bottom: 4rem; border-bottom: 1px solid var(--border); }
.post-card:last-child { border-bottom: none; }
.post-date { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem; display: block; font-weight: 500; }
.post-image-wrap { width: 100%; margin-bottom: 1.5rem; border-radius: 8px; overflow: hidden; background: var(--bg-alt); }
.post-image { width: 100%; height: auto; display: block; }
.post-content { font-size: 1.15rem; white-space: pre-wrap; word-wrap: break-word; color: #222; }
.post-content b, .post-content strong { font-weight: 700; color: #000; }
.post-content a { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
.post-footer { margin-top: 1.5rem; display: flex; flex-wrap: wrap; gap: 0.5rem; }
.badge { 
    font-size: 0.75rem; padding: 5px 12px; border-radius: 4px; 
    background: var(--bg-alt); color: #555; font-weight: 600; border: 1px solid #eee;
}
.person-badge { border-color: #fed7d7; color: var(--accent); }
.pagination { margin: 4rem 0; text-align: center; display: flex; justify-content: center; gap: 1rem; }
.btn { padding: 0.8rem 1.5rem; background: #fff; border: 1px solid #ddd; border-radius: 6px; font-weight: 700; font-size: 0.9rem; cursor: pointer; }
.btn:hover { border-color: var(--accent); color: var(--accent); }
.page-title { margin-bottom: 3rem; font-size: 2.2rem; font-weight: 900; letter-spacing: -0.02em; }
footer { text-align: center; padding: 4rem 0; color: #aaa; font-size: 0.75rem; border-top: 1px solid var(--border); }
@media (max-width: 600px) { .nav-menu { display: none; } }
"""

# ── ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ────────────────────────────
def slugify(text):
    text = text.lower()
    chars = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    res = "".join([chars.get(c, c) for c in text])
    res = re.sub(r'[^\w\s-]', '', res)
    return re.sub(r'[\s-]+', '-', res).strip('-')

def format_date(iso_str):
    dt = datetime.fromisoformat(iso_str)
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return f"{dt.day} {months[dt.month-1]} {dt.year}"

def parse_html_text(msg):
    if not msg.get('text'): return ""
    if isinstance(msg['text'], str): return msg['text']
    res = ""
    for part in msg['text']:
        if isinstance(part, str): res += part
        else:
            txt = part.get('text', '')
            ptype = part.get('type')
            if ptype == 'bold': res += f"<b>{txt}</b>"
            elif ptype == 'italic': res += f"<i>{txt}</i>"
            elif ptype in ['link', 'text_link']: res += f'<a href="{part.get("href")}">{txt}</a>'
            else: res += txt
    return res

# ── ГЕНЕРАЦИЯ HTML ─────────────────────────────────────
def wrap_html(title, content):
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | Maple Barrel</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
    <header>
        <div class="header-content">
            <a href="/" class="logo">MAPLE BARREL</a>
            <nav class="nav-menu">
                <a href="/materials/">Материалы</a>
                <a href="/longreads/">Лонгриды</a>
                <a href="/about/">О проекте</a>
            </nav>
        </div>
    </header>
    <main class="container">{content}</main>
    <footer>&copy; 2024–2026 Maple Barrel. Journalists.ca</footer>
</body>
</html>"""

def build_post_card(p):
    img = ""
    if p.get('photo'):
        img = f'<div class="post-image-wrap"><img src="/photos/{os.path.basename(p["photo"])}" class="post-image" loading="lazy"></div>'
    
    tags = "".join([f'<a href="/tag/{slugify(t)}/" class="badge">#{t}</a>' for t in p['tags']])
    pers = "".join([f'<a href="/person/{slugify(pe)}/" class="badge person-badge">{pe}</a>' for pe in p['persons']])
    
    return f"""<article class="post-card">
        <span class="post-date">{format_date(p['date'])}</span>
        {img}
        <div class="post-content">{p['html']}</div>
        <div class="post-footer">{pers} {tags}</div>
    </article>"""

def main():
    print("🚀 Сборка Maple Barrel...")
    if os.path.exists(SITE_DIR): shutil.rmtree(SITE_DIR)
    os.makedirs(SITE_DIR)
    
    photo_src = os.path.join(DATA_DIR, 'photos')
    if os.path.exists(photo_src):
        shutil.copytree(photo_src, os.path.join(SITE_DIR, 'photos'))

    json_path = os.path.join(DATA_DIR, 'result.json')
    if not os.path.exists(json_path):
        print(f"❌ Ошибка: Файл {json_path} не найден")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    processed = []
    for m in data.get('messages', []):
        if m.get('type') != 'message' or not m.get('text'): continue
        
        html_content = parse_html_text(m)
        raw_text = "".join([pt['text'] if isinstance(pt, dict) else pt for pt in (m['text'] if isinstance(m['text'], list) else [m['text']])])
        
        processed.append({
            'date': m['date'],
            'html': html_content,
            'photo': m.get('photo'),
            'tags': [t for t in TOP_TAGS if t.lower() in raw_text.lower()],
            'persons': [p for p in TOP_PERSONS if p.lower() in raw_text.lower()],
            'is_longread': any(mark.lower() in raw_text.lower() for mark in LONGREAD_MARKERS),
            'is_material': any(src.lower() in raw_text.lower() for src in MATERIAL_SRCS)
        })
    
    posts = sorted(processed, key=lambda x: x['date'], reverse=True)

    def create_section(post_list, title, prefix=""):
        if not post_list: return
        total = -(-len(post_list) // POSTS_PER_PAGE)
        for i in range(1, total + 1):
            start = (i - 1) * POSTS_PER_PAGE
            page_posts = post_list[start : start + POSTS_PER_PAGE]
            html_list = f'<h1 class="page-title">{title}</h1>' + "".join([build_post_card(p) for p in page_posts])
            
            nav = '<div class="pagination">'
            if i > 1:
                prev_p = "" if i == 2 else f"page/{i-1}/"
                nav += f'<a href="/{prefix}{prev_p}" class="btn">← Назад</a>'
            if i < total:
                nav += f'<a href="/{prefix}page/{i+1}/" class="btn">Вперед →</a>'
            nav += '</div>'
            
            path = os.path.join(SITE_DIR, prefix, "index.html" if i==1 else f"page/{i}/index.html")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(wrap_html(title, html_list + nav))

    create_section(posts, "Главная")
    create_section([p for p in posts if p['is_material']], "Материалы", "materials/")
    create_section([p for p in posts if p['is_longread']], "Лонгриды", "longreads/")

    tags_idx = defaultdict(list)
    pers_idx = defaultdict(list)
    for p in posts:
        for t in p['tags']: tags_idx[t].append(p)
        for pe in p['persons']: pers_idx[pe].append(p)
    
    for t, t_posts in tags_idx.items(): create_section(t_posts, f"#{t}", f"tag/{slugify(t)}/")
    for pe, p_posts in pers_idx.items(): create_section(p_posts, f"{pe}", f"person/{slugify(pe)}/")

    write_path = os.path.join(SITE_DIR, 'about/index.html')
    os.makedirs(os.path.dirname(write_path), exist_ok=True)
    with open(write_path, 'w') as f:
        f.write(wrap_html("О проекте", "<h1>О проекте</h1><p>Maple Barrel — новости и аналитика Канады.</p>"))

    print(f"✨ Готово! Сайт собран в /{SITE_DIR}")

if __name__ == "__main__":
    main()