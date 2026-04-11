# TemporaShop Deployment Instructions

## 1. Установка зависимостей

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Настройка переменных окружения

Создайте файл `.env` в корне проекта и укажите необходимые переменные (например, ключи Stripe, настройки БД и секреты).

## 3. Миграция и инициализация БД

Если требуется, выполните скрипты для создания и наполнения базы данных:

```bash
python seed_data.py
```

## 4. Запуск приложения (production)

Рекомендуется запускать через Uvicorn или Gunicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
или
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app
```

## 5. Статические файлы

Убедитесь, что папка `app/static` доступна для веб-сервера (например, через nginx).

## 6. Пример конфигурации nginx

```
server {
    listen 80;
    server_name your_domain.com;

    location /static/ {
        alias /path/to/your/project/app/static/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

- Проверьте, что все секреты и ключи не закоммичены в репозиторий.
- Для production используйте HTTPS.
- Для бота Telegram настройте отдельный процесс/сервер.
