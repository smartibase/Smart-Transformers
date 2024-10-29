# coding=utf-8
# Copyright 2024 Google TimesFM Authors and HuggingFace Inc. team.
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

import inspect
import unittest
from typing import List

import numpy as np
import torch

from transformers import TimesFMConfig, is_torch_available
from transformers.testing_utils import (
    require_torch,
    torch_device,
)
from transformers.utils import is_torch_fx_available

# from ...generation.test_utils import GenerationTesterMixin
# define our own GenerationTesters
from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin


# from ...test_pipeline_mixin import PipelineTesterMixin


if is_torch_fx_available():
    pass


if is_torch_available():

    from transformers import (
        TimesFMModel,
    )


class TimesFMModelTester:
    def __init__(
        self,
        parent,
        patch_len: int = 32,
        context_len: int = 512,
        horizon_len: int = 128,
        freq_size: int = 3,
        num_layers: int = 20,
        model_dim: int = 1280,
        head_dim: int = 80,
        num_heads: int = 16,
        dropout_rate: float = 0.1,
        tolerance: float = 1e-6,
        rms_norm_eps: float = 1e-6,
        quantiles: List[float] = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        pad_val: float = 1123581321.0,
        use_positional_embedding: bool = True,
        per_core_batch_size: int = 32,
        initializer_factor: float = 1.0,
        is_training: bool = False,
    ):
        self.parent = parent
        self.patch_len = patch_len
        self.context_len = context_len
        self.horizon_len = horizon_len
        self.quantiles = quantiles
        self.pad_val = pad_val
        self.freq_size = freq_size
        self.model_dim = model_dim
        self.head_dim = head_dim
        self.num_hidden_layers = num_layers
        self.num_attention_heads = num_heads
        self.dropout_rate = dropout_rate
        self.tolerance = tolerance
        self.rms_norm_eps = rms_norm_eps
        self.use_positional_embedding = use_positional_embedding
        self.per_core_batch_size = per_core_batch_size
        self.initializer_factor = initializer_factor
        self.is_training = is_training

    def get_large_model_config(self):
        return TimesFMConfig.from_pretrained("google/timesfm-1.0-200m-pytorch")

    def get_config(self):
        return TimesFMConfig(
            patch_len=self.patch_len,
            context_len=self.context_len,
            horizon_len=self.horizon_len,
            quantiles=self.quantiles,
            pad_val=self.pad_val,
            freq_size=self.freq_size,
            model_dim=self.model_dim,
            head_dim=self.head_dim,
            num_layers=self.num_hidden_layers,
            num_heads=self.num_attention_heads,
            dropout_rate=self.dropout_rate,
            tolerance=self.tolerance,
            rms_norm_eps=self.rms_norm_eps,
            use_positional_embedding=self.use_positional_embedding,
            per_core_batch_size=self.per_core_batch_size,
            initializer_factor=self.initializer_factor,
        )

    def get_pipeline_config(self):
        return self.get_config()

    def prepare_config_and_inputs(self):
        forecast_input = [
            np.sin(np.linspace(0, 20, 100)),
            np.sin(np.linspace(0, 20, 200)),
            np.sin(np.linspace(0, 20, 400)),
        ]
        frequency_input = [0, 1, 2]

        config = self.get_config()

        return (
            config,
            forecast_input,
            frequency_input,
        )

    def prepare_config_and_inputs_for_common(self):
        (
            config,
            forecast_input,
            frequency_input,
        ) = self.prepare_config_and_inputs()

        inputs_dict = {
            "inputs": forecast_input,
            "freq": frequency_input,
        }
        return config, inputs_dict


