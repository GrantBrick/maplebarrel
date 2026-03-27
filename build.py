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

# ── НОВАЯ ТАКСОНОМИЯ (20 тем + география) ──────────────

# Публичные теги — ровно 20 тем из документа
TOP_TAGS = [
    'Политика',
    'Международные отношения',
    'Экономика',
    'Жильё',
    'Транспорт',
    'Рынок труда',
    'Преступность',
    'Права и свободы',
    'Технологии и ИИ',
    'Личные финансы',
    'Общество',
    'Тарифы и торговля',
    'Иммиграция',
    'Энергетика',
    'Кризисы и происшествия',
    'Арктика и Север',
    'Здравоохранение',
    'Экология',
    'Туризм',
    'Статистика и опросы',
]

# Географические теги (отдельно от тематических)
GEO_TAGS = [
    'Онтарио', 'Британская Колумбия', 'Альберта', 'Квебек',
    'Торонто', 'Ванкувер', 'Калгари',
]

# Актуальные персоны — без Трюдо и Сингха в приоритете
TOP_PERSONS = [
    'Марк Карни', 'Пьер Полиев', 'Дональд Трамп',
    'Даг Форд', 'Даниэль Смит', 'Мелани Жоли', 'Анита Ананд',
]

# Цвета тегов по группам
TAG_COLORS = {
    # Политика — красный
    'Политика': 'pol',
    'Международные отношения': 'pol',
    'Права и свободы': 'pol',
    # Экономика — золотой
    'Экономика': 'eco',
    'Тарифы и торговля': 'eco',
    'Личные финансы': 'eco',
    'Жильё': 'eco',
    'Рынок труда': 'eco',
    # Иммиграция — синий
    'Иммиграция': 'imm',
    # Регионы — зелёный
    'Онтарио': 'reg', 'Британская Колумбия': 'reg', 'Альберта': 'reg',
    'Квебек': 'reg', 'Торонто': 'reg', 'Ванкувер': 'reg', 'Калгари': 'reg',
    'Арктика и Север': 'reg',
    # Данные — фиолетовый
    'Статистика и опросы': 'stat',
    # Остальные — серый по умолчанию
}

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

# Source display names for red badge
SOURCE_NAMES = {
    'cbc.ca': 'CBC', 'ctvnews.ca': 'CTV News',
    'theglobeandmail.com': 'Globe and Mail', 'globalnews.ca': 'Global News',
    'thestar.com': 'Toronto Star', 'bloomberg.com': 'Bloomberg',
    'nytimes.com': 'NY Times', 'theatlantic.com': 'The Atlantic',
    'macleans.ca': "Maclean's", 'thehub.ca': 'The Hub',
    'torontosun.com': 'Toronto Sun', 'nationalpost.com': 'National Post',
    'reuters.com': 'Reuters', 'theguardian.com': 'The Guardian',
    'financialpost.com': 'Financial Post', 'apple.news': 'Apple News',
    'westernstandard.news': 'Western Standard', 'spectator.com': 'Spectator',
}

def source_name(src):
    return SOURCE_NAMES.get(src, src or '—')

def tag_color(t):
    return TAG_COLORS.get(t, 'def')

def tag_html(t, href=True):
    cls = f'tag tag-{tag_color(t)}'
    if href:
        return f'<a class="{cls}" href="/tag/{slugify(t)}/">#{t}</a>'
    return f'<span class="{cls}">#{t}</span>'

def tags_row(tags, limit=3):
    """Render tag chips, skip internal flags."""
    shown = (tags or [])[:limit]
    return ''.join(tag_html(t) for t in shown)

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
    return src in MATERIAL_SRCS or any(m in body for m in LONGREAD_MARKERS)

def is_material(p):
    return (p.get('source', '') or '') in MATERIAL_SRCS

