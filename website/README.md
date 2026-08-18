# مُفكّر

مُفكّر مساحة داخلية لفكرة الموظف. تكتب المشكلة كما تواجهها في العمل، ولو عندك حل تضيفه، ويرجع لك التحليل مرتبًا: المشكلة أوضح، بدائل عملية، وتوصية تساعد الإدارة تقرر. القرار يبقى بشريًا.

المنصة مربوطة بمودل عربي متخصص يشتغل على الجهاز نفسه، فما تطلع الفكرة لخدمة خارجية.

## التشغيل

أول مرة على الجهاز:

1. فك الضغط.
2. شغّل `setup_windows.bat` مرة واحدة.
3. شغّل `run_windows.bat`.

يفتح المتصفح على:

```text
http://127.0.0.1:8000
```

`run_windows.bat` يشغّل المودل والموقع معًا. لا تغلق نافذة `Qwen3 CUDA Server`. التحميل الأول قد يأخذ دقائق، وبعدها استخدم «تقديم مقترح» مباشرة.

إذا كان الجهاز جديدًا تمامًا، شغّل أيضًا مرة واحدة من مجلد `model`:

```text
setup_model_windows.bat
```

ثم ارجع لـ `run_windows.bat`.

## وش يسوي مُفكّر؟

الموظف يدخل بحسابه ويطرح مقترحًا على قسمه. مُفكّر يقرأ النص بالعربية ويرتّبه، ثم يحفظ النتيجة مع تقييم من 100. لوحة المدير تعرض أعلى خمسة في كل قسم حتى ما تضيع الفكرة الجيدة بين الزحمة.

كل موظف يشوف مقترحاته فقط. مراجعة أبرز الأفكار عند حساب المدير.

## الصفحات

- `/` الرئيسية
- `/submit` تقديم مقترح
- `/my-suggestions` اقتراحاتي
- `/guide` دليل الاستخدام
- `/about` عن المنصة
- `/login` و`/register` حساب الموظف
- `/manager` لوحة المراجعة

## وش استخدمنا؟

الموقع مبني بـ FastAPI وصفحات HTML بسيطة، والمقترحات تُحفظ في SQLite. التحليل يجي من مودل محلي: `Qwen/Qwen3-8B` مع Adapter PEFT موجود في مجلد `model`. المتصفح ما يتصل بالمودل؛ الموقع هو اللي يكلمه من الخلف.

التفاصيل الخفيفة للمودل في `model/README.md`.

## دخول المدير

الإيميل في ملف `.env`. كلمة المرور محفوظة كهاش، مو كنص.

لتغييرها:

```text
python hash_manager_password.py "كلمة-المرور-الجديدة"
```

ضع السطر الناتج في `.env` واحذف أي `MANAGER_PASSWORD` نصي.

## لو تبي تعدل شيء

الأقسام في `app.py` داخل قائمة `DEPARTMENTS`.

شكل الموقع في `static/style.css`.

النصوص والصفحات في `templates/`. الهيدر والفوتر في `base.html`، فتعديلهما مرة ينعكس على الباقي.

---

# Mufakkir

Mufakkir is an internal employee-idea space. Describe a problem as you experience it at work, add a solution if you have one, and receive a structured analysis: a clearer problem statement, practical alternatives, and a recommendation that helps management decide. The decision remains human.

The platform is connected to a specialized Arabic model that runs on the same device, so the idea is not sent to an external service.

## Running the platform

The first time on a device:

1. Extract the files.
2. Run `setup_windows.bat` once.
3. Run `run_windows.bat`.

The browser opens at:

```text
http://127.0.0.1:8000
```

`run_windows.bat` starts both the model and the website. Do not close the `Qwen3 CUDA Server` window. The first load may take several minutes; after that, use “Submit a proposal” directly.

If the device is completely new, also run this once from the `model` directory:

```text
setup_model_windows.bat
```

Then return to `run_windows.bat`.

## What does Mufakkir do?

An employee signs in and submits a proposal to their department. Mufakkir reads and structures the Arabic text, then saves the result with a score out of 100. The manager dashboard shows the top five proposals in each department so a good idea is not lost in the crowd.

Each employee sees only their own proposals. The review of highlighted ideas is available through the manager account.

## Pages

- `/` — home
- `/submit` — submit a proposal
- `/my-suggestions` — my proposals
- `/guide` — user guide
- `/about` — about the platform
- `/login` and `/register` — employee account
- `/manager` — review dashboard

## What do we use?

The website is built with FastAPI and simple HTML pages, and proposals are stored in SQLite. Analysis comes from a local model: `Qwen/Qwen3-8B` with a PEFT Adapter in the `model` directory. The browser does not connect to the model; the website communicates with it in the background.

Additional model details are in `model/README.md`.

## Manager login

The email address is stored in `.env`. The password is stored as a hash, not as plaintext.

To change it:

```text
python hash_manager_password.py "كلمة-المرور-الجديدة"
```

Put the generated line in `.env` and remove any plaintext `MANAGER_PASSWORD`.

## If you want to edit something

The departments are in the `DEPARTMENTS` list in `app.py`.

The website appearance is in `static/style.css`.

The text and pages are in `templates/`. The header and footer are in `base.html`, so editing them once updates the rest.
