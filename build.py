#!/usr/bin/env python3
"""
Maple Barrel — Static Site Builder
Запуск: python build.py
Результат: папка /site/ готова для Cloudflare Pages
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
POSTS_PER_PAGE = 40
TG_CHANNEL = "https://t.me/maplebarrel"

MATERIAL_SRCS = {
    'macleans.ca', 'theatlantic.com', 'thehub.ca', 'spectator.com',
    'westernstandard.news', 'financialpost.com', 'nytimes.com',
    'nationalpost.com', 'torontosun.com'
}
LONGREAD_MARKERS = [
    'огромный материал', 'зацените оригинал', 'прекрасно оформлен',
    'обязательно зацените', 'кучу данн', 'большой текст'
]

TOP_TAGS = [
    'тарифы', 'иммиграция', 'жильё', 'выборы', 'экономика',
    'энергетика', 'преступность', 'Онтарио', 'Квебек',
    'Торонто', 'Арктика', 'IRCC', 'США–Канада', 'Украина'
]
TOP_PERSONS = [
    'Марк Карни', 'Пьер Полиев', 'Даг Форд',
    'Дональд Трамп', 'Джастин Трюдо'
]

MONTHS_RU = ['','янв','фев','мар','апр','май','июн',
             'июл','авг','сен','окт','ноя','дек']
MONTHS_FULL = ['','января','февраля','марта','апреля','мая','июня',
               'июля','августа','сентября','октября','ноября','декабря']

SOURCE_EMOJI = {
    'cbc.ca':'📻','ctvnews.ca':'📺','theglobeandmail.com':'📰',
    'globalnews.ca':'🌐','thestar.com':'⭐','bloomberg.com':'💹',
    'nytimes.com':'🗽','theatlantic.com':'🌊','macleans.ca':'🍁',
    'thehub.ca':'🔵','torontosun.com':'☀️','nationalpost.com':'📋',
    'reuters.com':'🔴','theguardian.com':'🛡','financialpost.com':'💰',
    'apple.news':'🍎'
}

# ── УТИЛИТЫ ────────────────────────────────────────────

def slugify(text):
    ru = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    en = ['a','b','v','g','d','e','yo','zh','z','i','y','k','l','m',
          'n','o','p','r','s','t','u','f','h','ts','ch','sh','sch',
          '','y','','e','yu','ya']
    result = (text or '').lower()
    for i, char in enumerate(ru):
        result = result.replace(char, en[i])
    result = re.sub(r'[^a-z0-9\s-]', '', result)
    result = re.sub(r'[\s-]+', '-', result).strip('-')
    return result[:60]

def fmt_date(d):
    y, m, day = d.split('-')
    return f"{int(day)} {MONTHS_RU[int(m)]} {y}"

def fmt_date_full(d):
    y, m, day = d.split('-')
    return f"{int(day)} {MONTHS_FULL[int(m)]} {y} года"

def fmt_date_full_short(d):
    y, m, day = d.split('-')
    return f"{int(day)} {MONTHS_FULL[int(m)]} {y}"

def esc(s):
    return (s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def clean_body(text):
    text = (text or '').replace('\u200b','').replace('\xa0',' ')
    text = re.sub(r'Подписывайтесь на @maplebarrel[^\n]*', '', text)
    return text.strip()

def get_emoji(src):
    return SOURCE_EMOJI.get(src, '📰')

TAG_CATEGORIES = {
    'тарифы': 'eco', 'экономика': 'eco', 'жильё': 'eco', 'энергетика': 'eco',
    'иммиграция': 'imm', 'IRCC': 'imm',
    'выборы': 'pol', 'преступность': 'pol', 'США–Канада': 'pol', 'Украина': 'pol',
    'Онтарио': 'reg', 'Квебек': 'reg', 'Торонто': 'reg', 'Альберта': 'reg', 'Арктика': 'reg',
    'в глубину': 'deep',
}

def tag_html(t, href=True):
    """Render a single tag with category color."""
    label = t
    cat = TAG_CATEGORIES.get(t, 'def')
    cls = f'tag tag-{cat}'
    if href:
        slug = slugify(t)
        return f'<a class="{cls}" data-t="{esc(t)}" href="/tag/{slug}/">#{label}</a>'
    return f'<span class="{cls}" data-t="{esc(t)}">#{label}</span>'

def tags_row(tags, limit=3, skip_deep=True):
    filtered = [t for t in (tags or []) if not (skip_deep and t == 'в глубину')][:limit]
    return ''.join(tag_html(t) for t in filtered)

def post_slug(p):
    return f"{p['date']}-{slugify(p['title'])}"

def post_url(p):
    return f"/post/{post_slug(p)}/"

def post_img_src(p):
    photo = p.get('photo', '')
    if photo:
        return '/photos/' + photo.replace('photos/', '')
    return None

def is_longread(p):
    src = p.get('source', '') or ''
    body = ((p.get('body') or '') + ' ' + (p.get('title') or ''))[:500].lower()
    is_analytical = src in MATERIAL_SRCS
    has_marker = any(m in body for m in LONGREAD_MARKERS)
    return is_analytical or has_marker

def is_material(p):
    src = p.get('source', '') or ''
    return src in MATERIAL_SRCS

def tag_posts(posts):
    """Auto-tag posts with topics and persons."""
    TAGS = {
        'тарифы': ['тариф', 'пошлин', 'торговая война'],
        'иммиграция': ['иммиграц', 'мигрант', 'IRCC', 'иностранных студент', 'беженц', 'визы'],
        'жильё': ['жиль', 'аренд', 'ипотек', 'кондо', 'недвижимост'],
        'выборы': ['выборах', 'выборы', 'голосован', 'кампани', 'баллотир'],
        'экономика': ['экономик', 'инфляц', 'безработиц', 'рецессий', 'бюджет', 'дефицит'],
        'США–Канада': ['51-й штат', 'торговая война', 'тарифы США'],
        'Арктика': ['арктик', 'Арктике', 'Крайний Север'],
        'коренные народы': ['коренных народ', 'примирени', 'First Nations'],
        'энергетика': ['нефт', 'газ', 'энергетик', 'трубопровод', 'Ормузск'],
        'преступность': ['убийств', 'арест', 'стрельб', 'мошенничест', 'наркотик'],
        'технологии': ['искусственный интеллект', 'нейросет', 'ChatGPT', 'дата-центр'],
        'Онтарио': ['Онтарио'],
        'Квебек': ['Квебек'],
        'Альберта': ['Альберта'],
        'Торонто': ['Торонто'],
        'здоровье': ['здоровь', 'больниц', 'медицин', 'психическ'],
        'климат': ['климат', 'окружающая среда', 'пожар'],
        'Украина': ['Украин', 'война на Украин'],
        'IRCC': ['IRCC', 'иностранных студент'],
    }
    PERSONS = {
        'Карни': 'Марк Карни',
        'Трюдо': 'Джастин Трюдо',
        'Полиев': 'Пьер Полиев',
        'Форд': 'Даг Форд',
        'Трамп': 'Дональд Трамп',
        'Сингх': 'Джагмит Сингх',
        'Жоли': 'Мелани Жоли',
        'Маск': 'Илон Маск',
    }
    for p in posts:
        text = ((p.get('title') or '') + ' ' + (p.get('body') or '')).lower()
        tags = [t for t, kws in TAGS.items() if any(kw.lower() in text for kw in kws)]
        if is_longread(p) or is_material(p):
            tags = ['в глубину'] + [t for t in tags if t != 'в глубину']
        p['tags'] = tags[:5]
        p['persons'] = [full for key, full in PERSONS.items() if key.lower() in text][:3]
    return posts


# ── ПАРСИНГ result.json ────────────────────────────────

def parse_telegram_export(json_path):
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    posts = []
    for m in data.get('messages', []):
        if m.get('type') != 'message':
            continue

        entities = m.get('text_entities', [])
        links = []
        text_parts = []

        for e in entities:
            t = e.get('type', '')
            if t in ('plain', 'italic', 'hashtag', 'mention', 'bold'):
                text_parts.append(e.get('text', ''))
            elif t == 'text_link':
                text_parts.append(e.get('text', ''))
                links.append({'text': e.get('text',''), 'href': e.get('href','')})
            elif t == 'url':
                links.append({'text': e.get('text',''), 'href': e.get('text','')})

        raw_text = m.get('text', '')
        if isinstance(raw_text, str):
            full_text = raw_text.strip()
        else:
            full_text = ''.join(text_parts).strip()

        if len(full_text) < 60:
            continue

        lines = [l.strip() for l in full_text.split('\n')
                 if l.strip() and l.strip() not in ('\u200b', '\xa0')]
        title = lines[0][:160] if lines else full_text[:100]
        body = clean_body(full_text)
        if body.startswith(title):
            body = body[len(title):].strip().lstrip('\n').strip()

        from urllib.parse import urlparse
        source = ''
        source_url = ''
        if links:
            href = links[0]['href']
            source_url = href
            try:
                source = urlparse(href).netloc.replace('www.', '')
            except Exception:
                pass

        posts.append({
            'id': m['id'],
            'date': m['date'][:10],
            'title': title,
            'body': body,
            'excerpt': body[:200].replace('\n', ' ').strip(),
            'source': source,
            'source_url': source_url,
            'tg_url': f'https://t.me/maplebarrel/{m["id"]}',
            'photo': m.get('photo', ''),
        })

    return posts


# ── CSS / JS ОБЩИЕ ────────────────────────────────────
COMMON_CSS = """

