# coding=utf-8
# Copyright 2024 The HuggingFace Inc. team.
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
"""Convert Sapiens checkpoints trained with the DINO method."""

import argparse
import json
from pathlib import Path

import requests
import torch
from huggingface_hub import hf_hub_download
from PIL import Image

from transformers import SapiensConfig, SapiensForSemanticSegmentation, SapiensImageProcessor
from transformers.utils import logging


logging.set_verbosity_info()
logger = logging.get_logger(__name__)


SEGMENTATIONS_LABEL_TO_ID = {
    "Background": 0,
    "Apparel": 1,
    "Face Neck": 2,
    "Hair": 3,
    "Left Foot": 4,
    "Left Hand": 5,
    "Left Lower Arm": 6,
    "Left Lower Leg": 7,
    "Left Shoe": 8,
    "Left Sock": 9,
    "Left Upper Arm": 10,
    "Left Upper Leg": 11,
    "Lower Clothing": 12,
    "Right Foot": 13,
    "Right Hand": 14,
    "Right Lower Arm": 15,
    "Right Lower Leg": 16,
    "Right Shoe": 17,
    "Right Sock": 18,
    "Right Upper Arm": 19,
    "Right Upper Leg": 20,
    "Torso": 21,
    "Upper Clothing": 22,
    "Lower Lip": 23,
    "Upper Lip": 24,
    "Lower Teeth": 25,
    "Upper Teeth": 26,
    "Tongue": 27,
}
SEGMENTATIONS_ID_TO_LABEL = {v: k for k, v in SEGMENTATIONS_LABEL_TO_ID.items()}


# here we list all keys to be renamed (original name on the left, our name on the right)
def create_rename_keys(config: SapiensConfig):
    rename_keys = []
    for i in range(config.num_hidden_layers):
        # encoder layers: attention, projection, 2 feedforward neural networks and 2 layernorms
        rename_keys.append((f"backbone.layers.{i}.attn.qkv.weight", f"model.encoder.layer.{i}.attention.attention.qkv.weight"))
        rename_keys.append((f"backbone.layers.{i}.attn.qkv.bias", f"model.encoder.layer.{i}.attention.attention.qkv.bias"))
        rename_keys.append((f"backbone.layers.{i}.attn.proj.weight", f"model.encoder.layer.{i}.attention.output.dense.weight"))
        rename_keys.append((f"backbone.layers.{i}.attn.proj.bias", f"model.encoder.layer.{i}.attention.output.dense.bias"))
        rename_keys.append((f"backbone.layers.{i}.ffn.layers.0.0.weight", f"model.encoder.layer.{i}.mlp.dense.weight"))
        rename_keys.append((f"backbone.layers.{i}.ffn.layers.0.0.bias", f"model.encoder.layer.{i}.mlp.dense.bias"))
        rename_keys.append((f"backbone.layers.{i}.ffn.layers.1.weight", f"model.encoder.layer.{i}.output.dense.weight"))
        rename_keys.append((f"backbone.layers.{i}.ffn.layers.1.bias", f"model.encoder.layer.{i}.output.dense.bias"))
        rename_keys.append((f"backbone.layers.{i}.ln1.weight", f"model.encoder.layer.{i}.layernorm_before.weight"))
        rename_keys.append((f"backbone.layers.{i}.ln1.bias", f"model.encoder.layer.{i}.layernorm_before.bias"))
        rename_keys.append((f"backbone.layers.{i}.ln2.weight", f"model.encoder.layer.{i}.layernorm_after.weight"))
        rename_keys.append((f"backbone.layers.{i}.ln2.bias", f"model.encoder.layer.{i}.layernorm_after.bias"))

    # embeddings
    rename_keys.extend(
        [
            ("backbone.pos_embed", "model.embeddings.position_embeddings"),
            ("backbone.patch_embed.projection.weight", "model.embeddings.patch_embeddings.projection.weight"),
            ("backbone.patch_embed.projection.bias", "model.embeddings.patch_embeddings.projection.bias"),
        ]
    )

    # backbone final layernorm
    rename_keys.extend(
        [
            ("backbone.ln1.weight", "model.layernorm.weight"),
            ("backbone.ln1.bias", "model.layernorm.bias"),
        ]
    )

    # head
    for i in range(len(config.deconv_out_channels)):
        rename_keys.append((f"decode_head.deconv_layers.{i * 3}.weight", f"head.deconv_layers.{i}.deconv.weight"))
    
    for i in range(len(config.conv_out_channels)):
        rename_keys.append((f"decode_head.conv_layers.{i * 3}.weight", f"head.conv_layers.{i}.conv.weight"))
        rename_keys.append((f"decode_head.conv_layers.{i * 3}.bias", f"head.conv_layers.{i}.conv.bias"))
    
    rename_keys.append((f"decode_head.conv_seg.weight", "head.final_conv.weight"))
    rename_keys.append((f"decode_head.conv_seg.bias", "head.final_conv.bias"))

    return rename_keys


