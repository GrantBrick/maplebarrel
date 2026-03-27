#!/usr/bin/env python3
"""
journAIsts.ca (Maple Barrel) — Static Site Builder
Запуск: python build.py
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
POSTS_PER_PAGE = 21        # кратно 3 для красивой сетки
TG_CHANNEL = "https://t.me/maplebarrel"

MATERIAL_SRCS = {
    'macleans.ca': "Maclean's", 
    'theatlantic.com': "The Atlantic", 
    'thehub.ca': "The Hub", 
    'spectator.com': "Spectator",
    'westernstandard.news': "Western Standard", 
    'financialpost.com': "Financial Post", 
    'nytimes.com': "NYT",
    'nationalpost.com': "National Post", 
    'torontosun.com': "Toronto Sun"
}

TOP_TAGS = [
    'тарифы', 'иммиграция', 'жильё', 'выборы', 'экономика',
    'энергетика', 'преступность', 'Онтарио', 'Квебек',
    'Торонто', 'Арктика', 'IRCC', 'США–Канада', 'Украина'
]
TOP_PERSONS = [
    'Марк Карни', 'Пьер Полиев', 'Даг Форд', 'Джастин Трюдо', 
    'Дональд Трамп', 'Мелани Жоли', 'Христя Фриланд'
]

# ── СТИЛИ (CSS) ────────────────────────────────────────
COMMON_CSS = """
:root {
    --bg: #f9fafb;
    --card-bg: #ffffff;
    --text-main: #111827;
    --text-muted: #6b7280;
    --accent: #2563eb; /* Технологичный синий для AI */
    --border: #e5e7eb;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { 
    font-family: 'Inter', -apple-system, sans-serif; 
    line-height: 1.5; color: var(--text-main); background: var(--bg); 
}
a { color: inherit; text-decoration: none; }

header { 
    background: #fff; border-bottom: 1px solid var(--border); 
    padding: 1.5rem 0; position: sticky; top: 0; z-index: 100;
}
.header-content { 
    max-width: 1200px; margin: 0 auto; padding: 0 20px;
    display: flex; justify-content: space-between; align-items: center;
}
.logo { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.05em; }
.logo span { color: var(--accent); } /* Выделение AI */

.container { max-width: 1200px; margin: 2rem auto; padding: 0 20px; }

/* Сетка постов */
.posts-grid { 
    display: grid; 
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); 
    gap: 2rem; 
}

