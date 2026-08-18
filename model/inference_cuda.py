"""Run the converted PEFT adapter on a CUDA GPU with 4-bit Transformers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def canonical_adapter_key(key: str) -> str:
    return key.replace(".default.", ".")


def model_adapter_shapes(model) -> dict[str, tuple[int, ...]]:
    shapes = {}
    for name, parameter in model.named_parameters():
        if ".lora_A." in name or ".lora_B." in name:
            shapes[canonical_adapter_key(name)] = tuple(int(dimension) for dimension in parameter.shape)
    return shapes


def validate_adapter_against_base(model, adapter_state: dict[str, object]) -> dict[str, object]:
    modules = dict(model.named_modules())
    expected_keys = set()
    missing_modules = []
    shape_mismatches = []
    for key, tensor in adapter_state.items():
        if not (key.endswith(".lora_A.weight") or key.endswith(".lora_B.weight")):
            raise RuntimeError(f"Unexpected PEFT tensor key: {key}")
        module_name = key.rsplit(".lora_A.weight", 1)[0].rsplit(".lora_B.weight", 1)[0]
        module_name = module_name.removeprefix("base_model.model.")
        module = modules.get(module_name)
        if module is None:
            missing_modules.append(module_name)
            continue
        expected_keys.add(key)
        if not hasattr(module, "weight"):
            raise RuntimeError(f"Adapter target is not a weighted module: {module_name}")
        # bitsandbytes Linear4bit stores a packed weight tensor. Its
        # ``weight.shape`` is therefore not the logical Linear shape (for
        # example, in_features can appear as 1 or a packed byte count).
        # PEFT must be checked against the logical module dimensions.
        in_features = getattr(module, "in_features", None)
        out_features = getattr(module, "out_features", None)
        if in_features is None or out_features is None:
            weight_shape = tuple(int(x) for x in module.weight.shape)
            if len(weight_shape) != 2:
                raise RuntimeError(f"Cannot infer logical dimensions for adapter target: {module_name}")
            out_features, in_features = weight_shape
        in_features = int(in_features)
        out_features = int(out_features)
        actual = tuple(int(x) for x in tensor.shape)
        if key.endswith(".lora_A.weight"):
            expected = (actual[0], in_features)
        else:
            expected = (out_features, actual[1])
        if actual != expected:
            shape_mismatches.append({"key": key, "adapter": list(actual), "expected": list(expected)})
    if missing_modules or shape_mismatches:
        raise RuntimeError(f"Base-model comparison failed: missing_modules={missing_modules}; shape_mismatches={shape_mismatches}")
    return {"adapter_tensor_count": len(adapter_state), "matched_adapter_tensors": len(expected_keys), "missing_modules": [], "shape_mismatches": []}


def build_chat_text(tokenizer, system_prompt: str, user_prompt: str) -> str:
    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    if getattr(tokenizer, "chat_template", None):
        try:
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return (f"System: {system_prompt}\n" if system_prompt.strip() else "") + f"User: {user_prompt}\nAssistant:"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", default="Qwen/Qwen3-8B")
    parser.add_argument("--adapter-dir", type=Path, default=Path("Summer_Arabic_Problem_Solver_PEFT"))
    parser.add_argument("--prompt", default="اكتب المشكلة هنا")
    parser.add_argument("--system-prompt-file", type=Path, default=Path("PROMPT_AR.txt"))
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--max-input-tokens", type=int, default=3072)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--trust-remote-code", action="store_true")
    args = parser.parse_args()

    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required")
    try:
        import torch
        from peft import PeftModel
        from safetensors.torch import load_file
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError as exc:
        raise RuntimeError("Install torch, transformers, peft, accelerate, bitsandbytes, and safetensors first") from exc

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. Verify the NVIDIA driver and install a CUDA-enabled PyTorch build.")
    print(f"torch={torch.__version__}")
    print(f"cuda_runtime={torch.version.cuda}")
    print(f"gpu={torch.cuda.get_device_name(0)}")

    system_prompt = args.system_prompt_file.read_text(encoding="utf-8") if args.system_prompt_file.is_file() else ""
    adapter_dir = args.adapter_dir.resolve()
    adapter_file = adapter_dir / "adapter_model.safetensors"
    if not adapter_file.is_file():
        raise FileNotFoundError(adapter_file)

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
        model = AutoModelForCausalLM.from_pretrained(args.base_model, dtype=compute_dtype, **load_kwargs)
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(args.base_model, torch_dtype=compute_dtype, **load_kwargs)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=args.trust_remote_code)

    adapter_state = load_file(str(adapter_file), device="cpu")
    adapter_config = json.loads((adapter_dir / "adapter_config.json").read_text(encoding="utf-8"))
    adapter_rank = int(adapter_config["r"])
    rank_mismatches = []
    for key, tensor in adapter_state.items():
        shape = tuple(int(x) for x in tensor.shape)
        if key.endswith(".lora_A.weight") and (len(shape) != 2 or shape[0] != adapter_rank):
            rank_mismatches.append({"key": key, "shape": list(shape), "rank": adapter_rank})
        if key.endswith(".lora_B.weight") and (len(shape) != 2 or shape[1] != adapter_rank):
            rank_mismatches.append({"key": key, "shape": list(shape), "rank": adapter_rank})
    if rank_mismatches:
        raise RuntimeError(f"Adapter rank validation failed: {rank_mismatches}")
    base_check = validate_adapter_against_base(model, adapter_state)
    print(json.dumps(base_check, ensure_ascii=False))
    model = PeftModel.from_pretrained(model, str(adapter_dir), is_trainable=False)

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
        raise RuntimeError(f"Adapter load verification failed: missing={missing}, unexpected={unexpected}, shape_mismatches={shape_mismatches}")
    print(f"adapter_load=ok tensors={len(source_keys)} missing=0 unexpected=0 shape_mismatches=0")

    text = build_chat_text(tokenizer, system_prompt, args.prompt)
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=args.max_input_tokens)
    input_device = model.get_input_embeddings().weight.device
    inputs = {key: value.to(input_device) for key, value in inputs.items()}
    generation_kwargs = {
        "max_new_tokens": args.max_new_tokens,
        "pad_token_id": tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id,
        "eos_token_id": tokenizer.eos_token_id,
    }
    if args.temperature > 0:
        generation_kwargs.update({"do_sample": True, "temperature": args.temperature, "top_p": args.top_p})
    else:
        generation_kwargs["do_sample"] = False
    with torch.inference_mode():
        generated = model.generate(**inputs, **generation_kwargs)
    new_tokens = generated[0, inputs["input_ids"].shape[1] :]
    print(tokenizer.decode(new_tokens, skip_special_tokens=True))


if __name__ == "__main__":
    main()
