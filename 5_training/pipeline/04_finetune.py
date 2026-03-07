"""
ReconMind — training/pipeline/04_finetune.py
Step 4: Fine-tune a local LLM on the ReconMind dataset.

Method: QLoRA (Quantized Low-Rank Adaptation)
  - Memory efficient: runs on 1x RTX 3090 (24GB) or better
  - Uses 4-bit quantization via bitsandbytes
  - LoRA adapters: trains only ~1% of parameters
  - Base model: Mistral-7B-Instruct-v0.2 (recommended)

Requirements:
  pip install transformers trl peft bitsandbytes accelerate datasets

Hardware recommendations:
  Minimum: NVIDIA GPU 16GB VRAM (RTX 3080 Ti, A4000)
  Recommended: NVIDIA GPU 24GB VRAM (RTX 3090, A5000)
  Best: NVIDIA A100 40GB or 80GB
"""

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
@dataclass
class TrainingConfig:
    # ── Model ────────────────────────────────────────
    base_model: str      = "mistralai/Mistral-7B-Instruct-v0.2"
    # Alternative options:
    # "meta-llama/Meta-Llama-3.1-8B-Instruct"  (requires HF token)
    # "google/gemma-2-9b-it"
    # "Qwen/Qwen2.5-7B-Instruct"               (strong performer)

    # ── Dataset ──────────────────────────────────────
    dataset_dir: str     = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "datasets"
    )

    # ── Output ───────────────────────────────────────
    output_dir: str      = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", "ai-model", "model", "reconmind-v1"
    )

    # ── LoRA hyperparameters ──────────────────────────
    lora_r: int          = 16       # LoRA rank
    lora_alpha: int      = 32       # LoRA scaling
    lora_dropout: float  = 0.05
    target_modules: list = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ])

    # ── Training ──────────────────────────────────────
    num_epochs: int       = 3
    batch_size: int       = 2       # per device
    grad_accumulation: int = 8      # effective batch = 16
    learning_rate: float  = 2e-4
    max_seq_length: int   = 2048
    warmup_ratio: float   = 0.03
    lr_scheduler: str     = "cosine"
    weight_decay: float   = 0.001

    # ── Quantization ─────────────────────────────────
    load_in_4bit: bool    = True
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_compute_dtype: str = "bfloat16"

    # ── Eval ──────────────────────────────────────────
    eval_steps: int       = 50
    save_steps: int       = 100
    logging_steps: int    = 10


