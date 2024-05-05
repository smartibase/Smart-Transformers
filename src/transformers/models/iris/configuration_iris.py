# coding=utf-8
# Copyright 2024 The HuggingFace Team and The HuggingFace Inc. team. All rights reserved.
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
""" IRIS model configuration"""

from ...configuration_utils import PretrainedConfig
from ...utils import logging


logger = logging.get_logger(__name__)


from ..deprecated._archive_maps import DECISION_TRANSFORMER_PRETRAINED_CONFIG_ARCHIVE_MAP  # noqa: F401, E402

#Common attributes present in all config classes are: hidden_size, num_attention_heads, and num_hidden_layers. Text models further implement: vocab_size.

class IrisConfig(PretrainedConfig):
    """
    This is the configuration class to store the configuration of a [`IrisModel`]. It is used to
    instantiate a IRIS model according to the specified arguments, defining the model architecture.
    Instantiating a configuration with the defaults will yield a similar configuration to that of the standard
    Iris architecture. Many of the config options are used to instatiate the GPT2 model that is used as
    part of the architecture.

    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information.


    Args:
        state_dim (`int`, *optional*, defaults to 17):
            The state size for the RL environment
        act_dim (`int`, *optional*, defaults to 4):
            The size of the output action space
        hidden_size (`int`, *optional*, defaults to 128):
            The size of the hidden layers
        max_ep_len (`int`, *optional*, defaults to 4096):
            The maximum length of an episode in the environment
        action_tanh (`bool`, *optional*, defaults to True):
            Whether to use a tanh activation on action prediction
        vocab_size (`int`, *optional*, defaults to 50257):
            Vocabulary size of the GPT-2 model. Defines the number of different tokens that can be represented by the
            `inputs_ids` passed when calling [`IrisModel`].
        n_positions (`int`, *optional*, defaults to 1024):
            The maximum sequence length that this model might ever be used with. Typically set this to something large
            just in case (e.g., 512 or 1024 or 2048).
        n_layer (`int`, *optional*, defaults to 3):
            Number of hidden layers in the Transformer encoder.
        n_head (`int`, *optional*, defaults to 1):
            Number of attention heads for each attention layer in the Transformer encoder.
        n_inner (`int`, *optional*):
            Dimensionality of the inner feed-forward layers. If unset, will default to 4 times `n_embd`.
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
    >>> from transformers import IrisConfig, IrisModel

    >>> # Initializing a Iris configuration
    >>> configuration = IrisConfig()

    >>> # Initializing a model (with random weights) from the configuration
    >>> model = IrisModel(configuration)

    >>> # Accessing the model configuration
    >>> configuration = model.config
    ```"""

    model_type = "iris"
    keys_to_ignore_at_inference = ["past_key_values"]
    attribute_map = {
        "max_position_embeddings": "n_positions",
        "num_attention_heads": "n_head",
        "num_hidden_layers": "n_layer",
    }
    #TO DO
    # vocab_size: 512
    # embed_dim_tokenizer: 512
    #     resolution: 64
    #     in_channels: 3
    #     z_channels: 512
    #     ch: 64
    #     ch_mult: [1, 1, 1, 1, 1]
    #     num_res_blocks: 2
    #     attn_resolutions: [8, 16]
    #     out_ch: 3
    #     dropout: 0.0

    # use_original_obs: False
    # max_ram_usage: 30G
    # name: train_dataset
    # max_num_episodes: null
    # name: test_dataset



    # tokens_per_block: 17
    # max_blocks: 20
    # attention: 'causal'
    # num_layers: 10
    # num_heads: 4
    # embed_dim_world_models: 256
    # embed_pdrop: 0.1
    # resid_pdrop: 0.1
    # attn_pdrop: 0.1




    # epochs: 600
    # device: cuda:0
    # do_checkpoint: True
    # seed: 0
    # resume: False # set by resume.sh script only.


    # should: True
    # learning_rate: 0.0001
    #     batch_num_samples_tokenizer: 128
    #     grad_acc_steps_tokenizer: 1
    #     max_grad_norm_tokenizer: 10.0
    #     start_after_epochs_tokenizer: 25
    #     steps_per_epoch_tokenizer: 200
        
    #     batch_num_samples_world_model: 32
    #     grad_acc_steps_world_model: 1
    #     max_grad_norm_world_model: 10.0
    #     weight_decay: 0.01
    #     start_after_epochs_world_model: 25
    #     steps_per_epoch_world_model: 200
    
    #     batch_num_samples_actor_critic: 32
    #     grad_acc_steps_actor_critic: 1
    #     max_grad_norm_actor_critic: 10.0
    #     start_after_epochs_actor_critic: 50
    #     steps_per_epoch_actor_critc: 200
    #     burn_in: 20
    #     gamma: 0.995
    #     lambda_: 0.95
    #     entropy_weight: 0.001

    #     save_reconstructions: True

    # action dim as keyword arg for different envs
    def __init__(
        self,
        state_dim=17,
        act_dim=4,
        hidden_size=128,
        max_ep_len=4096,
        action_tanh=True,
        vocab_size=1,
        n_positions=1024,
        n_layer=3,
        n_head=1,
        n_inner=None,
        activation_function="relu",
        resid_pdrop=0.1,
        embd_pdrop=0.1,
        attn_pdrop=0.1,
        layer_norm_epsilon=1e-5,
        initializer_range=0.02,
        scale_attn_weights=True,
        use_cache=True,
        bos_token_id=50256,
        eos_token_id=50256,
        scale_attn_by_inverse_layer_idx=False,
        reorder_and_upcast_attn=False,
        **kwargs,
    ):
        self.state_dim = state_dim
        self.num_actions = act_dim
        self.hidden_size = hidden_size
        self.max_ep_len = max_ep_len
        self.action_tanh = action_tanh
        self.vocab_size = vocab_size
        self.n_positions = n_positions
        self.n_layer = n_layer
        self.n_head = n_head
        self.n_inner = n_inner
        self.activation_function = activation_function
        self.resid_pdrop = resid_pdrop
        self.embd_pdrop = embd_pdrop
        self.attn_pdrop = attn_pdrop
        self.layer_norm_epsilon = layer_norm_epsilon
        self.initializer_range = initializer_range
        self.scale_attn_weights = scale_attn_weights
        self.use_cache = use_cache
        self.scale_attn_by_inverse_layer_idx = scale_attn_by_inverse_layer_idx
        self.reorder_and_upcast_attn = reorder_and_upcast_attn

        self.bos_token_id = bos_token_id
        self.eos_token_id = eos_token_id

        super().__init__(bos_token_id=bos_token_id, eos_token_id=eos_token_id, **kwargs)