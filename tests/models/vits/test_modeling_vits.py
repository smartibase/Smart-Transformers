# coding=utf-8
# Copyright 2023 The HuggingFace Inc. team. All rights reserved.
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
""" Testing suite for the PyTorch VITS model. """

import copy
import unittest

from transformers import PretrainedConfig, VitsConfig
from transformers.testing_utils import (
    is_torch_available,
    require_torch,
    slow,
    torch_device,
)
from transformers.trainer_utils import set_seed

from ...test_configuration_common import ConfigTester
from ...test_modeling_common import (
    ModelTesterMixin,
    global_rng,
    ids_tensor,
    random_attention_mask,
)


if is_torch_available():
    from transformers import VitsModel


def _config_zero_init(config):
    configs_no_init = copy.deepcopy(config)
    for key in configs_no_init.__dict__.keys():
        if "_range" in key or "_std" in key or "initializer_factor" in key or "layer_scale" in key:
            setattr(configs_no_init, key, 1e-10)
        if isinstance(getattr(configs_no_init, key, None), PretrainedConfig):
            no_init_subconfig = _config_zero_init(getattr(configs_no_init, key))
            setattr(configs_no_init, key, no_init_subconfig)
    return configs_no_init


@require_torch
class VitsModelTester:
    def __init__(
        self,
        parent,
        batch_size=13,
        seq_length=7,
        is_training=False,
        hidden_size=24,
        num_hidden_layers=4,
        num_attention_heads=2,
        intermediate_size=4,
        vocab_size=38,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.seq_length = seq_length
        self.is_training = is_training
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.intermediate_size = intermediate_size
        self.vocab_size = vocab_size

    def prepare_config_and_inputs(self):
        input_ids = ids_tensor([self.batch_size, self.seq_length], self.vocab_size).clamp(2)
        attention_mask = random_attention_mask([self.batch_size, self.seq_length])

        config = self.get_config()
        inputs_dict = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        return config, inputs_dict

    def prepare_config_and_inputs_for_common(self):
        config, inputs_dict = self.prepare_config_and_inputs()
        return config, inputs_dict

    def get_config(self):
        return VitsConfig(
            hidden_size=self.hidden_size,
            encoder_layers=self.num_hidden_layers,
            encoder_attention_heads=self.num_attention_heads,
            encoder_ffn_dim=self.intermediate_size,
            inter_channels=self.intermediate_size,
            vocab_size=self.vocab_size,
        )

    def create_and_check_model_forward(self, config, inputs_dict):
        model = VitsModel(config=config).to(torch_device).eval()

        input_ids = inputs_dict["input_ids"]
        attention_mask = inputs_dict["attention_mask"]

        result = model(input_ids, attention_mask=attention_mask)
        self.parent.assertEqual(result.audio.shape, (self.batch_size, 99072))


@require_torch
class VitsModelTest(ModelTesterMixin, unittest.TestCase):
    all_model_classes = (VitsModel,) if is_torch_available() else ()
    is_encoder_decoder = False
    test_pruning = False
    test_headmasking = False
    test_resize_embeddings = False
    test_head_masking = False
    test_torchscript = False
    has_attentions = False

    input_name = "input_ids"

    def setUp(self):
        self.model_tester = VitsModelTester(self)
        self.config_tester = ConfigTester(self, config_class=VitsConfig, hidden_size=37)

    def test_config(self):
        self.config_tester.run_common_tests()

    def test_model_forward(self):
        set_seed(12345)
        global_rng.seed(12345)
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model_forward(*config_and_inputs)

    @unittest.skip("this model is not deterministic")
    def test_determinism(self):
        pass

    @unittest.skip("this model does not return hidden_states")
    def test_hidden_states_output(self):
        pass

    def test_initialization(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        configs_no_init = _config_zero_init(config)
        for model_class in self.all_model_classes:
            model = model_class(config=configs_no_init)
            for name, param in model.named_parameters():
                uniform_init_parms = [
                    "emb_rel_k",
                    "emb_rel_v",
                    "conv_1",
                    "conv_2",
                    "conv_pre",
                    "conv_post",
                    "conv_proj",
                    "conv_dds",
                    "project",
                    "wavenet.in_layers",
                    "wavenet.res_skip_layers",
                    "upsampler",
                    "resblocks",
                ]
                if param.requires_grad:
                    if any([x in name for x in uniform_init_parms]):
                        self.assertTrue(
                            -1.0 <= ((param.data.mean() * 1e9).round() / 1e9).item() <= 1.0,
                            msg=f"Parameter {name} of model {model_class} seems not properly initialized",
                        )
                    else:
                        self.assertIn(
                            ((param.data.mean() * 1e9).round() / 1e9).item(),
                            [0.0, 1.0],
                            msg=f"Parameter {name} of model {model_class} seems not properly initialized",
                        )

    @unittest.skip("this model has no inputs_embeds")
    def test_inputs_embeds(self):
        pass

    @unittest.skip("this model has no input embeddings")
    def test_model_common_attributes(self):
        pass

    @unittest.skip("this model is not deterministic")
    def test_model_outputs_equivalence(self):
        pass

    @unittest.skip("this model does not return hidden_states")
    def test_retain_grad_hidden_states_attentions(self):
        pass

    @unittest.skip("this model is not deterministic")
    def test_save_load(self):
        pass

    # overwrite from test_modeling_common
    def _mock_init_weights(self, module):
        if hasattr(module, "weight") and module.weight is not None:
            module.weight.data.fill_(3)
        if hasattr(module, "weight_g") and module.weight_g is not None:
            module.weight_g.data.fill_(3)
        if hasattr(module, "weight_v") and module.weight_v is not None:
            module.weight_v.data.fill_(3)
        if hasattr(module, "bias") and module.bias is not None:
            module.bias.data.fill_(3)
