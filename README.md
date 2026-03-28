# 📋 البريفينج التحريري اليومي — Telegram Bot

بوت تيليجرام يرسل بريفينجاً تحريرياً يومياً عن سوريا (وأي بلد آخر) باستخدام الذكاء الاصطناعي.

---

## ⚡ الإعداد خطوة بخطوة

### 1. إنشاء بوت تيليجرام

1. افتح تيليجرام وابحث عن **@BotFather**
2. أرسل `/newbot`
3. اختر اسماً للبوت (مثلاً: Syria Brief Bot)
4. اختر username (مثلاً: `syriabrief_bot`)
5. انسخ الـ **Token** الذي يعطيك إياه

### 2. الحصول على معرف المجموعة (Chat ID)

1. أضف البوت للمجموعة أو القناة
2. أضف **@userinfobot** للمجموعة
3. أرسل `/start` — سيعطيك الـ Chat ID (رقم سالب مثل `-1001234567890`)

### 3. مفتاح Anthropic API

1. روح على [console.anthropic.com](https://console.anthropic.com)
2. سجّل حساباً مجانياً
3. من قائمة **API Keys** أنشئ مفتاحاً جديداً

### 4. رفع على Railway (مجاناً)

1. روح على [railway.app](https://railway.app) وسجّل بـ GitHub
2. اضغط **New Project** ← **Deploy from GitHub repo**
3. ارفع هذا المجلد على GitHub أولاً، ثم اختره
4. من **Variables** أضف هذه المتغيرات:

```
TELEGRAM_TOKEN    = (من BotFather)
ANTHROPIC_KEY     = (من Anthropic)
GROUP_CHAT_ID     = (معرف مجموعتك)
SEND_HOUR         = 7
SEND_MINUTE       = 0
TIMEZONE          = Asia/Damascus
COUNTRY           = سوريا
```

5. اضغط **Deploy** — خلاص! 🎉

---

## 🤖 أوامر البوت

| الأمر | الوظيفة |
|-------|---------|
| `/brief` | بريفينج سوريا الآن |
| `/brief لبنان` | بريفينج لبلد آخر |
| `/start` | بدء التشغيل |
| `/help` | المساعدة |

---

## ⏰ الجدولة التلقائية

البوت يرسل البريفينج تلقائياً كل يوم على الساعة المحددة في `SEND_HOUR`.
غيّر الوقت من متغيرات Railway في أي وقت.

---

## 💰 التكلفة

- **Railway**: مجاني حتى 5$/شهر استهلاك (يكفي بسهولة)
- **Anthropic API**: حوالي 0.02–0.05$ لكل بريفينج

---

## 📁 هيكل المشروع

```
syria-brief-bot/
├── bot.py              # الكود الرئيسي
├── requirements.txt    # المكتبات
├── railway.toml        # إعدادات Railway
├── .env.example        # نموذج المتغيرات
└── .gitignore
```
