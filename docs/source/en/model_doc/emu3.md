<!--Copyright 2024 The HuggingFace Team. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.

⚠️ Note that this file is in Markdown but contain specific syntax for our doc-builder (similar to MDX) that may not be
rendered properly in your Markdown viewer.

-->

# Emu3

## Overview

The Emu3 model was proposed in ["Emu3: Next-Token Prediction is All You Need"](https://arxiv.org/abs/2409.18869) by Xinlong Wang, Xiaosong Zhang, Zhengxiong Luo, Quan Sun, Yufeng Cui, Jinsheng Wang, Fan Zhang, Yueze Wang, Zhen Li, Qiying Yu, Yingli Zhao, Yulong Ao, Xuebin Min, Tao Li, Boya Wu, Bo Zhao, Bowen Zhang, Liangdong Wang, Guang Liu, Zheqi He, Xi Yang, Jingjing Liu, Yonghua Lin, Tiejun Huang, Zhongyuan Wang.

Emu3 is a multimodal LLM that uses vector quantization to tokenize images into discrete tokens. Discretized image tokens are later fused with text token ids for image+text generation, and additionally the model can generate images by predicting image token ids. 


The abstract from the paper is the following:

*While next-token prediction is considered a promising path towards artificial general intelligence, it has struggled to excel in multimodal tasks, which are still dominated by diffusion models (e.g., Stable Diffusion) and compositional approaches (e.g., CLIP combined with LLMs). In this paper, we introduce Emu3, a new suite of state-of-the-art multimodal models trained solely with next-token prediction. By tokenizing images, text, and videos into a discrete space, we train a single transformer from scratch on a mixture of multimodal sequences. Emu3 outperforms several well-established task-specific models in both generation and perception tasks, surpassing flagship models such as SDXL and LLaVA-1.6, while eliminating the need for diffusion or compositional architectures. Emu3 is also capable of generating high-fidelity video via predicting the next token in a video sequence. We simplify complex multimodal model designs by converging on a singular focus: tokens, unlocking great potential for scaling both during training and inference. Our results demonstrate that next-token prediction is a promising path towards building general multimodal intelligence beyond language. We open-source key techniques and models to support further research in this direction.
*

Tips:

- We advise users to use `padding_side="left"` when computing batched generation as it leads to more accurate results. Simply make sure to set `processor.tokenizer.padding_side = "left"` before generating.

- Note that the model has been trained with a specific prompt format for chatting. You can use processor's `apply_chat_template` to format your prompts correctly via `processor.apply_chat_tenplate(my_conversation_dict)`.

- Emu3 has two different checkpoints for image-generation and text-generation, make sure to use the correct checkpoint when loading the model. To generate image it is advised to use `prefix_constraints` so that the generated tokens are sampled only from possible image tokens. See more below for usage examples.

> [!NOTE]
> Emu3 implementation in Transformers uses a special image token to indicate where to merge image embeddings. For special image token we didn't add a new one but used one of the reserved tokens: `<|extra_0|>`. You have to add `<image>` to your prompt in the place where the image should be embedded for correct generation.


This model was contributed by [RaushanTurganbay](https://huggingface.co/RaushanTurganbay).
The original code can be found [here](https://github.com/baaivision/Emu3).


## Usage example

### Text generation inference

Here's how to load the model and perform inference in half-precision (`torch.bfloat16`) to generate textual output from "text" or "text+image" inputs:

```python
from transformers import Emu3Processor, Emu3ForConditionalGeneration
import torch
from PIL import Image
import requests

processor = Emu3Processor.from_pretrained("Emu3-community/Emu3-Chat-hf")
model = Emu3ForConditionalGeneration.from_pretrained("Emu3-community/Emu3-Chat-hf", torch_dtype=torch.bfloat16, device_map="cuda")

# prepare image and text prompt
url = 'http://images.cocodataset.org/val2017/000000039769.jpg'
image = Image.open(requests.get(url, stream=True).raw)
prompt = "What do you see in this image?<image>"

inputs = processor(images=image, text=prompt, return_tensors="pt").to(model.device, dtype=torch.bfloat16)

# autoregressively complete prompt
output = model.generate(**inputs, max_new_tokens=50)
print(processor.decode(output[0], skip_special_tokens=True))
```

### Image generation inference

Emu3 can also generate images from textual input. Here is how you can do it:

```python
processor = Emu3Processor.from_pretrained("Emu3-community/Emu3-Gen-hf")
model = Emu3ForConditionalGeneration.from_pretrained("Emu3-community/Emu3-Gen-hf", torch_dtype="bfloat16", device_map="auto", attn_implementation="flash_attention_2")


inputs = processor(
    text=["a portrait of young girl. masterpiece, film grained, best quality.", "a dog running under the rain"],
    padding=True,
    return_tensors="pt",
    return_for_image_generation=True,
)
inputs = inputs.to(device="cuda:0", dtype=torch.bfloat16)

neg_prompt = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry."
neg_inputs = processor(text=[neg_prompt] * 2, return_tensors="pt").to(device="cuda:0")

image_sizes = inputs.pop("image_sizes")
HEIGHT, WIDTH = image_sizes[0]
VISUAL_TOKENS = model.vocabulary_mapping.image_tokens

def prefix_allowed_tokens_fn(batch_id, input_ids):
    height, width = HEIGHT, WIDTH
    visual_tokens = VISUAL_TOKENS
    image_wrapper_token_id = processor.tokenizer.encode("<|image token|>", return_tensors="pt")[0].to(model.device)
    eoi_token_id = processor.tokenizer.encode("<|image end|>", return_tensors="pt")[0]
    eos_token_id = processor.tokenizer.encode("<|extra_204|>", return_tensors="pt")[0]
    pad_token_id = processor.tokenizer.encode("<|endoftext|>", return_tensors="pt")[0]
    eol_token_id = processor.tokenizer.encode("<|extra_200|>", return_tensors="pt")[0]
    eof_token_id = processor.tokenizer.encode("<|extra_201|>", return_tensors="pt")[0]

    position = torch.nonzero(input_ids == image_wrapper_token_id, as_tuple=True)[0][0]
    offset = input_ids.shape[0] - position
    if offset % (width + 1) == 0:
        return (eol_token_id, )
    elif offset == (width + 1) * height + 1:
        return (eof_token_id, )
    elif offset == (width + 1) * height + 2:
        return (eoi_token_id, )
    elif offset == (width + 1) * height + 3:
        return (eos_token_id, )
    elif offset > (width + 1) * height + 3:
        return (pad_token_id, )
    else:
        return visual_tokens


out = model.generate(
    **inputs,
    max_new_tokens=50_000, # make sure to have enough tokens for one image
    prefix_allowed_tokens_fn=prefix_allowed_tokens_fn,
    return_dict_in_generate=True,
    negative_prompt_ids=neg_inputs.input_ids, # indicate for Classifier-Free Guidance
    negative_prompt_attention_mask=neg_inputs.attention_mask,
)

image = model.decode_image_tokens(out.sequences[:, inputs.input_ids.shape[1]: ], height=HEIGHT, width=WIDTH)
images = processor.postprocess(list(image.float()), return_tensors="PIL.Image.Image") # internally we convert to np but it's not supported in bf16 precision
for i, image in enumerate(images['pixel_values']):
    image.save(f"result{i}.png")

```


## Emu3Config

[[autodoc]] Emu3Config

## Emu3VQVAEConfig

[[autodoc]] Emu3VQVAEConfig

## Emu3Processor

[[autodoc]] Emu3Processor

## Emu3ImageProcessor

[[autodoc]] Emu3ImageProcessor
    - preprocess

## Emu3VQVAE

[[autodoc]] Emu3VQVAE
    - forward

## Emu3Model

[[autodoc]] Emu3Model
    - forward

## Emu3ForConditionalGeneration

[[autodoc]] Emu3ForConditionalGeneration
    - forward