def tag_posts(posts):
    """Auto-tag with 20-topic taxonomy. Max 3 tags per post."""

    # Use word-boundary safe matching — all keywords are phrases, not substrings
    # Each keyword must match as a word/phrase, not inside another word
    import re as _re

    def match_kw(kw, text):
        """Match keyword safely — short kws need word boundaries."""
        if len(kw) <= 4:
            return bool(_re.search(r'(?<!\w)' + _re.escape(kw) + r'(?!\w)', text))
        return kw in text

    TOPIC_TAGS = {
        'Политика': [
            'парламент', 'либерал', 'консерват', 'выборы', 'выборах', 'голосован',
            'кампани', 'баллотир', 'депутат', 'сенат', 'федеральн', 'министр',
            'оппозиц', 'партия', 'ндп ', 'bloc québécois',
        ],
        'Международные отношения': [
            '51-й штат', 'нато', ' g7 ', ' g20 ', 'дипломат', 'санкц',
            'торговая война', 'китай', 'пекин', 'украин', 'израил', 'иран', 'россия',
            'канада и сша', 'трамп и канад',
        ],
        'Тарифы и торговля': [
            'тариф', 'пошлин', 'торговые ограничен', 'экспорт канад', 'импорт сша',
            'cusma', 'nafta', 'протекцион', 'торговые переговор',
        ],
        'Экономика': [
            'экономик', 'инфляц', 'ввп', 'процентная ставк', 'банк канады',
            'рецессий', 'бюджет канад', 'дефицит бюджет', 'рост цен',
            'стоимость жизни', 'покупательн', 'финансовый кризис',
        ],
        'Жильё': [
            'рынок жиль', 'аренд', 'ипотек', 'кондоминиум', 'недвижимост',
            'строительств жиль', 'арендодател', 'арендатор', 'стоимость жиль',
            'доступност жиль', 'жилищн кризис',
        ],
        'Рынок труда': [
            'безработиц', 'рабочих мест', 'зарплат', 'профсоюз', 'забастовк',
            'увольнен', 'минимальная зарплат', 'временных иностранных работник',
            'рынок труда', 'трудоустройств',
        ],
        'Иммиграция': [
            'иммиграц', 'мигрант', 'ircc', 'иностранных студент', 'беженц',
            'постоянн резидент', 'депортац', 'гражданств канад',
            'immigration canada', 'refugee', 'asylum',
        ],
        'Преступность': [
            'убийств', 'застрелил', 'стрельбу', 'стрельба', 'мошенничест',
            'наркотик', 'фентанил', 'ограблен', 'задержан полиц', 'осуждён',
            'приговор', 'преступник', 'банда', 'арестован',
        ],
        'Права и свободы': [
            'права человека', 'дискриминац', 'свобода слова', 'протест',
            'lgbtq', 'антисемит', 'расизм', 'коренных народ', 'примирени',
            'first nations', 'правозащит',
        ],
        'Технологии и ИИ': [
            'искусственный интеллект', 'нейросет', 'chatgpt', 'openai',
            'дата-центр', 'кибербезопасн', 'цифровой суверен', 'стартап технолог',
            'большие языковые модел', 'регулирование ии',
        ],
        'Личные финансы': [
            'пенсий', 'налог', 'cpp ', 'rrsp', 'tfsa', 'личные финанс',
            'страхован', 'банковск', 'процентные ставк', 'сбережен',
            'финансовое планирован', 'кредитн история',
        ],
        'Общество': [
            'культур', 'религи', 'образован', 'школ', 'университет',
            'молодёж', 'пожилых канадц', 'праздник', 'опрос канадц',
            'канадское общество', 'социальн',
        ],
        'Энергетика': [
            'нефтян', 'природный газ', 'энергетик', 'трубопровод',
            'trans mountain', 'электроэнерги', 'возобновляем', 'атомн электростанц',
            'энергетический кризис', 'нефтепровод',
        ],
        'Здравоохранение': [
            'здравоохранен', 'больниц', 'медицин', 'врач', 'пациент',
            'лекарств', 'психическ здоровь', 'фармацевт', 'ожирен', 'вакцин',
            'пандеми', 'система здоровь', 'препарат',
        ],
        'Экология': [
            'климат', 'окружающая среда', 'carbon tax', 'углеродн', 'выбросы',
            'лесной пожар', 'наводнен', 'потеплен', 'экологическ',
        ],
        'Транспорт': [
            'air canada', 'westjet', 'авиакомпани', 'аэропорт', 'авиакатастроф',
            'железнодорожн', 'via rail', 'электромобил', 'tesla ',
            'общественный транспорт',
        ],
        'Кризисы и происшествия': [
            'чрезвычайн', 'катастроф', 'авария', 'лесной пожар', 'взрыв',
            'землетрясен', 'наводнен', 'эвакуац', 'стихийн бедств',
        ],
        'Арктика и Север': [
            'арктик', 'крайний север', 'суверенитет', 'нунавут',
            'северные территор', 'северный полюс',
        ],
        'Туризм': [
            'туризм', 'туристов', 'путешеств канадц', 'отель', 'курорт',
            'лос-кабос', 'туристическ', 'поездк за рубеж',
        ],
        'Статистика и опросы': [
            'согласно опросу', 'новый опрос', 'statistics canada', 'statscan',
            'согласно данным', 'исследован показ', 'рейтинг одобрен',
            'индекс потребительск', 'ежегодный отчёт', 'канадцев считают',
            'канадцев поддерживают', 'канадцев против',
        ],
    }

    GEO_MAP = {
        'Онтарио':             ['онтарио'],
        'Британская Колумбия': ['британская колумбия', 'ванкувер', 'ричмонд', 'виктори'],
        'Альберта':            ['альберт', 'калгари', 'эдмонтон'],
        'Квебек':              ['квебек', 'монреаль'],
        'Торонто':             ['торонто', 'миссиссаг', 'брэмптон', 'гамильтон'],
    }

    PERSONS = {
        'Карни':  'Марк Карни',
        'Полиев': 'Пьер Полиев',
        'Трамп':  'Дональд Трамп',
        'Форд':   'Даг Форд',
        'Смит':   'Даниэль Смит',
        'Жоли':   'Мелани Жоли',
        'Ананд':  'Анита Ананд',
        'Трюдо':  'Джастин Трюдо',
        'Маск':   'Илон Маск',
    }

    for p in posts:
        text = ((p.get('title') or '') + ' ' + (p.get('body') or '')).lower()

        # Score topics
        topic_scores = []
        for topic, keywords in TOPIC_TAGS.items():
            score = sum(1 for kw in keywords if match_kw(kw, text))
            if score > 0:
                topic_scores.append((score, topic))
        topic_scores.sort(reverse=True)
        topic_tags = [t for _, t in topic_scores[:2]]

        # Geo — max 1
        geo_tag = next(
            (geo for geo, kws in GEO_MAP.items() if any(kw in text for kw in kws)),
            None
        )

        combined = topic_tags[:]
        if geo_tag and geo_tag not in combined:
            combined.append(geo_tag)
        p['tags'] = combined[:3]

        # Internal flags
        p['is_longread'] = is_longread(p)
        p['is_material'] = is_material(p)
        p['is_stat'] = any(kw in text for kw in [
            'statistics canada', 'statscan', 'согласно опросу', 'новый опрос',
            'рейтинг', 'индекс', 'согласно данным', 'исследован показ',
            'канадцев считают', 'канадцев поддерживают',
        ])

        p['persons'] = [full for key, full in PERSONS.items()
                        if key.lower() in text][:3]

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
  --bg:#f4f1eb;--bg2:#ffffff;--bg3:#f9f7f3;--bg4:#ede9e1;--bg5:#e4e0d6;
  --br:#e2ddd4;--br2:#ccc7bc;
  --card:#ffffff;--card-hover:#faf8f4;
  --t:#1a1916;--t2:#4a4740;--t3:#8a857a;--t4:#b8b3a8;
  --ac:#c0392b;--ac2:#c0392b;--ac3:#e05240;
  --gold:#9a6f20;--gold2:#c9963a;
  --tg:#2b6cb0;--tg2:#1a56a0;
  --maple:#c0392b;
  --shadow:0 2px 12px rgba(0,0,0,.08),0 1px 3px rgba(0,0,0,.06);
  --shadow-sm:0 1px 4px rgba(0,0,0,.07);
  --serif:'Playfair Display',Georgia,serif;
  --bserif:'Source Serif 4',Georgia,serif;
  --sans:'Golos Text',system-ui,sans-serif
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--t);font-family:var(--sans);font-size:16px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
img{display:block;width:100%;height:100%;object-fit:cover}

