# Деплой на Amvera Cloud — простая инструкция

Этот файл — пошаговая шпаргалка для новичка. Проект уже содержит `Dockerfile`
и `amvera.yml`, поэтому Amvera сама соберёт контейнер.

## 1. Что мы разворачиваем

В одном контейнере запускаются три вещи:

1. **FastAPI** — API каталога и одновременно раздаёт файлы Mini App (`frontend/`).
2. **aiogram-бот** — `/start`, `/stats`, уведомления администратору.
3. **PostgreSQL** — отдельная managed-база Amvera, в ней хранятся пользователи,
   объявления, фотографии (точнее, их имена в хранилище), аудит и очередь уведомлений.

Фотографии лежат не в базе, а в папке `/data/media` на постоянном диске Amvera.

Схема:

```text
Telegram
   │  открывает HTTPS-страницу Mini App
   ▼
Amvera: контейнер (FastAPI + frontend + aiogram)
   │                         │
   │                         └──► Telegram Bot API
   ├──► PostgreSQL (managed)
   └──► /data/media (постоянный диск)
```

Почему всё в одном контейнере: для MVP так дешевле и проще — один проект,
один домен, один диск, одна база. Позже API и бота можно разнести на два
приложения Amvera (см. раздел 11), код для этого уже готов (`RUN_API`/`RUN_BOT`).

## 2. Что понадобится

