# مُفكّر | Mufakkir

> منصة عربية مدعومة بالذكاء الاصطناعي لتحسين أفكار الموظفين وتحليلها وترتيبها، مع إبقاء القرار النهائي بيد المدير.

[العربية](#العربية) · [English](#english)

---

## العربية

### عن المشروع

**مُفكّر** هو نموذج أولي لمنصة داخلية تساعد الموظف على تحويل فكرته الأولية إلى مقترح أوضح وأكثر قابلية للمراجعة. يكتب الموظف المشكلة كما يواجهها في بيئة العمل، ثم تقوم المنصة بتنظيم الفكرة وإرجاع تحليل عملي يتضمن المشكلة، والبدائل الممكنة، والتوصية المناسبة.

لا يستبدل مُفكّر المدير ولا يتخذ القرار بدلًا عنه؛ بل يعمل كمساعد تفكير يرفع جودة المقترح ويسهّل مقارنته مع بقية المقترحات.

### ماذا يقدم مُفكّر؟

- استقبال مقترحات الموظفين باللغة العربية.
- تحسين صياغة الفكرة وتنظيمها دون تغيير مقصد الموظف.
- توضيح المشكلة والبدائل العملية والتوصية المقترحة.
- إعطاء درجة من 100 تساعد على ترتيب الأفكار ومقارنتها.
- عرض المقترحات الخاصة بكل موظف في حسابه.
- توفير لوحة للمدير لمراجعة المقترحات واتخاذ القرار المناسب.
- ترتيب أعلى خمسة مقترحات داخل القسم.
- دعم المراجعة البشرية؛ فالمدير يستطيع مراجعة المقترح وتعديله واعتماده أو رفضه.
- تشغيل النموذج محليًا على الجهاز بدل إرسال محتوى الأفكار إلى مزود ذكاء اصطناعي خارجي.
- توفير طريقة تشغيل مبسطة على Windows من خلال ملفات التشغيل المرفقة.

### كيف تعمل المنصة؟

~~~text
الموظف يكتب الفكرة
        ↓
الموقع يستقبل المقترح
        ↓
خادم FastAPI يتواصل مع النموذج المحلي
        ↓
Qwen3-8B + PEFT Adapter يحلل الفكرة
        ↓
النتيجة تُنظّم وتُحفظ مع التقييم
        ↓
المدير يراجع المقترحات ويعتمد القرار
        ↓
عرض أعلى خمسة مقترحات في القسم
~~~

### مكونات المشروع

ينقسم المشروع إلى مكوّنين رئيسيين:

| المجلد | الوصف |
|---|---|
| model | النموذج المحلي، خادم التحليل، وملفات الـAdapter وتعليمات تشغيل المودل |
| website | واجهة المنصة، الحسابات، تقديم المقترحات، لوحة المدير، الحفظ، والتكامل مع النموذج |

للتفاصيل الخاصة بكل جزء:

- [دليل تشغيل المودل](model/README.md)
- [دليل تشغيل الموقع](website/README.md)

### التقنيات المستخدمة

- Python
- FastAPI
- HTML وCSS
- SQLite
- Qwen/Qwen3-8B
- PEFT Adapter
- Transformers
- CUDA وNVIDIA GPU
- Hugging Face model cache
- Windows batch scripts

### تشغيل المشروع محليًا

#### المتطلبات

- Windows
- Python
- بطاقة NVIDIA متوافقة مع CUDA لتشغيل النموذج محليًا
- تثبيت المتطلبات الموضحة في ملفات README الداخلية

#### التشغيل الأول

1. من مجلد model شغّل ملف setup_model_windows.bat مرة واحدة.
2. من مجلد website شغّل ملف setup_windows.bat مرة واحدة.
3. شغّل run_windows.bat من مجلد website.
4. افتح المتصفح على:

~~~text
http://127.0.0.1:8000
~~~

قد يستغرق تحميل النموذج وقتًا أطول في المرة الأولى. لا تغلق نافذة خادم Qwen3 CUDA أثناء استخدام المنصة.

### الخصوصية والأمان

صُممت نسخة النموذج لتعمل محليًا على الجهاز، بحيث لا تحتاج أفكار الموظفين إلى الخروج إلى خدمة ذكاء اصطناعي خارجية أثناء التشغيل.

يجب عدم رفع أو مشاركة أي من العناصر التالية:

- ملفات .env أو مفاتيح API أو كلمات المرور.
- قواعد البيانات المحلية أو سجلات الاستخدام.
- البيانات الخام أو البيانات الداخلية غير المصرح بنشرها.
- أوزان النموذج الكبيرة أو الملفات الناتجة عن التدريب.
- أي مستندات أو شعارات داخلية لا تملك صلاحية نشرها.

يحتوي المشروع على ملفات إعداد محلية يجب تجهيزها على الجهاز، ولا ينبغي وضع قيم الأسرار الحقيقية داخل المستودع.

### طبيعة المشروع

هذا المشروع نموذج أولي تطبيقي يوضح كيف يمكن استخدام الذكاء الاصطناعي لمساندة الابتكار المؤسسي وتحسين دورة استقبال الأفكار ومراجعتها. مخرجات النموذج مساعدة تحليلية وليست قرارًا إداريًا أو اعتمادًا رسميًا.

### أعضاء الفريق

تم تطوير المشروع بشكل جماعي من خلال أربعة أعضاء:

- عمار العمري
- عبدالله مالكي
- وائل السلمي
- علي الناشري

---

## English

### About the Project

**Mufakkir** is an internal platform prototype that helps employees transform initial ideas into clearer and more reviewable proposals. An employee describes a problem as experienced in the workplace, and the platform organizes the idea and returns a practical analysis containing the problem, possible alternatives, and a recommendation.

Mufakkir does not replace the manager or make decisions on the manager’s behalf. It acts as a thinking assistant that improves proposal quality and makes ideas easier to compare.

### What Mufakkir Provides

- Arabic employee-idea submission.
- Idea refinement and structured presentation without changing the employee’s intended meaning.
- Clear problem framing, practical alternatives, and a suggested recommendation.
- A score out of 100 to support comparison and prioritization.
- A personal view where employees can access their own suggestions.
- A manager dashboard for reviewing submitted ideas.
- Top-five idea ranking within each department.
- Human-in-the-loop review, allowing the manager to review, edit, approve, or reject a proposal.
- Local model execution instead of sending idea content to an external AI provider.
- Simplified Windows startup scripts for running the system locally.

### How It Works

~~~text
Employee submits an idea
        ↓
The website receives the proposal
        ↓
FastAPI communicates with the local model
        ↓
Qwen3-8B + PEFT Adapter analyzes the idea
        ↓
The result is structured, stored, and scored
        ↓
The manager reviews and makes the decision
        ↓
The department’s top five ideas are displayed
~~~

### Repository Structure

The project is organized into two main components:

| Directory | Description |
|---|---|
| model | Local model files, analysis server, adapter, and model setup instructions |
| website | Platform interface, accounts, idea submission, manager dashboard, storage, and model integration |

Component-specific documentation:

- [Model Guide](model/README.md)
- [Website Guide](website/README.md)

### Technology Stack

- Python
- FastAPI
- HTML and CSS
- SQLite
- Qwen/Qwen3-8B
- PEFT Adapter
- Transformers
- CUDA and NVIDIA GPU
- Hugging Face model cache
- Windows batch scripts

### Running the Project Locally

#### Requirements

- Windows
- Python
- An NVIDIA GPU compatible with CUDA for local model execution
- The dependencies described in the component README files

#### First-Time Setup

1. From the model directory, run setup_model_windows.bat once.
2. From the website directory, run setup_windows.bat once.
3. Run run_windows.bat from the website directory.
4. Open the platform at:

~~~text
http://127.0.0.1:8000
~~~

The first model download and startup may take longer. Keep the Qwen3 CUDA Server window open while using the platform.

### Privacy and Security

The model is designed to run locally on the device, so employee ideas do not need to be sent to an external AI service during execution.

The following items must not be uploaded or shared:

- .env files, API keys, or passwords.
- Local databases or usage logs.
- Raw or internal data that is not approved for publication.
- Large model weights or training artifacts.
- Internal documents or logos without permission to publish them.

Local configuration files are required on the machine and real secret values must never be committed to the repository.

### Project Nature

This project is an applied prototype demonstrating how AI can support organizational innovation and improve the process of collecting and reviewing employee ideas. Model outputs are analytical assistance and do not represent an official administrative decision or approval.

### Team

The project was collaboratively developed by four team members:

- Ammar Al-Omari — عمار العمري
- Abdullah Maliki — عبدالله مالكي
- Wael Al-Sulami — وائل السلمي
- Ali Al-Nashri — علي الناشري

---

## Repository Documentation

- [Model README](model/README.md)
- [Website README](website/README.md)

