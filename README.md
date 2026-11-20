# Барахолка устройств — Telegram Mini App + bot (MVP)

Каталог объявлений о покупке и продаже техники внутри Telegram: поиск, фильтры,
карточки с фотографиями, публикация за пару шагов и управление своими
объявлениями. Оригинальный интерфейс, без чужих логотипов и текстов.

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2 (sync), Alembic, PostgreSQL.
- **Bot:** aiogram 3 (long polling в dev, webhook — на ваш выбор в production).
- **Frontend:** HTML + CSS + ES-модули, без сборки и без React.
- **Files:** локальное хранилище в dev, S3-совместимое объектное хранилище через конфигурацию.
- **Tests:** pytest + FastAPI TestClient на реальной SQLite-базе.

---

## 1. Что реализовано

### Каталог
- поиск по названию и описанию, фильтры по типу, району, состоянию и цене,
  сортировка по дате и цене, постраничная подгрузка (limit/offset);
- карточка: тип, название, цена/бюджет, краткое описание под фото (до 3 строк,
  чтобы не открывать объявление), состояние, район, обложка, количество фото,
  относительное время («3 часа назад»);
- состояния «загрузка» (skeleton), «ничего не найдено», «ошибка сети» с повтором;
- рекламный блок из конфигурации (отключаемый, без сырого HTML);
- открытие конкретного объявления по deep link `?listing=<id>` или `start_param`.

### Публикация
- пошаговый мастер: тип → детали → фото → проверка и публикация;
- «Продам»: название, состояние, цена и район обязательны;
- цена может быть числом или **«Договорная»** (в базе хранится `NULL`);
- состояние выбирается из списка или задаётся текстом («9 из 10»);
- «Куплю»: название/описание и район обязательны, состояние опционально,
  бюджет либо число, либо отметка «Бюджет не указан»;
- фотографии: до `PHOTO_MAX_COUNT`, форматы и размер задаются env,
  предпросмотр и удаление до публикации, повторная серверная проверка;
- объявление уходит на проверку администратору (по умолчанию) и попадает в каталог
  только после одобрения; статус `active` при этом сохраняется;
- владелец может редактировать название, описание, состояние, цену, район и фото.

### Аккаунт
- профиль Telegram, признак администратора;
- свои объявления, сгруппированные по статусам;
- смена статуса: «Продам» → `active`/`sold`, «Куплю» → `active`/`closed`,
  повторное нажатие идемпотентно;
- редактирование своих объявлений, включая фото;
- кнопка поддержки из `SUPPORT_URL` с корректным сообщением, если ссылка не задана.

### Жалобы
- кнопка «Пожаловаться» в карточке чужого объявления;
- фиксированный список причин и обязательный комментарий;
- жалоба сохраняется в PostgreSQL и попадает в audit trail;
- администраторы получают уведомление в Telegram с номером объявления,
  причиной и текстом жалобы.

### Бот
- `/start` с кнопкой запуска Mini App, `/help`, `/id` (ваш Telegram ID);
- **модерация**: уведомление о новом объявлении приходит админам с кнопками
  «✅ Опубликовать» и «❌ Отклонить». При отклонении бот просит причину и
  отправляет её автору; исправленное объявление уходит на проверку заново.
  До одобрения объявление видят только владелец и администратор;
- `/stats` только для ID из `TELEGRAM_ADMIN_IDS` (проверка на сервере);
- `/add` — пошаговое добавление рекламного баннера (заголовок, текст, ссылка,
  подпись кнопки, фото), `/dadd` — удаление баннера;
- `/pres` — рассылка текста и/или фото всем пользователям бота с подтверждением
  и отчётом о доставке; тоже только для администраторов;
- уведомления администраторам о каждом новом объявлении и новой жалобе через
  transactional outbox: запись создаётся в одной транзакции с событием,
  отправка повторяется с backoff, дубли исключены (`dedupe_key` + статус строки).

