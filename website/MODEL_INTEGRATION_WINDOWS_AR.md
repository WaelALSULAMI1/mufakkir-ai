# ربط Qwen3-8B + PEFT بالموقع على Windows (CUDA)

هذا الملف للتشغيل على Windows مع بطاقة NVIDIA. لا يستخدم MLX، ولا يدرّب المودل، ولا يلمس `adapters.safetensors` الأصلي.

## المعمارية

```text
المتصفح
   ↓
FastAPI Website  (website/)
   ↓
model_service.py
   ↓ HTTP  OpenAI Chat Completions
transformers_server_cuda.py  (model/)
   ↓
Qwen/Qwen3-8B (4-bit NF4) + Summer_Arabic_Problem_Solver_PEFT
```

المتصفح لا يتصل بخادم المودل مباشرة.

## 1. Adapter زميلك — قراءة فقط

استخدم المجلد المحوّل إلى PEFT داخل هذه الحزمة:

```text
model/Summer_Arabic_Problem_Solver_PEFT
```

يجب أن يحتوي على:

- `adapter_config.json`
- `adapter_model.safetensors`

لا تعدّل أو تحذف أي ملف داخله. لا تمرّر `adapters.safetensors` الأصلي إلى الخادم.

## 2. تجهيز بيئة خادم المودل

من PowerShell داخل مجلد `model`:

```powershell
cd model
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -r requirements-windows.txt
```

ثبّت أولًا نسخة PyTorch التي تدعم CUDA لجهازك إذا لم تكن موجودة.

## 3. التشغيل بنقرة واحدة

من مجلد الموقع شغّل `run_windows.bat` فقط. هذا الملف:

1. يشغّل `Qwen/Qwen3-8B` + Adapter PEFT على `127.0.0.1:8090`.
2. ينتظر حتى يصبح المودل جاهزًا.
3. يشغّل الموقع على `http://127.0.0.1:8000`.

المنفذ `8090` متعمد لأن `8080` قد يكون محجوزًا على Windows. لا تفتح ترمينالين يدويًا.

الخادم يقدّم:

```text
GET  /v1/models
POST /v1/chat/completions
```

ويدعم `messages` و`temperature` و`top_p` و`max_tokens`، ويعيد الجواب في `choices[0].message.content`.

## 4. اختبار الخادم

```powershell
curl http://127.0.0.1:8090/v1/models
```

النتيجة المتوقعة تحتوي على `"id": "Qwen/Qwen3-8B"`.

اختبار توليد بسيط:

```powershell
curl http://127.0.0.1:8090/v1/chat/completions -H "Content-Type: application/json" -d "{\"messages\":[{\"role\":\"user\",\"content\":\"اكتب كلمة اختبار فقط\"}],\"temperature\":0,\"max_tokens\":32}"
```

## 5. إعداد الموقع

في `website/.env`:

```env
MODEL_MODE=transformers
MODEL_API_URL=http://127.0.0.1:8090
MODEL_BASE=Qwen/Qwen3-8B
MODEL_ADAPTER_PATH=
MODEL_TIMEOUT_SECONDS=300
```

`MODEL_ADAPTER_PATH` يبقى فارغًا. الخادم نفسه يحمّل الـAdapter من `--adapter-path`.

يمكن استخدام `MODEL_MODE=api` بنفس الطريقة.

## 6. تشغيل الموقع

شغّل `run_windows.bat` من مجلد الموقع. لا تشغّل خادم المودل يدويًا في ترمينال ثانٍ.

ثم افتح:

```text
http://127.0.0.1:8000
```

## 7. ماذا يفعل الموقع؟

`model_service.py` يرسل طلبين إلى الخادم المحلي:

1. تحليل المشكلة وفق JSON في `model_schema.py`، ومن أهم الشروط أن `alternatives` تحتوي على أربعة بدائل بالضبط.
2. تقييم المقترح من 100 لترتيب أفضل 5 داخل القسم.

إذا رجع المودل JSON غير صالح، يُرسل الناتج مرة ثانية بطلب تصحيح JSON فقط، بدون إعادة تحليل المشكلة من البداية. الموقع يحذف وسوم `<think>` إن ظهرت.

لا تحتاج تعديل صفحات HTML لربط المودل.

## 8. ملاحظة أمنية

خادم المودل يستمع على `127.0.0.1:8090` فقط. لا تفتح المنفذ للعامة. FastAPI في الموقع هو الذي يتصل به من الخلفية.