@require_torch
class TimesFMModelTest(
    ModelTesterMixin, unittest.TestCase
):
    all_model_classes = (TimesFMModel,) if is_torch_available() else ()
    all_generative_model_classes = (TimesFMModel,) if is_torch_available() else ()
    all_parallelizable_model_classes = ()
    fx_compatible = False
    test_pruning = False
    test_resize_embeddings = False
    test_model_parallel = False
    is_encoder_decoder = False
    test_inputs_embeds = False

    def setUp(self):
        self.model_tester = TimesFMModelTester(self)
        self.config_tester = ConfigTester(self, config_class=TimesFMConfig)

    def test_create_and_run_model(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        model = TimesFMModel(config)
        model.to(torch_device)
        model.eval()
        results = model(**inputs_dict)
        assert results.mean_predictions is not None

    def test_attention_outputs(self):
        if not self.has_attentions:
            self.skipTest(reason="Model does not output attentions")

        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        config.return_dict = True

        seq_len = getattr(self.model_tester, "seq_length", None)
        decoder_seq_length = getattr(self.model_tester, "decoder_seq_length", seq_len)
        encoder_seq_length = getattr(self.model_tester, "encoder_seq_length", seq_len)
        decoder_key_length = getattr(self.model_tester, "decoder_key_length", decoder_seq_length)
        encoder_key_length = getattr(self.model_tester, "key_length", encoder_seq_length)
        chunk_length = getattr(self.model_tester, "chunk_length", None)
        if chunk_length is not None and hasattr(self.model_tester, "num_hashes"):
            encoder_seq_length = encoder_seq_length * self.model_tester.num_hashes

        for model_class in self.all_model_classes:
            inputs_dict["output_attentions"] = True
            inputs_dict["output_hidden_states"] = False
            config.return_dict = True
            model = model_class(config)
            model.to(torch_device)
            model.eval()
            with torch.no_grad():
                outputs = model(**self._prepare_for_class(inputs_dict, model_class))
            attentions = outputs.encoder_attentions if config.is_encoder_decoder else outputs.attentions
            self.assertEqual(len(attentions), self.model_tester.num_hidden_layers)

            # check that output_attentions also work using config
            del inputs_dict["output_attentions"]
            config.output_attentions = True
            model = model_class(config)
            model.to(torch_device)
            model.eval()
            with torch.no_grad():
                outputs = model(**self._prepare_for_class(inputs_dict, model_class))
            attentions = outputs.encoder_attentions if config.is_encoder_decoder else outputs.attentions
            self.assertEqual(len(attentions), self.model_tester.num_hidden_layers)

            out_len = len(outputs)

             # Check attention is always last and order is fine
            inputs_dict["output_attentions"] = True
            inputs_dict["output_hidden_states"] = True
            model = model_class(config)
            model.to(torch_device)
            model.eval()
            with torch.no_grad():
                outputs = model(**self._prepare_for_class(inputs_dict, model_class))

            if hasattr(self.model_tester, "num_hidden_states_types"):
                added_hidden_states = self.model_tester.num_hidden_states_types
            elif self.is_encoder_decoder:
                added_hidden_states = 2
            else:
                added_hidden_states = 1

            self.assertEqual(out_len + added_hidden_states, len(outputs))

            self_attentions = outputs.encoder_attentions if config.is_encoder_decoder else outputs.attentions

            self.assertEqual(len(self_attentions), self.model_tester.num_hidden_layers)
            if chunk_length is not None:
                self.assertListEqual(
                    list(self_attentions[0].shape[-4:]),
                    [self.model_tester.num_attention_heads, encoder_seq_length, chunk_length, encoder_key_length],
                )
            else:
                self.assertListEqual(
                    list(self_attentions[0].shape[-3:]),
                    [self.model_tester.num_attention_heads, encoder_seq_length, encoder_key_length],
                )

    @unittest.skip(reason="Model does not have input embeddings")
    def test_model_get_set_embeddings(self):
        pass

    # the main input name is `inputs`
    def test_model_main_input_name(self):
        model_signature = inspect.signature(getattr(TimesFMModel, "forward"))
        # The main input is the name of the argument after `self`
        observed_main_input_name = list(model_signature.parameters.keys())[1]
        self.assertEqual(TimesFMModel.main_input_name, observed_main_input_name)