# ─────────────────────────────────────────
# Fine-tuning function
# ─────────────────────────────────────────
def finetune(config: TrainingConfig):
    """
    Main fine-tuning function using QLoRA + TRL SFTTrainer.
    """
    print("=" * 55)
    print("  ReconMind Training — Step 4: Fine-tuning")
    print("=" * 55)
    print(f"\n  Base model  : {config.base_model}")
    print(f"  Dataset dir : {config.dataset_dir}")
    print(f"  Output dir  : {config.output_dir}")
    print(f"  Epochs      : {config.num_epochs}")
    print(f"  LoRA rank   : {config.lora_r}")

    # Import check
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
        )
        from peft import LoraConfig, get_peft_model, TaskType
        from trl import SFTTrainer, DataCollatorForCompletionOnlyLM
        from datasets import Dataset
    except ImportError as e:
        print(f"\n  ERROR: Missing dependency: {e}")
        print("  Install: pip install transformers trl peft bitsandbytes accelerate datasets")
        sys.exit(1)

    import torch

    # ── GPU check ─────────────────────────────────────
    if not torch.cuda.is_available():
        print("\n  WARNING: No GPU detected. Training on CPU will be extremely slow.")
        print("  Recommended: NVIDIA GPU with 16GB+ VRAM")
    else:
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem  = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"\n  GPU: {gpu_name} ({gpu_mem:.1f} GB)")

    # ── Load dataset ──────────────────────────────────
    print("\n  Loading dataset...")
    train_path = os.path.join(config.dataset_dir, "train.jsonl")
    val_path   = os.path.join(config.dataset_dir, "validation.jsonl")

    if not os.path.exists(train_path):
        print(f"  ERROR: {train_path} not found.")
        print("  Run Step 3 first: python pipeline/03_build_dataset.py")
        sys.exit(1)

    def load_jsonl(path):
        with open(path, "r") as f:
            return [json.loads(line) for line in f if line.strip()]

    train_data = load_jsonl(train_path)
    val_data   = load_jsonl(val_path)
    print(f"  Train: {len(train_data)} examples")
    print(f"  Val  : {len(val_data)} examples")

    train_dataset = Dataset.from_list(train_data)
    val_dataset   = Dataset.from_list(val_data)

    # ── Quantization config ───────────────────────────
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=config.load_in_4bit,
        bnb_4bit_quant_type=config.bnb_4bit_quant_type,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # ── Load model and tokenizer ──────────────────────
    print(f"\n  Loading base model: {config.base_model}")
    print("  (This may take a few minutes on first run...)")

    tokenizer = AutoTokenizer.from_pretrained(
        config.base_model, trust_remote_code=True
    )
    tokenizer.pad_token     = tokenizer.eos_token
    tokenizer.padding_side  = "right"

    model = AutoModelForCausalLM.from_pretrained(
        config.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False
    model.config.pretraining_tp = 1

    # ── LoRA config ───────────────────────────────────
    lora_config = LoraConfig(
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        target_modules=config.target_modules,
        lora_dropout=config.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, lora_config)
    trainable, total = model.get_nb_trainable_parameters()
    print(f"\n  Trainable params : {trainable:,} ({100*trainable/total:.2f}%)")
    print(f"  Total params     : {total:,}")

    # ── Training arguments ────────────────────────────
    os.makedirs(config.output_dir, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=config.output_dir,
        num_train_epochs=config.num_epochs,
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.grad_accumulation,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        warmup_ratio=config.warmup_ratio,
        lr_scheduler_type=config.lr_scheduler,
        evaluation_strategy="steps",
        eval_steps=config.eval_steps,
        save_steps=config.save_steps,
        logging_steps=config.logging_steps,
        load_best_model_at_end=True,
        save_total_limit=3,
        fp16=False,
        bf16=torch.cuda.is_available(),
        report_to="none",      # Change to "tensorboard" or "wandb" if desired
        push_to_hub=False,     # Local only — never push to Hub
    )

    # ── Format messages into strings ──────────────────
    def format_chatml(example):
        """Convert ChatML messages to a single training string."""
        messages = example["messages"]
        text = ""
        for msg in messages:
            role    = msg["role"]
            content = msg["content"]
            if role == "system":
                text += f"<|system|>\n{content}</s>\n"
            elif role == "user":
                text += f"<|user|>\n{content}</s>\n"
            elif role == "assistant":
                text += f"<|assistant|>\n{content}</s>\n"
        return {"text": text}

    train_dataset = train_dataset.map(format_chatml)
    val_dataset   = val_dataset.map(format_chatml)

    # ── Trainer ───────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        dataset_text_field="text",
        max_seq_length=config.max_seq_length,
        packing=False,
    )

    # ── Train ─────────────────────────────────────────
    print(f"\n  Starting training for {config.num_epochs} epochs...")
    print("  Monitor progress in the logs below.\n")

    trainer.train()

    # ── Save final model ──────────────────────────────
    final_path = os.path.join(config.output_dir, "final")
    trainer.save_model(final_path)
    tokenizer.save_pretrained(final_path)

    print(f"\n  ✅ Training complete!")
    print(f"  Model saved: {final_path}")
    print("\n  Next step: python pipeline/05_evaluate.py")
    print("=" * 55)


# ─────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────
if __name__ == "__main__":
    config = TrainingConfig()

    # Override from environment variables if set
    if os.getenv("BASE_MODEL"):
        config.base_model = os.getenv("BASE_MODEL")
    if os.getenv("TRAIN_EPOCHS"):
        config.num_epochs = int(os.getenv("TRAIN_EPOCHS"))

    finetune(config)
