# coding=utf-8
# Copyright 2021 The HuggingFace Inc. team. All rights reserved.
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
""" Testing suite for the PyTorch Wav2Vec2 model. """

import math
import unittest

import numpy as np
from datasets import load_dataset

from tests.test_modeling_common import floats_tensor, ids_tensor, random_attention_mask
from transformers import Wav2Vec2Config, is_torch_available
from transformers.testing_utils import (
    is_pt_flax_cross_test,
    is_pyctcdecode_available,
    is_torchaudio_available,
    require_datasets,
    require_pyctcdecode,
    require_soundfile,
    require_torch,
    require_torchaudio,
    slow,
    torch_device,
)

from .test_configuration_common import ConfigTester
from .test_modeling_common import ModelTesterMixin, _config_zero_init


if is_torch_available():
    import torch

    from transformers import (
        Wav2Vec2FeatureExtractor,
        Wav2Vec2ForCTC,
        Wav2Vec2ForMaskedLM,
        Wav2Vec2ForPreTraining,
        Wav2Vec2ForSequenceClassification,
        Wav2Vec2Model,
        Wav2Vec2Processor,
    )
    from transformers.models.wav2vec2.modeling_wav2vec2 import (
        Wav2Vec2GumbelVectorQuantizer,
        _compute_mask_indices,
        _sample_negative_indices,
    )


if is_torchaudio_available():
    import torchaudio


if is_pyctcdecode_available():
    from transformers import Wav2Vec2ProcessorWithLM


