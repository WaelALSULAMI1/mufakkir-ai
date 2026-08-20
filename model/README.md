# مودل مُفكّر

هذا الجزء اللي يقرأ مقترح الموظف ويرجّع تحليلًا جاهزًا للمنصة: يوضح المشكلة، يقترح بدائل، ويعطي توصية. يشتغل محليًا على الجهاز، والموقع يتصل فيه من الخلف. المتصفح ما يكلمه مباشرة.

مُفكّر مو مودل عام للأسئلة. هو مضبوط على أسلوب مقترحات العمل، عشان النتيجة تطلع بلغة القسم مو بترجمة عامة.

## وش استخدمنا؟

الأساس `Qwen/Qwen3-8B`. فوقه Adapter PEFT درّبناه على مقترحات عربية، والمجلد المعتمد هو:

```text
Summer_Arabic_Problem_Solver_PEFT
```

التشغيل على Windows مع بطاقة NVIDIA (CUDA). المودل يتحمّل مرة واحدة بأوزان خفيفة (4-bit) عشان الجهاز يقدر يشيله بدون تعقيد.

الأدوات الأساسية: Transformers وPEFT وFastAPI. ما نستخدم MLX على هذا الجهاز.

## كيف تشغّله؟

الأسهل تترك الموقع يشغّله. من مجلد `website` اضغط `run_windows.bat`. يفتح خادم المودل، ينتظر لين يصير جاهز، بعدين يفتح المنصة على:

```text
http://127.0.0.1:8000
```

لا تغلق نافذة `Qwen3 CUDA Server`.

أول مرة على جهاز جديد، شغّل مرة واحدة:

```text
setup_model_windows.bat
```

ومن مجلد الموقع شغّل `setup_windows.bat`، وبعدها `run_windows.bat` يكفي.

إذا كان `Qwen3-8B` محمّل مسبقًا في كاش الجهاز، التشغيل عادة دقيقة إلى دقيقة ونصف. على جهاز جديد التحميل الأول أطول.

## الملفات هنا

- `setup_model_windows.bat` — تجهيز البيئة مرة واحدة
- `run_cuda_server.bat` — تشغيل المودل والأدبتر
- `transformers_server_cuda.py` — خادم التحليل
- `Summer_Arabic_Problem_Solver_PEFT` — الأدبتر المعتمد

لا تعدّل ملفات الأدبتر ولا تحذفها.

المودل الأساسي `Qwen3-8B` ما ينحط داخل المجلد لأن حجمه كبير. يُحمَّل من كاش Hugging Face على الجهاز.

---

# Mufakkir Model

This component reads an employee's proposal and returns an analysis ready for the platform: it clarifies the problem, suggests alternatives, and provides a recommendation. It runs locally on the device, while the website connects to it in the background. The browser does not call it directly.

Mufakkir is not a general-purpose question-answering model. It is tuned for workplace proposals so that the result uses the department's language rather than a generic translation.

## What do we use?

The base model is `Qwen/Qwen3-8B`. A PEFT Adapter trained on Arabic proposals is applied on top of it, using the following directory:

```text
Summer_Arabic_Problem_Solver_PEFT
```

It runs on Windows with an NVIDIA GPU (CUDA). The model is loaded once with lightweight (4-bit) weights so the device can run it without unnecessary complexity.

The main tools are Transformers, PEFT, and FastAPI. MLX is not used on this device.

## How do you run it?

The easiest option is to let the website start it. From the `website` directory, run `run_windows.bat`. It starts the model server, waits until it is ready, and then opens the platform at:

```text
http://127.0.0.1:8000
```

Do not close the `Qwen3 CUDA Server` window.

On a new device, run this once:

```text
setup_model_windows.bat
```

From the website directory, run `setup_windows.bat`; after that, `run_windows.bat` is sufficient.

If `Qwen3-8B` is already available in the local cache, startup usually takes one to one and a half minutes. The first load on a new device takes longer.

## Files here

- `setup_model_windows.bat` — one-time environment setup
- `run_cuda_server.bat` — starts the model and adapter
- `transformers_server_cuda.py` — analysis server
- `Summer_Arabic_Problem_Solver_PEFT` — the approved adapter

Do not modify or delete the adapter files.

The base `Qwen3-8B` model is not stored in this directory because it is large. It is loaded from the Hugging Face cache on the device.
built by Ali.