/* ── NAV ── */
nav{background:#fff;border-bottom:1px solid var(--br);position:sticky;top:0;z-index:300;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.ni{max-width:1300px;margin:0 auto;padding:0 20px;height:56px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.logo{font-family:var(--serif);font-size:21px;font-weight:900;letter-spacing:-.4px;display:flex;align-items:center;gap:5px;color:var(--t)}
.logo .lf{color:var(--maple)}
.nav-links{display:flex;gap:1px}
.nl{font-size:13px;font-weight:500;color:var(--t3);padding:5px 12px;border-radius:5px;transition:all .15s;white-space:nowrap}
.nl:hover{color:var(--t);background:var(--bg4)}
.nl.on{color:var(--t);background:var(--bg4);font-weight:600}
.nav-r{display:flex;align-items:center;gap:10px}
/* Telegram — prominent button */
.tgb{display:flex;align-items:center;gap:7px;background:var(--tg2);color:#fff;border-radius:6px;font-size:13px;font-weight:600;padding:7px 14px;text-decoration:none;transition:all .2s;box-shadow:0 1px 4px rgba(26,86,160,.3)}
.tgb:hover{background:var(--tg);box-shadow:0 2px 8px rgba(26,86,160,.4)}
.tgb svg{width:14px;height:14px;flex-shrink:0}

.wrap{max-width:1300px;margin:0 auto;padding:24px 20px 56px}

/* ── SOURCE BADGE (red) ── */
.src-badge{display:inline-block;background:var(--ac);color:#fff;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;padding:2px 8px;border-radius:3px;white-space:nowrap}

/* ── CARD SYSTEM ── */
.card{background:var(--card);border-radius:8px;overflow:hidden;transition:transform .15s,box-shadow .15s;box-shadow:var(--shadow-sm);display:flex;flex-direction:column}
.card:hover{transform:translateY(-2px);box-shadow:var(--shadow)}

/* Image — fixed 16:9, cover, contained */
.card-img{aspect-ratio:16/9;overflow:hidden;background:var(--bg4);flex-shrink:0;display:flex;align-items:center;justify-content:center}
.card-img img{width:100%;height:100%;object-fit:cover;display:block}
.card-img .emoji-fallback{font-size:28px;color:var(--t4)}

/* Card body */
.card-body{padding:14px 16px 16px;flex:1;display:flex;flex-direction:column;gap:7px}
.card-title{font-family:var(--serif);font-weight:700;line-height:1.3;color:var(--t);font-size:15px}
.card-excerpt{font-size:13px;color:var(--t2);line-height:1.55;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-meta{display:flex;align-items:center;gap:8px;margin-top:auto;padding-top:8px;flex-wrap:wrap;border-top:1px solid var(--br)}
.card-date{font-size:11px;color:var(--t3)}
.card-tags{display:flex;gap:4px;flex-wrap:wrap}
/* Read more link */
.card-read{font-size:12px;font-weight:600;color:var(--ac);margin-top:4px}
.card:hover .card-read{text-decoration:underline}

/* ── TAG CHIPS ── */
.tag{font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px;white-space:nowrap;transition:opacity .12s;letter-spacing:.2px}
.tag:hover{opacity:.8}
/* Politics — red */
.tag-pol{background:#fde8e8;color:#9b1c1c}
/* Economy — amber */
.tag-eco{background:#fef3c7;color:#78350f}
/* Immigration — blue */
.tag-imm{background:#dbeafe;color:#1e40af}
/* Regions — green */
.tag-reg{background:#d1fae5;color:#065f46}
/* Stats — purple */
.tag-stat{background:#ede9fe;color:#4c1d95}
/* Default — gray */
.tag-def{background:var(--bg4);color:var(--t3)}

/* ── PAGINATION ── */
.pgn{display:flex;gap:5px;justify-content:center;padding:32px 0 8px;flex-wrap:wrap}
.pb{padding:6px 13px;border-radius:5px;border:1px solid var(--br);background:#fff;color:var(--t3);font-size:13px;transition:all .15s}
.pb:hover{border-color:var(--br2);color:var(--t)}
.pb.on{background:var(--ac);color:#fff;border-color:var(--ac)}
.pb.disabled{opacity:.3;pointer-events:none}

/* ── TAG FILTER BAR ── */
.tag-bar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px}
.tc{font-size:12px;padding:4px 12px;border-radius:12px;border:1px solid var(--br);color:var(--t3);background:#fff;transition:all .15s;white-space:nowrap}
.tc:hover{border-color:var(--br2);color:var(--t)}
.tc.on{background:var(--ac);color:#fff;border-color:var(--ac)}

/* ── FOOTER ── */
footer{border-top:2px solid var(--br);padding:36px 20px;margin-top:56px;background:#fff}
.fi{max-width:1300px;margin:0 auto;display:grid;grid-template-columns:2fr 1fr 1fr;gap:36px}
.flogo{font-family:var(--serif);font-size:18px;font-weight:900;margin-bottom:8px;display:flex;align-items:center;gap:5px}
.flogo .lf{color:var(--maple)}
.fdesc{font-size:13px;color:var(--t3);line-height:1.65;max-width:340px;margin-bottom:8px}
.fsrcs{font-size:11px;color:var(--t4);line-height:1.9}
.fcol h4{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--t4);margin-bottom:12px}
.fcol a{display:block;font-size:13px;color:var(--t3);margin-bottom:7px;transition:color .15s}
.fcol a:hover{color:var(--t)}
.fcp{max-width:1300px;margin:20px auto 0;padding-top:18px;border-top:1px solid var(--br);display:flex;justify-content:space-between;font-size:12px;color:var(--t4)}

/* ── TG CTA (bottom of post) ── */
.tgcta{display:flex;align-items:center;gap:16px;background:var(--bg3);border:1px solid var(--br);border-left:4px solid var(--tg2);border-radius:8px;padding:18px 22px;margin-top:36px}
.tgcta svg{width:28px;height:28px;flex-shrink:0;color:var(--tg2)}
.ctxt{flex:1}
.ctit{font-weight:700;font-size:15px;margin-bottom:3px;color:var(--t)}
.csub{font-size:13px;color:var(--t2)}
.ctgp{font-size:11px;color:var(--t3);margin-top:6px}
.ctgp a{color:var(--tg2)}
.cbtn2{flex-shrink:0;background:var(--tg2);color:#fff;font-size:13px;font-weight:600;padding:9px 18px;border-radius:5px;text-decoration:none;transition:all .15s;white-space:nowrap;box-shadow:0 1px 4px rgba(26,86,160,.3)}
.cbtn2:hover{background:var(--tg)}

/* ── CARD PLACEHOLDER ── */
.card-placeholder{width:100%;height:100%;display:flex;align-items:center;justify-content:center}
.card-placeholder span{font-size:13px;font-weight:700;letter-spacing:.5px;opacity:.9}
/* Consistent card-img — always 16:9, photo is decorative */
.card-img{position:relative}
.card-img img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}

/* Read more */
.card-read{font-size:12px;font-weight:600;color:var(--ac);margin-top:2px}

/* ci-badge smaller */
.ci-badge{font-size:9px!important;padding:1px 6px!important}

/* lr-card */
.lr-card{display:flex;background:#fff;border-radius:6px;overflow:hidden;box-shadow:var(--shadow-sm);transition:transform .15s,box-shadow .15s}
.lr-card:hover{transform:translateY(-1px);box-shadow:var(--shadow)}
.lr-img{width:80px;min-width:80px;height:80px;overflow:hidden;position:relative;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.lr-img img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.lr-body{padding:10px 12px;flex:1;display:flex;flex-direction:column;gap:5px;min-width:0}
.lr-title{font-family:var(--serif);font-size:13px;font-weight:700;line-height:1.3;color:var(--t);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}

/* ── RESPONSIVE ── */
@media(max-width:900px){.fi{grid-template-columns:1fr}.nav-links .nl:not(.on){display:none}}
@media(max-width:640px){.ni{gap:8px}.tgcta{flex-direction:column;align-items:flex-start}}
"""

FONTS_LINK = '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Golos+Text:wght@400;500;600&display=swap" rel="stylesheet">'

TG_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12s5.37 12 12 12 12-5.37 12-12S18.63 0 12 0zm5.88 8.18l-2.02 9.52c-.15.67-.54.84-1.1.52l-3-2.21-1.45 1.39c-.16.16-.3.3-.61.3l.21-3.02 5.49-4.96c.24-.21-.05-.33-.37-.12L6.26 14.38l-2.96-.92c-.64-.2-.65-.64.14-.95l11.54-4.45c.53-.19 1 .13.9.12z"/></svg>'


# ── ШАБЛОНЫ ──────────────────────────────────────────

def nav_html(active='news'):
    pages = [
        ('news',      '/',           'Новости'),
        ('materials', '/materials/', 'Материалы'),
        ('longreads', '/longreads/', 'Лонгриды'),
        ('surveys',   '/surveys/',   'Опросы'),
        ('about',     '/about/',     'О проекте'),
    ]
    links = ''.join(
        f'<a class="nl{" on" if k==active else ""}" href="{url}">{label}</a>'
        for k, url, label in pages
    )
    return f"""<nav><div class="ni">
  <a class="logo" href="/"><span>Maple</span><span class="lf">🍁</span><span>Barrel</span></a>
  <div class="nav-links">{links}</div>
  <div class="nav-r">
    <a class="tgb" href="{TG_CHANNEL}" target="_blank" rel="noopener">
      {TG_SVG}
      <span>Telegram</span>
    </a>
  </div>
</div></nav>"""


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

# Source placeholder colors for cards without photo
SOURCE_COLORS = {
    'cbc.ca':              ('#cc0000', '#fff', 'CBC'),
    'ctvnews.ca':          ('#005eb8', '#fff', 'CTV'),
    'theglobeandmail.com': ('#1a1a1a', '#fff', 'Globe'),
    'globalnews.ca':       ('#003087', '#fff', 'Global'),
    'thestar.com':         ('#c41230', '#fff', 'Star'),
    'bloomberg.com':       ('#1f1f1f', '#fff', 'BBG'),
    'nytimes.com':         ('#1a1a1a', '#fff', 'NYT'),
    'theatlantic.com':     ('#bf0000', '#fff', 'Atlantic'),
    'macleans.ca':         ('#c8102e', '#fff', "Maclean's"),
    'thehub.ca':           ('#0d4f8c', '#fff', 'Hub'),
    'torontosun.com':      ('#e8000d', '#fff', 'Sun'),
    'nationalpost.com':    ('#003087', '#fff', 'NatPost'),
    'reuters.com':         ('#ff8000', '#1a1a1a', 'Reuters'),
    'theguardian.com':     ('#005689', '#fff', 'Guardian'),
    'financialpost.com':   ('#003366', '#fff', 'FinPost'),
    'westernstandard.news':('#8b0000', '#fff', 'WStd'),
    'spectator.com':       ('#cc0000', '#fff', 'Spectator'),
}

def card_placeholder(src):
    """Colored placeholder when no photo."""
    bg, fg, label = SOURCE_COLORS.get(src, ('#4a4740', '#fff', src[:3].upper() if src else '?'))
    return f'<div class="card-placeholder" style="background:{bg}"><span style="color:{fg}">{label}</span></div>'

def card_img_html(p, loading='lazy'):
    """Render card image area — photo or colored placeholder."""
    img = post_img_src(p)
    src = p.get('source', '')
    if img:
        ph = card_placeholder(src)
        return f'''<div class="card-img">
  <img src="{img}" alt="{esc(p["title"])}" loading="{loading}"
       onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
  <div style="display:none;position:absolute;inset:0">{ph}</div>
</div>'''
    return f'<div class="card-img">{card_placeholder(src)}</div>'

def _img_block(p, loading='lazy'):
    """Unified image block — photo with colored placeholder fallback."""
    img = post_img_src(p)
    src = p.get('source', '')
    bg, fg, label = SOURCE_COLORS.get(src, ('#4a4740', '#fff', src[:4].upper() if src else '?'))
    ph_html = f'<div class=card-placeholder style=background:{bg}><span style=color:{fg}>{label}</span></div>'
    if img:
        return (f'<div class="card-img">'
                f'<img src="{img}" alt="" loading="{loading}" '
                f"onerror=\"this.parentNode.innerHTML='{ph_html}'\">"
                f'</div>')
    return f'<div class="card-img"><div class="card-placeholder" style="background:{bg}"><span style="color:{fg}">{label}</span></div></div>'


def hero_card(p):
    src_label = source_name(p.get('source', ''))
    img = post_img_src(p)
    src = p.get('source', '')
    bg, fg, label = SOURCE_COLORS.get(src, ('#4a4740', '#fff', src[:4].upper() if src else '?'))
    if img:
        img_html = (f'<div class="hc-img">'
                    f'<img src="{img}" alt="" loading="eager" '
                    f"onerror=\"this.parentNode.style.background='{bg}'\">"
                    f'</div>')
    else:
        img_html = (f'<div class="hc-img" style="background:{bg}">'
                    f'<span style="color:{fg};font-size:14px;font-weight:700;letter-spacing:.5px">{label}</span>'
                    f'</div>')
    return (f'<a class="hero-card" href="{post_url(p)}">'
            f'{img_html}'
            f'<div class="hc-body">'
            f'<div><span class="src-badge">{esc(src_label)}</span></div>'
            f'<div class="hc-title">{esc(p["title"])}</div>'
            f'<div class="hc-ex">{esc(p.get("excerpt",""))}</div>'
            f'<div class="card-meta" style="margin-top:auto;padding-top:10px;border-top:1px solid var(--br)">'
            f'<span class="card-date">{fmt_date(p["date"])}</span>'
            f'<div class="card-tags">{tags_row(p.get("tags"), 3)}</div>'
            f'</div>'
            f'<div class="card-read">Читать далее →</div>'
            f'</div></a>')


def small_card(p, loading='lazy'):
    src_label = source_name(p.get('source', ''))
    return (f'<a class="card" href="{post_url(p)}">'
            f'{_img_block(p, loading)}'
            f'<div class="card-body">'
            f'<div><span class="src-badge">{esc(src_label)}</span></div>'
            f'<div class="card-title">{esc(p["title"])}</div>'
            f'<div class="card-excerpt">{esc(p.get("excerpt",""))}</div>'
            f'<div class="card-meta">'
            f'<span class="card-date">{fmt_date(p["date"])}</span>'
            f'<div class="card-tags">{tags_row(p.get("tags"), 2)}</div>'
            f'</div>'
            f'<div class="card-read">Читать далее →</div>'
            f'</div></a>')


def compact_item(p, num):
    src_label = source_name(p.get('source', ''))
    return (f'<a class="compact-item" href="{post_url(p)}">'
            f'<div class="ci-num">{num:02d}</div>'
            f'<div class="ci-body">'
            f'<span class="src-badge ci-badge">{esc(src_label)}</span>'
            f'<div class="card-title ci-title">{esc(p["title"])}</div>'
            f'<div class="card-meta" style="border:none;padding-top:4px">'
            f'<span class="card-date">{fmt_date(p["date"])}</span>'
            f'<div class="card-tags">{tags_row(p.get("tags"), 1)}</div>'
            f'</div></div></a>')


def lr_card(p):
    """Horizontal mini-card for longreads and related posts."""
    src_label = source_name(p.get('source', ''))
    src = p.get('source', '')
    bg, fg, label = SOURCE_COLORS.get(src, ('#4a4740', '#fff', src[:4].upper() if src else '?'))
    img = post_img_src(p)
    if img:
        img_html = f'<div class="lr-img"><img src="{img}" alt="" loading="lazy" onerror="this.parentNode.style.background=\'{bg}\';this.remove()"></div>'
    else:
        img_html = f'<div class="lr-img" style="background:{bg}"><span style="color:{fg};font-size:10px;font-weight:700">{label}</span></div>'
    return (f'<a class="lr-card" href="{post_url(p)}">'
            f'{img_html}'
            f'<div class="lr-body">'
            f'<span class="src-badge" style="font-size:9px">{esc(src_label)}</span>'
            f'<div class="lr-title">{esc(p["title"])}</div>'
            f'<div class="card-date" style="font-size:10px;margin-top:4px">{fmt_date(p["date"])}</div>'
            f'</div></a>')


# ── СТРАНИЦА ПОСТА ─────────────────────────────────────

def build_post_page(p, related):
    img = post_img_src(p)
    og_img = ''
    src = p.get('source', '')
    bg, fg, label = SOURCE_COLORS.get(src, ('#4a4740', '#fff', src[:4].upper() if src else '?'))

    # Hero image
    if img:
        og_img = BASE_URL + img
        img_html = (f'<div class="art-hero">'
                    f'<img src="{img}" alt="" loading="eager" '
                    f"onerror=\"this.parentNode.innerHTML='<div class=art-hero-ph style=background:{bg}><span style=color:{fg};font-size:24px;font-weight:700>{label}</span></div>\'\""
                    f'></div>')
    else:
        img_html = f'<div class="art-hero"><div class="art-hero-ph" style="background:{bg}"><span style="color:{fg};font-size:24px;font-weight:700">{label}</span></div></div>'

    tags_html = ''.join(tag_html(t) for t in (p.get('tags') or []))
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
        src_link = f'<a class="src-link" href="{esc(p["source_url"])}" target="_blank" rel="noopener">Читать оригинал на {esc(source_name(src))} →</a>'

    # JSON-LD
    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": p['title'],
        "datePublished": p['date'],
        "publisher": {"@type": "Organization", "name": "Maple Barrel", "url": BASE_URL},
        "url": BASE_URL + post_url(p),
        "description": p.get('excerpt', '')[:160]
    }, ensure_ascii=False)

    # Related — 4 lr_cards by tag
    post_tags = set(p.get('tags') or [])
    related_by_tag = [r for r in related if set(r.get('tags') or []) & post_tags][:4]
    related_final = related_by_tag if related_by_tag else related[:4]
    related_html = ''.join(lr_card(r) for r in related_final)

    css = """
.art-layout{display:grid;grid-template-columns:1fr 300px;gap:52px}
.art-src-row{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.art-pers{display:flex;gap:6px;flex-wrap:wrap}
.art-per{font-size:11px;color:var(--tg2);background:rgba(43,108,176,.08);border:1px solid rgba(43,108,176,.2);padding:2px 9px;border-radius:8px}
.art-title{font-family:var(--serif);font-size:30px;font-weight:700;line-height:1.2;margin-bottom:18px;color:var(--t)}
.art-hero{aspect-ratio:16/9;overflow:hidden;background:var(--bg4);margin-bottom:20px;border-radius:8px;box-shadow:var(--shadow)}
.art-hero img{width:100%;height:100%;object-fit:cover}
.art-hero-ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center}
.art-metabar{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--br);border-bottom:1px solid var(--br);padding:11px 0;margin-bottom:28px;gap:10px;flex-wrap:wrap}
.art-date{font-size:13px;color:var(--t3)}
.art-tags{display:flex;gap:5px;flex-wrap:wrap}
.art-body-wrap{background:#fff;border-radius:8px;padding:28px 32px;box-shadow:var(--shadow-sm);border:1px solid var(--br)}
.art-body{font-family:var(--bserif);font-size:18px;line-height:1.85;color:var(--t)}
.art-body p{margin-bottom:1.2em}
.src-link{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--t3);border:1px solid var(--br);padding:7px 14px;border-radius:5px;margin-top:20px;background:#fff;transition:all .15s}
.src-link:hover{color:var(--t);border-color:var(--br2)}
.art-sb .sbt{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--t4);padding-bottom:10px;border-bottom:2px solid var(--br);margin-bottom:14px}
.rel-posts{display:flex;flex-direction:column;gap:8px}
.bk{display:inline-flex;align-items:center;gap:5px;color:var(--t3);font-size:13px;margin-bottom:24px;transition:color .15s}
.bk:hover{color:var(--t)}
@media(max-width:900px){.art-layout{grid-template-columns:1fr}.art-sb{display:none}.art-title{font-size:22px}.art-body-wrap{padding:20px 18px}}
"""

    content = (
        f'<div class="wrap">'
        f'<a class="bk" href="javascript:history.back()">← Назад</a>'
        f'<div class="art-layout"><div>'
        f'<div class="art-src-row">'
        f'<span class="src-badge">{esc(source_name(src))}</span>'
        f'<div class="art-pers">{persons_html}</div>'
        f'</div>'
        f'<h1 class="art-title">{esc(p["title"])}</h1>'
        f'{img_html}'
        f'<div class="art-metabar">'
        f'<span class="art-date">{fmt_date_full_short(p["date"])}</span>'
        f'<div class="art-tags">{tags_html}</div>'
        f'</div>'
        f'<div class="art-body-wrap"><div class="art-body">{body_html}</div></div>'
        f'{src_link}'
        f'<div class="tgcta">{TG_SVG}'
        f'<div class="ctxt">'
        f'<div class="ctit">Читайте Maple Barrel в Telegram</div>'
        f'<div class="csub">Новые материалы каждый день — прямо в мессенджере</div>'
        f'<div class="ctgp">Этот пост в Telegram: <a href="{esc(p["tg_url"])}" target="_blank" rel="noopener">{esc(p["tg_url"])}</a></div>'
        f'</div>'
        f'<a class="cbtn2" href="{TG_CHANNEL}" target="_blank" rel="noopener">Подписаться</a>'
        f'</div>'
        f'</div>'
        f'<div class="art-sb">'
        f'<div class="sbt">Читайте также</div>'
        f'<div class="rel-posts">{related_html}</div>'
        f'</div>'
        f'</div></div>'
        f'<script type="application/ld+json">{json_ld}</script>'
    )

    active = 'longreads' if p.get('is_longread') else 'news'
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
    css = """
.day-hdr{display:flex;align-items:baseline;gap:12px;padding:18px 0 12px;border-bottom:2px solid var(--br);margin-bottom:18px}
.day-label{font-family:var(--serif);font-size:20px;font-weight:700;color:var(--t)}
.day-sub{font-size:12px;color:var(--t3)}
.hero-card{display:grid;grid-template-columns:1.2fr 1fr;margin-bottom:18px;border-radius:8px;overflow:hidden;box-shadow:var(--shadow);background:#fff;transition:transform .15s}
.hero-card:hover{box-shadow:0 4px 20px rgba(0,0,0,.12)}
.hc-img{overflow:hidden;background:var(--bg4);aspect-ratio:4/3}
.hc-img img{width:100%;height:100%;object-fit:cover;display:block}
.hc-img .card-placeholder{height:100%}
.hc-body{padding:22px 22px 20px;display:flex;flex-direction:column;gap:9px;background:#fff}
.hc-title{font-family:var(--serif);font-size:18px;font-weight:700;line-height:1.3;color:var(--t);flex:1}
.hc-ex{font-size:13px;color:var(--t2);line-height:1.55;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.sec-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:16px}
.card{background:#fff}.card-img{aspect-ratio:3/2}
.compact-grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--br);margin-bottom:22px;border-radius:6px;overflow:hidden}
.compact-item{background:#fff;display:flex;gap:10px;padding:11px 14px;align-items:flex-start;transition:background .12s}
.compact-item:hover{background:var(--bg3)}
.ci-num{font-family:var(--serif);font-size:17px;font-weight:700;color:var(--br2);flex-shrink:0;line-height:1;min-width:22px;text-align:right;padding-top:2px}
.ci-body{flex:1;display:flex;flex-direction:column;gap:4px}
.ci-title{font-family:var(--serif);font-size:13px;font-weight:700;line-height:1.3;color:var(--t);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.yesterday-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}
.prev-section{margin-top:8px}
.prev-day{margin-bottom:10px}
.prev-day-btn{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--br);cursor:pointer;width:100%;background:none;border-top:none;border-left:none;border-right:none;text-align:left;font-family:var(--sans)}
.prev-day-btn:hover .pd-label{color:var(--t)}
.pd-label{font-family:var(--serif);font-size:14px;font-weight:700;color:var(--t3);transition:color .15s}
.pd-count{font-size:11px;color:var(--t3)}
.pd-tog{font-size:11px;color:var(--t4);margin-left:auto}
.prev-posts{display:none;grid-template-columns:repeat(4,1fr);gap:12px;padding:12px 0}
.prev-posts.open{display:grid}
.pp-card{background:#fff;border-radius:6px;padding:10px 12px;display:flex;flex-direction:column;gap:4px;box-shadow:var(--shadow-sm);transition:transform .12s}
.pp-card:hover{transform:translateY(-1px)}
.pp-src{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#fff;background:var(--ac);padding:1px 6px;border-radius:2px;display:inline-block;width:fit-content;margin-bottom:2px}
.pp-title{font-family:var(--serif);font-size:12px;font-weight:700;line-height:1.3;color:var(--t);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
@media(max-width:1100px){.yesterday-grid{grid-template-columns:repeat(3,1fr)}.prev-posts{grid-template-columns:repeat(3,1fr)}}
@media(max-width:900px){.hero-card{grid-template-columns:1fr}.hc-img{min-height:180px}.sec-grid{grid-template-columns:1fr 1fr}.yesterday-grid{grid-template-columns:1fr 1fr}.compact-grid{grid-template-columns:1fr}.prev-posts{grid-template-columns:repeat(2,1fr)}}
@media(max-width:600px){.sec-grid{grid-template-columns:1fr}.yesterday-grid{grid-template-columns:1fr 1fr}}
"""
    dates = sorted(posts_by_date.keys(), reverse=True)
    html = '<div class="wrap">'

    for di, date in enumerate(dates[:9]):
        posts = posts_by_date[date]
        if di == 0:
            label = 'Сегодня'
        elif di == 1:
            label = 'Вчера'
        else:
            label = fmt_date_full_short(date)

        if di == 0:
            # TODAY: hero + 3-grid + compact list
            html += f'<div class="day-hdr"><div class="day-label">{label}</div><div class="day-sub">{len(posts)} материалов · {fmt_date_full_short(date)}</div></div>'
            if posts:
                html += hero_card(posts[0])
            if len(posts) > 1:
                sec = posts[1:4]
                html += f'<div class="sec-grid">{"".join(small_card(p) for p in sec)}</div>'
            if len(posts) > 4:
                rest = posts[4:]
                html += f'<div class="compact-grid">{"".join(compact_item(p, i+5) for i, p in enumerate(rest))}</div>'

        elif di == 1:
            # YESTERDAY: 4-card grid
            html += f'<div class="day-hdr"><div class="day-label">{label}</div><div class="day-sub">{len(posts)} материалов</div></div>'
            html += f'<div class="yesterday-grid">{"".join(small_card(p) for p in posts[:8])}</div>'
            if len(posts) > 8:
                extra = posts[8:]
                html += f'<div class="compact-grid" style="margin-top:-10px;margin-bottom:24px">{"".join(compact_item(p, i+9) for i, p in enumerate(extra))}</div>'

        else:
            # PREVIOUS DAYS: collapsible
            if di == 2:
                html += '<div class="prev-section">'
            posts_html = ''.join(f'''<a class="pp-card" href="{post_url(p)}">
              <span class="pp-src">{esc(source_name(p.get("source","")))}</span>
              <div class="pp-title">{esc(p["title"])}</div>
              <div class="card-date" style="font-size:10px;color:var(--t3)">{fmt_date(p["date"])}</div>
            </a>''' for p in posts)
            idx_str = str(di)
            html += f'''<div class="prev-day">
              <button class="prev-day-btn" onclick="toggleDay('{idx_str}')">
                <span class="pd-label">{label}</span>
                <span class="pd-count">{len(posts)} материалов</span>
                <span class="pd-tog" id="pt{idx_str}">+ показать</span>
              </button>
              <div class="prev-posts" id="pd{idx_str}">{posts_html}</div>
            </div>'''

    if len(dates) > 2:
        html += '</div>'  # close prev-section

    html += '</div>'
    html += '<script>function toggleDay(id){const el=document.getElementById("pd"+id);const tog=document.getElementById("pt"+id);const open=el.classList.toggle("open");tog.textContent=open?"− скрыть":"+ показать"}</script>'

    return page_shell(
        title="Maple Barrel — Новости Канады на русском",
        desc="Ежедневный обзор канадских СМИ на русском языке. Политика, экономика и жизнь Канады из CBC, Globe and Mail, CTV и других ведущих изданий.",
        url="/",
        content=html,
        active='news',
        css_extra=css
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


def build_surveys_page(posts, page=1):
    per = POSTS_PER_PAGE
    total = len(posts)
    pages = max(1, -(-total // per))
    page_posts = posts[(page-1)*per:page*per]
    pgn = _pagination(page, pages, '/surveys/')
    css = """
.mat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.page-intro{padding:16px 0 22px;border-bottom:1px solid var(--br);margin-bottom:22px}
.page-intro h1{font-family:var(--serif);font-size:26px;font-weight:700;margin-bottom:6px;color:var(--cream)}
.page-intro p{font-size:14px;color:var(--t2)}
@media(max-width:900px){.mat-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:640px){.mat-grid{grid-template-columns:1fr}}
"""
    content = f"""<div class="wrap">
  <div class="page-intro">
    <h1>Опросы и статистика</h1>
    <p>Данные, исследования, опросы и рейтинги — всё что можно измерить о Канаде.</p>
  </div>
  <div class="mat-grid">{"".join(small_card(p) for p in page_posts)}</div>
  {pgn}
</div>"""
    return page_shell(
        title="Опросы и статистика — Maple Barrel",
        desc="Данные, исследования, опросы и рейтинги о Канаде на русском языке.",
        url="/surveys/",
        content=content,
        active='surveys',
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

    if os.path.exists(SITE_DIR):
        shutil.rmtree(SITE_DIR)
    os.makedirs(SITE_DIR)

    photos_src = os.path.join(DATA_DIR, 'photos')
    photos_dst = os.path.join(SITE_DIR, 'photos')
    os.makedirs(photos_dst, exist_ok=True)
    if os.path.exists(photos_src):
        import glob
        photos = glob.glob(os.path.join(photos_src, '*.jpg')) + \
                 glob.glob(os.path.join(photos_src, '*.jpeg')) + \
                 glob.glob(os.path.join(photos_src, '*.png')) + \
                 glob.glob(os.path.join(photos_src, '*.webp'))
        for ph in photos:
            shutil.copy2(ph, photos_dst)
        print(f"   📷 Скопировано фото: {len(photos)}")
    else:
        print(f"   ⚠️  Папка data/photos не найдена — фото не будет")

    json_path = os.path.join(DATA_DIR, 'result.json')
    if not os.path.exists(json_path):
        print(f"❌ Не найден {json_path}")
        return

    print(f"   📖 Парсим result.json...")
    posts = parse_telegram_export(json_path)
    print(f"   ✅ {len(posts)} постов")

    posts = tag_posts(posts)
    posts_desc = list(reversed(posts))

    by_date = defaultdict(list)
    for p in posts_desc:
        by_date[p['date']].append(p)

    # Use internal flags (not tag strings)
    material_posts  = [p for p in posts_desc if p.get('is_material')]
    longread_posts  = [p for p in posts_desc if p.get('is_longread')]
    survey_posts    = [p for p in posts_desc if p.get('is_stat')]

    print(f"   📰 Материалы: {len(material_posts)}  Лонгриды: {len(longread_posts)}  Опросы: {len(survey_posts)}")

    # ── Главная ──
    write('index.html', build_news_index(by_date))

    # ── Страницы постов ──
    print(f"   📄 Генерируем {len(posts_desc)} страниц постов...")
    for p in posts_desc:
        related = [r for r in posts_desc if r['id'] != p['id']
                   and any(t in (r.get('tags') or []) for t in (p.get('tags') or []))][:4]
        if not related:
            related = posts_desc[:4]
        write(f"post/{post_slug(p)}/index.html", build_post_page(p, related))

    per = POSTS_PER_PAGE

    # ── Материалы ──
    for pg in range(1, max(1, -(-len(material_posts) // per)) + 1):
        write(f'materials/{"" if pg==1 else f"page/{pg}/"}index.html',
              build_materials_page(material_posts, pg))

    # ── Лонгриды ──
    for pg in range(1, max(1, -(-len(longread_posts) // per)) + 1):
        write(f'longreads/{"" if pg==1 else f"page/{pg}/"}index.html',
              build_longreads_page(longread_posts, pg))

    # ── Опросы ──
    for pg in range(1, max(1, -(-len(survey_posts) // per)) + 1):
        write(f'surveys/{"" if pg==1 else f"page/{pg}/"}index.html',
              build_surveys_page(survey_posts, pg))

    # ── Теги (только публичные темы) ──
    tag_index = defaultdict(list)
    for p in posts_desc:
        for t in (p.get('tags') or []):
            tag_index[t].append(p)

    print(f"   🏷  Генерируем {len(tag_index)} тегов...")
    for tag, tposts in tag_index.items():
        for pg in range(1, max(1, -(-len(tposts) // per)) + 1):
            write(f'tag/{slugify(tag)}/{"" if pg==1 else f"page/{pg}/"}index.html',
                  build_tag_page(tag, tposts, pg))

    # ── Персоны ──
    person_index = defaultdict(list)
    for p in posts_desc:
        for per_name in (p.get('persons') or []):
            person_index[per_name].append(p)

    print(f"   👤 Генерируем {len(person_index)} персон...")
    for person, pposts in person_index.items():
        for pg in range(1, max(1, -(-len(pposts) // per)) + 1):
            write(f'person/{slugify(person)}/{"" if pg==1 else f"page/{pg}/"}index.html',
                  build_person_page(person, pposts, pg))

    write('about/index.html', build_about_page())
    write('contacts/index.html', build_contacts_page())
    write('sitemap.xml', build_sitemap(posts_desc))
    write('robots.txt', build_robots())
    write('_redirects', '/post/*  /post/:splat  200\n/tag/*  /tag/:splat  200\n/surveys/*  /surveys/:splat  200\n')

    elapsed = (datetime.now() - start).total_seconds()
    total_files = sum(len(fs) for _, _, fs in os.walk(SITE_DIR))
    print(f"\n✅ Готово за {elapsed:.1f} сек — {total_files} файлов в папке /{SITE_DIR}/")
    print(f"   Следующий шаг: commit + push в GitHub Desktop")


if __name__ == '__main__':
    build()