- аккаунт на [amvera.ru](https://amvera.ru) и небольшой баланс;
- GitHub-репозиторий проекта (уже есть: `https://github.com/zamaledinovr-max/stor`);
- токен Telegram-бота от [@BotFather](https://t.me/BotFather);
- ваш Telegram ID (бот покажет его командой `/id`);
- 10–20 минут.

Ориентировочная стоимость: одно приложение + managed PostgreSQL — примерно
от 580 ₽/мес (тарифы Amvera могут меняться; смотрите актуальные на сайте).
Начальный тариф 0.5 ГБ может хватить для теста, но для обработки фото лучше
1 ГБ.

## 3. Шаг 1 — создайте проект в Amvera

1. Зарегистрируйтесь и войдите в Amvera Cloud.
2. Нажмите **«Создать проект»**.
3. Имя проекта: например `telegram-market`.
4. Тип/окружение: выберите **«Приложение»** (веб-приложение) и **Docker**.
   Нам нужен HTTPS-домен для Mini App, поэтому это должен быть HTTP-проект,
   а не отдельный «бот без порта».
5. Регион: **Москва** (в Amvera есть бесплатный прокси до Telegram API) или
   Варшава/Майами. Для 152-ФЗ выбирайте Москву.
6. После создания откройте проект и найдите раздел **«Домены»** — там будет
   бесплатный HTTPS-домен вида `https://<проект>-<логин>.amvera.io`.
   Скопируйте его: он нужен для `TELEGRAM_WEBAPP_URL`.

> Точные названия кнопок могут немного отличаться — Amvera периодически
> обновляет интерфейс. Смысл один: создать веб-приложение с Docker и доменом.

## 4. Шаг 2 — создайте PostgreSQL

1. В панели Amvera откройте **Managed PostgreSQL** / **Базы данных**.
2. Создайте кластер PostgreSQL 16 или 17 в **том же регионе**, что и приложение.
3. Скопируйте параметры подключения:
   - host;
   - port (обычно 5432);
   - user;
   - password;
   - database name.
4. Соберите строку:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

Важно:

- схема должна быть именно `postgresql+psycopg`, а не просто `postgresql`;
- если в пароле есть `@`, `:`, `/`, `#` или другие спецсимволы, их нужно
  закодировать (`@` → `%40`, `:` → `%3A`);
- если Amvera выдаёт готовую строку `postgresql://...`, замените начало на
  `postgresql+psycopg://`;
- если база доступна только по внешнему адресу и требует SSL, добавьте в конец
  `?sslmode=require`.

Миграции применяются автоматически при старте контейнера
(`scripts/start_all.sh` вызывает `alembic upgrade head`).

## 5. Шаг 3 — переменные окружения

В проекте Amvera откройте вкладку **«Переменные»** / **«Секреты»**
(название зависит от версии интерфейса) и добавьте переменные.

Секреты (обязательно отметьте как secret/скрытые):

| Переменная | Пример | Зачем |
| --- | --- | --- |
| `APP_SECRET_KEY` | длинная случайная строка | подпись ссылок на фото, защита сессий |
| `DATABASE_URL` | `postgresql+psycopg://user:pass@host:5432/db` | подключение к PostgreSQL |
| `TELEGRAM_BOT_TOKEN` | `123456:AA...` | проверка initData и работа бота |

Остальные:

| Переменная | Значение |
| --- | --- |
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` |
| `APP_DOCS_ENABLED` | `false` |
| `APP_AUTO_CREATE_TABLES` | `false` |
| `TELEGRAM_BOT_USERNAME` | имя бота без `@`, например `my_market_bot` |
| `TELEGRAM_WEBAPP_URL` | `https://<ваш-домен>.amvera.io` |
| `TELEGRAM_ADMIN_IDS` | ваш Telegram ID, можно несколько через запятую |
| `SUPPORT_URL` | ссылка на поддержку, например `https://t.me/my_support` |
| `LISTING_RULES_TEXT` | правила публикации (можно оставить пустым) |
| `ALLOWED_HOSTS` | `<ваш-домен>.amvera.io,localhost,127.0.0.1` |
| `TRUST_PROXY_HEADERS` | `true` |
| `STORAGE_BACKEND` | `local` |
| `LOCAL_STORAGE_DIR` | `/data/media` |
| `RUN_API` | `1` |
| `RUN_BOT` | `1` |
| `RUN_MIGRATIONS` | `1` (для одного контейнера; в bot-only ставьте `0`) |
| `LOG_LEVEL` | `INFO` |

`CORS_ALLOWED_ORIGINS` оставьте пустым: frontend и API на одном домене.
Если позже разделите их — укажите домен frontend через запятую.

Пример блока для копирования (замените значения):

```dotenv
APP_ENV=production
APP_DEBUG=false
APP_DOCS_ENABLED=false
APP_AUTO_CREATE_TABLES=false
APP_SECRET_KEY=CHANGE_ME_TO_A_LONG_RANDOM_STRING
DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
TELEGRAM_BOT_TOKEN=123456:AAExampleReplaceMe
TELEGRAM_BOT_USERNAME=my_market_bot
TELEGRAM_WEBAPP_URL=https://my-market-username.amvera.io
TELEGRAM_ADMIN_IDS=111111111
SUPPORT_URL=https://t.me/my_support
LISTING_RULES_TEXT=
ALLOWED_HOSTS=my-market-username.amvera.io,localhost,127.0.0.1
TRUST_PROXY_HEADERS=true
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=/data/media
RUN_API=1
RUN_BOT=1
RUN_MIGRATIONS=1
LOG_LEVEL=INFO
```

### Как получить `APP_SECRET_KEY`

В Windows PowerShell:

```powershell
[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
```

Скопируйте результат — это 64 символа. Не используйте пример из `.env.example`.

### Если домен ещё неизвестен

Можно временно поставить `ALLOWED_HOSTS=*.amvera.io,localhost,127.0.0.1`.
После первого деплоя замените `*` на точный домен — так строже.
`TELEGRAM_WEBAPP_URL` всё равно должен быть настоящим HTTPS-адресом.

### Telegram ID администратора

После первого запуска бота отправьте ему `/id`. Полученное число добавьте в
`TELEGRAM_ADMIN_IDS` и перезапустите проект. Без этого `/stats` будет запрещён,
а уведомления не отправятся.

> Администратор должен сам нажать `/start` у бота: Telegram не разрешает ботам
> писать первыми.

## 6. Шаг 4 — загрузите код в Amvera

Amvera использует свой Git-репозиторий. GitHub — это архив кода, но для деплоя
нужно сделать push ещё и в Amvera.

1. На странице проекта Amvera найдите Git-адрес вида:

```text
https://git.amvera.ru/<amvera-логин>/<имя-проекта>
```

2. В рабочей копии добавьте remote:

```powershell
cd C:\projects\telegram-device-market
C:\projects\git.cmd remote add amvera https://git.amvera.ru/<amvera-логин>/<имя-проекта>
```

Если remote уже существует:

```powershell
C:\projects\git.cmd remote set-url amvera https://git.amvera.ru/<amvera-логин>/<имя-проекта>
```

3. Отправьте код. Amvera ждёт ветку `master`, а у нас `main`:

```powershell
C:\projects\git.cmd push amvera main:master
```

Введите логин и пароль Amvera (это не GitHub-пароль). Если включена
двухфакторная авторизация, используйте токен/пароль из настроек Amvera.

4. Откройте в проекте **«Логи сборки»**. Amvera найдёт `amvera.yml` и
   `Dockerfile`, соберёт образ, применит миграции и запустит контейнер.
   Дождитесь статуса **«Успешно развернуто»**.


## 7. Шаг 5 — проверьте, что всё работает

1. Откройте в браузере:

```text
https://<ваш-домен>.amvera.io/api/health
```

Ожидаемый ответ:

```json
{"status":"ok","time":"..."}
```

2. Откройте корень домена в обычном браузере. Увидите экран «Нужен вход через
   Telegram» — это нормально: без Telegram `initData` API возвращает 401.
3. Откройте бота в Telegram, нажмите `/start`, затем кнопку **«Открыть каталог»**.
4. Опубликуйте тестовое объявление с фото и без фото.
5. Проверьте вкладку «Аккаунт» и смену статуса.
6. Отправьте боту `/id`, добавьте ID в `TELEGRAM_ADMIN_IDS`, перезапустите проект,
   затем проверьте `/stats` и уведомление о новом объявлении.

Если на шаге 1 ошибка `Invalid host header`, добавьте домен в `ALLOWED_HOSTS`.
Если 401 внутри Telegram — почти всегда не совпадает `TELEGRAM_WEBAPP_URL`
(лишний `/` в конце, HTTP вместо HTTPS или другой домен).

## 8. Как обновлять проект

Код хранится в двух местах:

- GitHub — `origin`;
- Amvera Git — `amvera`.

После изменений:

```powershell
C:\projects\push.cmd "Describe the change"
C:\projects\git.cmd push amvera main:master
```

`push.cmd` отправляет в GitHub, вторая команда запускает сборку в Amvera.
Можно пользоваться только Amvera Git, если GitHub не нужен.

Миграции применяются автоматически при старте контейнера. Если добавили новую
миграцию — просто сделайте push, Amvera выполнит `alembic upgrade head`.

## 9. Фотографии и постоянный диск

`amvera.yml` монтирует постоянный диск в `/data`, а переменная
`LOCAL_STORAGE_DIR=/data/media` указывает туда хранилище фото.

- фотографии переживают перезапуск и новый деплой;
- Amvera делает бэкап `/data`;
- не меняйте `LOCAL_STORAGE_DIR` на путь внутри `/app` — он потеряется при
  пересборке;
- `start_all.sh` при старте выставляет владельца `/data` для пользователя
  `appuser`, чтобы загрузка фото работала.

Если фото не загружаются, посмотрите логи: там будет `Permission denied` или
`No space left on device`. Проверьте, что в тарифе включён постоянный диск.

Для масштабирования или нескольких инстансов лучше S3:

```dotenv
STORAGE_BACKEND=s3
S3_BUCKET=your-bucket
S3_REGION=ru-central1
S3_ENDPOINT_URL=https://storage.yandexcloud.net
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_PREFIX=photos
```

Тогда `/data` для фото не нужен. Для MVP проще локальный диск.

## 10. Частые ошибки

| Ошибка | Что делать |
| --- | --- |
| `Invalid configuration for: database_url` | не задан `DATABASE_URL` в переменных Amvera |
| `Invalid host header` | добавьте домен в `ALLOWED_HOSTS` (без `https://`) |
| `could not connect to server` | проверьте host/port/пароль, регион БД и `?sslmode=require` |
| `password authentication failed` | неверный пароль или спецсимволы не закодированы в URL |
| Бот не отвечает | проверьте `TELEGRAM_BOT_TOKEN` и логи приложения; контейнер должен быть запущен |
| `/stats` отвечает «только администратору» | ваш ID не добавлен в `TELEGRAM_ADMIN_IDS` |
| Уведомления не приходят | админ не нажимал `/start` или контейнер перезапускается |
| Mini App 401 | `TELEGRAM_WEBAPP_URL` не совпадает с фактическим HTTPS-доменом |
| Фото 403 | истекла подписанная ссылка — обновите страницу; это нормально |
| Фото не сохраняются | проверьте `/data`, права и свободное место |
| Сборка падает на `pip install` | смотрите лог; обычно сеть или несовместимая версия Python |
| `APP_SECRET_KEY looks like a placeholder` | сгенерируйте новый ключ, не используйте пример |
| `TELEGRAM_WEBAPP_URL must use https` | в production нужен HTTPS-домен |

Логи приложения и сборки — на странице проекта Amvera. Секреты в логи не
выводятся: приложение специально не печатает токены и переменные.

## 11. Если захотите разделить API и бота

Сейчас по умолчанию оба процесса живут в одном контейнере. Это нормально для
небольшого каталога. Если нагрузка вырастет:

1. Создайте второй проект Amvera из того же репозитория.
2. В проекте **API**:
   ```dotenv
   RUN_API=1
   RUN_BOT=0
   RUN_MIGRATIONS=1
   ```
3. В проекте **бота**:
   ```dotenv
   RUN_API=0
   RUN_BOT=1
   RUN_MIGRATIONS=0
   ```
4. Оба проекта должны смотреть на одну `DATABASE_URL`.
5. Домен Mini App указывайте на API-проект.
6. `LOCAL_STORAGE_DIR=/data/media` нужен только API-проекту.

Не запускайте два экземпляра бота одновременно: Telegram будет отдавать
обновления то одному, то другому, а outbox-воркер может отправлять уведомления
дважды.

## 12. Безопасность и правила

- Реальный `.env` не загружайте в Git и не кладите в образ: все секреты
  задаются в переменных Amvera.
- `TELEGRAM_ADMIN_IDS` проверяется на сервере; обычный пользователь не увидит
  `/stats`.
- В production включён HTTPS, HSTS, CSP и ограничения размера/типа фото.
- Rate limit сейчас хранится в памяти процесса. Для нескольких API-инстансов
  нужен общий Redis/прокси-лимит.
- Перед публичным запуском проверьте законодательство о персональных данных
  (вы храните Telegram ID и username), правила Telegram и ограничения на товары.
  Текст правил можно задать в `LISTING_RULES_TEXT`; тогда сервер не примет
  объявление без подтверждения.
- Сделайте репозиторий приватным, если в нём когда-либо появятся чувствительные
  данные. Сейчас в нём только код и `.env.example`.
