# Как выгрузить проект на Git

## Статус

Репозиторий уже инициализирован и выгружен:

```text
https://github.com/zamaledinovr-max/stor
```

- рабочая копия: `C:\projects\telegram-device-market`;
- ветка: `main`;
- remote: `origin`;
- первый коммит: `289814c` — `Initial commit: Telegram Mini App + aiogram marketplace MVP`.

Дальнейшие изменения:

```powershell
cd C:\projects\telegram-device-market
git add --all
git commit -m "Describe the change"
git push
```

Ниже — инструкция на случай повторной инициализации/переезда проекта.

## Git на этой машине

Системный Git не установлен, поэтому используется портативный MinGit:

```text
C:\projects\tools\mingit\cmd\git.exe
```

Удобные обёртки:

```powershell
C:\projects\git.cmd --version
C:\projects\git.cmd status
C:\projects\push.cmd "Describe the change"
```

`push.cmd` делает `git add --all`, коммит с указанным сообщением и `git push`.
Логин GitHub уже сохранён в Git Credential Manager (аккаунт `zamaledinovr-max`).

## Исходное расположение

Проект сохранён в отдельной папке:

```text
C:\Users\282_АУЕ_228\.cline\data\workspaces\chat\telegram-device-market
```

Git-репозиторий ещё не инициализирован. Используйте скрипты ниже: они выполняют
инициализацию, первый коммит и push одной командой.

---

## 0. (Рекомендуется) Скопировать в путь без кириллицы

Некоторые Git-клиенты и CI плохо работают с путями, содержащими кириллицу.
Скопируйте проект, например, в `C:\projects`:

```powershell
$source = "C:\Users\282_АУЕ_228\.cline\data\workspaces\chat\telegram-device-market"
$target = "C:\projects\telegram-device-market"
New-Item -ItemType Directory -Force -Path "C:\projects" | Out-Null
Copy-Item -Recurse -Force $source $target
cd $target
```

Дальше все команды выполняйте из `C:\projects\telegram-device-market`.

---

## 1. Создайте пустой репозиторий

- **GitHub:** Repositories → New → имя → **без** README, .gitignore и license.
- **GitLab:** New project → Create blank project → **без** README.

Скопируйте HTTPS-ссылку вида:

```text
https://github.com/<user>/<repo>.git
```

---

## 2. Одна команда для инициализации и push

### Windows: самый простой вариант

Дважды щёлкните `scripts\init_git.cmd` (или запустите его из проводника). Скрипт
спросит URL репозитория и выполнит инициализацию, коммит и push. Если оставить
поле пустым, будет создан только локальный репозиторий.

### Windows PowerShell

```powershell
cd C:\projects\telegram-device-market
git config --global user.name "Your Name"
git config --global user.email "you@example.com"

powershell -ExecutionPolicy Bypass -File .\scripts\init_git.ps1 https://github.com/<user>/<repo>.git
```

### Linux / macOS / Git Bash

```bash
cd /path/to/telegram-device-market
chmod +x scripts/init_git.sh
./scripts/init_git.sh https://github.com/<user>/<repo>.git
```

Скрипт:

1. проверяет наличие `git` и запуск из корня проекта;
2. делает `git init` и ветку `main`;
3. проверяет, что настроены `user.name` / `user.email`;
4. делает `git add --all` и **отказывается коммитить реальные `.env`-файлы**;
5. создаёт первый коммит;
6. добавляет `origin` и выполняет `git push -u origin main`.

`init_git.sh` нужно запускать через `bash` (например, Git Bash), иначе Windows
не выполнит shebang-скрипт напрямую.

---

## 3. Ручной вариант (если скрипт недоступен)

```bash
cd C:\projects\telegram-device-market

git init
git symbolic-ref HEAD refs/heads/main

git config user.name "Your Name"
git config user.email "you@example.com"

git add --all
git status --short          # убедитесь, что .env и var/ отсутствуют
git commit -m "Initial commit: Telegram Mini App + aiogram marketplace MVP"

git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

Если `origin` уже существует:

```bash
git remote set-url origin https://github.com/<user>/<repo>.git
git push -u origin main
```

---

## 4. Аутентификация

GitHub не принимает пароль аккаунта при `git push`. Используйте:

- **Git Credential Manager** (ставится вместе с Git for Windows) — откроется окно входа;
- **Personal Access Token** (classic или fine-grained) с правом `Contents: Read and write`
  для нужного репозитория. В качестве пароля введите токен.

Никогда не сохраняйте токен в `.env`, `README` или скриптах.

---

## 5. Проверка безопасности перед push

```bash
git status --short
git ls-files | findstr /I ".env"        # Windows
git ls-files | grep -E '(^|/)\.env'     # Git Bash/Linux
```

Ожидаемо: в индексе есть только `.env.example`, реального `.env` нет.
Также не должны попасть:

- `var/`, `media/` — загруженные фотографии;
- `*.db`, `*.sqlite3`, `*.log`;
- `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`;
- токены, пароли, приватные ключи.

Эти правила уже прописаны в `.gitignore`.

---

## 6. Что делать после push

1. Убедитесь, что на странице репозитория виден `README.md`.
2. Проверьте, что `.env` отсутствует в списке файлов.
3. Если планируете CI: добавьте секреты (`APP_SECRET_KEY`, `DATABASE_URL`,
   `TELEGRAM_BOT_TOKEN`) в настройки репозитория, а не в файлы.
4. Для production используйте `APP_ENV=production` и отдельный `.env` на сервере
   (не в репозитории).

---

## 7. Если позже понадобится отдельная ветка

```bash
git switch -c feature/my-change
git add --all
git commit -m "Describe the change"
git push -u origin feature/my-change
```

---

## 8. Альтернатива: GitHub CLI

Если установлен `gh` и выполнен `gh auth login`:

```bash
gh repo create <user>/telegram-device-market --private --source=. --remote=origin --push
```

Проверьте, что репозиторий создаётся **пустым** (`--source=.` при уже готовом
локальном проекте) и что `.env` не попал в коммит.