:root{
  --bg:#ffffff;
  --card:#ffffff;
  --t:#111;
  --t2:#555;
  --t3:#888;
  --br:#e5e5e5;
--serif:'Playfair Display', Georgia, serif;
--sans:'Golos Text', system-ui, sans-serif;
}

body{
  background:#ffffff;
  color:#111;
  font-family:var(--sans);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--t);font-family:var(--sans);font-size:16px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
img{display:block;width:100%;height:100%;object-fit:cover}

/* ── NAV ── */
nav{background:var(--bg);border-bottom:1px solid var(--br);position:sticky;top:0;z-index:300;backdrop-filter:blur(6px)}
.ni{max-width:1300px;margin:0 auto;padding:0 20px;height:54px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.logo{font-family:var(--serif);font-size:20px;font-weight:900;letter-spacing:-.4px;display:flex;align-items:center;gap:5px;color:var(--cream)}
.logo .lf{color:var(--maple)}
.nav-links{display:flex;gap:1px}
.nl{font-size:13px;font-weight:500;color:var(--t3);padding:5px 12px;border-radius:5px;transition:all .15s;white-space:nowrap}
.nl:hover{color:var(--cream);background:var(--bg3)}
.nl.on{color:var(--cream);background:var(--bg3)}
.nav-r{display:flex;align-items:center;gap:10px}
.tgb{display:flex;align-items:center;gap:6px;background:rgba(91,155,213,.1);color:var(--tg2);border:1px solid rgba(91,155,213,.2);border-radius:18px;font-size:13px;font-weight:600;padding:5px 13px;text-decoration:none;transition:all .2s}
.tgb:hover{background:rgba(91,155,213,.2)}
.tgb{
  background:#c0392b;
  color:#fff;
  border-radius:6px;
  padding:6px 14px;
  font-weight:600;
  font-size:13px;
  border:none;
}

.tgb:hover{
  background:#a93226;
}

.wrap{max-width:1300px;margin:0 auto;padding:24px 20px 56px}

/* ── CARD SYSTEM ── */
/* Every card: dark bg, cream text, consistent image ratio, subtle shadow */
.card{
  background:#fff;
  border:1px solid #eee;
  border-radius:6px;
  overflow:hidden;
  transition:transform .15s;
}
.card:hover{
  transform:translateY(-2px);
}

/* Image container — always 16:9, consistent shadow on image */
.card-img{
  aspect-ratio:16/9;
  overflow:hidden;
  background:var(--bg4);
  flex-shrink:0;
  position:relative;
  display:flex;align-items:center;justify-content:center;

.card-img img{width:100%;height:100%;object-fit:cover;display:block}
.card-img .emoji-fallback{font-size:32px;color:var(--t4)}

/* Card body — cream-tinted text on dark */
.card-body{padding:14px 16px 16px;flex:1;display:flex;flex-direction:column;gap:6px}
.card-src{
  font-size:11px;
  font-weight:700;
  text-transform:uppercase;
  letter-spacing:.8px;
  color:#c0392b;
}
.card-title{
  font-family:var(--serif);
  font-size:17px;
  line-height:1.35;
  color:#111;
}
.card-excerpt{font-size:13px;color:var(--t2);line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-meta{display:flex;align-items:center;gap:8px;margin-top:auto;padding-top:8px;flex-wrap:wrap}
.card-date{font-size:10px;color:var(--t3)}
.card-tags{display:flex;gap:3px;flex-wrap:wrap}

/* Tags — topic-colored by category */
.tag{font-size:10px;font-weight:500;padding:2px 7px;border-radius:6px;white-space:nowrap;transition:opacity .12s}
.tag:hover{opacity:.8}
/* politics/elections */
.tag-pol{background:rgba(192,57,43,.15);color:#e87060;border:1px solid rgba(192,57,43,.25)}
/* economy/tariffs */
.tag-eco{background:rgba(201,150,58,.12);color:#d4a040;border:1px solid rgba(201,150,58,.22)}
/* immigration */
.tag-imm{background:rgba(91,155,213,.12);color:#7ab8f5;border:1px solid rgba(91,155,213,.22)}
/* regions */
.tag-reg{background:rgba(80,160,100,.12);color:#70c080;border:1px solid rgba(80,160,100,.22)}
/* longreads */
.tag-deep{background:rgba(150,100,200,.12);color:#c090e8;border:1px solid rgba(150,100,200,.22)}
/* default */
.tag-def{background:var(--bg4);color:var(--t3);border:1px solid var(--br2)}

/* Tag category mapping */
.tag[data-t="тарифы"],.tag[data-t="экономика"],.tag[data-t="жильё"]{background:rgba(201,150,58,.12);color:#d4a040;border:1px solid rgba(201,150,58,.22)}
.tag[data-t="иммиграция"],.tag[data-t="IRCC"]{background:rgba(91,155,213,.12);color:#7ab8f5;border:1px solid rgba(91,155,213,.22)}
.tag[data-t="выборы"],.tag[data-t="преступность"],.tag[data-t="США–Канада"]{background:rgba(192,57,43,.15);color:#e87060;border:1px solid rgba(192,57,43,.25)}
.tag[data-t="Онтарио"],.tag[data-t="Квебек"],.tag[data-t="Торонто"],.tag[data-t="Альберта"],.tag[data-t="Арктика"]{background:rgba(80,160,100,.12);color:#70c080;border:1px solid rgba(80,160,100,.22)}
.tag[data-t="в глубину"]{background:rgba(150,100,200,.12);color:#c090e8;border:1px solid rgba(150,100,200,.22)}
.tag[data-t="Украина"],.tag[data-t="энергетика"],.tag[data-t="климат"]{background:rgba(100,140,200,.12);color:#90b8e8;border:1px solid rgba(100,140,200,.22)}

/* ── PAGINATION ── */
.pgn{display:flex;gap:5px;justify-content:center;padding:32px 0 8px;flex-wrap:wrap}
.pb{padding:6px 13px;border-radius:5px;border:1px solid var(--br);background:var(--card);color:var(--t3);font-size:13px;transition:all .15s}
.pb:hover{border-color:var(--br2);color:var(--cream)}
.pb.on{background:var(--ac);color:#fff;border-color:var(--ac)}
.pb.disabled{opacity:.3;pointer-events:none}

/* ── TAG FILTER BAR ── */
.tag-bar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px}
.tc{font-size:12px;padding:4px 12px;border-radius:12px;border:1px solid var(--br);color:var(--t3);background:var(--card);transition:all .15s;white-space:nowrap}
.tc:hover{border-color:var(--br2);color:var(--cream)}
.tc.on{background:var(--ac);color:#fff;border-color:var(--ac)}

/* ── FOOTER ── */
footer{border-top:1px solid var(--br);padding:36px 20px;margin-top:56px}
.fi{max-width:1300px;margin:0 auto;display:grid;grid-template-columns:2fr 1fr 1fr;gap:36px}
.flogo{font-family:var(--serif);font-size:18px;font-weight:900;margin-bottom:8px;display:flex;align-items:center;gap:5px;color:var(--cream)}
.flogo .lf{color:var(--maple)}
.fdesc{font-size:13px;color:var(--t3);line-height:1.65;max-width:340px;margin-bottom:8px}
.fsrcs{font-size:11px;color:var(--t4);line-height:1.9}
.fcol h4{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--t4);margin-bottom:12px}
.fcol a{display:block;font-size:13px;color:var(--t3);margin-bottom:7px;transition:color .15s}
.fcol a:hover{color:var(--cream)}
.fcp{max-width:1300px;margin:20px auto 0;padding-top:18px;border-top:1px solid var(--br);display:flex;justify-content:space-between;font-size:12px;color:var(--t4)}

/* ── TG CTA ── */
.tgcta{display:flex;align-items:center;gap:16px;background:rgba(91,155,213,.07);border:1px solid rgba(91,155,213,.15);border-radius:8px;padding:18px 22px;margin-top:36px}
.tgcta svg{width:28px;height:28px;flex-shrink:0;color:var(--tg2)}
.ctxt{flex:1}
.ctit{font-weight:600;font-size:15px;margin-bottom:3px;color:var(--cream)}
.csub{font-size:13px;color:var(--t2)}
.ctgp{font-size:11px;color:var(--t3);margin-top:6px}
.ctgp a{color:var(--tg)}
.cbtn2{flex-shrink:0;background:var(--tg);color:#fff;font-size:13px;font-weight:600;padding:9px 18px;border-radius:5px;text-decoration:none;transition:all .15s;white-space:nowrap}
.cbtn2:hover{background:var(--tg2);color:#1a1a2e}

/* ── RESPONSIVE ── */
@media(max-width:900px){.fi{grid-template-columns:1fr}.nav-links .nl:not(.on){display:none}}
@media(max-width:640px){.ni{gap:8px}.tgcta{flex-direction:column;align-items:flex-start}}
"""
FONTS_LINK = '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Golos+Text:wght@400;500;600&display=swap" rel="stylesheet">'

TG_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12s5.37 12 12 12 12-5.37 12-12S18.63 0 12 0zm5.88 8.18l-2.02 9.52c-.15.67-.54.84-1.1.52l-3-2.21-1.45 1.39c-.16.16-.3.3-.61.3l.21-3.02 5.49-4.96c.24-.21-.05-.33-.37-.12L6.26 14.38l-2.96-.92c-.64-.2-.65-.64.14-.95l11.54-4.45c.53-.19 1 .13.9.12z"/></svg>'


# ── ШАБЛОНЫ ──────────────────────────────────────────
def nav_html(active='news'):
    return f"""
<nav style="background:#fff;border-bottom:1px solid #eee;">
  <div style="max-width:1200px;margin:0 auto;padding:14px 20px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center">

    <!-- LEFT -->
    <div style="display:flex;gap:16px;font-size:14px;color:#555">
      <a href="/" style="color:#000">Новости</a>
      <a href="/materials/">Материалы</a>
      <a href="/longreads/">Лонгриды</a>
    </div>

    <!-- CENTER LOGO -->
    <div style="text-align:center;font-family:Playfair Display,serif;font-size:28px;font-weight:700;color:#000">
      Maple <span style="color:#d44">🍁</span> Barrel
    </div>

    <!-- RIGHT -->
    <div style="display:flex;justify-content:flex-end;gap:16px;font-size:14px;color:#555">
      <a href="/about/">О проекте</a>
      <a href="{TG_CHANNEL}" style="color:#d44">Telegram</a>
    </div>

  </div>
</nav>
"""


def footer_html():
    tag_links = ''.join(
        f'<a href="/tag/{slugify(t)}/">#{t}</a>' for t in TOP_TAGS[:8]
    )
    person_links = ''.join(
        f'<a href="/person/{slugify(p)}/">{p}</a>' for p in TOP_PERSONS
    )
    return f"""<footer>
<div class="fi">
  <div>
    <div class="flogo"><span>Maple</span><span class="lf">🍁</span><span>Barrel</span></div>
    <p class="fdesc">Ежедневный обзор канадских СМИ на русском языке. Политика, экономика, общество Канады — отобрано и пересказано по-русски.</p>
    <p class="fsrcs">CBC · CTV · Globe and Mail · National Post · Global News · Bloomberg · Reuters · NY Times · Maclean's · The Atlantic · Toronto Star · The Hub</p>
  </div>
  <div class="fcol"><h4>Темы</h4>{tag_links}</div>
  <div class="fcol"><h4>Персоны</h4>{person_links}</div>
</div>
<div class="fcp"><span>© 2025–{datetime.now().year} Maple Barrel</span><span>journalists.ca</span></div>
</footer>"""


def page_shell(title, desc, url, content, active='news', og_img='', css_extra='', canonical=None):
    can = canonical or (BASE_URL + url)
    og_image = og_img or f"{BASE_URL}/og-default.jpg"
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{can}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{can}">
<meta property="og:type" content="article">
<meta property="og:image" content="{esc(og_image)}">
<meta property="og:locale" content="ru_RU">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{esc(og_image)}">
{FONTS_LINK}
<style>{COMMON_CSS}{css_extra}</style>
</head>
<body>
{nav_html(active)}
{content}
{footer_html()}
</body>
</html>"""


# ── КАРТОЧКИ ──────────────────────────────────────────

def _card_img(p, loading='lazy', size=32):
    img = post_img_src(p)
    if img:
        return f'<div class="card-img"><img src="{img}" alt="{esc(p["title"])}" loading="{loading}"></div>'
    return f'<div class="card-img"><span class="emoji-fallback" style="font-size:{size}px">{get_emoji(p.get("source",""))}</span></div>'

def hero_card(p):
    """Big hero card — left column main story."""
    deep_badge = tag_html('в глубину', href=False) if 'в глубину' in (p.get('tags') or []) else ''
    return f"""<a class="hero-card card" href="{post_url(p)}">
  <div class="card-img hc-img"><img src="{post_img_src(p) or ''}" alt="{esc(p['title'])}" loading="eager" onerror="this.parentNode.innerHTML='<span class=emoji-fallback style=font-size:56px>{get_emoji(p.get("source",""))}</span>'"></div>
  <div class="card-body hc-body">
    <div class="card-src">{esc(p.get('source',''))} {deep_badge}</div>
    <div class="card-title hc-title">{esc(p['title'])}</div>
    <div class="card-excerpt hc-ex">{esc(p.get('excerpt',''))}</div>
    <div class="card-meta hc-meta">
      <span class="card-date">{fmt_date(p['date'])}</span>
      <div class="card-tags">{tags_row(p.get('tags'), 3)}</div>
    </div>
  </div>
</a>"""

def small_card(p, loading='lazy'):
    """Standard grid card."""
    return f"""<a class="card" href="{post_url(p)}">
  {_card_img(p, loading)}
  <div class="card-body">
    <div class="card-src">{esc(p.get('source',''))}</div>
    <div class="card-title">{esc(p['title'])}</div>
    <div class="card-excerpt">{esc(p.get('excerpt',''))}</div>
    <div class="card-meta">
      <span class="card-date">{fmt_date(p['date'])}</span>
      <div class="card-tags">{tags_row(p.get('tags'), 2)}</div>
    </div>
  </div>
</a>"""

def compact_item(p, num):
    """Numbered compact list item — no image."""
    return f"""<a class="compact-item" href="{post_url(p)}">
  <div class="ci-num">{num:02d}</div>
  <div class="ci-body">
    <div class="card-src">{esc(p.get('source',''))}</div>
    <div class="card-title ci-title">{esc(p['title'])}</div>
    <div class="card-meta">
      <span class="card-date">{fmt_date(p['date'])}</span>
      <div class="card-tags">{tags_row(p.get('tags'), 1)}</div>
    </div>
  </div>
</a>"""

def lr_card(p):
    """Longread horizontal card."""
    return f"""<a class="lr-card card" href="{post_url(p)}">
  {_card_img(p, 'lazy', 28)}
  <div class="card-body lrc-body">
    <div class="card-src">{esc(p.get('source',''))}{' ' + tag_html('в глубину', href=False) if 'в глубину' in (p.get('tags') or []) else ''}</div>
    <div class="card-title lrc-title">{esc(p['title'])}</div>
    <div class="card-excerpt lrc-ex">{esc(p.get('excerpt',''))}</div>
    <div class="card-meta">
      <span class="card-date">{fmt_date(p['date'])}</span>
      <div class="card-tags">{tags_row(p.get('tags'), 3)}</div>
    </div>
  </div>
</a>"""


# ── СТРАНИЦА ПОСТА ─────────────────────────────────────

def build_post_page(p, related):
    img = post_img_src(p)
    img_html = ''
    og_img = ''
    if img:
        og_img = BASE_URL + img
        img_html = f'<div class="art-hero"><img src="{img}" alt="{esc(p["title"])}" loading="eager"></div>'
    else:
        img_html = f'<div class="art-hero art-hero-emoji"><span>{get_emoji(p.get("source",""))}</span></div>'

    tags_html = ''.join(
        f'<a class="ptag" href="/tag/{slugify(t)}/">#{t}</a>'
        for t in (p.get('tags') or [])
    )
    persons_html = ''.join(
        f'<a class="art-per" href="/person/{slugify(per)}/">{esc(per)}</a>'
        for per in (p.get('persons') or [])
    )
    body_html = ''.join(
        f'<p>{esc(line)}</p>'
        for line in clean_body(p.get('body', '')).split('\n')
        if line.strip()
    )
    src_link = ''
    if p.get('source_url'):
        src_link = f'<a class="src-link" href="{esc(p["source_url"])}" target="_blank" rel="noopener">Читать оригинал на {esc(p.get("source",""))} →</a>'

    # Related by tag — smarter matching
    post_tags = set(p.get('tags') or [])
    related_by_tag = [r for r in related if set(r.get('tags') or []) & post_tags and r['id'] != p['id']]
    related_final = (related_by_tag + [r for r in related if r not in related_by_tag])[:6]

    related_html = ''.join(f"""<a class="rel-item" href="{post_url(r)}">
      <div class="rel-src">{esc(r.get('source',''))}</div>
      <div class="rel-title">{esc(r['title'])}</div>
      <div class="rel-date">{fmt_date(r['date'])}</div>
    </a>""" for r in related_final)

    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": p['title'],
        "datePublished": p['date'],
        "publisher": {
            "@type": "Organization",
            "name": "Maple Barrel",
            "url": BASE_URL
        },
        "url": BASE_URL + post_url(p),
        "description": p.get('excerpt', '')[:160]
    }, ensure_ascii=False)

    css = """
.art-layout{display:grid;grid-template-columns:1fr 300px;gap:52px}
.art-src-row{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.art-src{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--ac2)}
.art-pers{display:flex;gap:6px;flex-wrap:wrap}
.art-per{font-size:11px;color:var(--gold);background:rgba(201,150,58,.1);border:1px solid rgba(201,150,58,.2);padding:2px 9px;border-radius:8px}
.art-title{font-family:var(--serif);font-size:30px;font-weight:700;line-height:1.2;margin-bottom:16px;color:var(--cream)}
.art-hero{aspect-ratio:16/9;overflow:hidden;background:var(--bg4);margin-bottom:20px;border-radius:8px;box-shadow:var(--shadow)}
.art-hero-emoji{display:flex;align-items:center;justify-content:center;font-size:64px;color:var(--t4)}
.art-metabar{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--br);border-bottom:1px solid var(--br);padding:11px 0;margin-bottom:28px;gap:10px;flex-wrap:wrap}
.art-date{font-size:13px;color:var(--t3)}
.art-tags{display:flex;gap:5px;flex-wrap:wrap}
/* Article body — the readable cream area */
.art-body-wrap{background:var(--card);border-radius:8px;padding:28px 32px;box-shadow:var(--shadow-sm)}
.art-body{font-family:var(--bserif);font-size:18px;line-height:1.85;color:var(--cream2)}
.art-body p{margin-bottom:1.2em}
.src-link{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--t3);border:1px solid var(--br);padding:7px 14px;border-radius:5px;margin-top:24px;background:var(--bg3);transition:all .15s}
.src-link:hover{color:var(--cream);border-color:var(--br2)}
.art-sb .sbt{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--t4);padding-bottom:10px;border-bottom:1px solid var(--br);margin-bottom:14px}
.rel-item{display:flex;flex-direction:column;gap:4px;padding:11px 0;border-bottom:1px solid var(--br);transition:opacity .12s}
.rel-item:hover{opacity:.7}
.rel-src{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--ac2)}
.rel-title{font-family:var(--serif);font-size:14px;font-weight:700;line-height:1.3;color:var(--cream)}
.rel-date{font-size:10px;color:var(--t3)}
.bk{display:inline-flex;align-items:center;gap:5px;color:var(--t3);font-size:13px;margin-bottom:24px;transition:color .15s}
.bk:hover{color:var(--cream)}
@media(max-width:900px){.art-layout{grid-template-columns:1fr}.art-sb{display:none}.art-title{font-size:22px}.art-body-wrap{padding:20px 18px}}
"""
    content = f"""<div class="wrap">
  <a class="bk" href="javascript:history.back()">← Назад</a>
  <div class="art-layout">
    <div>
      <div class="art-src-row">
        <span class="art-src">{esc(p.get('source',''))}</span>
        <div class="art-pers">{persons_html}</div>
      </div>
      <h1 class="art-title">{esc(p['title'])}</h1>
      {img_html}
      <div class="art-metabar">
        <span class="art-date">{fmt_date_full_short(p['date'])}</span>
        <div class="art-tags">{tags_html}</div>
      </div>
      <div class="art-body-wrap">
        <div class="art-body">{body_html}</div>
      </div>
      {src_link}
      <div class="tgcta">
        {TG_SVG}
        <div class="ctxt">
          <div class="ctit">Читайте Maple Barrel в Telegram</div>
          <div class="csub">Новые материалы каждый день — прямо в мессенджере</div>
          <div class="ctgp">Этот пост в Telegram: <a href="{esc(p['tg_url'])}" target="_blank" rel="noopener">{esc(p['tg_url'])}</a></div>
        </div>
        <a class="cbtn2" href="{TG_CHANNEL}" target="_blank" rel="noopener">Подписаться</a>
      </div>
    </div>
    <div class="art-sb">
      <div class="sbt">Читайте также</div>
      {related_html}
    </div>
  </div>
</div>
<script type="application/ld+json">{json_ld}</script>"""

    # Active nav based on post type
    active = 'longreads' if 'в глубину' in (p.get('tags') or []) else 'news'
    return page_shell(
        title=f"{p['title']} — Maple Barrel",
        desc=(p.get('excerpt') or '')[:155],
        url=post_url(p),
        content=content,
        active=active,
        og_img=og_img,
        css_extra=css
    )


# ── ГЛАВНАЯ (НОВОСТИ) ─────────────────────────────────

def build_news_index(posts_by_date):
    posts = []
    for d in sorted(posts_by_date.keys(), reverse=True):
        posts.extend(posts_by_date[d])

    # --- логика ---
    featured = [p for p in posts if 'в глубину' in (p.get('tags') or [])][:4]
    if len(featured) < 4:
        featured += posts[:4 - len(featured)]

    longreads = [p for p in posts if 'в глубину' in (p.get('tags') or [])][:6]
    latest = posts[:10]
    feed = posts[4:]

    html = '<div class="wrap">'

    # ГЛАВНОЕ
    html += '<h2 style="margin-bottom:16px">Главное</h2>'
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">'
    for p in featured:
        html += small_card(p)
    html += '</div>'

    # ЛОНГРИДЫ
    html += '<h2 style="margin:36px 0 16px">Лонгриды</h2>'
    html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px">'
    for p in longreads:
        html += small_card(p)
    html += '</div>'

    # ЛЕНТА + САЙДБАР
    html += '<div style="display:grid;grid-template-columns:3fr 1fr;gap:40px;margin-top:40px">'

    # ЛЕНТА
    html += '<div>'
    html += '<h2 style="margin-bottom:16px">Лента</h2>'
    html += ''.join(small_card(p) for p in feed[:40])
    html += '</div>'

    # САЙДБАР
    html += '<div>'
    html += '<h3 style="margin-bottom:12px">Последние</h3>'
    html += ''.join(compact_item(p, i+1) for i, p in enumerate(latest))
    html += '</div>'

    html += '</div>'
    html += '</div>'

    return page_shell(
        title="Maple Barrel",
        desc="Новости Канады",
        url="/",
        content=html,
        active='news'
    )

# ── МАТЕРИАЛЫ ─────────────────────────────────────────

def build_materials_page(posts, page=1, tag=''):
    css = """
.mat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.page-intro{padding:16px 0 22px;border-bottom:1px solid var(--br);margin-bottom:22px}
.page-intro h1{font-family:var(--serif);font-size:26px;font-weight:700;margin-bottom:6px;color:var(--cream)}
.page-intro p{font-size:14px;color:var(--t2)}
@media(max-width:900px){.mat-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:640px){.mat-grid{grid-template-columns:1fr}}
"""
    per = POSTS_PER_PAGE
    total = len(posts)
    pages = max(1, -(-total // per))
    page_posts = posts[(page-1)*per:page*per]

    tag_chips = '<div class="tag-chips">' + \
        f'<a class="tc{" on" if not tag else ""}" href="/materials/">Все</a>' + \
        ''.join(f'<a class="tc{" on" if tag==t else ""}" href="/materials/tag/{slugify(t)}/">#{t}</a>' for t in TOP_TAGS[:10]) + \
        '</div>'

    pgn = _pagination(page, pages, f'/materials/', tag and f'/materials/tag/{slugify(tag)}/')

    content = f"""<div class="wrap">
  <div class="page-intro">
    <h1>Материалы</h1>
    <p>Аналитика, мнения и тексты из The Atlantic, Maclean's, The Hub и других изданий — не привязанные к конкретной дате.</p>
  </div>
  {tag_chips}
  <div class="mat-grid">{"".join(small_card(p) for p in page_posts)}</div>
  {pgn}
</div>"""
    return page_shell(
        title="Материалы — Maple Barrel",
        desc="Аналитика, мнения и большие тексты о Канаде на русском языке.",
        url="/materials/",
        content=content,
        active='materials',
        css_extra=css
    )


# ── ЛОНГРИДЫ ──────────────────────────────────────────

def build_longreads_page(posts, page=1, tag=''):
    css = """
.lr-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.lr-card{display:grid!important;grid-template-columns:200px 1fr;border-radius:8px;overflow:hidden;box-shadow:var(--shadow-sm)}
.lr-card .card-img{border-radius:0!important}
.lrc-body{padding:18px 20px;display:flex;flex-direction:column;gap:7px}
.lrc-title{font-family:var(--serif);font-size:16px;font-weight:700;line-height:1.3;color:var(--cream);flex:1}
.lrc-ex{-webkit-line-clamp:3}
.page-intro{padding:16px 0 22px;border-bottom:1px solid var(--br);margin-bottom:22px}
.page-intro h1{font-family:var(--serif);font-size:26px;font-weight:700;margin-bottom:6px;color:var(--cream)}
.page-intro p{font-size:14px;color:var(--t2)}
@media(max-width:900px){.lr-grid{grid-template-columns:1fr}.lr-card{grid-template-columns:140px 1fr}}
@media(max-width:640px){.lr-card{grid-template-columns:1fr}.lr-card .card-img{display:none}}
"""
    per = POSTS_PER_PAGE
    total = len(posts)
    pages = max(1, -(-total // per))
    page_posts = posts[(page-1)*per:page*per]

    tag_chips = '<div class="tag-chips">' + \
        f'<a class="tc{" on" if not tag else ""}" href="/longreads/">Все</a>' + \
        ''.join(f'<a class="tc{" on" if tag==t else ""}" href="/longreads/tag/{slugify(t)}/">#{t}</a>' for t in TOP_TAGS[:10]) + \
        '</div>'

    pgn = _pagination(page, pages, '/longreads/', tag and f'/longreads/tag/{slugify(tag)}/')

    content = f"""<div class="wrap">
  <div class="page-intro">
    <h1>Лонгриды</h1>
    <p>Большие тексты и глубокий анализ — всё, что требует времени и внимания, а не просто заголовка.</p>
  </div>
  {tag_chips}
  <div class="lr-grid">{"".join(lr_card(p) for p in page_posts)}</div>
  {pgn}
</div>"""
    return page_shell(
        title="Лонгриды — Maple Barrel",
        desc="Большие материалы и аналитика о Канаде на русском языке.",
        url="/longreads/",
        content=content,
        active='longreads',
        css_extra=css
    )


# ── ТЕГОВЫЕ СТРАНИЦЫ ──────────────────────────────────

def build_tag_page(tag, posts, page=1):
    per = POSTS_PER_PAGE
    total = len(posts)
    pages = max(1, -(-total // per))
    page_posts = posts[(page-1)*per:page*per]
    pgn = _pagination(page, pages, f'/tag/{slugify(tag)}/')
    css = """
.tag-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.tag-hdr{padding:16px 0 20px;border-bottom:1px solid var(--br);margin-bottom:18px}
.tag-hdr h1{font-family:var(--serif);font-size:24px;font-weight:700;margin-bottom:4px;color:var(--cream)}
.tag-hdr p{font-size:13px;color:var(--t3)}
@media(max-width:1100px){.tag-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:700px){.tag-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:480px){.tag-grid{grid-template-columns:1fr}}
"""
    content = f"""<div class="wrap">
  <div class="tag-hdr">
    <h1>#{tag}</h1>
    <p>{total} материалов по теме</p>
  </div>
  <div class="tag-grid">{"".join(small_card(p) for p in page_posts)}</div>
  {pgn}
</div>"""
    return page_shell(
        title=f"#{tag} — Maple Barrel",
        desc=f"Все материалы по теме «{tag}» на русском языке. Канадские новости из CBC, CTV, Globe and Mail.",
        url=f"/tag/{slugify(tag)}/",
        content=content,
        active='news',
        css_extra=css
    )


def build_person_page(person, posts, page=1):
    per = POSTS_PER_PAGE
    total = len(posts)
    pages = max(1, -(-total // per))
    page_posts = posts[(page-1)*per:page*per]
    pgn = _pagination(page, pages, f'/person/{slugify(person)}/')
    css = """
.tag-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.tag-hdr{padding:16px 0 20px;border-bottom:1px solid var(--br);margin-bottom:18px}
.tag-hdr h1{font-family:var(--serif);font-size:24px;font-weight:700;margin-bottom:4px;color:var(--cream)}
.tag-hdr p{font-size:13px;color:var(--t3)}
@media(max-width:1100px){.tag-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:700px){.tag-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:480px){.tag-grid{grid-template-columns:1fr}}
"""
    content = f"""<div class="wrap">
  <div class="tag-hdr">
    <h1>{esc(person)}</h1>
    <p>{total} материалов</p>
  </div>
  <div class="tag-grid">{"".join(small_card(p) for p in page_posts)}</div>
  {pgn}
</div>"""
    return page_shell(
        title=f"{person} — Maple Barrel",
        desc=f"Все материалы о {person} на русском языке. Новости Канады из ведущих изданий.",
        url=f"/person/{slugify(person)}/",
        content=content,
        active='news',
        css_extra=css
    )


# ── О ПРОЕКТЕ / КОНТАКТЫ ──────────────────────────────

def build_about_page():
    content = """<div class="wrap" style="max-width:760px">
  <h1 style="font-family:var(--serif);font-size:32px;font-weight:700;margin-bottom:20px">О проекте</h1>
  <div style="font-family:var(--bserif);font-size:18px;line-height:1.85;color:var(--t)">
    <p>Maple Barrel — независимый русскоязычный медиапроект о Канаде. Каждый день мы отбираем главное из ведущих канадских изданий и пересказываем по-русски.</p>
    <p>Никакого машинного перевода. Только живой текст, контекст и редакторский выбор того, что важно знать о стране.</p>
    <p>Проект работает с февраля 2025 года. В архиве — более 2700 материалов о канадской политике, экономике, иммиграции, жилье и повседневной жизни страны.</p>
    <p><strong>Источники:</strong> CBC, CTV, Globe and Mail, National Post, Global News, Bloomberg, Reuters, NY Times, Maclean's, The Atlantic, Toronto Star, The Hub и другие надёжные издания.</p>
  </div>
</div>"""
    return page_shell(
        title="О проекте — Maple Barrel",
        desc="Maple Barrel — независимый русскоязычный медиапроект о Канаде. Ежедневный обзор канадских СМИ.",
        url="/about/",
        content=content,
        active='about'
    )


def build_contacts_page():
    content = f"""<div class="wrap" style="max-width:760px">
  <h1 style="font-family:var(--serif);font-size:32px;font-weight:700;margin-bottom:20px">Контакты</h1>
  <div style="font-family:var(--bserif);font-size:18px;line-height:1.85;color:var(--t)">
    <p>Telegram-канал: <a href="{TG_CHANNEL}" style="color:var(--tg2)">{TG_CHANNEL}</a></p>
    <p>Все вопросы, предложения и сотрудничество — через Telegram.</p>
  </div>
</div>"""
    return page_shell(
        title="Контакты — Maple Barrel",
        desc="Контакты редакции Maple Barrel. Telegram-канал о новостях Канады на русском языке.",
        url="/contacts/",
        content=content,
        active='contacts'
    )


# ── SITEMAP ───────────────────────────────────────────

def build_sitemap(posts):
    urls = [
        f"  <url><loc>{BASE_URL}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>",
        f"  <url><loc>{BASE_URL}/materials/</loc><changefreq>daily</changefreq><priority>0.8</priority></url>",
        f"  <url><loc>{BASE_URL}/longreads/</loc><changefreq>daily</changefreq><priority>0.8</priority></url>",
        f"  <url><loc>{BASE_URL}/about/</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>",
    ]
    for p in posts:
        urls.append(f"  <url><loc>{BASE_URL}{post_url(p)}</loc><lastmod>{p['date']}</lastmod><priority>0.7</priority></url>")
    for tag in TOP_TAGS:
        urls.append(f"  <url><loc>{BASE_URL}/tag/{slugify(tag)}/</loc><changefreq>daily</changefreq><priority>0.6</priority></url>")
    for per in TOP_PERSONS:
        urls.append(f"  <url><loc>{BASE_URL}/person/{slugify(per)}/</loc><changefreq>daily</changefreq><priority>0.6</priority></url>")

    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + \
           '\n'.join(urls) + '\n</urlset>'


def build_robots():
    return f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"


# ── PAGINATION HELPER ─────────────────────────────────

def _pagination(page, pages, base_url, tagged_base=None):
    if pages <= 1:
        return ''
    base = tagged_base or base_url

    def pg_url(n):
        if n == 1:
            return base
        return f"{base}page/{n}/"

    items = []
    if page > 1:
        items.append(f'<a class="pb" href="{pg_url(page-1)}">←</a>')
    prev = 0
    for i in range(1, pages+1):
        if i == 1 or i == pages or abs(i - page) <= 2:
            if prev and i - prev > 1:
                items.append('<span style="color:var(--t4);padding:0 4px">…</span>')
            cls = 'pb on' if i == page else 'pb'
            items.append(f'<a class="{cls}" href="{pg_url(i)}">{i}</a>')
            prev = i
    if page < pages:
        items.append(f'<a class="pb" href="{pg_url(page+1)}">→</a>')
    return f'<div class="pgn">{"".join(items)}</div>'


# ── WRITE FILE ────────────────────────────────────────

def write(path, content):
    full = os.path.join(SITE_DIR, path.lstrip('/'))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(content)


# ── MAIN BUILD ────────────────────────────────────────

def build():
    start = datetime.now()
    print(f"🍁 Maple Barrel — сборка сайта...")

    # Создаём папку site
    if os.path.exists(SITE_DIR):
        shutil.rmtree(SITE_DIR)
    os.makedirs(SITE_DIR)

    # Копируем фото если есть
    photos_src = os.path.join(DATA_DIR, 'photos')
    if os.path.exists(photos_src):
        shutil.copytree(photos_src, os.path.join(SITE_DIR, 'photos'))
        print(f"   📷 Фото скопированы")
    else:
        os.makedirs(os.path.join(SITE_DIR, 'photos'))

    # Парсим посты
    json_path = os.path.join(DATA_DIR, 'result.json')
    if not os.path.exists(json_path):
        print(f"❌ Не найден {json_path}")
        return

    print(f"   📖 Парсим result.json...")
    posts = parse_telegram_export(json_path)
    print(f"   ✅ {len(posts)} постов")

    # Тегируем
    posts = tag_posts(posts)

    # Сортируем новые первыми
    posts_desc = list(reversed(posts))

    # Группируем по дате
    by_date = defaultdict(list)
    for p in posts_desc:
        by_date[p['date']].append(p)

    # Разбиваем по типам
    news_posts = [p for p in posts_desc if 'в глубину' not in (p.get('tags') or [])]
    material_posts = [p for p in posts_desc if p.get('source','') in MATERIAL_SRCS]
    longread_posts = [p for p in posts_desc if 'в глубину' in (p.get('tags') or [])]

    # slug -> post mapping для related
    slug_map = {post_slug(p): p for p in posts_desc}

    print(f"   📰 Новости: {len(news_posts)}, Материалы: {len(material_posts)}, Лонгриды: {len(longread_posts)}")

    # ── Главная ──
    write('index.html', build_news_index(by_date))

    # ── Страницы постов ──
    print(f"   📄 Генерируем {len(posts)} страниц постов...")
    for p in posts_desc:
        related = [r for r in posts_desc if r['id'] != p['id']
                   and any(t in (r.get('tags') or []) for t in (p.get('tags') or []))][:6]
        if not related:
            related = posts_desc[:6]
        write(f"post/{post_slug(p)}/index.html", build_post_page(p, related))

    # ── Материалы ──
    per = POSTS_PER_PAGE
    mat_pages = max(1, -(-len(material_posts) // per))
    write('materials/index.html', build_materials_page(material_posts, 1))
    for pg in range(2, mat_pages + 1):
        write(f'materials/page/{pg}/index.html', build_materials_page(material_posts, pg))

    # ── Лонгриды ──
    lr_pages = max(1, -(-len(longread_posts) // per))
    write('longreads/index.html', build_longreads_page(longread_posts, 1))
    for pg in range(2, lr_pages + 1):
        write(f'longreads/page/{pg}/index.html', build_longreads_page(longread_posts, pg))

    # ── Теги ──
    tag_index = defaultdict(list)
    for p in posts_desc:
        for t in (p.get('tags') or []):
            if t != 'в глубину':
                tag_index[t].append(p)

    print(f"   🏷  Генерируем {len(tag_index)} тегов...")
    for tag, tposts in tag_index.items():
        tpages = max(1, -(-len(tposts) // per))
        write(f'tag/{slugify(tag)}/index.html', build_tag_page(tag, tposts, 1))
        for pg in range(2, tpages + 1):
            write(f'tag/{slugify(tag)}/page/{pg}/index.html', build_tag_page(tag, tposts, pg))

    # ── Персоны ──
    person_index = defaultdict(list)
    for p in posts_desc:
        for per_name in (p.get('persons') or []):
            person_index[per_name].append(p)

    print(f"   👤 Генерируем {len(person_index)} персон...")
    for person, pposts in person_index.items():
        ppages = max(1, -(-len(pposts) // per))
        write(f'person/{slugify(person)}/index.html', build_person_page(person, pposts, 1))
        for pg in range(2, ppages + 1):
            write(f'person/{slugify(person)}/page/{pg}/index.html', build_person_page(person, pposts, pg))

    # ── О проекте / Контакты ──
    write('about/index.html', build_about_page())
    write('contacts/index.html', build_contacts_page())

    # ── Sitemap ──
    write('sitemap.xml', build_sitemap(posts_desc))
    write('robots.txt', build_robots())

    # ── _redirects для Cloudflare Pages ──
    write('_redirects', '/post/*  /post/:splat  200\n/tag/*  /tag/:splat  200\n')

    elapsed = (datetime.now() - start).total_seconds()
    total_files = sum(len(fs) for _, _, fs in os.walk(SITE_DIR))
    print(f"\n✅ Готово за {elapsed:.1f} сек — {total_files} файлов в папке /{SITE_DIR}/")
    print(f"   Следующий шаг: commit + push в GitHub Desktop")


if __name__ == '__main__':
    build()