### Безопасность (реализована, а не только описана)
- HMAC-проверка Telegram `initData` официальным алгоритмом + проверка `auth_date`;
- никакой идентификации по `telegram_id` из тела запроса (лишние поля запрещены);
- проверка владельца в каждом endpoint изменения/чтения;
- роли только из env; `/stats` проверяет ID на сервере;
- деньги — `NUMERIC(12,2)` и `Decimal`, на клиент уходят строкой;
- параметризованные запросы SQLAlchemy, `LIKE` с экранированием;
- загрузка файлов: лимиты количества/размера, проверка заявленного MIME,
  определение формата по содержимому (Pillow), перекодирование со сбросом EXIF,
  случайные имена, хранение вне публичной директории, отдача по подписанной ссылке;
- rate limit на публикацию, фото, смену статуса и общий лимит по IP;
- CORS только для заданных origin, security headers + CSP, HSTS в production;

---

## 2. Структура проекта

```text
telegram-device-market/
├── app/
│   ├── main.py                 # создание FastAPI, middleware, static-раздача frontend
│   ├── api/
│   │   ├── deps.py             # settings/session/storage/auth, rate limit dependency
│   │   ├── errors.py           # обработчики ошибок (без утечек)
│   │   ├── meta.py             # meta, support, ad, rules
│   │   ├── presenters.py       # ORM → Pydantic
│   │   ├── routes_me.py        # /api/me, /api/meta, /api/me/listings
│   │   ├── routes_listings.py  # каталог, создание, статус, фото
│   │   ├── routes_photos.py    # подписанная выдача файла
│   │   ├── routes_ads.py       # выдача рекламного баннера
│   │   └── routes_system.py    # /api/health
│   ├── bot/
│   │   ├── handlers.py         # команды, модерация, /add, /dadd, /pres
│   │   ├── keyboards.py        # клавиатуры и тексты
│   │   ├── notifications.py    # sender + outbox worker
│   │   └── main.py             # entrypoint aiogram
│   ├── core/
│   │   ├── config.py           # pydantic-settings, production-валидаторы
│   │   ├── districts.py        # фиксированный список районов
│   │   ├── enums.py            # типы, статусы, состояния, подписи
│   │   ├── errors.py           # AppError и подклассы
│   │   ├── logging.py          # маскирование секретов
│   │   ├── rate_limit.py       # in-process limiter
│   │   ├── security.py         # initData
│   │   └── signing.py          # подписанные URL фотографий
│   ├── db/                     # Base, engine, session factory
│   ├── models/                 # User, Listing, ListingPhoto, Ad, AuditEvent, NotificationOutbox
│   ├── schemas/                # Pydantic-схемы запросов/ответов
│   ├── services/               # бизнес-логика и проверки прав
│   ├── storage/                # Protocol + LocalStorage + S3Storage
│   └── tests/                  # pytest
├── frontend/
│   ├── index.html
│   ├── assets/logo.svg
│   ├── css/app.css
│   └── js/
│       ├── api.js  telegram.js  format.js  dom.js  app.js
│       └── views/ catalog.js  create.js  account.js  detail.js
├── migrations/                 # Alembic env + ревизии 0001–0003
├── scripts/dev_init_data.py    # подписанный initData для локальной отладки
├── scripts/start_all.sh        # миграции + API + бот в одном контейнере
├── scripts/init_git.ps1        # инициализация Git и push одной командой
├── scripts/init_git.cmd        # то же самое двойным щелчком в Windows
├── scripts/init_git.sh
├── amvera.yml                  # конфигурация деплоя на Amvera
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
├── .gitattributes
├── .dockerignore
├── DEPLOY_AMVERA.md            # пошаговый деплой на Amvera
├── GIT_SETUP.md                # как выгрузить проект на GitHub/GitLab
├── pyproject.toml
└── README.md
```

---

## 3. Быстрый старт (Docker Compose: PostgreSQL + API + бот)

```bash
cp .env.example .env
# отредактируйте .env: APP_SECRET_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBAPP_URL,
# TELEGRAM_ADMIN_IDS, SUPPORT_URL при необходимости

docker compose up --build
```