class Wav2Vec2ModelTester:
    def __init__(
        self,
        parent,
        batch_size=13,
        seq_length=1024,  # speech is longer
        is_training=False,
        hidden_size=16,
        feat_extract_norm="group",
        feat_extract_dropout=0.0,
        feat_extract_activation="gelu",
        conv_dim=(32, 32, 32),
        conv_stride=(4, 4, 4),
        conv_kernel=(8, 8, 8),
        conv_bias=False,
        num_conv_pos_embeddings=16,
        num_conv_pos_embedding_groups=2,
        num_hidden_layers=4,
        num_attention_heads=2,
        hidden_dropout_prob=0.1,  # this is most likely not correctly set yet
        intermediate_size=20,
        layer_norm_eps=1e-5,
        hidden_act="gelu",
        initializer_range=0.02,
        mask_time_prob=0.5,
        mask_time_length=2,
        vocab_size=32,
        do_stable_layer_norm=False,
        num_adapter_layers=1,
        adapter_stride=2,
        scope=None,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.seq_length = seq_length
        self.is_training = is_training
        self.hidden_size = hidden_size
        self.feat_extract_norm = feat_extract_norm
        self.feat_extract_dropout = feat_extract_dropout
        self.feat_extract_activation = feat_extract_activation
        self.conv_dim = conv_dim
        self.conv_stride = conv_stride
        self.conv_kernel = conv_kernel
        self.conv_bias = conv_bias
        self.num_conv_pos_embeddings = num_conv_pos_embeddings
        self.num_conv_pos_embedding_groups = num_conv_pos_embedding_groups
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.hidden_dropout_prob = hidden_dropout_prob
        self.intermediate_size = intermediate_size
        self.layer_norm_eps = layer_norm_eps
        self.hidden_act = hidden_act
        self.initializer_range = initializer_range
        self.vocab_size = vocab_size
        self.do_stable_layer_norm = do_stable_layer_norm
        self.num_adapter_layers = num_adapter_layers
        self.adapter_stride = adapter_stride
        self.mask_time_prob = mask_time_prob
        self.mask_time_length = mask_time_length
        self.scope = scope

        output_seq_length = self.seq_length
        for kernel, stride in zip(self.conv_kernel, self.conv_stride):
            output_seq_length = (output_seq_length - (kernel - 1)) / stride
        self.output_seq_length = int(math.ceil(output_seq_length))
        self.encoder_seq_length = self.output_seq_length

        self.adapter_output_seq_length = (self.output_seq_length - 1) // adapter_stride + 1

    def prepare_config_and_inputs(self):
        input_values = floats_tensor([self.batch_size, self.seq_length], self.vocab_size)
        attention_mask = random_attention_mask([self.batch_size, self.seq_length])

        config = self.get_config()

        return config, input_values, attention_mask

    def get_config(self):
        return Wav2Vec2Config(
            hidden_size=self.hidden_size,
            feat_extract_norm=self.feat_extract_norm,
            feat_extract_dropout=self.feat_extract_dropout,
            feat_extract_activation=self.feat_extract_activation,
            conv_dim=self.conv_dim,
            conv_stride=self.conv_stride,
            conv_kernel=self.conv_kernel,
            conv_bias=self.conv_bias,
            mask_time_prob=self.mask_time_prob,
            mask_time_length=self.mask_time_length,
            num_conv_pos_embeddings=self.num_conv_pos_embeddings,
            num_conv_pos_embedding_groups=self.num_conv_pos_embedding_groups,
            num_hidden_layers=self.num_hidden_layers,
            num_attention_heads=self.num_attention_heads,
            hidden_dropout_prob=self.hidden_dropout_prob,
            intermediate_size=self.intermediate_size,
            layer_norm_eps=self.layer_norm_eps,
            do_stable_layer_norm=self.do_stable_layer_norm,
            hidden_act=self.hidden_act,
            initializer_range=self.initializer_range,
            vocab_size=self.vocab_size,
            num_adapter_layers=self.num_adapter_layers,
            adapter_stride=self.adapter_stride,
        )

    def create_and_check_model(self, config, input_values, attention_mask):
        model = Wav2Vec2Model(config=config)
        model.to(torch_device)
        model.eval()
        result = model(input_values, attention_mask=attention_mask)
        self.parent.assertEqual(
            result.last_hidden_state.shape, (self.batch_size, self.output_seq_length, self.hidden_size)
        )

    def create_and_check_model_with_adapter(self, config, input_values, attention_mask):
        config.add_adapter = True
        model = Wav2Vec2Model(config=config)
        model.to(torch_device)
        model.eval()
        result = model(input_values, attention_mask=attention_mask)
        self.parent.assertEqual(
            result.last_hidden_state.shape, (self.batch_size, self.adapter_output_seq_length, self.hidden_size)
        )

    def create_and_check_model_with_adapter_proj_dim(self, config, input_values, attention_mask):
        config.add_adapter = True
        config.output_hidden_size = 8
        model = Wav2Vec2Model(config=config)
        model.to(torch_device)
        model.eval()
        result = model(input_values, attention_mask=attention_mask)
        self.parent.assertEqual(
            result.last_hidden_state.shape,
            (self.batch_size, self.adapter_output_seq_length, config.output_hidden_size),
        )

    def create_and_check_batch_inference(self, config, input_values, *args):
        # test does not pass for models making use of `group_norm`
        # check: https://github.com/pytorch/fairseq/issues/3227
        model = Wav2Vec2Model(config=config)
        model.to(torch_device)
        model.eval()

        input_values = input_values[:3]
        attention_mask = torch.ones(input_values.shape, device=torch_device, dtype=torch.bool)

        input_lengths = [input_values.shape[-1] // i for i in [4, 2, 1]]

        # pad input
        for i in range(len(input_lengths)):
            input_values[i, input_lengths[i] :] = 0.0
            attention_mask[i, input_lengths[i] :] = 0.0

        batch_outputs = model(input_values, attention_mask=attention_mask).last_hidden_state

        for i in range(input_values.shape[0]):
            input_slice = input_values[i : i + 1, : input_lengths[i]]
            output = model(input_slice).last_hidden_state

            batch_output = batch_outputs[i : i + 1, : output.shape[1]]
            self.parent.assertTrue(torch.allclose(output, batch_output, atol=1e-3))

    def check_ctc_loss(self, config, input_values, *args):
        model = Wav2Vec2ForCTC(config=config)
        model.to(torch_device)

        # make sure that dropout is disabled
        model.eval()

        input_values = input_values[:3]
        attention_mask = torch.ones(input_values.shape, device=torch_device, dtype=torch.long)

        input_lengths = [input_values.shape[-1] // i for i in [4, 2, 1]]
        max_length_labels = model._get_feat_extract_output_lengths(torch.tensor(input_lengths))
        labels = ids_tensor((input_values.shape[0], min(max_length_labels) - 1), model.config.vocab_size)

        # pad input
        for i in range(len(input_lengths)):
            input_values[i, input_lengths[i] :] = 0.0
            attention_mask[i, input_lengths[i] :] = 0

        model.config.ctc_loss_reduction = "sum"
        sum_loss = model(input_values, attention_mask=attention_mask, labels=labels).loss.item()

        model.config.ctc_loss_reduction = "mean"
        mean_loss = model(input_values, attention_mask=attention_mask, labels=labels).loss.item()

        self.parent.assertTrue(isinstance(sum_loss, float))
        self.parent.assertTrue(isinstance(mean_loss, float))

    def check_seq_classifier_loss(self, config, input_values, *args):
        model = Wav2Vec2ForSequenceClassification(config=config)
        model.to(torch_device)

        # make sure that dropout is disabled
        model.eval()

        input_values = input_values[:3]
        attention_mask = torch.ones(input_values.shape, device=torch_device, dtype=torch.long)

        input_lengths = [input_values.shape[-1] // i for i in [4, 2, 1]]
        labels = ids_tensor((input_values.shape[0], 1), len(model.config.id2label))

        # pad input
        for i in range(len(input_lengths)):
            input_values[i, input_lengths[i] :] = 0.0
            attention_mask[i, input_lengths[i] :] = 0

        masked_loss = model(input_values, attention_mask=attention_mask, labels=labels).loss.item()
        unmasked_loss = model(input_values, labels=labels).loss.item()

        self.parent.assertTrue(isinstance(masked_loss, float))
        self.parent.assertTrue(isinstance(unmasked_loss, float))
        self.parent.assertTrue(masked_loss != unmasked_loss)

    def check_ctc_training(self, config, input_values, *args):
        config.ctc_zero_infinity = True
        model = Wav2Vec2ForCTC(config=config)
        model.to(torch_device)
        model.train()

        # freeze feature encoder
        model.freeze_feature_extractor()

        input_values = input_values[:3]

        input_lengths = [input_values.shape[-1] // i for i in [4, 2, 1]]
        max_length_labels = model._get_feat_extract_output_lengths(torch.tensor(input_lengths))
        labels = ids_tensor((input_values.shape[0], max(max_length_labels) - 2), model.config.vocab_size)

        # pad input
        for i in range(len(input_lengths)):
            input_values[i, input_lengths[i] :] = 0.0

            if max_length_labels[i] < labels.shape[-1]:
                # it's important that we make sure that target lenghts are at least
                # one shorter than logit lenghts to prevent -inf
                labels[i, max_length_labels[i] - 1 :] = -100

        loss = model(input_values, labels=labels).loss
        self.parent.assertFalse(torch.isinf(loss).item())

        loss.backward()

    def check_seq_classifier_training(self, config, input_values, *args):
        config.ctc_zero_infinity = True
        model = Wav2Vec2ForSequenceClassification(config=config)
        model.to(torch_device)
        model.train()

        # freeze everything but the classification head
        model.freeze_base_model()

        input_values = input_values[:3]

        input_lengths = [input_values.shape[-1] // i for i in [4, 2, 1]]
        labels = ids_tensor((input_values.shape[0], 1), len(model.config.id2label))

        # pad input
        for i in range(len(input_lengths)):
            input_values[i, input_lengths[i] :] = 0.0

        loss = model(input_values, labels=labels).loss
        self.parent.assertFalse(torch.isinf(loss).item())

        loss.backward()

    def check_labels_out_of_vocab(self, config, input_values, *args):
        model = Wav2Vec2ForCTC(config)
        model.to(torch_device)
        model.train()

        input_values = input_values[:3]

        input_lengths = [input_values.shape[-1] // i for i in [4, 2, 1]]
        max_length_labels = model._get_feat_extract_output_lengths(torch.tensor(input_lengths))
        labels = ids_tensor((input_values.shape[0], max(max_length_labels) - 2), model.config.vocab_size + 100)

        with self.parent.assertRaises(ValueError):
            model(input_values, labels=labels)

    def prepare_config_and_inputs_for_common(self):
        config, input_values, attention_mask = self.prepare_config_and_inputs()
        inputs_dict = {"input_values": input_values, "attention_mask": attention_mask}
        return config, inputs_dict


@require_torch
class Wav2Vec2ModelTest(ModelTesterMixin, unittest.TestCase):
    all_model_classes = (
        (Wav2Vec2ForCTC, Wav2Vec2Model, Wav2Vec2ForMaskedLM, Wav2Vec2ForSequenceClassification, Wav2Vec2ForPreTraining)
        if is_torch_available()
        else ()
    )
    test_pruning = False
    test_headmasking = False
    test_torchscript = False

    def setUp(self):
        self.model_tester = Wav2Vec2ModelTester(self)
        self.config_tester = ConfigTester(self, config_class=Wav2Vec2Config, hidden_size=37)

    def test_config(self):
        self.config_tester.run_common_tests()

    def test_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model(*config_and_inputs)

    def test_model_with_adapter(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model_with_adapter(*config_and_inputs)

    def test_model_with_adapter_proj_dim(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model_with_adapter_proj_dim(*config_and_inputs)

    def test_ctc_loss_inference(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_ctc_loss(*config_and_inputs)

    def test_seq_classifier_loss_inference(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_seq_classifier_loss(*config_and_inputs)

    def test_ctc_train(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_ctc_training(*config_and_inputs)

    def test_seq_classifier_train(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_seq_classifier_training(*config_and_inputs)

    def test_labels_out_of_vocab(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_labels_out_of_vocab(*config_and_inputs)

    # Wav2Vec2 has no inputs_embeds
    def test_inputs_embeds(self):
        pass

    # `input_ids` is renamed to `input_values`
    def test_forward_signature(self):
        pass

    # Wav2Vec2 cannot resize token embeddings
    # since it has no tokens embeddings
    def test_resize_tokens_embeddings(self):
        pass

    # Wav2Vec2 has no inputs_embeds
    # and thus the `get_input_embeddings` fn
    # is not implemented
    def test_model_common_attributes(self):
        pass

    @is_pt_flax_cross_test
    # non-robust architecture does not exist in Flax
    def test_equivalence_flax_to_pt(self):
        pass

    @is_pt_flax_cross_test
    # non-robust architecture does not exist in Flax
    def test_equivalence_pt_to_flax(self):
        pass

    def test_retain_grad_hidden_states_attentions(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        config.output_hidden_states = True
        config.output_attentions = True

        # no need to test all models as different heads yield the same functionality
        model_class = self.all_model_classes[0]
        model = model_class(config)
        model.to(torch_device)

        # set layer drop to 0
        model.config.layerdrop = 0.0

        input_values = inputs_dict["input_values"]

        input_lengths = torch.tensor(
            [input_values.shape[1] for _ in range(input_values.shape[0])], dtype=torch.long, device=torch_device
        )
        output_lengths = model._get_feat_extract_output_lengths(input_lengths)

        labels = ids_tensor((input_values.shape[0], output_lengths[0] - 2), self.model_tester.vocab_size)
        inputs_dict["attention_mask"] = torch.ones_like(inputs_dict["attention_mask"])
        inputs_dict["labels"] = labels

        outputs = model(**inputs_dict)

        output = outputs[0]

        # Encoder-/Decoder-only models
        hidden_states = outputs.hidden_states[0]
        attentions = outputs.attentions[0]

        hidden_states.retain_grad()
        attentions.retain_grad()

        output.flatten()[0].backward(retain_graph=True)

        self.assertIsNotNone(hidden_states.grad)
        self.assertIsNotNone(attentions.grad)

    def test_initialization(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        configs_no_init = _config_zero_init(config)
        for model_class in self.all_model_classes:
            model = model_class(config=configs_no_init)
            for name, param in model.named_parameters():
                uniform_init_parms = [
                    "conv.weight",
                    "masked_spec_embed",
                    "codevectors",
                    "quantizer.weight_proj.weight",
                    "project_hid.weight",
                    "project_hid.bias",
                    "project_q.weight",
                    "project_q.bias",
                    "feature_projection.projection.weight",
                    "feature_projection.projection.bias",
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
        if hasattr(module, "codevectors") and module.codevectors is not None:
            module.codevectors.data.fill_(3)
        if hasattr(module, "masked_spec_embed") and module.masked_spec_embed is not None:
            module.masked_spec_embed.data.fill_(3)

    def test_mask_feature_prob_ctc(self):
        model = Wav2Vec2ForCTC.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", mask_feature_prob=0.2, mask_feature_length=2
        )
        model.to(torch_device).train()
        processor = Wav2Vec2Processor.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", return_attention_mask=True
        )

        batch_duration_in_seconds = [1, 3, 2, 6]
        input_features = [np.random.random(16_000 * s) for s in batch_duration_in_seconds]

        batch = processor(
            input_features, padding=True, sampling_rate=processor.feature_extractor.sampling_rate, return_tensors="pt"
        )

        logits = model(
            input_values=batch["input_values"].to(torch_device),
            attention_mask=batch["attention_mask"].to(torch_device),
        ).logits

        self.assertEqual(logits.shape, (4, 1498, 32))

    def test_mask_time_prob_ctc(self):
        model = Wav2Vec2ForCTC.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", mask_time_prob=0.2, mask_time_length=2
        )
        model.to(torch_device).train()
        processor = Wav2Vec2Processor.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", return_attention_mask=True
        )

        batch_duration_in_seconds = [1, 3, 2, 6]
        input_features = [np.random.random(16_000 * s) for s in batch_duration_in_seconds]

        batch = processor(
            input_features, padding=True, sampling_rate=processor.feature_extractor.sampling_rate, return_tensors="pt"
        )

        logits = model(
            input_values=batch["input_values"].to(torch_device),
            attention_mask=batch["attention_mask"].to(torch_device),
        ).logits

        self.assertEqual(logits.shape, (4, 1498, 32))

    @slow
    def test_model_from_pretrained(self):
        model = Wav2Vec2Model.from_pretrained("facebook/wav2vec2-base-960h")
        self.assertIsNotNone(model)


@require_torch
class Wav2Vec2RobustModelTest(ModelTesterMixin, unittest.TestCase):
    all_model_classes = (
        (Wav2Vec2ForCTC, Wav2Vec2Model, Wav2Vec2ForMaskedLM, Wav2Vec2ForSequenceClassification, Wav2Vec2ForPreTraining)
        if is_torch_available()
        else ()
    )
    test_pruning = False
    test_headmasking = False
    test_torchscript = False

    def setUp(self):
        self.model_tester = Wav2Vec2ModelTester(
            self, conv_stride=(3, 3, 3), feat_extract_norm="layer", do_stable_layer_norm=True
        )
        self.config_tester = ConfigTester(self, config_class=Wav2Vec2Config, hidden_size=37)

    def test_config(self):
        self.config_tester.run_common_tests()

    def test_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model(*config_and_inputs)

    def test_model_with_adapter(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model_with_adapter(*config_and_inputs)

    def test_model_with_adapter_proj_dim(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model_with_adapter_proj_dim(*config_and_inputs)

    def test_batched_inference(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_batch_inference(*config_and_inputs)

    def test_ctc_loss_inference(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_ctc_loss(*config_and_inputs)

    def test_seq_classifier_loss_inference(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_seq_classifier_loss(*config_and_inputs)

    def test_ctc_train(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_ctc_training(*config_and_inputs)

    def test_seq_classifier_train(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_seq_classifier_training(*config_and_inputs)

    def test_labels_out_of_vocab(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.check_labels_out_of_vocab(*config_and_inputs)

    # Wav2Vec2 has no inputs_embeds
    def test_inputs_embeds(self):
        pass

    # `input_ids` is renamed to `input_values`
    def test_forward_signature(self):
        pass

    # Wav2Vec2 cannot resize token embeddings
    # since it has no tokens embeddings
    def test_resize_tokens_embeddings(self):
        pass

    # Wav2Vec2 has no inputs_embeds
    # and thus the `get_input_embeddings` fn
    # is not implemented
    def test_model_common_attributes(self):
        pass

    def test_retain_grad_hidden_states_attentions(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        config.output_hidden_states = True
        config.output_attentions = True

        # no need to test all models as different heads yield the same functionality
        model_class = self.all_model_classes[0]
        model = model_class(config)
        model.to(torch_device)

        # set layer drop to 0
        model.config.layerdrop = 0.0

        input_values = inputs_dict["input_values"]

        input_lengths = torch.tensor(
            [input_values.shape[1] for _ in range(input_values.shape[0])], dtype=torch.long, device=torch_device
        )
        output_lengths = model._get_feat_extract_output_lengths(input_lengths)

        labels = ids_tensor((input_values.shape[0], output_lengths[0] - 2), self.model_tester.vocab_size)
        inputs_dict["attention_mask"] = torch.ones_like(inputs_dict["attention_mask"])
        inputs_dict["labels"] = labels

        outputs = model(**inputs_dict)

        output = outputs[0]

        # Encoder-/Decoder-only models
        hidden_states = outputs.hidden_states[0]
        attentions = outputs.attentions[0]

        hidden_states.retain_grad()
        attentions.retain_grad()

        output.flatten()[0].backward(retain_graph=True)

        self.assertIsNotNone(hidden_states.grad)
        self.assertIsNotNone(attentions.grad)

    def test_initialization(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        configs_no_init = _config_zero_init(config)
        for model_class in self.all_model_classes:
            model = model_class(config=configs_no_init)
            for name, param in model.named_parameters():
                uniform_init_parms = [
                    "conv.weight",
                    "masked_spec_embed",
                    "codevectors",
                    "quantizer.weight_proj.weight",
                    "project_hid.weight",
                    "project_hid.bias",
                    "project_q.weight",
                    "project_q.bias",
                    "feature_projection.projection.weight",
                    "feature_projection.projection.bias",
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
        if hasattr(module, "codevectors") and module.codevectors is not None:
            module.codevectors.data.fill_(3)
        if hasattr(module, "masked_spec_embed") and module.masked_spec_embed is not None:
            module.masked_spec_embed.data.fill_(3)

    def test_model_for_pretraining(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        model = Wav2Vec2ForPreTraining(config).to(torch_device)

        features_shape = (
            inputs_dict["input_values"].shape[0],
            model._get_feat_extract_output_lengths(inputs_dict["input_values"].shape[1]),
        )

        mask_time_indices = _compute_mask_indices(
            features_shape,
            model.config.mask_time_prob,
            model.config.mask_time_length,
            min_masks=2,
        )
        sampled_negative_indices = _sample_negative_indices(features_shape, 10, mask_time_indices)

        mask_time_indices = torch.from_numpy(mask_time_indices).to(torch_device)
        sampled_negative_indices = torch.from_numpy(sampled_negative_indices).to(torch_device)

        loss = model(
            inputs_dict["input_values"],
            attention_mask=inputs_dict["attention_mask"],
            mask_time_indices=mask_time_indices,
            sampled_negative_indices=sampled_negative_indices,
        ).loss

        # more losses
        mask_time_indices[:, : mask_time_indices.shape[-1] // 2] = True

        sampled_negative_indices = _sample_negative_indices(features_shape, 10, mask_time_indices.cpu().numpy())
        sampled_negative_indices = torch.from_numpy(sampled_negative_indices).to(torch_device)
        loss_more_masked = model(
            inputs_dict["input_values"],
            attention_mask=inputs_dict["attention_mask"],
            mask_time_indices=mask_time_indices,
            sampled_negative_indices=sampled_negative_indices,
        ).loss

        # loss_more_masked has to be bigger or equal loss since more masked inputs have to be predicted
        self.assertTrue(loss.detach().item() <= loss_more_masked.detach().item())

    def test_mask_feature_prob_ctc(self):
        model = Wav2Vec2ForCTC.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", mask_feature_prob=0.2, mask_feature_length=2
        )
        model.to(torch_device).train()
        processor = Wav2Vec2Processor.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", return_attention_mask=True
        )

        batch_duration_in_seconds = [1, 3, 2, 6]
        input_features = [np.random.random(16_000 * s) for s in batch_duration_in_seconds]

        batch = processor(
            input_features, padding=True, sampling_rate=processor.feature_extractor.sampling_rate, return_tensors="pt"
        )

        logits = model(
            input_values=batch["input_values"].to(torch_device),
            attention_mask=batch["attention_mask"].to(torch_device),
        ).logits

        self.assertEqual(logits.shape, (4, 1498, 32))

    def test_mask_time_prob_ctc(self):
        model = Wav2Vec2ForCTC.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", mask_time_prob=0.2, mask_time_length=2
        )
        model.to(torch_device).train()
        processor = Wav2Vec2Processor.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", return_attention_mask=True
        )

        batch_duration_in_seconds = [1, 3, 2, 6]
        input_features = [np.random.random(16_000 * s) for s in batch_duration_in_seconds]

        batch = processor(
            input_features, padding=True, sampling_rate=processor.feature_extractor.sampling_rate, return_tensors="pt"
        )

        logits = model(
            input_values=batch["input_values"].to(torch_device),
            attention_mask=batch["attention_mask"].to(torch_device),
        ).logits

        self.assertEqual(logits.shape, (4, 1498, 32))

    def test_mask_time_feature_prob_ctc_single_batch(self):
        model = Wav2Vec2ForCTC.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2",
            mask_time_prob=0.2,
            mask_feature_prob=0.2,
            mask_time_length=2,
            mask_feature_length=2,
        )
        model.to(torch_device).train()
        processor = Wav2Vec2Processor.from_pretrained(
            "hf-internal-testing/tiny-random-wav2vec2", return_attention_mask=True
        )

        batch_duration_in_seconds = [6]
        input_features = [np.random.random(16_000 * s) for s in batch_duration_in_seconds]

        batch = processor(
            input_features, padding=True, sampling_rate=processor.feature_extractor.sampling_rate, return_tensors="pt"
        )

        logits = model(
            input_values=batch["input_values"].to(torch_device),
            attention_mask=batch["attention_mask"].to(torch_device),
        ).logits

        self.assertEqual(logits.shape, (1, 1498, 32))

    @slow
    def test_model_from_pretrained(self):
        model = Wav2Vec2Model.from_pretrained("facebook/wav2vec2-base-960h")
        self.assertIsNotNone(model)


@require_torch
class Wav2Vec2UtilsTest(unittest.TestCase):
    def test_compute_mask_indices(self):
        batch_size = 4
        sequence_length = 60
        mask_prob = 0.5
        mask_length = 1

        mask = _compute_mask_indices((batch_size, sequence_length), mask_prob, mask_length)
        mask = torch.from_numpy(mask).to(torch_device)

        self.assertListEqual(mask.sum(axis=-1).tolist(), [mask_prob * sequence_length for _ in range(batch_size)])

    def test_compute_mask_indices_low_prob(self):
        # with these settings num_masked_spans=0.5, which means probabilistic rounding
        # ensures that in 5 out of 10 method calls, num_masked_spans=0, and in
        # the other 5 out of 10, cases num_masked_spans=1
        n_trials = 100
        batch_size = 4
        sequence_length = 100
        mask_prob = 0.05
        mask_length = 10

        count_dimensions_masked = 0
        count_dimensions_not_masked = 0

        for _ in range(n_trials):
            mask = _compute_mask_indices((batch_size, sequence_length), mask_prob, mask_length)
            mask = torch.from_numpy(mask).to(torch_device)

            num_masks = torch.sum(mask).item()

            if num_masks > 0:
                count_dimensions_masked += 1
            else:
                count_dimensions_not_masked += 1

        # as we test for at least 10 masked dimension and at least
        # 10 non-masked dimension, this test could fail with probability:
        # P(100 coin flips, at most 9 heads) = 1.66e-18
        self.assertGreater(count_dimensions_masked, int(n_trials * 0.1))
        self.assertGreater(count_dimensions_not_masked, int(n_trials * 0.1))

    def test_compute_mask_indices_overlap(self):
        batch_size = 4
        sequence_length = 80
        mask_prob = 0.5
        mask_length = 4

        mask = _compute_mask_indices((batch_size, sequence_length), mask_prob, mask_length)
        mask = torch.from_numpy(mask).to(torch_device)

        # because of overlap mask don't have to add up exactly to `mask_prob * sequence_length`, but have to be smaller or equal
        for batch_sum in mask.sum(axis=-1):
            self.assertTrue(int(batch_sum) <= mask_prob * sequence_length)

    def test_compute_mask_indices_attn_mask_overlap(self):
        batch_size = 4
        sequence_length = 80
        mask_prob = 0.5
        mask_length = 4

        attention_mask = torch.ones((batch_size, sequence_length), dtype=torch.long, device=torch_device)
        attention_mask[:2, sequence_length // 2 :] = 0

        mask = _compute_mask_indices(
            (batch_size, sequence_length), mask_prob, mask_length, attention_mask=attention_mask
        )
        mask = torch.from_numpy(mask).to(torch_device)

        for batch_sum in mask.sum(axis=-1):
            self.assertTrue(int(batch_sum) <= mask_prob * sequence_length)

        self.assertTrue(mask[:2, sequence_length // 2 :].sum() == 0)

    def test_compute_perplexity(self):
        probs = torch.arange(100, device=torch_device).reshape(2, 5, 10) / 100

        ppl = Wav2Vec2GumbelVectorQuantizer._compute_perplexity(probs)
        self.assertTrue(abs(ppl.item() - 141.4291) < 1e-3)

        # mask half of the input
        mask = torch.ones((2,), device=torch_device, dtype=torch.bool)
        mask[0] = 0

        ppl = Wav2Vec2GumbelVectorQuantizer._compute_perplexity(probs, mask)
        self.assertTrue(abs(ppl.item() - 58.6757) < 1e-3)

    def test_sample_negatives(self):
        batch_size = 2
        sequence_length = 10
        hidden_size = 4
        num_negatives = 3

        features = (torch.arange(sequence_length * hidden_size, device=torch_device) // hidden_size).view(
            sequence_length, hidden_size
        )  # each value in vector consits of same value
        features = features[None, :].expand(batch_size, sequence_length, hidden_size).contiguous()

        # sample negative indices
        sampled_negative_indices = _sample_negative_indices((batch_size, sequence_length), num_negatives, None)
        sampled_negative_indices = torch.from_numpy(sampled_negative_indices).to(torch_device)
        negatives = features.view(-1, hidden_size)[sampled_negative_indices.long().view(-1)]
        negatives = negatives.view(batch_size, sequence_length, -1, hidden_size).permute(2, 0, 1, 3)
        self.assertTrue(negatives.shape == (num_negatives, batch_size, sequence_length, hidden_size))

        # make sure no negatively sampled vector is actually a positive one
        for negative in negatives:
            self.assertTrue(((negative - features) == 0).sum() == 0.0)

        # make sure that full vectors are sampled and not values of vectors => this means that `unique()` yields a single value for `hidden_size` dim
        self.assertTrue(negatives.unique(dim=-1).shape, (num_negatives, batch_size, sequence_length, 1))

    def test_sample_negatives_with_mask(self):
        batch_size = 2
        sequence_length = 10
        hidden_size = 4
        num_negatives = 3

        # second half of last input tensor is padded
        mask = torch.ones((batch_size, sequence_length), dtype=torch.long, device=torch_device)
        mask[-1, sequence_length // 2 :] = 0

        features = (torch.arange(sequence_length * hidden_size, device=torch_device) // hidden_size).view(
            sequence_length, hidden_size
        )  # each value in vector consits of same value
        features = features[None, :].expand(batch_size, sequence_length, hidden_size).contiguous()

        # replace masked feature vectors with -100 to test that those are not sampled
        features = torch.where(mask[:, :, None].expand(features.shape).bool(), features, -100)

        # sample negative indices
        sampled_negative_indices = _sample_negative_indices(
            (batch_size, sequence_length), num_negatives, mask.cpu().numpy()
        )
        sampled_negative_indices = torch.from_numpy(sampled_negative_indices).to(torch_device)
        negatives = features.view(-1, hidden_size)[sampled_negative_indices.long().view(-1)]
        negatives = negatives.view(batch_size, sequence_length, -1, hidden_size).permute(2, 0, 1, 3)

        self.assertTrue((negatives >= 0).all().item())

        self.assertTrue(negatives.shape == (num_negatives, batch_size, sequence_length, hidden_size))

        # make sure no negatively sampled vector is actually a positive one
        for negative in negatives:
            self.assertTrue(((negative - features) == 0).sum() == 0.0)

        # make sure that full vectors are sampled and not values of vectors => this means that `unique()` yields a single value for `hidden_size` dim
        self.assertTrue(negatives.unique(dim=-1).shape, (num_negatives, batch_size, sequence_length, 1))


@require_torch
@require_datasets
@require_soundfile
@slow
class Wav2Vec2ModelIntegrationTest(unittest.TestCase):
    def _load_datasamples(self, num_samples):
        ds = load_dataset("hf-internal-testing/librispeech_asr_dummy", "clean", split="validation")
        # automatic decoding with librispeech
        speech_samples = ds.sort("id").filter(
            lambda x: x["id"] in [f"1272-141231-000{i}" for i in range(num_samples)]
        )[:num_samples]["audio"]

        return [x["array"] for x in speech_samples]

    def _load_superb(self, task, num_samples):
        ds = load_dataset("anton-l/superb_dummy", task, split="test")

        return ds[:num_samples]

    def test_inference_ctc_normal(self):
        model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")
        model.to(torch_device)
        processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h", do_lower_case=True)
        input_speech = self._load_datasamples(1)

        input_values = processor(input_speech, return_tensors="pt").input_values.to(torch_device)

        with torch.no_grad():
            logits = model(input_values).logits

        predicted_ids = torch.argmax(logits, dim=-1)
        predicted_trans = processor.batch_decode(predicted_ids)

        EXPECTED_TRANSCRIPTIONS = ["a man said to the universe sir i exist"]
        self.assertListEqual(predicted_trans, EXPECTED_TRANSCRIPTIONS)

    def test_inference_ctc_normal_batched(self):
        model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")
        model.to(torch_device)
        processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h", do_lower_case=True)

        input_speech = self._load_datasamples(2)

        inputs = processor(input_speech, return_tensors="pt", padding=True)

        input_values = inputs.input_values.to(torch_device)

        with torch.no_grad():
            logits = model(input_values).logits

        predicted_ids = torch.argmax(logits, dim=-1)
        predicted_trans = processor.batch_decode(predicted_ids)

        EXPECTED_TRANSCRIPTIONS = [
            "a man said to the universe sir i exist",
            "sweat covered brion's body trickling into the tight lowing cloth that was the only garment he wore",
        ]
        self.assertListEqual(predicted_trans, EXPECTED_TRANSCRIPTIONS)

    def test_inference_ctc_robust_batched(self):
        model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-large-960h-lv60-self").to(torch_device)
        processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-large-960h-lv60-self", do_lower_case=True)

        input_speech = self._load_datasamples(4)

        inputs = processor(input_speech, return_tensors="pt", padding=True)

        input_values = inputs.input_values.to(torch_device)
        attention_mask = inputs.attention_mask.to(torch_device)

        with torch.no_grad():
            logits = model(input_values, attention_mask=attention_mask).logits

        predicted_ids = torch.argmax(logits, dim=-1)
        predicted_trans = processor.batch_decode(predicted_ids)

        EXPECTED_TRANSCRIPTIONS = [
            "a man said to the universe sir i exist",
            "sweat covered brion's body trickling into the tight loin cloth that was the only garment he wore",
            "the cut on his chest still dripping blood the ache of his overstrained eyes even the soaring arena around him with the thousands of spectators were trivialities not worth thinking about",
            "his instant panic was followed by a small sharp blow high on his chest",
        ]
        self.assertListEqual(predicted_trans, EXPECTED_TRANSCRIPTIONS)

    @unittest.skipIf(torch_device != "cpu", "cannot make deterministic on GPU")
    def test_inference_integration(self):
        model = Wav2Vec2ForPreTraining.from_pretrained("facebook/wav2vec2-base")
        model.to(torch_device)
        feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained("facebook/wav2vec2-base")
        input_speech = self._load_datasamples(2)

        inputs_dict = feature_extractor(input_speech, return_tensors="pt", padding=True)

        features_shape = (
            inputs_dict["input_values"].shape[0],
            model._get_feat_extract_output_lengths(torch.tensor(inputs_dict["input_values"].shape[1])),
        )

        np.random.seed(4)
        mask_time_indices = _compute_mask_indices(
            features_shape,
            model.config.mask_time_prob,
            model.config.mask_time_length,
            min_masks=2,
        )
        mask_time_indices = torch.from_numpy(mask_time_indices).to(torch_device)

        with torch.no_grad():
            outputs = model(
                inputs_dict.input_values.to(torch_device),
                mask_time_indices=mask_time_indices,
            )

        # compute cosine similarity
        cosine_sim = torch.cosine_similarity(outputs.projected_states, outputs.projected_quantized_states, dim=-1)

        # retrieve cosine sim of masked features
        cosine_sim_masked = cosine_sim[mask_time_indices]

        # cosine similarity of model is all > 0.5 as model is
        # pre-trained on contrastive loss
        # fmt: off
        expected_cosine_sim_masked = torch.tensor([
            0.8523, 0.5860, 0.6905, 0.5557, 0.7456, 0.5249, 0.6639, 0.7654, 0.7565,
            0.8167, 0.8222, 0.7960, 0.8034, 0.8166, 0.8310, 0.8263, 0.8274, 0.8258,
            0.8179, 0.8412, 0.8536, 0.5098, 0.4728, 0.6461, 0.4498, 0.6002, 0.5774,
            0.6457, 0.7123, 0.5668, 0.6866, 0.4960, 0.6293, 0.7423, 0.7419, 0.7526,
            0.7768, 0.4898, 0.5393, 0.8183
        ], device=torch_device)
        # fmt: on

        self.assertTrue(torch.allclose(cosine_sim_masked, expected_cosine_sim_masked, atol=1e-3))

    def test_inference_pretrained(self):
        model = Wav2Vec2ForPreTraining.from_pretrained("facebook/wav2vec2-base")
        model.to(torch_device)
        feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(
            "facebook/wav2vec2-base", return_attention_mask=True
        )
        input_speech = self._load_datasamples(2)

        inputs_dict = feature_extractor(input_speech, return_tensors="pt", padding=True)

        features_shape = (
            inputs_dict["input_values"].shape[0],
            model._get_feat_extract_output_lengths(torch.tensor(inputs_dict["input_values"].shape[1])),
        )

        torch.manual_seed(0)
        mask_time_indices = _compute_mask_indices(
            features_shape,
            model.config.mask_time_prob,
            model.config.mask_time_length,
            min_masks=2,
        )
        mask_time_indices = torch.from_numpy(mask_time_indices).to(torch_device)

        with torch.no_grad():
            outputs = model(
                inputs_dict.input_values.to(torch_device),
                attention_mask=inputs_dict.attention_mask.to(torch_device),
                mask_time_indices=mask_time_indices,
            )

        # compute cosine similarity
        cosine_sim = torch.cosine_similarity(outputs.projected_states, outputs.projected_quantized_states, dim=-1)

        # retrieve cosine sim of masked features
        cosine_sim_masked = cosine_sim[mask_time_indices]

        # ... now compare to randomly initialized model

        config = Wav2Vec2Config.from_pretrained("facebook/wav2vec2-base")
        model_rand = Wav2Vec2ForPreTraining(config).to(torch_device).eval()

        with torch.no_grad():
            outputs_rand = model_rand(
                inputs_dict.input_values.to(torch_device),
                attention_mask=inputs_dict.attention_mask.to(torch_device),
                mask_time_indices=mask_time_indices,
            )

        # compute cosine similarity
        cosine_sim_rand = torch.cosine_similarity(
            outputs_rand.projected_states, outputs_rand.projected_quantized_states, dim=-1
        )

        # retrieve cosine sim of masked features
        cosine_sim_masked_rand = cosine_sim_rand[mask_time_indices]

        # a pretrained wav2vec2 model has learned to predict the quantized latent states
        # => the cosine similarity between quantized states and predicted states > 0.5
        # a random wav2vec2 model has not learned to predict the quantized latent states
        # => the cosine similarity between quantized states and predicted states is very likely < 0.1
        self.assertTrue(cosine_sim_masked.mean().item() - 5 * cosine_sim_masked_rand.mean().item() > 0)

    @unittest.skipIf(torch_device != "cpu", "cannot make deterministic on GPU")
    def test_loss_pretraining(self):
        model = Wav2Vec2ForPreTraining.from_pretrained(
            "facebook/wav2vec2-base",
            attention_dropout=0.0,
            feat_proj_dropout=0.0,
            hidden_dropout=0.0,
            layerdrop=0.0,
        )
        model.to(torch_device).train()

        feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(
            "facebook/wav2vec2-base", return_attention_mask=True
        )
        input_speech = self._load_datasamples(2)

        inputs_dict = feature_extractor(input_speech, return_tensors="pt", padding=True)

        features_shape = (
            inputs_dict["input_values"].shape[0],
            model._get_feat_extract_output_lengths(inputs_dict["input_values"].shape[1]),
        )

        torch.manual_seed(0)
        np.random.seed(0)

        mask_time_indices = _compute_mask_indices(
            features_shape,
            model.config.mask_time_prob,
            model.config.mask_time_length,
            min_masks=2,
        )
        sampled_negative_indices = _sample_negative_indices(
            mask_time_indices.shape, model.config.num_negatives, mask_time_indices
        )

        mask_time_indices = torch.from_numpy(mask_time_indices).to(torch_device)
        sampled_negative_indices = torch.from_numpy(sampled_negative_indices).to(torch_device)

        with torch.no_grad():
            outputs = model(
                inputs_dict.input_values.to(torch_device),
                attention_mask=inputs_dict.attention_mask.to(torch_device),
                mask_time_indices=mask_time_indices,
                sampled_negative_indices=sampled_negative_indices,
            )

        # check diversity loss
        num_codevectors = model.config.num_codevectors_per_group * model.config.num_codevector_groups
        diversity_loss = (num_codevectors - outputs.codevector_perplexity) / num_codevectors
        self.assertTrue(abs(diversity_loss.item() - 0.9538) < 1e-3)

        # check overall loss (contrastive loss + diversity loss)
        expected_loss = 116.7094

        self.assertTrue(abs(outputs.loss.item() - expected_loss) < 1e-3)

    def test_inference_keyword_spotting(self):
        model = Wav2Vec2ForSequenceClassification.from_pretrained("superb/wav2vec2-base-superb-ks").to(torch_device)
        processor = Wav2Vec2FeatureExtractor.from_pretrained("superb/wav2vec2-base-superb-ks")
        input_data = self._load_superb("ks", 4)
        inputs = processor(input_data["speech"], return_tensors="pt", padding=True)

        input_values = inputs.input_values.to(torch_device)
        attention_mask = inputs.attention_mask.to(torch_device)
        with torch.no_grad():
            outputs = model(input_values, attention_mask=attention_mask)
        predicted_logits, predicted_ids = torch.max(outputs.logits, dim=-1)

        expected_labels = [7, 6, 10, 9]
        # s3prl logits for the same batch
        expected_logits = torch.tensor([6.1186, 11.8961, 10.2931, 6.0898], device=torch_device)

        self.assertListEqual(predicted_ids.tolist(), expected_labels)
        self.assertTrue(torch.allclose(predicted_logits, expected_logits, atol=1e-2))

    def test_inference_intent_classification(self):
        model = Wav2Vec2ForSequenceClassification.from_pretrained("superb/wav2vec2-base-superb-ic").to(torch_device)
        processor = Wav2Vec2FeatureExtractor.from_pretrained("superb/wav2vec2-base-superb-ic")
        input_data = self._load_superb("ic", 4)
        inputs = processor(input_data["speech"], return_tensors="pt", padding=True)

        input_values = inputs.input_values.to(torch_device)
        attention_mask = inputs.attention_mask.to(torch_device)
        with torch.no_grad():
            outputs = model(input_values, attention_mask=attention_mask)

        predicted_logits_action, predicted_ids_action = torch.max(outputs.logits[:, :6], dim=-1)
        predicted_logits_object, predicted_ids_object = torch.max(outputs.logits[:, 6:20], dim=-1)
        predicted_logits_location, predicted_ids_location = torch.max(outputs.logits[:, 20:24], dim=-1)

        expected_labels_action = [0, 0, 2, 3]
        expected_logits_action = torch.tensor([0.4568, 11.0848, 1.6621, 9.3841], device=torch_device)
        expected_labels_object = [3, 10, 3, 4]
        expected_logits_object = torch.tensor([1.5322, 10.7094, 5.2469, 22.1318], device=torch_device)
        expected_labels_location = [0, 0, 0, 1]
        expected_logits_location = torch.tensor([1.5335, 6.5096, 10.5704, 11.0569], device=torch_device)

        self.assertListEqual(predicted_ids_action.tolist(), expected_labels_action)
        self.assertListEqual(predicted_ids_object.tolist(), expected_labels_object)
        self.assertListEqual(predicted_ids_location.tolist(), expected_labels_location)

        self.assertTrue(torch.allclose(predicted_logits_action, expected_logits_action, atol=1e-2))
        self.assertTrue(torch.allclose(predicted_logits_object, expected_logits_object, atol=1e-2))
        self.assertTrue(torch.allclose(predicted_logits_location, expected_logits_location, atol=1e-2))

    def test_inference_speaker_identification(self):
        model = Wav2Vec2ForSequenceClassification.from_pretrained("superb/wav2vec2-base-superb-sid").to(torch_device)
        processor = Wav2Vec2FeatureExtractor.from_pretrained("superb/wav2vec2-base-superb-sid")
        input_data = self._load_superb("si", 4)

        output_logits = []
        with torch.no_grad():
            for example in input_data["speech"]:
                input = processor(example, return_tensors="pt", padding=True)
                output = model(input.input_values.to(torch_device), attention_mask=None)
                output_logits.append(output.logits[0])
        output_logits = torch.stack(output_logits)
        predicted_logits, predicted_ids = torch.max(output_logits, dim=-1)

        expected_labels = [251, 1, 1, 3]
        # s3prl logits for the same batch
        expected_logits = torch.tensor([37.5627, 71.6362, 64.2419, 31.7778], device=torch_device)

        self.assertListEqual(predicted_ids.tolist(), expected_labels)
        self.assertTrue(torch.allclose(predicted_logits, expected_logits, atol=1e-2))

    def test_inference_emotion_recognition(self):
        model = Wav2Vec2ForSequenceClassification.from_pretrained("superb/wav2vec2-base-superb-er").to(torch_device)
        processor = Wav2Vec2FeatureExtractor.from_pretrained("superb/wav2vec2-base-superb-er")
        input_data = self._load_superb("er", 4)
        inputs = processor(input_data["speech"], return_tensors="pt", padding=True)

        input_values = inputs.input_values.to(torch_device)
        attention_mask = inputs.attention_mask.to(torch_device)
        with torch.no_grad():
            outputs = model(input_values, attention_mask=attention_mask)
        predicted_logits, predicted_ids = torch.max(outputs.logits, dim=-1)

        expected_labels = [1, 1, 2, 2]
        # s3prl logits for the same batch
        expected_logits = torch.tensor([2.1722, 3.0779, 8.0287, 6.6797], device=torch_device)

        self.assertListEqual(predicted_ids.tolist(), expected_labels)
        self.assertTrue(torch.allclose(predicted_logits, expected_logits, atol=1e-2))

    def test_phoneme_recognition(self):
        model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-lv-60-espeak-cv-ft").to(torch_device)
        processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-lv-60-espeak-cv-ft")

        input_speech = self._load_datasamples(4)

        inputs = processor(input_speech, return_tensors="pt", padding=True)

        input_values = inputs.input_values.to(torch_device)
        attention_mask = inputs.attention_mask.to(torch_device)

        with torch.no_grad():
            logits = model(input_values, attention_mask=attention_mask).logits

        predicted_ids = torch.argmax(logits, dim=-1)
        predicted_trans = processor.batch_decode(predicted_ids)

        EXPECTED_TRANSCRIPTIONS = [
            "ɐ m æ n s ɛ d t ə ð ə j uː n ɪ v ɚ s s ɚ aɪ ɛ ɡ z ɪ s t",
            "s w ɛ t k ʌ v ɚ d b ɹ iː ɔ n z b ɑː d i t ɹ ɪ k l ɪ ŋ ɪ n t ə ð ə t aɪ t l oɪ n k l ɑː θ ð æ w ʌ z ð ɪ oʊ n l i ɡ ɑːɹ m ə n t h iː w ɔːɹ",
            "ð ə k aɪ t ɔ n h ɪ z tʃ ɛ s t s t ɪ l d ɹ ɪ p ɪ ŋ b l ʌ d ð ɪ eɪ k ʌ v h ɪ z oʊ v ɚ s t ɹ eɪ n d aɪ z iː v ə n ð ə s ɔːɹ ɹ ɪ ŋ ɐ ɹ iː n ɐ ɚ ɹ aʊ n d h ɪ m w ɪ ð ə θ aʊ z ə n d z ʌ v s p ɛ k t eɪ ɾ ɚ z w ɜː t ɹ ɪ v ɪ æ l ᵻ ɾ i z n ɑː t w ɜː θ θ ɪ ŋ k ɪ ŋ ɐ b aʊ t",
            "h ɪ z ɪ n s t ə n t v p æ n ɪ k w ʌ z f ɑː l oʊ d b aɪ ɐ s m ɔː l ʃ ɑːɹ p b l oʊ h aɪ ɔ n h ɪ z tʃ ɛ s t",
        ]
        # should correspond to =>:
        # [
        # "a man said to the universe sir i exist",
        # "sweat covered brion's body trickling into the tight loin cloth that was the only garment he wore",
        # "the cut on his chest still dripping blood the ache of his overstrained eyes even the soaring arena around him with the thousands of spectators were trivialities not worth thinking about",
        # "his instant panic was followed by a small sharp blow high on his chest",
        # ]
        self.assertListEqual(predicted_trans, EXPECTED_TRANSCRIPTIONS)

    @require_pyctcdecode
    @require_torchaudio
    def test_wav2vec2_with_lm(self):
        ds = load_dataset("common_voice", "es", split="test", streaming=True)
        sample = next(iter(ds))

        resampled_audio = torchaudio.functional.resample(
            torch.tensor(sample["audio"]["array"]), 48_000, 16_000
        ).numpy()

        model = Wav2Vec2ForCTC.from_pretrained("patrickvonplaten/wav2vec2-large-xlsr-53-spanish-with-lm").to(
            torch_device
        )
        processor = Wav2Vec2ProcessorWithLM.from_pretrained("patrickvonplaten/wav2vec2-large-xlsr-53-spanish-with-lm")

        input_values = processor(resampled_audio, return_tensors="pt").input_values

        with torch.no_grad():
            logits = model(input_values.to(torch_device)).logits

        transcription = processor.batch_decode(logits.cpu().numpy()).text

        self.assertEqual(transcription[0], "bien y qué regalo vas a abrir primero")
