# Maple Barrel — Инструкция по деплою

## Структура проекта

```
твоя-папка/
├── build.py          ← этот скрипт
├── data/
│   ├── result.json   ← экспорт из Telegram
│   └── photos/       ← папка с фото из архива
└── site/             ← генерируется автоматически (не трогать руками)
```

## Первый запуск

1. Установи Python 3 если нет: https://python.org
2. Положи `result.json` в папку `data/`
3. Положи фото из архива Telegram в `data/photos/`
4. Запусти: `python build.py`
5. Папка `site/` — это готовый сайт

## Обновление (каждый день)

1. Экспортируй новый `result.json` из Telegram Desktop
2. Положи в `data/result.json` (замени старый)
3. `python build.py` — 8-10 секунд
4. GitHub Desktop: увидишь изменения → Commit → Push
5. Cloudflare Pages задеплоит автоматически за 20 сек

## Настройка Cloudflare Pages

1. Зайди на pages.cloudflare.com
2. Create Project → Connect to Git → выбери репозиторий
3. Build settings:
   - Build command: (пусто)
   - Build output directory: site
4. Подключи домен journalists.ca:
   - Settings → Custom domains → Add domain
   - На GoDaddy добавь CNAME запись: journalists.ca → твой-сайт.pages.dev

## Добавление фото

В архиве Telegram есть папка `photos/` — скопируй её содержимое в `data/photos/`.
Имена файлов должны совпадать с теми что в result.json (photo_XXXX@дата.jpg).

## Настройки в build.py

Первые строки файла — всё что можно менять:
- `BASE_URL` — твой домен
- `TG_CHANNEL` — ссылка на канал
- `POSTS_PER_PAGE` — постов на странице
