# PC Controller

Desktop-приложение для управления своим ПК через Telegram-бота.

## Что есть сейчас

- Один `EXE` через `py-auto-build.bat`
- GUI на `PySide6` с треем, автозагрузкой и настройками
- Telegram-бот на `python-telegram-bot`
- Inline-панель `/panel`
- Управление питанием, файлами, процессами, вводом текста, hotkeys и мышью
- `AutoAccept` по шаблонам изображений

## Команды Telegram

### Основное

- `/panel`
- `/help`
- `/myid`
- `/ping`
- `/status`
- `/uptime`
- `/screenshot`

### Питание

- `/lock`
- `/sleep`
- `/hibernate`
- `/shutdown [sec]`
- `/reboot [sec]`
- `/cancelshutdown`

### Файлы

- `/pwd`
- `/ls [path]`
- `/cd <path>`
- `/mkdir <path>`
- `/rm <path>`
- `/rmr <path>`
- `/download <path>`
- `/upload [path]`
- `/cancelupload`

### Процессы

- `/tasklist [filter]`
- `/taskkill <pid>`

### Ввод и мышь

- `/printtext <text>`
- `/combination <keys...>`
- `/leftclick`
- `/rightclick`
- `/leftdoubleclick`
- `/middleclick`
- `/righthold [sec]`
- `/movemouse <x> <y> [sec]`
- `/message <text>`
- `/voice <text>`
- `/say <text>`
- `/autoaccepton [timeout]`
- `/autoacceptoff`

### Прочее

- `/openurl <https://...>`
- `/logtail [n]`

Все команды, кроме `/myid`, доступны только `admin_ids`.

## Быстрый старт

1. Создай окружение:
   - `python -m venv .venv`
2. Установи зависимости:
   - `.venv\Scripts\python -m pip install -r requirements.txt`
3. Запусти приложение:
   - `.venv\Scripts\python main.py`
4. В GUI укажи `bot token` и `admin_ids`
5. Сохрани настройки и запусти бота

## Сборка EXE

Запуск из корня проекта:

- `py-auto-build.bat`

Результат:

- `dist\PCController.exe`
- `output\PCController.exe`

## Автозагрузка

Управляется из GUI:

- включение и выключение автозагрузки
- запуск в трей
- автозапуск бота

Используется ключ `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

## AutoAccept

В настройках есть путь к папке шаблонов `AutoAccept templates`.

- Положи туда изображения кнопок подтверждения
- Запусти `/autoaccepton`
- Бот будет искать совпадение на экране и кликать по найденному шаблону

## Конфиг и логи

- Конфиг: `%LOCALAPPDATA%\PCController\config.json`
- Логи: `%LOCALAPPDATA%\PCController\logs\app.log`

## Безопасность

- Не публикуй `bot token`
- Добавляй в `admin_ids` только свои аккаунты
- Ненужные категории команд можно отключать в GUI