Что произойдёт:

1. поднимется PostgreSQL 16 с healthcheck;
2. контейнер `api` применит `alembic upgrade head` и запустит uvicorn на `http://localhost:8000`;
3. контейнер `bot` запустит long polling aiogram и воркер уведомлений.

Проверка:

```bash
curl http://localhost:8000/api/health
```

Mini App: откройте `http://localhost:8000` в браузере — интерфейс загрузится, но
API вернёт 401, пока нет валидного `initData`. Для локальной отладки см. раздел 8.

> `docker-compose.yml` использует dev-пароль `market` для PostgreSQL. Для любого
> доступного извне окружения задайте `POSTGRES_PASSWORD` и обновите `DATABASE_URL`.

---

## 4. Локальный запуск без Docker (только PostgreSQL в Docker)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d db
cp .env.example .env        # и заполните значения

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Отдельный процесс бота:

```bash
python -m app.bot.main
```

Frontend раздаётся тем же приложением (`GET /`), поэтому отдельный dev-server не нужен.
API-документация (Swagger): `http://localhost:8000/api/docs` (отключается
`APP_DOCS_ENABLED=false`).

### Как настроить бота

1. Откройте [@BotFather](https://t.me/BotFather), создайте бота, получите токен.
2. `TELEGRAM_BOT_TOKEN` — токен, `TELEGRAM_BOT_USERNAME` — username без `@`.
3. Разместите приложение на публичном HTTPS-домене (Telegram не откроет HTTP Mini App).
4. `TELEGRAM_WEBAPP_URL=https://your-domain.example` — тот же домен отдаёт `frontend/`.
5. Узнайте свой Telegram ID: запустите бота и отправьте `/id`, затем впишите его
   в `TELEGRAM_ADMIN_IDS` (можно несколько через запятую).
6. Перезапустите бота: `/start` покажет кнопку «Открыть каталог», меню бота тоже
   получит Web App кнопку.
7. Каждый администратор из `TELEGRAM_ADMIN_IDS` должен хотя бы раз нажать `/start`
   у бота: Telegram не позволяет ботам писать первыми. Если админ не начинал диалог,
   уведомление помечается как `failed` с ошибкой доступа и повторно не отправляется.

Если настроить нечего, бот не падает: команды работают, а кнопка появляется только
при корректном `TELEGRAM_WEBAPP_URL`.

---

## 5. Переменные окружения

Все значения читаются из переменных окружения (`.env` подхватывается автоматически).
`.env.example` содержит только фиктивные примеры; реальный `.env` в `.gitignore`.

| Переменная | Обязательна | Назначение |
| --- | --- | --- |
| `APP_ENV` | нет | `development` / `test` / `production` (в production включаются строгие проверки) |
| `APP_SECRET_KEY` | **да** | ≥32 символов; ключ подписи URL фотографий |
| `DATABASE_URL` | да | `postgresql+psycopg://user:pass@host:5432/db` |
| `TELEGRAM_BOT_TOKEN` | **да** | токен бота, используется для проверки initData и для aiogram |
| `TELEGRAM_WEBAPP_URL` | **да** | публичный HTTPS URL Mini App |
| `TELEGRAM_ADMIN_IDS` | нет | ID администраторов через запятую (для `/stats` и уведомлений) |
| `TELEGRAM_INIT_DATA_MAX_AGE_SECONDS` | нет | срок жизни initData (по умолчанию 86400) |
| `SUPPORT_URL` | нет | `https://t.me/...`, `tg://...`; пусто — кнопка покажет сообщение |
| `LISTING_RULES_TEXT` | нет | правила публикации; если задано, сервер требует `rules_accepted=true` |
| `LISTING_MODERATION_ENABLED` | нет | `true` (по умолчанию) — новые объявления ждут одобрения админа; `false` — публикуются сразу |
| `AD_ENABLED` | нет | включает fallback-рекламу из env (если баннер не задан через бота) |
| `AD_TITLE`, `AD_TEXT`, `AD_IMAGE_URL`, `AD_LINK_URL`, `AD_BUTTON_TEXT` | нет | env-реклама; используется только когда в БД нет баннера, добавленного командой `/add` |
| `STORAGE_BACKEND` | нет | `local` (по умолчанию) или `s3` |
| `LOCAL_STORAGE_DIR` | нет | каталог локального хранилища (по умолчанию `var/media`) |
| `S3_*` | при `s3` | bucket/region/endpoint/keys, префикс, SSL |
| `PHOTO_MAX_COUNT` | нет | максимум фото на объявление (по умолчанию 5) |
| `PHOTO_MAX_SIZE_MB` | нет | максимальный размер файла (по умолчанию 8) |
| `PHOTO_ALLOWED_MIME_TYPES` | нет | список разрешённых типов (JPEG/PNG/WEBP) |
| `PHOTO_URL_TTL_SECONDS` | нет | срок жизни подписанной ссылки на фото |
| `RATE_LIMIT_*` | нет | лимиты запросов (0 отключает конкретный лимит) |
| `RUN_API` | нет | `1` — запускать FastAPI; `0` — только бот (для раздельного деплоя) |
| `RUN_BOT` | нет | `1` — запускать aiogram; `0` — только API |
| `RUN_MIGRATIONS` | нет | `1` — применять Alembic при старте; `0` — пропустить (для bot-контейнера) |
| `APP_PORT` | нет | порт uvicorn, должен совпадать с `run.containerPort` в `amvera.yml` |
| `CORS_ALLOWED_ORIGINS` | нет | список origin через запятую; пусто — CORS не включается |
| `ALLOWED_HOSTS` | нет | список Host через запятую; в production нельзя `*`, но можно `*.amvera.io` |
| `TRUST_PROXY_HEADERS` | нет | доверять `X-Forwarded-For` (только за своим reverse proxy) |
| `APP_DOCS_ENABLED` | нет | Swagger/OpenAPI под `/api/docs` |
| `APP_AUTO_CREATE_TABLES` | нет | только dev; в production запрещено, используйте Alembic |
| `LOG_LEVEL` | нет | `INFO` по умолчанию |

> Секреты не имеют значений по умолчанию — приложение не стартует без
> `APP_SECRET_KEY` и `TELEGRAM_BOT_TOKEN`.

---

## 6. База данных и миграции

Модели: `users`, `listings`, `listing_photos`, `listing_complaints`, `audit_events`,
`notification_outbox`. Миграции: `0001_initial`, `0002_features`.
Индексы: `(status, kind, created_at)`, `(district, status)`, `price_amount`,
`(owner_telegram_id, status)`, `created_at`, индексы фото и outbox.

```bash
# применить миграции
alembic upgrade head

# откатить последнюю
alembic downgrade -1

# новая миграция после изменения моделей (autogenerate)
alembic revision --autogenerate -m "describe change"
```

`migrations/env.py` берёт URL из `DATABASE_URL` (или из настроек приложения),
поэтому миграции можно запускать без остальных секретов.

Деньги хранятся как `NUMERIC(12,2)`; бюджет «Куплю» может быть `NULL`.
Время — `TIMESTAMPTZ`, все значения в UTC; API отдаёт ISO-8601 с `+00:00`,
клиент показывает относительное время.

---

## 7. Тесты и линтер

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

Тесты используют изолированную SQLite-базу на каждый тест-клиент (файл во временном
каталоге) и реальный `TestClient`, поэтому проверяются middleware, зависимости,
Pillow-валидация, подписанные URL и outbox. PostgreSQL-специфика (типы, индексы,
миграции) проверяется запуском `alembic upgrade head` против контейнера из
`docker-compose.yml`.

Покрытые сценарии:

- недействительный, изменённый и просроченный initData; отсутствие заголовка;
- доступ к чужому объявлению (просмотр, смена статуса, загрузка/удаление фото);
- создание объявления: валидные и невалидные поля, цены, длины, лишние поля;
- договорная цена, своё состояние и их серверная валидация;
- редактирование объявления владельцем и запрет для чужого пользователя;
- жалобы: сохранение, причины, запрет на своё объявление, уведомление админу;
- недопустимый район, нормализация регистра;
- переходы статусов для «Продам» и «Куплю», идемпотентность;
- фильтры, сортировка, пагинация каталога;
- статистика и запрет `/stats` не-администратору (включая отсутствие аудита);
- формат/размер/количество фото, подписанные ссылки, удаление файла;
- ошибка доставки уведомления: объявление сохранено, outbox повторяет попытки;
- rate limit, security headers, CORS, отсутствие внутренних деталей в ошибках.

---

## 8. Локальная проверка Mini App без Telegram

Telegram передаёт `initData` только внутри клиента. Для отладки в браузере можно
сгенерировать **валидную подпись** тем же алгоритмом, что использует сервер:

```bash
python scripts/dev_init_data.py --user-id 100000001
```

Скрипт печатает строку и готовый фрагмент для консоли браузера:

```js
localStorage.setItem("dev_init_data", "<строка>");
location.reload();
```

Это не обход авторизации: сервер всё равно проверяет HMAC и `auth_date`.
Фронтенд читает `localStorage.dev_init_data` только как fallback, когда окно
открыто вне Telegram. Перед production этот fallback можно удалить.

---

## 9. API

Все endpoint’ы, кроме `/api/health` и выдачи фото по подписи, требуют заголовок:

```
Authorization: tma <initData>
```

также поддерживается `X-Telegram-Init-Data: <initData>`. `initData` никогда не
передаётся в query string.

Ошибки имеют единый формат:

```json
{"error": {"code": "validation_error", "message": "Проверьте правильность заполнения полей."},
 "fields": [{"field": "title", "message": "Обязательное поле."}]}
```

| Метод | Путь | Доступ | Описание / ошибки |
| --- | --- | --- | --- |
| GET | `/api/health` | без авторизации | `{status, time}` |
| GET | `/api/me` | авторизован | текущий пользователь, `is_admin`, признак настроенной поддержки. 401 |
| GET | `/api/meta` | авторизован | районы, типы, состояния, статусы, лимиты фото, поддержка, реклама, правила, причины жалоб. 401 |
| GET | `/api/me/listings` | авторизован | свои объявления + счётчики по статусам. 401 |
| GET | `/api/listings` | авторизован | каталог только активных. Параметры: `q`, `kind`, `district`, `condition`, `min_price`, `max_price`, `sort` (`newest`/`price_asc`/`price_desc`), `limit` (1–50), `offset`. Каждая карточка содержит `description` — превью показывается под фото. 401, 422 |
| POST | `/api/listings` | авторизован + rate limit | создание. Тело: `kind`, `title`, `description?`, `condition?`, `condition_text?`, `price_amount?`, `price_negotiable?`, `district`, `rules_accepted?`. 201; 401, 409, 422 (`rules_not_accepted`, `validation_error`), 429 |
| GET | `/api/listings/{id}` | авторизован | активное объявление видят все; неактивное — только владелец (иначе 404). 401, 404 |
| GET | `/api/ad/image` | без авторизации | изображение активного рекламного баннера; 404, если баннера нет |
| PUT | `/api/listings/{id}` | только владелец | обновление названия, описания, состояния, цены, района. Тип объявления не меняется. 200; 401, 403, 404, 422, 429 |
| POST | `/api/listings/{id}/complaints` | авторизован + rate limit | `{"reason": "fraud", "comment": "..."}`; 201 `ComplaintOut`. 401, 404, 422 (`own_listing`, `validation_error`), 429 |
| PATCH | `/api/listings/{id}/status` | только владелец | `{"status": "sold"|"closed"|"active"}`; неверная пара тип/статус → 422 `invalid_status_for_kind`; чужое → 403. 401, 403, 404 |
| POST | `/api/listings/{id}/photos` | только владелец | multipart `file`; 201 `PhotoOut`. 401, 403, 404, 409 (`photo_limit_reached`), 413, 422, 429 |
| DELETE | `/api/listings/{id}/photos/{photo_id}` | только владелец | 204; 401, 403, 404 |
| GET | `/api/photos/{id}/file?exp=&sig=` | подписанная ссылка | байты изображения, `Cache-Control`, `nosniff`. 403 при истёкшей/неверной подписи, 404 |

Пример создания:

```json
POST /api/listings
{
  "kind": "sell",
  "title": "iPhone 12 128 ГБ",
  "description": "Комплект, чехол в подарок.",
  "condition": "good",
  "price_amount": "35000.00",
  "district": "Центр",
  "rules_accepted": true
}
```

Схемы ответов (Pydantic, ORM наружу не отдаётся): `ListingSummaryOut`,
`ListingDetailOut`, `ListingListOut`, `MyListingsOut`, `PhotoOut`, `PriceOut`,
`MeOut`, `MetaOut`. Полные схемы — в `/api/docs` и `app/schemas/`.

---

## 10. Как устроена безопасность

| Угроза | Мера в коде |
| --- | --- |
| Подделка пользователя | `validate_init_data`: HMAC-SHA256(`WebAppData` → bot token), сравнение `compare_digest`, обязательный `hash`, запрет дублей полей, проверка `auth_date` (возраст и часы в будущем) |
| Подмена роли/владельца | `is_admin` только из env; владелец берётся из проверенного initData; `extra="forbid"` не даёт передать `owner_telegram_id`/`status` |
| Чужое объявление | `get_owned_listing` бросает 403, `get_listing_for_viewer` скрывает неактивные чужие объявления за 404 |
| Инъекции | SQLAlchemy ORM/параметры; `%`/`_` в поиске экранируются, `escape="\\"` |
| Деньги | `Numeric(12,2)` + `Decimal`, строгая валидация, строка в JSON |
| Файлы | лимит чтения до `max+1` байт, заявленный MIME + Pillow-сниффинг, повторное кодирование без EXIF, случайный ключ, запрет `..` и абсолютных путей, вне static-root |
| Кража фото | HMAC-подпись `photo_id + exp` ключом из `APP_SECRET_KEY`, TTL, `nosniff`, `CSP: default-src 'none'`, `private` cache |
| Флуд | in-process лимиты по Telegram ID и по IP, `Retry-After` |
| XSS | фронтенд строит DOM через `createElement`/`textContent`, `innerHTML` нигде не используется; CSP без `unsafe-inline`; уведомления бота экранируются `html.escape` |
| Утечка секретов | секреты только из env, `repr=False`, фильтр логов маскирует bot token и `Authorization`, полные заголовки не логируются |
| Утечка ошибок | единый JSON-конверт, `Exception` handler без stack trace, 500 не содержит деталей |
| Кликджекинг | `frame-ancestors` только Telegram Web |

### Что обязательно настроить перед production

1. **HTTPS и reverse proxy** (nginx/Caddy) с редиректом с HTTP; HSTS включается
   автоматически при `APP_ENV=production`. На прокси задайте лимит тела запроса
   (например, `client_max_body_size 12m`), чтобы отсекать гигантские multipart
   до попадания в приложение.
2. `APP_ENV=production`, `APP_DEBUG=false`, `APP_DOCS_ENABLED=false` (или закрыть
   документацию на уровне прокси), `APP_AUTO_CREATE_TABLES=false`.
3. Уникальные `APP_SECRET_KEY` (≥32 символов) и `POSTGRES_PASSWORD`, выданные
   менеджером секретов; не хранить `.env` в образе/репозитории.
4. `ALLOWED_HOSTS` = ваш домен, `CORS_ALLOWED_ORIGINS` = только домен Mini App
   (если frontend и API на разных origin), `TRUST_PROXY_HEADERS=true` только за
   своим прокси.
5. `TELEGRAM_ADMIN_IDS` — реальные ID; `SUPPORT_URL` — рабочий чат поддержки.
6. PostgreSQL: отдельный пользователь без суперправ, бэкапы, `pool_pre_ping`
   уже включён; при нескольких API-инстансах вынесите rate limit в Redis/прокси.
7. Объектное хранилище: `STORAGE_BACKEND=s3`, приватный bucket, ключи с доступом
   только к префиксу `S3_PREFIX`; локальный диск — только для одного инстанса.
8. Запускать **ровно один** контейнер бота (long polling и воркер outbox внутри
   него). Если нужно несколько — используйте webhook + отдельный singleton-воркер.
9. Мониторинг: `/api/health`, алерты на рост `notification_outbox` со `status=failed`,
   логи без секретов, ротация.
10. Проверьте применимое законодательство, правила Telegram и требования к
    товарам (возрастные/региональные ограничения) и заполните `LISTING_RULES_TEXT`:
    при непустом значении сервер не принимает публикацию без `rules_accepted=true`.

### Юридические и платформенные ограничения

Каталог может содержать товары, на которые распространяются возрастные,
лицензионные или местные ограничения. Проект **не помогает обходить** такие
правила: вместо этого в интерфейсе показываются настраиваемые правила, а сервер
требует явного подтверждения. Перед запуском проверьте:

- законодательство вашего региона о продаже устройств и сопутствующих товаров;
- правила Telegram для Mini Apps и ботов (запрещённые категории, реклама);
- требования к персональным данным (вы обрабатываете Telegram ID и username);
- необходимость модерации/UGC-политики, если каталог станет публичным.

---

## 11. Реклама

Рекламный баннер добавляется прямо из бота командой `/add`: заголовок, текст,
ссылка, подпись кнопки и фото (фото можно пропустить). Удаляется командой `/dadd`.
Баннер хранится в таблице `ads` и в том же хранилище, что и фотографии объявлений;
картинка отдаётся с нашего origin через `/api/ad/image`, поэтому сторонние домены
и расширение CSP не нужны. В каталоге баннер показывается первым блоком сверху,
растянут на всю ширину и целиком кликабелен — открывает указанную ссылку.

Если баннер через бота не задан, используется реклама из env (`AD_*`): она
показывается только при `AD_ENABLED=true` и заполненных `AD_TITLE` + `AD_LINK_URL`.
Текст в обоих случаях выводится через `textContent`, ссылка проверяется как
`http(s)` на старте приложения, изображение добавляется в `img-src` CSP.
Неполная конфигурация не рендерится вовсе, битая картинка скрывается.

---

## 12. Допущения и границы MVP

1. **Один инстанс API** для in-process rate limit. Для горизонтального
   масштабирования нужен общий счётчик (Redis) или лимиты на прокси.
2. **Long polling** у бота. Webhook не реализован, но обработчики от этого не
   зависят; при переезде на webhook outbox-воркер нужно оставить один.
3. **Фото загружаются после создания объявления.** Если загрузка не удалась,
   объявление уже сохранено, клиент показывает предупреждение. Отдельный endpoint
   для добавления фото позже есть.
4. **Пагинация offset-based.** Для больших каталогов стоит перейти на keyset
   (`created_at, id`); индексы под это уже заложены.
5. **Валюта — RUB** (поле `currency` есть, конвертации и выбора валюты нет).
6. **Нет удаления объявления**, только смена статуса, редактирование полей и
   удаление фото: это сознательно минимальный набор для MVP.
7. **Нет чата внутри приложения**: связь через публичный username продавца или
   ссылку поддержки. Рассылка `/pres` уходит только тем, кто уже написал боту
   (Telegram не позволяет писать первым), остальные получат ошибку доставки.
8. **Модерация ручная**: решение принимает администратор в боте, автоматической
   проверки контента нет. Лимиты на пользователя — только rate limit.
9. **Удаление объявлений** не предусмотрено, поэтому файлы фото удаляются только
   вместе с фото; при будущем удалении объявления нужно чистить storage.
10. **SQLite в тестах**, PostgreSQL в production: регистрозависимость `ILIKE` в
    тестах ограничена ASCII, в PostgreSQL поиск по кириллице регистронезависим.
11. `TZ` пользователя не передаётся: относительное время считается на клиенте,
    точное время показывается в локальной зоне устройства.
12. Районы жёстко заданы списком из ТЗ; изменение требует миграции CHECK-ограничения
    и обновления `app/core/districts.py`.
13. Доставка уведомлений — at-least-once: если процесс бота упадёт между успешным
    вызовом Telegram API и отметкой строки outbox, сообщение может прийти повторно.
    При штатной обработке дубли исключены.

---

## 13. Диагностика

| Симптом | Причина / решение |
| --- | --- |
| `401 unauthorized` в браузере | нет `initData`; откройте через бота или используйте `scripts/dev_init_data.py` |
| `Session expired` | `auth_date` старше `TELEGRAM_INIT_DATA_MAX_AGE_SECONDS`; перезапустите Mini App |
| Кнопка Mini App не появляется | пустой/некорректный `TELEGRAM_WEBAPP_URL` или бот запущен в группе |
| Уведомления не приходят | не задан `TELEGRAM_ADMIN_IDS`, бот не запущен, или админ не начинал диалог; смотрите `notification_outbox.last_error` |
| `/stats` отвечает «только администратору» | ваш ID не в `TELEGRAM_ADMIN_IDS`; узнайте ID командой `/id` |
| Фото не загружается | проверьте `PHOTO_MAX_SIZE_MB`, MIME и что каталог `LOCAL_STORAGE_DIR` доступен на запись |
| `TELEGRAM_WEBAPP_URL must use https` | в production разрешён только HTTPS |
| `ALLOWED_HOSTS must list explicit hostnames` | в production нельзя `*` |
| Пустая страница после сборки | frontend не скопирован в образ; проверьте `frontend/` и права |

---

## 14. Git

Репозиторий проекта: **https://github.com/zamaledinovr-max/stor**  
Рабочая копия: `C:\projects\telegram-device-market` (ветка `main`, remote `origin`).

Проект уже инициализирован и выгружен. Для дальнейших изменений:

```powershell
cd C:\projects\telegram-device-market
git add --all
git commit -m "Describe the change"
git push
```

Подробная инструкция (включая повторную инициализацию) — в [GIT_SETUP.md](GIT_SETUP.md).

Быстрый путь (Windows PowerShell, из корня проекта):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\init_git.ps1 https://github.com/<user>/<repo>.git
```

Linux/macOS/Git Bash:

```bash
./scripts/init_git.sh https://github.com/<user>/<repo>.git
```

Скрипт инициализирует `main`, создаёт первый коммит, добавляет `origin` и делает
`push`. Реальный `.env` в коммит не попадает: `.gitignore` его исключает, а скрипт
дополнительно проверяет индекс и останавливается, если там оказался секрет.

---

## 15. Деплой на Amvera Cloud

Подробная пошаговая инструкция для новичка — в [DEPLOY_AMVERA.md](DEPLOY_AMVERA.md).

Коротко:

1. Создайте в Amvera веб-проект с Docker и HTTPS-доменом.
2. Создайте Managed PostgreSQL в том же регионе.
3. Добавьте переменные окружения (`APP_SECRET_KEY`, `DATABASE_URL`,
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBAPP_URL`, `TELEGRAM_ADMIN_IDS`,
   `LOCAL_STORAGE_DIR=/data/media` и остальные из инструкции).
4. Добавьте Amvera Git remote и сделайте push:
   ```powershell
   C:\projects\git.cmd remote add amvera https://git.amvera.ru/<login>/<project>
   C:\projects\git.cmd push amvera main:master
   ```
5. Дождитесь успешной сборки и проверьте `https://<домен>/api/health`.

`amvera.yml` уже задаёт порт `8000` и постоянный диск `/data`.
`scripts/start_all.sh` применяет миграции и запускает API и бота в одном
контейнере. Для раздельного запуска есть `RUN_API` и `RUN_BOT`.
