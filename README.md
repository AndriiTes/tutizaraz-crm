# Тут&Зараз — CRM бекенд

FastAPI-сервіс, який приймає заявки через вебхуки (зараз — з форми сайту,
далі — з Telegram/Viber/WhatsApp/телефонії) і показує їх у простій
адмін-панелі за адресою `/` (та сам сайт-форма шле дані на `/webhooks/website-order`).

## Що є зараз

- `POST /webhooks/website-order` — приймає заявку з форми сайту
- `POST /webhooks/telegram`, `/webhooks/viber`, `/webhooks/whatsapp`, `/webhooks/telephony` — заготовки під наступні канали (відповідають 200 OK, логіку розбору повідомлень додамо, коли будуть токени ботів)
- `POST /api/login` — вхід у CRM-панель за паролем
- `GET /api/orders` — список заявок (з фільтрами `?source=` і `?status=`), потребує токен
- `PATCH /api/orders/{id}` — зміна статусу заявки, потребує токен
- `GET /` — CRM-панель (логін + таблиця заявок)
- `GET /health` — перевірка, що сервіс живий

## Деплой на Render (покроково)

### 1. База даних на Neon

1. Зареєструватись на [neon.tech](https://neon.tech) (можна через GitHub).
2. Створити проєкт, скопіювати **Connection string** (режим *Pooled connection*) —
   виглядає як `postgresql://user:password@host/dbname`.

### 2. Викласти код у GitHub

1. Створити новий репозиторій, наприклад `tutizaraz-crm`.
2. Залити вміст цієї папки (`backend/`) у корінь репозиторію.

### 3. Деплой на Render

Найпростіше — через Blueprint (файл `render.yaml` вже є в репозиторії):

1. У Render: **New** → **Blueprint** → обрати щойно створений GitHub-репозиторій.
2. Render сам прочитає `render.yaml` і запропонує створити сервіс `tutizaraz-crm`.
3. Перед запуском треба вручну заповнити змінні середовища (Render попросить):
   - `DATABASE_URL` — рядок підключення з Neon (крок 1)
   - `ADMIN_PASSWORD` — пароль, яким будете заходити в CRM-панель
   - `SECRET_KEY` — Render згенерує сам
4. Натиснути **Apply** — почнеться білд і деплой.
5. Через 1-3 хвилини сервіс буде доступний на адресі типу
   `https://tutizaraz-crm.onrender.com`.

### 4. Перевірка

- Відкрити `https://tutizaraz-crm.onrender.com/health` — має повернути `{"status":"ok"}`.
- Відкрити `https://tutizaraz-crm.onrender.com/` — має відкритись екран входу в CRM,
  увійти паролем з `ADMIN_PASSWORD`.

### 5. Підключити сайт до бекенду

У файлі `script.js` сайту замінити:

```js
const CONFIG = {
  WEBHOOK_URL: "https://tutizaraz-crm.onrender.com/webhooks/website-order",
  SOURCE: "website"
};
```

Перезалити `script.js` на Cloudflare. Після цього форма замовлення на сайті
реально створюватиме заявки, які з'являться в CRM-панелі.

## Важливо про безкоштовний план Render

- Сервіс "засинає" після 15 хв без запитів, перший запит після паузи
  обробляється ~30-50 секунд (далі швидко). Для тестового етапу це нормально.
- Сама база даних — на Neon, а не на Render, тому 30-денного видалення бази
  можна не боятись.
