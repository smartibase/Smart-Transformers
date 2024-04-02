# coding=utf-8
# Copyright 2024 Meta and The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Convert Hiera checkpoints trained with the DINO method."""


import argparse
import json

import requests
import torch
from huggingface_hub import hf_hub_download
from PIL import Image
from torchvision import transforms

from transformers import BitImageProcessor, HieraConfig, HieraForImageClassification, HieraModel
from transformers.utils import logging


logging.set_verbosity_info()
logger = logging.get_logger(__name__)


# here we list all keys to be renamed (original name on the left, our name on the right)
def create_rename_keys(config, base_model=False):
    rename_keys = []
    # fmt: off
    num_stages = len(config.depths)
    # embedding dimensions for input and stages
    dims = [config.embed_dim] + [int(config.embed_dim * config.embed_dim_multiplier**i) for i in range(num_stages)]

    global_layer_idx = 0
    for stage_idx in range(num_stages):
        dim_in = dims[stage_idx]
        dim_out = dims[stage_idx + 1]
        for layer_idx in range(config.depths[stage_idx]):
            rename_keys.append((f"blocks.{global_layer_idx}.norm1.weight", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.layernorm_before.weight"))
            rename_keys.append((f"blocks.{global_layer_idx}.norm1.bias", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.layernorm_before.bias"))
            rename_keys.append((f"blocks.{global_layer_idx}.attn.qkv.weight", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.attn.qkv.weight"))
            rename_keys.append((f"blocks.{global_layer_idx}.attn.qkv.bias", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.attn.qkv.bias"))
            rename_keys.append((f"blocks.{global_layer_idx}.attn.proj.weight", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.attn.proj.weight"))
            rename_keys.append((f"blocks.{global_layer_idx}.attn.proj.bias", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.attn.proj.bias"))
            rename_keys.append((f"blocks.{global_layer_idx}.norm2.weight", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.layernorm_after.weight"))
            rename_keys.append((f"blocks.{global_layer_idx}.norm2.bias", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.layernorm_after.bias"))
            rename_keys.append((f"blocks.{global_layer_idx}.mlp.fc1.weight", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.mlp.fc1.weight"))
            rename_keys.append((f"blocks.{global_layer_idx}.mlp.fc1.bias", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.mlp.fc1.bias"))
            rename_keys.append((f"blocks.{global_layer_idx}.mlp.fc2.weight", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.mlp.fc2.weight"))
            rename_keys.append((f"blocks.{global_layer_idx}.mlp.fc2.bias", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.mlp.fc2.bias"))

            # projection layer only for the first layer of each stage boundary (except the first stage)
            if dim_out != dim_in and layer_idx == 0:
                rename_keys.append((f"blocks.{global_layer_idx}.proj.weight", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.proj.weight"))
                rename_keys.append((f"blocks.{global_layer_idx}.proj.bias", f"hiera.encoder.stages.{stage_idx}.layers.{layer_idx}.proj.bias"))

            global_layer_idx += 1

    # projection layer + position embeddings
    rename_keys.extend(
        [
            ("patch_embed.proj.weight", "hiera.embeddings.patch_embeddings.projection.weight"),
            ("patch_embed.proj.bias", "hiera.embeddings.patch_embeddings.projection.bias")
        ]
    )

    if config.sep_pos_embed:
        rename_keys.extend(
            [
                ("pos_embed_spatial", "hiera.embeddings.position_embeddings_spatial"),
                ("pos_embed_temporal", "hiera.embeddings.position_embeddings_temporal")
            ]
        )
    else:
        rename_keys.append(("pos_embed", "hiera.embeddings.position_embeddings"))

    if base_model:
        # layernorm + pooler
        rename_keys.extend([("norm.weight", "pooler.layernorm.weight"), ("norm.bias", "pooler.layernorm.bias")])

        # if just the base model, we should remove "hiera" from all keys that start with "hiera"
        rename_keys = [(pair[0], pair[1][6:]) if pair[1].startswith("hiera") else pair for pair in rename_keys]
    else:
        # layernorm + classification head
        rename_keys.extend(
            [
                ("norm.weight", "hiera.pooler.layernorm.weight"),
                ("norm.bias", "hiera.pooler.layernorm.bias"),
                ("head.projection.weight", "classifier.weight"),
                ("head.projection.bias", "classifier.bias"),
            ]
        )
    # fmt: on
    return rename_keys


def remove_classification_head_(state_dict):
    ignore_keys = ["head.projection.weight", "head.projection.bias"]
    for k in ignore_keys:
        state_dict.pop(k, None)


def rename_key(dct, old, new):
    val = dct.pop(old)
    dct[new] = val


# We will verify our results on an image of cute cats
def prepare_img():
    url = "http://images.cocodataset.org/val2017/000000039769.jpg"
    im = Image.open(requests.get(url, stream=True).raw)
    return im


def get_hiera_config(model_name: str, base_model: bool) -> HieraConfig:
    if model_name == "hiera-tiny-224":
        config = HieraConfig(depths=[1, 2, 7, 2])
    elif model_name == "hiera-small-224":
        HieraConfig(depths=[1, 2, 11, 2])
    elif model_name == "hiera-base-224":
        config = HieraConfig()
    elif model_name == "hiera-base-plus-224":
        config = HieraConfig(embed_dim=112, initial_num_heads=2)
    elif model_name == "hiera-large-224":
        config = HieraConfig(embed_dim=144, initial_num_heads=2, depths=[2, 6, 36, 4])
    elif model_name == "hiera-huge-224":
        config = HieraConfig(embed_dim=256, initial_num_heads=4, depths=[2, 6, 36, 4])
    elif model_name == "hiera-base-16x224":
        config = HieraConfig(
            input_size=(16, 224, 224),
            query_stride=(1, 2, 2),
            masked_unit_size=(1, 8, 8),
            patch_kernel=(3, 7, 7),
            patch_stride=(2, 4, 4),
            patch_padding=(1, 3, 3),
            sep_pos_embed=True,
        )
    elif model_name == "hiera-base-plus-16x224":
        config = HieraConfig(
            input_size=(16, 224, 224),
            query_stride=(1, 2, 2),
            masked_unit_size=(1, 8, 8),
            patch_kernel=(3, 7, 7),
            patch_stride=(2, 4, 4),
            patch_padding=(1, 3, 3),
            sep_pos_embed=True,
            embed_dim=112,
            initial_num_heads=2,
        )
    elif model_name == "hiera-large-16x224":
        config = HieraConfig(
            input_size=(16, 224, 224),
            query_stride=(1, 2, 2),
            masked_unit_size=(1, 8, 8),
            patch_kernel=(3, 7, 7),
            patch_stride=(2, 4, 4),
            patch_padding=(1, 3, 3),
            sep_pos_embed=True,
            embed_dim=144,
            initial_num_heads=2,
            depths=[2, 6, 36, 4],
        )
    elif model_name == "hiera-huge-16x224":
        config = HieraConfig(
            input_size=(16, 224, 224),
            query_stride=(1, 2, 2),
            masked_unit_size=(1, 8, 8),
            patch_kernel=(3, 7, 7),
            patch_stride=(2, 4, 4),
            patch_padding=(1, 3, 3),
            sep_pos_embed=True,
            embed_dim=256,
            initial_num_heads=4,
            depths=[2, 6, 36, 4],
        )
    else:
        raise ValueError(f"Unrecognized model name: {model_name}")

    repo_id = "huggingface/label-files"

    if not model_name.endswith("16x224") and not base_model:
        filename = "imagenet-1k-id2label.json"
        id2label = json.load(open(hf_hub_download(repo_id, filename, repo_type="dataset"), "r"))
        id2label = {int(k): v for k, v in id2label.items()}
        config.id2label = id2label
        config.label2id = {v: k for k, v in id2label.items()}
        config.num_labels = len(id2label)

    if model_name.endswith("16x224") and not base_model:
        filename = "kinetics400-id2label.json"
        id2label = json.load(open(hf_hub_download(repo_id, filename, repo_type="dataset"), "r"))
        id2label = {int(k): v for k, v in id2label.items()}
        config.id2label = id2label
        config.label2id = {v: k for k, v in id2label.items()}
        config.num_labels = len(id2label)

        config.num_labels = 400

    return config


@torch.no_grad()
def convert_hiera_checkpoint(args):
    model_name = args.model_name
    base_model = args.base_model
    pytorch_dump_folder_path = args.pytorch_dump_folder_path
    verify_logits = args.verify_logits
    verify_pixel_values = args.verify_pixel_values
    push_to_hub = args.push_to_hub
    IMAGENET_DEFAULT_MEAN = [0.485, 0.456, 0.406]
    IMAGENET_DEFAULT_STD = [0.229, 0.224, 0.225]

    config = get_hiera_config(model_name, base_model)

    # Load original hiera model
    original_model = torch.hub.load(
        "facebookresearch/hiera",
        model=model_name.replace("-", "_"),
        pretrained=True,
        checkpoint="mae_in1k_ft_in1k" if not base_model else "mae_in1k",
    )

    original_model.eval()
    original_state_dict = original_model.state_dict()
    if base_model:
        remove_classification_head_(original_state_dict)

    # # Rename keys
    new_state_dict = original_state_dict.copy()
    rename_keys = create_rename_keys(config, base_model)

    for src, dest in rename_keys:
        rename_key(new_state_dict, src, dest)

    # Load HF hiera model
    model = HieraModel(config) if base_model else HieraForImageClassification(config)
    model.eval()

    missing_keys, unexpected_keys = model.load_state_dict(new_state_dict, strict=False)
    print("Missing keys:", missing_keys)
    print("Unexpected keys:", unexpected_keys)

    input_image = prepare_img()

    if model_name.endswith("16x224"):
        original_image_preprocessor = None
    else:
        original_image_preprocessor = transforms.Compose(
            [
                transforms.Resize(
                    int((256 / 224) * 224), interpolation=transforms.functional.InterpolationMode.BICUBIC
                ),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_DEFAULT_MEAN, IMAGENET_DEFAULT_STD),
            ]
        )

    image_processor = BitImageProcessor(
        image_mean=IMAGENET_DEFAULT_MEAN, image_std=IMAGENET_DEFAULT_STD, size={"shortest_edge": 256}
    )
    inputs = image_processor(images=input_image, return_tensors="pt")

    expected_pixel_values = original_image_preprocessor(input_image).unsqueeze(0)

    if verify_pixel_values:
        input_image = prepare_img()

        inputs = image_processor(images=input_image, return_tensors="pt")
        expected_pixel_values = original_image_preprocessor(input_image).unsqueeze(0)
        assert torch.allclose(inputs.pixel_values, expected_pixel_values, atol=1e-4)
        print("Pixel values look good!")
        print(f"{inputs.pixel_values[0, :3, :3, :3]=}")
    else:
        print("Converted without verifying pixel values")
        inputs = {"pixel_values": torch.rand((1, 3, 224, 224))}
        expected_pixel_values = inputs["pixel_values"]

    outputs = model(**inputs)
    # original implementation returns logits.softmax(dim=-1)
    expected_prob, expected_intermediates = original_model(expected_pixel_values, return_intermediates=True)

    if verify_logits:
        if not base_model:
            assert torch.allclose(outputs.logits.softmax(dim=-1), expected_prob, atol=1e-4)
            print("Logits look good!")
            print(f"{outputs.logits[:, :5]=}")
        else:
            expected_last_hidden = expected_intermediates[-1]
            batch_size, _, _, hidden_dim = expected_last_hidden.shape
            expected_last_hidden = expected_last_hidden.reshape(batch_size, -1, hidden_dim)
            assert torch.allclose(outputs.last_hidden_state, expected_last_hidden, atol=1e-4)
            print("Logits look good!")
            print(f"{outputs.last_hidden_state[0, :3, :3]=}")
    else:
        print("Converted without verifying logits")

    if pytorch_dump_folder_path is not None:
        print(f"Saving model and processor for {model_name} to {pytorch_dump_folder_path}")
        model.save_pretrained(pytorch_dump_folder_path)
        image_processor.save_pretrained(pytorch_dump_folder_path)

    if push_to_hub:
        print(f"Pushing model and processor for {model_name} to hub")
        hub_name = model_name
        if not base_model:
            hub_name = f"{model_name}-k400" if model_name.endswith("16x224") else f"{model_name}-in1k"
        model.push_to_hub(f"EduardoPacheco/{hub_name}")
        image_processor.push_to_hub(f"EduardoPacheco/{hub_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Required parameters
    parser.add_argument(
        "--model-name",
        default="hiera-tiny-224",
        type=str,
        choices=[
            "hiera-tiny-224",
            "hiera-small-224",
            "hiera-base-224",
            "hiera-base-plus-224",
            "hiera-large-224",
            "hiera-huge-224",
            "hiera-base-16x224",
            "hiera-base-plus-16x224",
            "hiera-large-16x224",
            "hiera-huge-16x224",
        ],
        help="Name of the Hiera model you'd like to convert.",
    )
    parser.add_argument(
        "--pytorch-dump-folder_path", default=None, type=str, help="Path to the output PyTorch model directory."
    )
    parser.add_argument(
        "--verify-logits",
        action="store_true",
        help="Whether or not to verify the logits against the original implementation.",
    )
    parser.add_argument(
        "--push-to-hub", action="store_true", help="Whether or not to push the converted model to the 🤗 hub."
    )
    parser.add_argument(
        "--base-model",
        action="store_true",
        help="Whether to only convert the base model (no projection head weights).",
    )
    parser.add_argument(
        "--verify-pixel-values",
        action="store_true",
        help="Whether to verify the pixel values of the input image.",
    )

    args = parser.parse_args()
    convert_hiera_checkpoint(args)
