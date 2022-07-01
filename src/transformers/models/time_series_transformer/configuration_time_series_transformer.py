# coding=utf-8
# Copyright 2022 kashif and The HuggingFace Inc. team. All rights reserved.
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
""" TimeSeriesTransformer model configuration """
from typing import List, Optional

from gluonts.time_feature import TimeFeature, time_features_from_frequency_str, get_lags_for_frequency
from gluonts.torch.distributions import DistributionOutput, StudentTOutput

from ...configuration_utils import PretrainedConfig
from ...utils import logging


logger = logging.get_logger(__name__)

TIME_SERIES_TRANSFORMER_PRETRAINED_CONFIG_ARCHIVE_MAP = {
    "huggingface/tst-ett": "https://huggingface.co/huggingface/tst-ett/resolve/main/config.json",
    # See all TimeSeriesTransformer models at https://huggingface.co/models?filter=time_series_transformer
}


class TimeSeriesTransformerConfig(PretrainedConfig):
    r"""
    This is the configuration class to store the configuration of a [`~TimeSeriesTransformerModel`].
    It is used to instantiate an TimeSeriesTransformer model according to the specified arguments, defining the model
    architecture. Instantiating a configuration with the defaults will yield a similar configuration to that of
    the TimeSeriesTransformer [huggingface/tst-ett](https://huggingface.co/huggingface/tst-ett) architecture.

    Configuration objects inherit from  [`PretrainedConfig`] and can be used
    to control the model outputs. Read the documentation from  [`PretrainedConfig`]
    for more information.


    Args:
        prediction_length (`int`):
            The prediction horizon for the model.
        context_length (`int`, *optional*, default to `None`):
            The context length for the encoder. If  `None`, the context length will be the same as the prediction length.
        distr_output (`DistributionOutput` default to `StudentTOutput()`):
            The distribution emission head for the model.
        scaling (`bool` default to `True`):
            Whether to scale the input targets.
        freq (`str`, *optional* default to `None`):
            The frequency of the input time series. If `None`, the `lag_seq` and `time_features` must be provided.
        lags_seq (`list` of `int`, *optional* default to `None`):
            The lags of the input time series. Cannot be `None` if `freq` is `None`.
        time_features (`list` of `TimeFeature`, *optional* default to `None`):
            The time features transformations to apply to the input time series. Cannot be `None` if `freq` is `None`.
        num_feat_dynamic_real (`int`, *optional* default to `0`):
            The number of dynamic real valued features.
        num_feat_static_cat (`int`, *optional* default to `0`):
            The number of static categorical features.
        num_feat_static_real (`int`, *optional* default to `0`):
            The number of static real valued features.
        cardinality (`list` of `int`, *optional* default to `None`):
            The cardinality of the categorical features. Cannot be `None` if `num_feat_static_cat` is `> 0`.
        embedding_dimension (`list` of `int`, *optional* default to `None`):
            The dimension of the embedding for the categorical features. Cannot be `None` if `num_feat_static_cat` is `> 0`.
        encoder_layers (`int`, *optional*, defaults to 2):
            Number of encoder layers.
        decoder_layers (`int`, *optional*, defaults to 2):
            Number of decoder layers.
        nhead (`int`, *optional*, defaults to 2):
            Number of attention heads for each attention layer in the Transformer encoder and decoder.
        ffn_dim (`int`, *optional*, defaults to 32):
            Dimension of the "intermediate" (often named feed-forward) layer in encoder and decoder.
        activation_function (`str` or `function`, *optional*, defaults to `"gelu"`):
            The non-linear activation function (function or string) in the encoder and decoder. If string,
            `"gelu"` and `"relu"` are supported.
        dropout (`float`, *optional*, defaults to 0.1):
            The dropout probability for all fully connected layers in the encoder, and decoder.

        Example:

    ```python
    >>> from transformers import TimeSeriesTransformerModel, TimeSeriesTransformerConfig

    >>> # Initializing a TimeSeriesTransformer huggingface/tst-ett style configuration
    >>> configuration = TimeSeriesTransformerConfig()

    >>> # Initializing a model from the huggingface/tst-ett style configuration
    >>> model = TimeSeriesTransformerModel(configuration)

    >>> # Accessing the model configuration
    >>> configuration = model.config
    ```"""
    model_type = "time_series_transformer"

    def __init__(
        self,
        prediction_length,
        context_length: Optional[int] = None,
        freq: Optional[str] = None,
        distr_output: DistributionOutput = StudentTOutput(),
        lags_seq: Optional[List[int]] = None,
        time_features: Optional[List[TimeFeature]] = None,
        scaling: bool = True,
        num_feat_dynamic_real: int = 0,
        num_feat_static_cat: int = 0,
        num_feat_static_real: int = 0,
        cardinality: Optional[List[int]] = None,
        embedding_dimension: Optional[List[int]] = None,
        ffn_dim: int = 32,
        nhead: int = 2,
        encoder_layers: int = 2,
        decoder_layers: int = 2,
        is_encoder_decoder: bool = True,
        activation_function: str = "gelu",
        dropout: float = 0.1,
        init_std: float = 0.02,
        **kwargs
    ):
        self.context_length = context_length or prediction_length
        self.prediction_length = prediction_length
        self.distr_output = distr_output
        self.time_features = time_features or time_features_from_frequency_str(freq)
        self.lags_seq = lags_seq or get_lags_for_frequency(freq_str=freq)
        self.scaling = scaling
        self.num_feat_dynamic_real = num_feat_dynamic_real
        self.num_feat_static_cat = num_feat_static_cat
        self.num_feat_static_real = num_feat_static_real
        self.cardinality = cardinality if cardinality and num_feat_static_cat > 0 else [1]
        self.embedding_dimension = embedding_dimension

        # Transformer architecture parameters
        self.nhead = nhead
        self.encoder_layers = encoder_layers
        self.decoder_layers = decoder_layers
        self.ffn_dim = ffn_dim
        self.dropout = dropout
        self.activation_function = activation_function
        self.init_std = init_std

        super().__init__(is_encoder_decoder=is_encoder_decoder, **kwargs)