.post-card { 
    background: var(--card-bg); border-radius: 16px; overflow: hidden;
    border: 1px solid var(--border); transition: transform 0.2s, box-shadow 0.2s;
    display: flex; flex-direction: column;
}
.post-card:hover { transform: translateY(-4px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }

.post-image-wrap { width: 100%; height: 200px; overflow: hidden; background: #eee; }
.post-image { width: 100%; height: 100%; object-fit: cover; }

.post-body { padding: 1.5rem; flex-grow: 1; }
.post-date { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }
.post-text { margin-top: 0.75rem; font-size: 1rem; color: #374151; display: -webkit-box; -webkit-line-clamp: 6; -webkit-box-orient: vertical; overflow: hidden; }

.post-footer { padding: 1rem 1.5rem; border-top: 1px solid var(--border); display: flex; flex-wrap: wrap; gap: 0.5rem; }
.badge { font-size: 0.7rem; padding: 4px 10px; border-radius: 6px; font-weight: 500; }
.tag-badge { background: #f3f4f6; color: #4b5563; }
.person-badge { background: #eff6ff; color: var(--accent); }

.pagination { margin-top: 3rem; text-align: center; }
.btn { padding: 0.75rem 1.5rem; background: #fff; border: 1px solid var(--border); border-radius: 8px; font-weight: 600; cursor: pointer; }
.btn:hover { background: #f3f4f6; }

@media (max-width: 600px) {
    .posts-grid { grid-template-columns: 1fr; }
}
"""

# ── ЛОГИКА СБОРКИ ──────────────────────────────────────
def slugify(text):
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text).strip('-')

def format_date(iso_str):
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime("%d.%m.%Y")

def wrap_html(title, content):
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | journAIsts.ca</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
    <style>{COMMON_CSS}</style>
</head>
<body>
    <header>
        <div class="header-content">
            <a href="/" class="logo">journ<span>AI</span>sts</a>
            <nav style="display:flex; gap:1.5rem; font-size:0.9rem; font-weight:500;">
                <a href="/">Главная</a>
                <a href="{TG_CHANNEL}" target="_blank">Telegram</a>
            </nav>
        </div>
    </header>
    <main class="container">
        {content}
    </main>
    <footer style="text-align:center; padding: 4rem 0; color: var(--text-muted); font-size: 0.8rem;">
        &copy; 2026 journAIsts.ca | Powered by Maple Barrel
    </footer>
</body>
</html>"""

def build_post_card(p):
    img_html = ""
    if p.get('photo'):
        img_name = os.path.basename(p['photo'])
        img_html = f'<div class="post-image-wrap"><img src="/photos/{img_name}" class="post-image" loading="lazy"></div>'
    
    tags = "".join([f'<a href="/tag/{slugify(t)}/" class="badge tag-badge">#{t}</a>' for t in (p.get('tags') or [])])
    pers = "".join([f'<a href="/person/{slugify(pe)}/" class="badge person-badge">{pe}</a>' for pe in (p.get('persons') or [])])
    
    return f"""
    <div class="post-card">
        {img_html}
        <div class="post-body">
            <span class="post-date">{format_date(p['date'])}</span>
            <div class="post-text">{p['text_clean']}</div>
        </div>
        <div class="post-footer">
            {pers} {tags}
        </div>
    </div>
    """

def parse_messages():
    json_path = os.path.join(DATA_DIR, 'result.json')
    if not os.path.exists(json_path): return []
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    processed = []
    for m in data.get('messages', []):
        if m.get('type') != 'message' or not m.get('text'): continue
        
        raw_text = "".join([pt['text'] if isinstance(pt, dict) else pt for pt in (m['text'] if isinstance(m['text'], list) else [m['text']])])
        
        found_tags = [t for t in TOP_TAGS if t.lower() in raw_text.lower()]
        found_pers = [p for p in TOP_PERSONS if p.lower() in raw_text.lower()]
        
        processed.append({
            'date': m['date'],
            'text_clean': raw_text.split("​")[0].strip(),
            'photo': m.get('photo'),
            'tags': list(set(found_tags)),
            'persons': list(set(found_pers))
        })
    return sorted(processed, key=lambda x: x['date'], reverse=True)

def write_file(path, content):
    full_path = os.path.join(SITE_DIR, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f: f.write(content)

def main():
    if os.path.exists(SITE_DIR): shutil.rmtree(SITE_DIR)
    os.makedirs(SITE_DIR)
    
    # Копируем картинки
    if os.path.exists(os.path.join(DATA_DIR, 'photos')):
        shutil.copytree(os.path.join(DATA_DIR, 'photos'), os.path.join(SITE_DIR, 'photos'))

    posts = parse_messages()
    
    # Главная страница
    total_pages = -(-len(posts) // POSTS_PER_PAGE)
    for p_idx in range(1, total_pages + 1):
        start = (p_idx - 1) * POSTS_PER_PAGE
        page_posts = posts[start : start + POSTS_PER_PAGE]
        
        grid = '<div class="posts-grid">' + "".join([build_post_card(p) for p in page_posts]) + '</div>'
        
        nav = '<div class="pagination">'
        if p_idx > 1: nav += f'<a href="/{"page/"+str(p_idx-1) if p_idx > 2 else ""}" class="btn">← Сюда</a> '
        if p_idx < total_pages: nav += f'<a href="/page/{p_idx+1}/" class="btn">Туда →</a>'
        nav += '</div>'
        
        html = wrap_html("Главная", grid + nav)
        write_file('index.html' if p_idx == 1 else f'page/{p_idx}/index.html', html)

    # Теги
    all_tags = set()
    for p in posts: all_tags.update(p['tags'])
    for t in all_tags:
        t_posts = [p for p in posts if t in p['tags']]
        grid = f'<h1>#{t}</h1><div class="posts-grid" style="margin-top:2rem">' + "".join([build_post_card(p) for p in t_posts]) + '</div>'
        write_file(f'tag/{slugify(t)}/index.html', wrap_html(f"Тема: {t}", grid))

    print(f"✅ Готово! Сайт собран в /{SITE_DIR}")

if __name__ == "__main__":
    main()