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

    # Never execute scripts from user-upload directory.
    location ^~ /static/uploads/ {
        alias /path/to/your/project/app/static/uploads/;
        autoindex off;
        types { }
        default_type application/octet-stream;
        add_header X-Content-Type-Options nosniff always;
        try_files $uri =404;
    }

    location ~* ^/static/uploads/.*\.(php|phtml|phar|cgi|pl|py|sh)$ {
        deny all;
        return 403;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header Origin $http_origin;
        proxy_set_header Referer $http_referer;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'" always;
}
```

## 7. Reverse proxy checklist (обязательно)

Чтобы CSRF-защита и rate limiting работали корректно за reverse proxy:

1. Всегда прокидывайте оригинальный `Host` (`proxy_set_header Host $host;`).
2. Не затирайте `Origin` и `Referer`; при наличии прокидывайте как есть.
3. Прокидывайте клиентский IP через `X-Forwarded-For` c `proxy_add_x_forwarded_for`.
4. Отключите доверие к пользовательскому `X-Forwarded-For` на внешнем уровне (доверять только вашему proxy/load balancer).
5. Для нескольких прокси убедитесь, что левый IP в `X-Forwarded-For` остаётся реальным клиентом.
6. На edge-уровне включите HTTPS-redirect и HSTS.
7. В production включите `SESSION_COOKIE_SECURE=true` в `.env`.

Проверка после деплоя:

```bash
# Должен вернуть 403 (cross-site POST blocked by CSRF guard)
curl -i -X POST https://your_domain.com/set-currency \
    -H "Origin: https://evil.example" \
    -d "cur=usd&next_url=/"

# Серия запросов с одного IP должна упереться в 429
for i in {1..25}; do
    curl -s -o /dev/null -w "%{http_code}\n" -X POST https://your_domain.com/api/quick-order \
        -H "X-Forwarded-For: 198.51.100.77" \
        -d "product_id=1&guest_name=A&guest_email=a%40a.com&phone=1&address=A&quantity=1";
done
```

---

- Проверьте, что все секреты и ключи не закоммичены в репозиторий.
- Для production используйте HTTPS.
