#!/usr/bin/env python3
"""
Maple Barrel — Static Site Builder
Запуск: python build.py
Результат: папка /site/ готова для Cloudflare Pages (journalists.ca)
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
DATA_DIR = "data"          # папка с result.json и photos/
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
    --bg: #fdfdfd;
    --card-bg: #ffffff;
    --text-main: #1a1a1a;
    --text-muted: #666666;
    --accent: #c53030; /* Канадский красный */
    --border: #eeeeee;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { 
    font-family: 'Inter', -apple-system, system-ui, sans-serif; 
    line-height: 1.7; color: var(--text-main); background: var(--bg); 
}
a { color: inherit; text-decoration: none; }

header { 
    background: #fff; border-bottom: 1px solid var(--border); 
    padding: 1.5rem 0; position: sticky; top: 0; z-index: 100;
}
.header-content { 
    max-width: 900px; margin: 0 auto; padding: 0 20px;
    display: flex; justify-content: space-between; align-items: center;
}
.logo { font-size: 1.6rem; font-weight: 800; letter-spacing: -0.04em; color: var(--accent); }
.nav-menu { display: flex; gap: 1.5rem; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
.nav-menu a:hover { color: var(--accent); }

.container { max-width: 800px; margin: 3rem auto; padding: 0 20px; }

/* Список постов */
.posts-list { display: flex; flex-direction: column; gap: 4rem; }
.post-card { border-bottom: 1px solid var(--border); padding-bottom: 4rem; }
.post-card:last-child { border-bottom: none; }

.post-image-wrap { width: 100%; margin-bottom: 1.5rem; border-radius: 8px; overflow: hidden; }
.post-image { width: 100%; height: auto; display: block; }

.post-date { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem; display: block; }
.post-content { font-size: 1.15rem; white-space: pre-wrap; word-wrap: break-word; }
.post-content b, .post-content strong { font-weight: 700; }
.post-content a { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }

.post-footer { margin-top: 1.5rem; display: flex; flex-wrap: wrap; gap: 0.5rem; }
.badge { font-size: 0.75rem; padding: 4px 12px; border-radius: 4px; background: #f5f5f5; color: #444; font-weight: 500; }
.person-badge { background: #fff1f1; color: var(--accent); }

.pagination { margin: 5rem 0; text-align: center; display: flex; justify-content: center; gap: 1rem; }
.btn { padding: 0.8rem 1.5rem; background: #fff; border: 1px solid #ddd; border-radius: 6px; font-weight: 600; cursor: pointer; }
.btn:hover { border-color: var(--accent); color: var(--accent); }

.page-title { margin-bottom: 3rem; font-size: 2rem; font-weight: 800; }
footer { text-align: center; padding: 5rem 0; color: #999; font-size: 0.8rem; border-top: 1px solid var(--border); }

@media (max-width: 600px) {
    header .nav-menu { display: none; } /* Упрощаем для мобилок */
}
"""

# ── ЛОГИКА ОБРАБОТКИ ТЕКСТА ────────────────────────────
def slugify(text):
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')

def format_date(iso_str):
    dt = datetime.fromisoformat(iso_str)
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", 
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return f"{dt.day} {months[dt.month-1]} {dt.year}"

def parse_html_text(msg):
    """Восстанавливает форматирование из JSON Telegram"""
    if not msg.get('text'): return ""
    if isinstance(msg['text'], str): return msg['text']
    
    res = ""
    for part in msg['text']:
        if isinstance(part, str):
            res += part
        else:
            txt = part.get('text', '')
            ptype = part.get('type')
            if ptype == 'bold': res += f"<b>{txt}</b>"
            elif ptype == 'italic': res += f"<i>{txt}</i>"
            elif ptype in ['link', 'text_link']: res += f'<a href="{part.get("href")}">{txt}</a>'
            else: res += txt
    return res

