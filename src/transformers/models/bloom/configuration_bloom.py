# coding=utf-8
# Copyright 2018 The OpenAI Team Authors and HuggingFace Inc. team.
# Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
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
""" Bloom configuration"""
from ...configuration_utils import PretrainedConfig
from ...utils import logging


logger = logging.get_logger(__name__)

BLOOM_PRETRAINED_CONFIG_ARCHIVE_MAP = {
    "bigscience/Bloom": "https://huggingface.co/bigscience/bloom/resolve/main/config.json",
}
BLOOM_PRETRAINED_CONFIG_ARCHIVE_MAP = {}


class BloomConfig(PretrainedConfig):
    """
    This is the configuration class to store the configuration of a [`BloomModel`]. It is used to instantiate a GPT-2
    model according to the specified arguments, defining the model architecture. Instantiating a configuration with the
    defaults will yield a similar configuration to the Bloom architecture
    [bigscience/bloom](https://huggingface.co/bigscience/bloom).

    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information.


    Args:
        vocab_size (`int`, *optional*, defaults to 50257):
            Vocabulary size of the GPT-2 model. Defines the number of different tokens that can be represented by the
            `inputs_ids` passed when calling [`BloomModel`].
        seq_length (`int`, *optional*, defaults to 1024):
            The maximum sequence length that this model might ever be used with. Typically set this to something large
            just in case (e.g., 512 or 1024 or 2048).
        offset_alibi (`int`, *optional*, defaults to 100):
            The padding added to the alibi positional embeddings to deal with cached input
        hidden_size (`int`, *optional*, defaults to 768):
            Dimensionality of the embeddings and hidden states.
        n_layer (`int`, *optional*, defaults to 12):
            Number of hidden layers in the Transformer encoder.
        n_head (`int`, *optional*, defaults to 12):
            Number of attention heads for each attention layer in the Transformer encoder.
        n_inner (`int`, *optional*, defaults to None):
            Dimensionality of the inner feed-forward layers. `None` will set it to 4 times hidden_size
        activation_function (`str`, *optional*, defaults to `"gelu"`):
            Activation function, to be selected in the list `["relu", "silu", "gelu", "tanh", "gelu_new"]`.
        resid_pdrop (`float`, *optional*, defaults to 0.1):
            The dropout probability for all fully connected layers in the embeddings, encoder, and pooler.
        embd_pdrop (`int`, *optional*, defaults to 0.1):
            The dropout ratio for the embeddings.
        attn_pdrop (`float`, *optional*, defaults to 0.1):
            The dropout ratio for the attention.
        layer_norm_epsilon (`float`, *optional*, defaults to 1e-5):
            The epsilon to use in the layer normalization layers.
        initializer_range (`float`, *optional*, defaults to 0.02):
            The standard deviation of the truncated_normal_initializer for initializing all weight matrices.
        apply_residual_connection_post_layernorm (`bool`, *optional*, defaults to `False`):
            If enabled, use the layer norm of the hidden states as the residual in the transformer blocks
        bias_dropout_fusion (`bool`, *optional*, defaults to `True`):
            If enabled, apply dropout when adding the attention output together with the attention bias in the
            transformer blocks
        skip_bias_add (`bool`, *optional*, defaults to `True`):
            If set to `True`, it will skip bias add for each linear layer in the transformer blocks
        skip_bias_add_qkv (`bool`, *optional*, defaults to `False`):
            If set to `True`, it will skip bias add for the first linear layer in the transformer blocks
        attention_softmax_in_fp32 (`bool`, *optional*, defaults to `True`):
            If set to `True` and the `dtype` is set to `float16` it will scale the input of the Softmax function to
            `fp32`
        hidden_dropout (`float`, *optional*, defaults to 0.1):
            Dropout rate of the dropout function in `bias_dropout_fusion`
        attention_dropout (`float`, *optional*, defaults to 0.1):
            Dropout rate applied to the attention probs
        scale_attn_weights (`bool`, *optional*, defaults to `True`):
            Scale attention weights by dividing by sqrt(hidden_size)..
        use_cache (`bool`, *optional*, defaults to `True`):
            Whether or not the model should return the last key/values attentions (not used by all models).
        scale_attn_by_inverse_layer_idx (`bool`, *optional*, defaults to `False`):
            Whether to additionally scale attention weights by `1 / layer_idx + 1`.
        reorder_and_upcast_attn (`bool`, *optional*, defaults to `False`):
            Whether to scale keys (K) prior to computing attention (dot-product) and upcast attention
            dot-product/softmax to float() when training with mixed precision.

    Example:

    ```python
    >>> from transformers import BloomModel, BloomConfig

    >>> # Initializing a Bloom configuration
    >>> configuration = BloomConfig()

    >>> # Initializing a model from the configuration
    >>> model = BloomModel(configuration)

    >>> # Accessing the model configuration
    >>> configuration = model.config
    ```"""

    model_type = "bloom"
    keys_to_ignore_at_inference = ["past_key_values"]
    attribute_map = {
        "max_position_embeddings": "seq_length",
        "num_hidden_layers": "n_layer",
        "n_head": "num_attention_heads",
        "hidden_size": "n_embed",
    }

    def __init__(
        self,
        vocab_size=250880,
        seq_length=20,  # TODO remove it in the future
        offset_alibi=100,
        hidden_size=64,  # 1024,
        n_layer=2,  # 24,
        n_head=8,  # 16,
        n_inner=None,
        masked_softmax_fusion=True,
        layer_norm_epsilon=1e-5,  # TODO
        initializer_range=0.02,  # TODO
        use_cache=False,  # TODO
        bos_token_id=50256,  # TODO
        eos_token_id=50256,  # TODO
        apply_residual_connection_post_layernorm=False,
        bias_dropout_fusion=True,
        skip_bias_add=True,
        skip_bias_add_qkv=False,
        hidden_dropout=0.0,
        attention_dropout=0.0,
        attention_softmax_in_fp32=True,
        pretraining_tp=1,  # TODO
        pretraining_pp=1,  # TODO
        dtype="bfloat16",
        **kwargs,
    ):
        self.vocab_size = vocab_size
        self.seq_length = seq_length
        self.hidden_size = hidden_size
        self.n_layer = n_layer
        self.n_head = n_head
        self.n_inner = n_inner
        self.masked_softmax_fusion = masked_softmax_fusion
        self.layer_norm_epsilon = layer_norm_epsilon
        self.initializer_range = initializer_range
        self.use_cache = use_cache
        self.pretraining_tp = pretraining_tp
        self.pretraining_pp = pretraining_pp
        self.apply_residual_connection_post_layernorm = apply_residual_connection_post_layernorm
        self.bias_dropout_fusion = bias_dropout_fusion
        self.hidden_dropout = hidden_dropout
        self.skip_bias_add = skip_bias_add
        self.skip_bias_add_qkv = skip_bias_add_qkv
        self.attention_dropout = attention_dropout
        self.attention_softmax_in_fp32 = attention_softmax_in_fp32
        self.offset_alibi = offset_alibi

        self.bos_token_id = bos_token_id
        self.eos_token_id = eos_token_id
        self.dtype = dtype

        super().__init__(bos_token_id=bos_token_id, eos_token_id=eos_token_id, **kwargs)
