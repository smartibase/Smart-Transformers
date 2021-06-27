# coding=utf-8
# Copyright 2020 The Allen Institute for AI team and The HuggingFace Inc. team.
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
""" Longformer configuration """

from typing import List, Union

from ...onnx import OnnxConfig
from ...utils import logging
from ..roberta.configuration_roberta import RobertaConfig


logger = logging.get_logger(__name__)

LONGFORMER_PRETRAINED_CONFIG_ARCHIVE_MAP = {
    "allenai/longformer-base-4096": "https://huggingface.co/allenai/longformer-base-4096/resolve/main/config.json",
    "allenai/longformer-large-4096": "https://huggingface.co/allenai/longformer-large-4096/resolve/main/config.json",
    "allenai/longformer-large-4096-finetuned-triviaqa": "https://huggingface.co/allenai/longformer-large-4096-finetuned-triviaqa/resolve/main/config.json",
    "allenai/longformer-base-4096-extra.pos.embd.only": "https://huggingface.co/allenai/longformer-base-4096-extra.pos.embd.only/resolve/main/config.json",
    "allenai/longformer-large-4096-extra.pos.embd.only": "https://huggingface.co/allenai/longformer-large-4096-extra.pos.embd.only/resolve/main/config.json",
}


class LongformerConfig(RobertaConfig):
    r"""
    This is the configuration class to store the configuration of a :class:`~transformers.LongformerModel` or a
    :class:`~transformers.TFLongformerModel`. It is used to instantiate a Longformer model according to the specified
    arguments, defining the model architecture.

    This is the configuration class to store the configuration of a :class:`~transformers.LongformerModel`. It is used
    to instantiate an Longformer model according to the specified arguments, defining the model architecture.
    Instantiating a configuration with the defaults will yield a similar configuration to that of the RoBERTa
    `roberta-base <https://huggingface.co/roberta-base>`__ architecture with a sequence length 4,096.

    The :class:`~transformers.LongformerConfig` class directly inherits :class:`~transformers.RobertaConfig`. It reuses
    the same defaults. Please check the parent class for more information.

    Args:
        attention_window (:obj:`int` or :obj:`List[int]`, `optional`, defaults to 512):
            Size of an attention window around each token. If an :obj:`int`, use the same size for all layers. To
            specify a different window size for each layer, use a :obj:`List[int]` where ``len(attention_window) ==
            num_hidden_layers``.

    Example::

        >>> from transformers import LongformerConfig, LongformerModel

        >>> # Initializing a Longformer configuration
        >>> configuration = LongformerConfig()

        >>> # Initializing a model from the configuration
        >>> model = LongformerModel(configuration)

        >>> # Accessing the model configuration
        >>> configuration = model.config
    """
    model_type = "longformer"

    def __init__(self, attention_window: Union[List[int], int] = 512, sep_token_id: int = 2, **kwargs):
        super().__init__(sep_token_id=sep_token_id, **kwargs)
        self.attention_window = attention_window

# LONGFORMER_ONNX_CONFIG = OnnxConfig(
#     inputs=[
#         OnnxVariable("input_ids", {0: "batch", 1: "sequence"}, repeated=1, value=None),
#         OnnxVariable("attention_mask", {0: "batch", 1: "sequence"}, repeated=1, value=None),
#     ],
#     outputs=[
#         OnnxVariable("last_hidden_state", {0: "batch", 1: "sequence"}, repeated=1, value=None),
#         OnnxVariable("pooler_output", {0: "batch"}, repeated=1, value=None),
#     ],
#     runtime_config_overrides=None,
#     use_external_data_format=False,
#     minimum_required_onnx_opset=12,
#     optimizer="bert",
#     optimizer_features={
#         "enable_gelu": True,
#         "enable_layer_norm": True,
#         "enable_attention": True,
#         "enable_skip_layer_norm": True,
#         "enable_embed_layer_norm": True,
#         "enable_bias_skip_layer_norm": True,
#         "enable_bias_gelu": True,
#         "enable_gelu_approximation": False,
#     },
#     optimizer_additional_args={"num_heads": "$config.num_attention_heads", "hidden_size": "$config.hidden_size"},
# )
