import argparse
import copy
import gc
import time

import pandas as pd
import torch
from torch.nn.utils import _stateless
from transformers import AutoConfig
from transformers import AutoModelForCausalLM
from transformers import AutoModelForMaskedLM
from transformers import AutoModelForSeq2SeqLM
from transformers import BertConfig
from transformers import BigBirdConfig
from transformers import ReformerConfig

import torchdynamo
from torchdynamo.optimizations.training import aot_autograd_speedup_strategy
from torchdynamo.testing import clone_me
from torchdynamo.testing import collect_results
from torchdynamo.testing import same

benchmarks = [
    (BertConfig(), AutoModelForMaskedLM, (4, 512), []),
    # (AutoConfig.from_pretrained("albert-base-v2"), AutoModelForMaskedLM, (8, 512), []),
    # (AutoConfig.from_pretrained("gpt2"), AutoModelForCausalLM, (4, 512), []),
    # (
    #     AutoConfig.from_pretrained("allenai/longformer-base-4096"),
    #     AutoModelForMaskedLM,
    #     (2, 1024),
    #     [torch.float16, torch.bfloat16],
    # ),  # hmm, nans with float16
    # (AutoConfig.from_pretrained("t5-small"), AutoModelForSeq2SeqLM, (4, 1024), [torch.float16, torch.bfloat16]), # Doesn't work with nn.utils._stateless for some reason...
    # (AutoConfig.from_pretrained("facebook/bert-base"), AutoModelForSeq2SeqLM, (4, 512), []), # Doesn't work with nn.utils._stateless for some reason...
    # (ReformerConfig(), AutoModelForMaskedLM, (8, 4096), []), # not sure...
    # (BigBirdConfig(attention_type="block_sparse"), AutoModelForMaskedLM, (2, 1024), []), # not sure...
    # (AutoConfig.from_pretrained("distilbert-base-uncased"),  AutoModelForMaskedLM, (8, 512), []), # encounters inf as a global value
]

device = "cuda"

USE_EVAL = False


class NullContext:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@torchdynamo.skip
def get_cur_memory():
    torch.cuda.synchronize()

    gc.collect()
    torch.cuda.empty_cache()
    stats = torch.cuda.memory_stats()
    peak_bytes_requirement = stats["allocated_bytes.all.current"]
    print(f"Current memory requirement: {peak_bytes_requirement / 1024 ** 3:.2f} GB")
    return peak_bytes_requirement


@torchdynamo.skip
def forward_pass(mod, inputs, collect_outputs=True):
    return mod(*inputs)


@torchdynamo.skip
def forward_and_backward_pass(mod, inputs, collect_outputs=True):
    mod.zero_grad(True)
    pred = mod(**inputs)
    loss = pred.loss.mean()
    loss.backward()
    if collect_outputs:
        return collect_results(mod, pred, loss, example_inputs=())
    return None


@torchdynamo.skip
def check_correctness(mod, train_inputs):
    optimize_ctx = torchdynamo.optimize(aot_autograd_speedup_strategy)
    torch.manual_seed(1337)
    correct_result = forward_and_backward_pass(copy.deepcopy(mod), train_inputs)

    torch.manual_seed(1337)
    correct_rerun_result = forward_and_backward_pass(copy.deepcopy(mod), train_inputs)
    if not same(correct_result, correct_rerun_result):
        print("INCORRECT - Variation in Eager runs itself")
        return False

    torch.manual_seed(1337)
    torchdynamo.reset()
    try:
        with optimize_ctx:
            new_result = forward_and_backward_pass(mod, train_inputs)
    except Exception:
        print("ERROR")
        return False

    if not same(correct_result, new_result, tol=1e-3):
        print("INCORRECT")
        return False
    return True


@torchdynamo.skip
def bench_model(name, mod, train_inputs):
    assert name in ("eager", "dynamo_aot")
    if name == "eager":
        optimize_ctx = NullContext()
    else:
        optimize_ctx = torchdynamo.optimize(aot_autograd_speedup_strategy)

    with optimize_ctx:
        # Profile memory
        m = None
        for i in range(5):
            out = mod(**train_inputs).loss.abs().sum()
            if i == 4:
                m = get_cur_memory()
            out.backward()

        # Profile time
        iters = 20
        torch.cuda.synchronize()
        begin = time.time()
        for _ in range(iters):
            forward_and_backward_pass(mod, train_inputs, False)
        torch.cuda.synchronize()
        end = time.time()
        t = (end - begin) / iters

    print(name, t)
    return t, m


model_header, dtype_header, nh, th, mh, tp, mp, acc = (
    "model",
    "dtype",
    "name",
    "time (s)",
    "mem (GB)",
    "time %",
    "mem %",
    "is_accurate",
)


def create_record(model_name, dtype, is_accurate, name, t, m):
    return {
        model_header: model_name,
        dtype_header: str(dtype),
        acc: is_accurate,
        nh: name,
        th: t,
        mh: m / 2**30,
    }


numerical_diffs = []
results = []


def run_all():
    for config, model_type, input_size, not_supported_dtypes in benchmarks:
        for dtype in [torch.float, torch.half, torch.bfloat16]:
            if dtype in not_supported_dtypes:
                continue
            for attr in dir(config):
                if "drop" in attr:
                    setattr(
                        config, attr, 1e-60
                    )  # So we can check for correct gradients without eliminating the dropout computation
            model = model_type.from_config(config).to(device, dtype=dtype)

            if USE_EVAL:
                model.eval()

            model_name = type(model).__name__

            # Prepare inputs
            input_ids = torch.randint(0, config.vocab_size, input_size).to(device)
            decoder_ids = torch.randint(0, config.vocab_size, input_size).to(device)
            train_inputs = {"input_ids": input_ids, "labels": decoder_ids}

            # Correctness check
            is_accurate = check_correctness(model, train_inputs)

            # Profile eager
            t, m = bench_model("eager", model, train_inputs)
            results.append(create_record(model_name, dtype, is_accurate, "eager", t, m))

            # Profile Dynamo nvfuser
            with torch.jit.fuser("fuser2"):
                t, m = bench_model("dynamo_aot", model, train_inputs)
            results.append(create_record(model_name, dtype, is_accurate, "dynamo_aot", t, m))

            # calculate relative improvements
            base_r = results[-2]
            for r in results[-2:]:
                r[tp] = round(100 * (r[th] - base_r[th]) / base_r[th])
                r[mp] = round(100 * (r[mh] - base_r[mh]) / base_r[mh])
            print(pd.DataFrame(results[-2:]).to_markdown(index=False, floatfmt=".3f"))

    print("=== Final results ===")
    print(pd.DataFrame(results).to_markdown(index=False, floatfmt=".3f"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--use-eval-mode",
        action="store_true",
        help="sets model.eval() to reduce randomness",
    )

    args = parser.parse_args()
    if args.use_eval_mode:
        global USE_EVAL
        USE_EVAL = True

    run_all()


if __name__ == "__main__":
    main()
