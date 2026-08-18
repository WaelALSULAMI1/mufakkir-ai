"""OpenAI-compatible local server for Qwen3-8B + PEFT on NVIDIA CUDA.

Loads the base model and the converted PEFT adapter once at startup.
Does not train, does not use MLX, and does not read adapters.safetensors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from inference_cuda import model_adapter_shapes, validate_adapter_against_base


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_configure_stdio()

THINK_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
THINK_OPEN = re.compile(r"<think>.*", flags=re.DOTALL | re.IGNORECASE)
THINK_TAG = re.compile(r"</?think>", flags=re.IGNORECASE)
FORBIDDEN_ADAPTER_NAMES = {"adapters.safetensors"}
FORBIDDEN_ADAPTER_DIRS = {"qlora_idea_eval", "mufakkir_training", "mufakkir_training_v2"}


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    stream: bool = False


class ModelRuntime:
    def __init__(self, model, tokenizer, model_id: str, adapter_dir: Path):
        self.model = model
        self.tokenizer = tokenizer
        self.model_id = model_id
        self.adapter_dir = adapter_dir
        self.lock = threading.Lock()
        self.created = int(time.time())


RUNTIME: ModelRuntime | None = None


def _require_runtime() -> ModelRuntime:
    if RUNTIME is None:
        raise HTTPException(status_code=503, detail="النموذج لم يُحمَّل بعد.")
    return RUNTIME


def strip_think(text: str) -> str:
    text = THINK_BLOCK.sub("", text or "")
    text = THINK_OPEN.sub("", text)
    text = THINK_TAG.sub("", text)
    return text.strip()


def message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return str(content)


def build_prompt(tokenizer, messages: list[dict[str, str]]) -> str:
    if getattr(tokenizer, "chat_template", None):
        try:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
    lines = []
    for message in messages:
        lines.append(f"{message['role']}: {message['content']}")
    lines.append("assistant:")
    return "\n".join(lines)


def refuse_original_mlx_adapter(adapter_dir: Path) -> None:
    if adapter_dir.name in FORBIDDEN_ADAPTER_NAMES or adapter_dir.suffix == ".safetensors":
        raise RuntimeError(
            "لا تستخدم adapters.safetensors الأصلي. مرّر مجلد Summer_Arabic_Problem_Solver_PEFT."
        )
    for part in adapter_dir.parts:
        if part in FORBIDDEN_ADAPTER_DIRS:
            raise RuntimeError(f"مسار الـAdapter غير مسموح: {part}")
    if adapter_dir.name == "adapters" and (adapter_dir / "adapters.safetensors").is_file():
        raise RuntimeError("هذا مجلد MLX. استخدم مجلد PEFT المحوّل فقط.")


def load_runtime(args: argparse.Namespace) -> ModelRuntime:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 أو أحدث مطلوب")

    try:
        import torch
        from peft import PeftModel
        from safetensors.torch import load_file
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:
        raise RuntimeError(
            "ثبّت torch وtransformers وpeft وaccelerate وbitsandbytes وsafetensors وfastapi وuvicorn أولًا"
        ) from exc

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA غير متاحة. تحقق من تعريف NVIDIA وثبّت نسخة PyTorch التي تدعم CUDA.")

    adapter_dir = Path(args.adapter_path).expanduser().resolve()
    refuse_original_mlx_adapter(adapter_dir)
    adapter_file = adapter_dir / "adapter_model.safetensors"
    adapter_config_file = adapter_dir / "adapter_config.json"
    if not adapter_file.is_file():
        raise FileNotFoundError(f"لم يُوجد adapter_model.safetensors داخل: {adapter_dir}")
    if not adapter_config_file.is_file():
        raise FileNotFoundError(f"لم يُوجد adapter_config.json داخل: {adapter_dir}")

    print(f"torch={torch.__version__}")
    print(f"cuda_runtime={torch.version.cuda}")
    print(f"gpu={torch.cuda.get_device_name(0)}")
    print(f"base_model={args.model}")
    print(f"adapter_dir={adapter_dir}")
    print("تحميل المودل الأساسي بضغط 4-bit NF4...")

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )
    load_kwargs = {
        "quantization_config": bnb_config,
        "device_map": "auto",
        "low_cpu_mem_usage": True,
        "trust_remote_code": args.trust_remote_code,
    }
    try:
        model = AutoModelForCausalLM.from_pretrained(args.model, dtype=compute_dtype, **load_kwargs)
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=compute_dtype, **load_kwargs)

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=args.trust_remote_code)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    adapter_state = load_file(str(adapter_file), device="cpu")
    adapter_config = json.loads(adapter_config_file.read_text(encoding="utf-8"))
    adapter_rank = int(adapter_config["r"])
    rank_mismatches = []
    for key, tensor in adapter_state.items():
        shape = tuple(int(x) for x in tensor.shape)
        if key.endswith(".lora_A.weight") and (len(shape) != 2 or shape[0] != adapter_rank):
            rank_mismatches.append({"key": key, "shape": list(shape), "rank": adapter_rank})
        if key.endswith(".lora_B.weight") and (len(shape) != 2 or shape[1] != adapter_rank):
            rank_mismatches.append({"key": key, "shape": list(shape), "rank": adapter_rank})
    if rank_mismatches:
        raise RuntimeError(f"فشل التحقق من rank الـAdapter: {rank_mismatches}")

    print(json.dumps(validate_adapter_against_base(model, adapter_state), ensure_ascii=False))
    print("تحميل Adapter PEFT مرة واحدة...")
    model = PeftModel.from_pretrained(model, str(adapter_dir), is_trainable=False)
    model.eval()

    loaded_shapes = model_adapter_shapes(model)
    loaded_keys = set(loaded_shapes)
    source_keys = set(adapter_state)
    missing = sorted(source_keys - loaded_keys)
    unexpected = sorted(loaded_keys - source_keys)
    shape_mismatches = [
        {"key": key, "file": list(adapter_state[key].shape), "model": list(loaded_shapes[key])}
        for key in sorted(source_keys & loaded_keys)
        if tuple(int(x) for x in adapter_state[key].shape) != loaded_shapes[key]
    ]
    if missing or unexpected or shape_mismatches:
        raise RuntimeError(
            f"فشل التحقق بعد تحميل PEFT: missing={missing}, unexpected={unexpected}, shape_mismatches={shape_mismatches}"
        )
    print(f"adapter_load=ok tensors={len(source_keys)} missing=0 unexpected=0 shape_mismatches=0")
    print("المودل جاهز على CUDA. لن يُعاد تحميله مع كل طلب.")
    return ModelRuntime(model=model, tokenizer=tokenizer, model_id=args.model, adapter_dir=adapter_dir)


def generate_text(
    runtime: ModelRuntime,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float,
    max_tokens: int,
    max_input_tokens: int,
) -> tuple[str, int, int]:
    import torch

    prompt = build_prompt(runtime.tokenizer, messages)
    inputs = runtime.tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=max_input_tokens,
    )
    input_device = runtime.model.get_input_embeddings().weight.device
    inputs = {key: value.to(input_device) for key, value in inputs.items()}
    prompt_tokens = int(inputs["input_ids"].shape[1])

    generation_kwargs: dict[str, Any] = {
        "max_new_tokens": max_tokens,
        "pad_token_id": runtime.tokenizer.pad_token_id,
        "eos_token_id": runtime.tokenizer.eos_token_id,
    }
    if temperature and temperature > 0:
        generation_kwargs.update({"do_sample": True, "temperature": float(temperature), "top_p": float(top_p)})
    else:
        generation_kwargs["do_sample"] = False

    with runtime.lock:
        with torch.inference_mode():
            generated = runtime.model.generate(**inputs, **generation_kwargs)

    new_tokens = generated[0, prompt_tokens:]
    completion_tokens = int(new_tokens.shape[0])
    text = runtime.tokenizer.decode(new_tokens, skip_special_tokens=True)
    return strip_think(text), prompt_tokens, completion_tokens


def create_app(max_input_tokens: int) -> FastAPI:
    app = FastAPI(title="Qwen3-8B CUDA Chat Server", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/v1/models")
    def list_models():
        runtime = _require_runtime()
        return {
            "object": "list",
            "data": [
                {
                    "id": runtime.model_id,
                    "object": "model",
                    "created": runtime.created,
                    "owned_by": "local",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    def chat_completions(body: ChatCompletionRequest):
        runtime = _require_runtime()
        if body.stream:
            raise HTTPException(status_code=400, detail="البث stream غير مدعوم. أرسل stream=false.")

        messages = []
        for item in body.messages:
            role = (item.role or "user").strip().lower()
            if role not in {"system", "user", "assistant"}:
                role = "user"
            messages.append({"role": role, "content": message_text(item.content)})
        if not any(message["content"].strip() for message in messages):
            raise HTTPException(status_code=400, detail="messages فارغة.")

        max_tokens = body.max_tokens or body.max_completion_tokens or 1024
        max_tokens = max(1, min(int(max_tokens), 8192))
        temperature = max(0.0, min(float(body.temperature), 2.0))
        top_p = max(0.0, min(float(body.top_p), 1.0))

        try:
            content, prompt_tokens, completion_tokens = generate_text(
                runtime,
                messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                max_input_tokens=max_input_tokens,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"فشل التوليد: {exc}") from exc

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.model or runtime.model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="Qwen/Qwen3-8B", help="المودل الأساسي من Hugging Face")
    parser.add_argument(
        "--adapter-path",
        required=True,
        help="مجلد PEFT المحوّل (يجب أن يحتوي adapter_model.safetensors)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--max-input-tokens", type=int, default=8192)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def main() -> None:
    global RUNTIME
    args = parse_args()
    RUNTIME = load_runtime(args)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("ثبّت uvicorn: python -m pip install fastapi uvicorn") from exc

    print(f"الخادم يستمع على http://{args.host}:{args.port}")
    uvicorn.run(create_app(args.max_input_tokens), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
