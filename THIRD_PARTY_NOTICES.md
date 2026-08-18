# Third-Party Notices and Data Provenance

## إشعارات الجهات الخارجية ومصدر بيانات التدريب

هذا الملف يوثق المكونات الخارجية ومعلومات مصدر بيانات التدريب المعروفة حاليًا. لا يمنح هذا الملف أي حقوق إضافية في الشعارات أو البيانات أو الأوزان.

This file records the currently known third-party components and training-data provenance. It does not grant additional rights to use logos, data, or model weights.

## Qwen/Qwen3-8B

- الاستخدام: يشير إعداد النموذج إلى `Qwen/Qwen3-8B` كنموذج أساس. أوزان النموذج الأساس غير مضمنة في هذا المستودع.
- Usage: the model configuration references `Qwen/Qwen3-8B` as the base model. The base-model weights are not included in this repository.
- الترخيص / License: Apache-2.0، وفق [بطاقة النموذج الرسمية](https://huggingface.co/Qwen/Qwen3-8B) و[المستودع الرسمي لـQwen3](https://github.com/QwenLM/Qwen3).
- عند تنزيل النموذج أو إعادة توزيعه، يجب الالتزام بملف الترخيص وبشروط بطاقة النموذج الحالية.
- When downloading or redistributing the model, follow the applicable license file and the current model-card terms.

## Hugging Face PEFT

- الاستخدام: يستخدم المشروع PEFT/LoRA لتطبيق Adapter على النموذج الأساس.
- Usage: the project uses PEFT/LoRA to apply an adapter to the base model.
- الترخيص / License: Apache-2.0، وفق [المستودع الرسمي لـPEFT](https://github.com/huggingface/peft).
- يجب الاحتفاظ بإشعار الترخيص عند توزيع نسخ من المكوّن أو الأعمال التي تتضمنه.
- Preserve the license notice when redistributing copies of the component or works that include it.

## Dataset and training-data provenance

- لا يحتوي المستودع على ملفات Dataset أو ملفات بيانات خام.
- بيانات التدريب غير مرفقة في المستودع وغير قابلة لإعادة التوزيع من خلاله.
- لا تحدد الملفات الحالية اسم Dataset أو مصدره أو ترخيصه أو إثبات الموافقة على استخدامه.
- تشير وثائق النموذج إلى أن الـAdapter دُرّب على مقترحات عربية، لكن هذه المعلومة لا تكفي لإثبات حق النشر أو إعادة التوزيع.
- حالة النشر: **غير معتمدة حتى يتم التحقق**.

Before publishing or distributing the adapter, record all of the following:

1. Dataset name and source owner.
2. License or written permission for use and redistribution.
3. Whether the data contains employee, personal, confidential, or municipal information.
4. Consent, anonymization, retention, and deletion requirements.
5. Whether the trained adapter itself may be distributed.

Do not replace this status with an invented dataset name or license. If the provenance cannot be verified, keep the adapter and training data private and do not claim that they are publicly licensed.

The training data is not included in this repository and is not redistributable through it.

## Official branding assets

The following assets use official-looking Jeddah Municipality and Saudi Vision 2030 branding and may require separate permission or trademark review. Software licenses above do not authorize their use:

- `website/static/img/header_logo.png`
- `website/static/img/footer_logo.png`
- `website/static/img/vision2030.png`
- `docs/screenshots/homepage.png`
