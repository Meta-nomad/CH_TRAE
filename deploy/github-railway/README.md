# GitHub + Railway деплой

Эта папка содержит короткую инструкцию для публикации проекта в GitHub и запуска на Railway.

## Что уже настроено

- `Procfile` запускает бота как `worker`
- `railway.json` задаёт команду запуска `python -m bot.main`
- `.gitignore` исключает `.env`, локальные кеши и служебные файлы
- токен бота на Railway ожидается из переменной окружения `BOT_TOKEN`

## Что загрузить в GitHub

Загружайте весь проект целиком, включая:

- `bot/`
- `config/`
- `services/`
- `utils/`
- `data/.gitkeep`
- `requirements.txt`
- `Procfile`
- `railway.json`
- `.env.example`
- `README.md`

## Публикация в GitHub

Если репозиторий ещё не создан:

```powershell
git init
git add .
git commit -m "Initial Telegram bot for Railway"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

Если репозиторий уже есть:

```powershell
git add .
git commit -m "Prepare deploy for GitHub and Railway"
git push
```

## Запуск на Railway

1. Создайте новый проект в Railway.
2. Выберите `Deploy from GitHub repo`.
3. Подключите нужный репозиторий.
4. В `Variables` добавьте:
   - `BOT_TOKEN`
   - `CRYPTOCOMPARE_API_KEY`
   - при необходимости `COINGECKO_API_KEY`
5. Railway автоматически установит зависимости из `requirements.txt`.
6. Старт будет выполнен командой `python -m bot.main`.

## Минимальные переменные

- `BOT_TOKEN` — уже задан на Railway по вашему условию
- `CRYPTOCOMPARE_API_KEY` — настоятельно рекомендуется, иначе историческая глубина будет хуже

## После деплоя

Если бот не отвечает:

- проверьте логи Railway
- убедитесь, что сервис запущен как `worker`
- убедитесь, что `BOT_TOKEN` задан без лишних пробелов
- проверьте, что у бота нет активного webhook от старого запуска
