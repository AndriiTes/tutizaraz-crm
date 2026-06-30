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

## Підключення WhatsApp + Instagram (через Meta)

Обидва канали йдуть через один і той самий **Meta for Developers** App —
бізнес-верифікація не обов'язкова для старту, Meta видає безкоштовний
тестовий номер одразу.

### 1. Створення Meta App

1. Зайти на [developers.facebook.com](https://developers.facebook.com) → увійти своїм Facebook-акаунтом → **My Apps** → **Create App**.
2. Тип застосунку — **Business**.
3. У списку продуктів додати **WhatsApp** (і за бажанням **Instagram** — буде в розділі Messenger / Instagram).

### 2. Тестовий номер WhatsApp

1. У розділі **WhatsApp → API Setup** Meta вже видасть тестовий номер і **тимчасовий токен доступу** (`Temporary access token`).
2. Знизу на тій же сторінці — **Phone number ID** (довгий числовий ID, не сам номер).
3. Додайте свій особистий номер у список **To** (тестові отримувачі) — без цього Meta не дозволить надсилати на нього повідомлення.

### 3. Змінні середовища на Render

Додайте:
- `WHATSAPP_ACCESS_TOKEN` — токен з кроку 2
- `WHATSAPP_PHONE_NUMBER_ID` — Phone number ID з кроку 2
- `META_VERIFY_TOKEN` — придумайте самі будь-який рядок (наприклад `tutizaraz-secret-2026`), він буде потрібен на наступному кроці

### 4. Підключення вебхука

1. У Meta App Dashboard → **WhatsApp → Configuration** → **Edit** біля Webhook.
2. **Callback URL**: `https://tutizaraz-crm.onrender.com/webhooks/whatsapp`
3. **Verify token**: той самий рядок, що ви вписали в `META_VERIFY_TOKEN` на Render.
4. **Verify and Save** — Meta зробить GET-запит на наш сервер, бекенд автоматично підтвердить (це вже реалізовано в коді).
5. Підпишіться на поле **messages** (Webhook fields → messages → Subscribe).

### 5. Instagram (та сама Meta App)

1. Підключіть Instagram-акаунт до Meta Business Suite (Settings → Instagram accounts).
2. У Meta App Dashboard додайте продукт **Instagram** (через Messenger API for Instagram), отримайте **Page Access Token** — це і є `INSTAGRAM_ACCESS_TOKEN`.
3. Налаштуйте webhook так само, як для WhatsApp, але:
   - Callback URL: `https://tutizaraz-crm.onrender.com/webhooks/instagram`
   - Verify token: той самий `META_VERIFY_TOKEN`
   - Підпишіться на поле **messages**

### 6. Тест

- Напишіть з особистого WhatsApp на тестовий номер (з кроку 2.3) → перевірте CRM.
- Напишіть в директ Instagram-акаунту → перевірте CRM.

## Важливо про безкоштовний план Render

- Сервіс "засинає" після 15 хв без запитів, перший запит після паузи
  обробляється ~30-50 секунд (далі швидко). Для тестового етапу це нормально.
- Сама база даних — на Neon, а не на Render, тому 30-денного видалення бази
  можна не боятись.