# we split up the matrix of each encoder layer into queries, keys and values
def split_qkv_to_query_key_values_(state_dict):

    layer_names = [k for k in state_dict.keys() if ".qkv." in k]
    for layer_name in layer_names:
        query_key_values = state_dict.pop(layer_name)
        query, key, value = query_key_values.chunk(3, dim=0)
        state_dict[layer_name.replace(".qkv.", ".query.")] = query
        state_dict[layer_name.replace(".qkv.", ".key.")] = key
        state_dict[layer_name.replace(".qkv.", ".value.")] = value


def rename_key(dct, old, new):
    val = dct.pop(old)
    dct[new] = val


# We will verify our results on an image of cute cats
def prepare_img():
    url = "https://fashn-ai-sapiens-body-part-segmentation.hf.space/file=/tmp/gradio/62ef0655f51f630544d982d3e41050895dc66f87/idris_elba.jpg"
    im = Image.open(requests.get(url, stream=True).raw)
    return im


@torch.no_grad()
def convert_sapiens_checkpoint(model_name, checkpoints_dir, save_dir):
    """
    Copy/paste/tweak model's weights to our Sapiens structure.
    """

    all_params = {
        "segmentation-body-0.3b": {
            "config": {
                "num_labels": 28,
                "num_hidden_layers": 24,
                "hidden_size": 1024,
                "label2id": SEGMENTATIONS_LABEL_TO_ID,
                "id2label": SEGMENTATIONS_ID_TO_LABEL,
            },
            "checkpoint_local_path": "sapiens_host/seg/checkpoints/sapiens_0.3b/sapiens_0.3b_goliath_best_goliath_mIoU_7673_epoch_194.pth",
        },
        "segmentation-body-0.6b": {
            "config": {
                "num_labels": 28,
                "num_hidden_layers": 32,
                "hidden_size": 1280,
                "label2id": SEGMENTATIONS_LABEL_TO_ID,
                "id2label": SEGMENTATIONS_ID_TO_LABEL,
            },
            "checkpoint_local_path": "sapiens_host/seg/checkpoints/sapiens_0.6b/sapiens_0.6b_goliath_best_goliath_mIoU_7777_epoch_178.pth",
        },
        "segmentation-body-1b": {
            "config": {
                "num_labels": 28,
                "num_hidden_layers": 40,
                "hidden_size": 1536,
                "label2id": SEGMENTATIONS_LABEL_TO_ID,
                "id2label": SEGMENTATIONS_ID_TO_LABEL,
            },
            "checkpoint_local_path": "sapiens_host/seg/checkpoints/sapiens_1b/sapiens_1b_goliath_best_goliath_mIoU_7994_epoch_151.pth",
        },
        "segmentation-body-2b": {
            "config": {
                "num_labels": 28,
                "num_hidden_layers": 48,
                "hidden_size": 1920,
                "label2id": SEGMENTATIONS_LABEL_TO_ID,
                "id2label": SEGMENTATIONS_ID_TO_LABEL,
            },
            "checkpoint_local_path": "sapiens_host/seg/checkpoints/sapiens_2b/sapiens_2b_goliath_best_goliath_mIoU_8111_epoch_155.pth",
        },
        "segmentation-face-1b": {
            "config": {
                "num_labels": 19,
                "num_hidden_layers": 40,
                "hidden_size": 1536,
            },
            "checkpoint_local_path": "sapiens_host/seg/checkpoints/sapiens_1b/sapiens_1b_seg_face_epoch_200.pth",
        },
        "normal-estimation-0.3b": {
            "config": {
                "num_labels": 3,
                "num_hidden_layers": 24,
                "hidden_size": 1024,
                "patch_embeddings_padding": 2,
            },
            "checkpoint_local_path": "sapiens_host/normal/checkpoints/sapiens_0.3b/sapiens_0.3b_normal_render_people_epoch_66.pth",
        },
        "normal-estimation-0.6b": {
            "config": {
                "num_labels": 3,
                "num_hidden_layers": 32,
                "hidden_size": 1280,
                "patch_embeddings_padding": 2,
            },
            "checkpoint_local_path": "sapiens_host/normal/checkpoints/sapiens_0.6b/sapiens_0.6b_normal_render_people_epoch_200.pth",
        },
        "normal-estimation-1b": {
            "config": {
                "num_labels": 3,
                "num_hidden_layers": 40,
                "hidden_size": 1536,
                "patch_embeddings_padding": 2,
            },
            "checkpoint_local_path": "sapiens_host/normal/checkpoints/sapiens_1b/sapiens_1b_normal_render_people_epoch_115.pth",
        },
        "normal-estimation-2b": {
            "config": {
                "num_labels": 3,
                "num_hidden_layers": 48,
                "hidden_size": 1920,
                "patch_embeddings_padding": 2,
            },
            "checkpoint_local_path": "sapiens_host/normal/checkpoints/sapiens_2b/sapiens_2b_normal_render_people_epoch_70.pth",
        },
    }
    checkpoint_params = all_params[model_name]
    config_params = checkpoint_params["config"]
    config_params["intermediate_size"] = config_params["hidden_size"] * 4

    # define default Sapiens configuration
    config = SapiensConfig(**config_params)

    full_checkpoint_path = Path(checkpoints_dir) / checkpoint_params["checkpoint_local_path"]
    state_dict = torch.load(full_checkpoint_path, map_location="cpu", weights_only=True)["state_dict"]
    
    # rename state dict keys
    rename_keys = create_rename_keys(config)
    for src, dest in rename_keys:
        if src in state_dict:
            rename_key(state_dict, src, dest)
        else:
            print(f"Key {src} not found in the state dict.")

    # split qkv weights
    split_qkv_to_query_key_values_(state_dict)

    # load model and state dict
    model = SapiensForSemanticSegmentation(config).eval()
    model.load_state_dict(state_dict)

    # Check outputs on an image, prepared by SapiensImageProcessor
    image_processor = SapiensImageProcessor(
        do_resize=True,
        size={"height": config.image_size[0], "width": config.image_size[1]},
        do_rescale=False,
        rescale_factor=1,
        do_normalize=True,
        image_mean=[123.675, 116.28, 103.53],
        image_std=[58.395, 57.12, 57.375],
    )
    inputs = image_processor(images=prepare_img(), return_tensors="pt")

    # TODO: logits check
    # with torch.no_grad():
    #     outputs = model(**inputs)

    model_save_dir = Path(save_dir) / f"sapiens-{model_name}-hf"
    model_save_dir.mkdir(exist_ok=True, parents=True)

    print(f"Saving model {model_name} to {model_save_dir}")
    model.save_pretrained(model_save_dir)

    print(f"Saving image processor to {model_save_dir}")
    image_processor.save_pretrained(model_save_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # Required parameters
    parser.add_argument(
        "--model_name",
        default="normal-estimation-0.3b",
        type=str,
        help="Name of the model trained with DINO you'd like to convert.",
    )
    parser.add_argument(
        "--checkpoints_dir",
        default="/home/ubuntu/projects/sapiens/sapiens_host/",
        type=str,
        help="Path to the directory containing the Sapiens checkpoints.",
    )
    parser.add_argument(
        "--save_dir",
        default="converted_hf_models/",
        type=str,
        help="Path to the directory where the converted model will be saved.",
    )

    args = parser.parse_args()
    convert_sapiens_checkpoint(args.model_name, args.checkpoints_dir, args.save_dir)