def parse_messages():
    json_path = os.path.join(DATA_DIR, 'result.json')
    if not os.path.exists(json_path): return []
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    processed = []
    for m in data.get('messages', []):
        if m.get('type') != 'message' or not m.get('text'): continue
        
        html_content = parse_html_text(m)
        raw_text = "".join([pt['text'] if isinstance(pt, dict) else pt for pt in (m['text'] if isinstance(m['text'], list) else [m['text']])])
        
        processed.append({
            'id': m['id'],
            'date': m['date'],
            'html': html_content,
            'photo': m.get('photo'),
            'tags': [t for t in TOP_TAGS if t.lower() in raw_text.lower()],
            'persons': [p for p in TOP_PERSONS if p.lower() in raw_text.lower()],
            'is_longread': any(mark.lower() in raw_text.lower() for mark in LONGREAD_MARKERS),
            'is_material': any(src.lower() in raw_text.lower() for src in MATERIAL_SRCS)
        })
    return sorted(processed, key=lambda x: x['date'], reverse=True)

# ── ГЕНЕРАЦИЯ СТРАНИЦ ──────────────────────────────────
def wrap_html(title, content):
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | Maple Barrel</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
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
                <a href="{TG_CHANNEL}" target="_blank">Telegram</a>
            </nav>
        </div>
    </header>
    <main class="container">
        {content}
    </main>
    <footer>
        &copy; 2024–2026 Maple Barrel. Все права защищены.
    </footer>
</body>
</html>"""

def build_post(p):
    img = ""
    if p.get('photo'):
        img = f'<div class="post-image-wrap"><img src="/photos/{os.path.basename(p["photo"])}" class="post-image"></div>'
    
    tags = "".join([f'<a href="/tag/{slugify(t)}/" class="badge">#{t}</a>' for t in p['tags']])
    pers = "".join([f'<a href="/person/{slugify(pe)}/" class="badge person-badge">{pe}</a>' for pe in p['persons']])
    
    return f"""
    <article class="post-card">
        <span class="post-date">{format_date(p['date'])}</span>
        {img}
        <div class="post-content">{p['html']}</div>
        <div class="post-footer">{pers} {tags}</div>
    </article>
    """

def write_f(path, content):
    full = os.path.join(SITE_DIR, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f: f.write(content)

def main():
    if os.path.exists(SITE_DIR): shutil.rmtree(SITE_DIR)
    os.makedirs(SITE_DIR)
    
    if os.path.exists(os.path.join(DATA_DIR, 'photos')):
        shutil.copytree(os.path.join(DATA_DIR, 'photos'), os.path.join(SITE_DIR, 'photos'))

    posts = parse_messages()

    def create_section(post_list, title, prefix=""):
        total = -(-len(post_list) // POSTS_PER_PAGE)
        for i in range(1, total + 1):
            start = (i - 1) * POSTS_PER_PAGE
            page_posts = post_list[start : start + POSTS_PER_PAGE]
            html_list = f'<h1 class="page-title">{title}</h1><div class="posts-list">' + "".join([build_post(p) for p in page_posts]) + '</div>'
            
            nav = '<div class="pagination">'
            if i > 1: nav += f'<a href="/{prefix}{"page/"+str(i-1)+"/" if i > 2 else ""}" class="btn">← Назад</a>'
            if i < total: nav += f'<a href="/{prefix}page/{i+1}/" class="btn">Вперед →</a>'
            nav += '</div>'
            
            write_f(f'{prefix}{"index.html" if i==1 else "page/"+str(i)+"/index.html"}', wrap_html(title, html_list + nav))

    # Сборка всех разделов
    create_section(posts, "Главная лента")
    create_section([p for p in posts if p['is_material']], "Материалы", "materials/")
    create_section([p for p in posts if p['is_longread']], "Лонгриды", "longreads/")

    # Теги и персоны
    tags_idx = defaultdict(list)
    pers_idx = defaultdict(list)
    for p in posts:
        for t in p['tags']: tags_idx[t].append(p)
        for pe in p['persons']: pers_idx[pe].append(p)
    
    for t, t_posts in tags_idx.items(): create_section(t_posts, f"Тема: #{t}", f"tag/{slugify(t)}/")
    for pe, p_posts in pers_idx.items(): create_section(p_posts, f"Персона: {pe}", f"person/{slugify(pe)}/")

    # Статика
    write_f('about/index.html', wrap_html("О проекте", "<h1 class='page-title'>О проекте</h1><p>Maple Barrel — авторский взгляд на политику и жизнь в Канаде.</p>"))

    print(f"✅ Готово! Maple Barrel собран в /{SITE_DIR}")

if __name__ == "__main__":
    main()