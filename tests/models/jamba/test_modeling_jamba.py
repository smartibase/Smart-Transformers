# coding=utf-8
# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
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
""" Testing suite for the PyTorch Jamba model. """
import math
import tempfile
import unittest

import pytest

from transformers import JambaConfig, is_torch_available
from transformers.testing_utils import (
    require_bitsandbytes,
    require_flash_attn,
    require_torch,
    require_torch_gpu,
    slow,
    torch_device,
)

from ...generation.test_utils import GenerationTesterMixin
from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin, _config_zero_init, ids_tensor, random_attention_mask
from ...test_pipeline_mixin import PipelineTesterMixin


if is_torch_available():
    import torch

    from transformers import (
        JambaForCausalLM,
        JambaForSequenceClassification,
        JambaModel,
    )
    from transformers.models.jamba.modeling_jamba import (
        JambaAttentionDecoderLayer,
        JambaMambaDecoderLayer,
    )


class JambaModelTester:
    def __init__(
        self,
        parent,
        batch_size=13,
        seq_length=7,
        is_training=True,
        use_input_mask=True,
        use_labels=True,
        vocab_size=99,
        hidden_size=32,
        num_hidden_layers=5,
        attn_layer_offset=1,
        attn_layer_period=8,
        num_attention_heads=4,
        num_key_value_heads=2,
        intermediate_size=37,
        hidden_act="gelu",
        hidden_dropout_prob=0.1,
        attention_probs_dropout_prob=0.1,
        max_position_embeddings=512,
        type_vocab_size=16,
        type_sequence_label_size=2,
        initializer_range=0.02,
        num_labels=3,
        num_choices=4,
        scope=None,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.seq_length = seq_length
        self.is_training = is_training
        self.use_input_mask = use_input_mask
        self.use_labels = use_labels
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.attn_layer_offset = attn_layer_offset
        self.attn_layer_period = attn_layer_period
        self.num_attention_heads = num_attention_heads
        self.num_key_value_heads = num_key_value_heads
        self.intermediate_size = intermediate_size
        self.hidden_act = hidden_act
        self.hidden_dropout_prob = hidden_dropout_prob
        self.attention_probs_dropout_prob = attention_probs_dropout_prob
        self.max_position_embeddings = max_position_embeddings
        self.type_vocab_size = type_vocab_size
        self.type_sequence_label_size = type_sequence_label_size
        self.initializer_range = initializer_range
        self.num_labels = num_labels
        self.num_choices = num_choices
        self.scope = scope

    def prepare_config_and_inputs(self):
        input_ids = ids_tensor([self.batch_size, self.seq_length], self.vocab_size)

        input_mask = None
        if self.use_input_mask:
            input_mask = random_attention_mask([self.batch_size, self.seq_length])

        sequence_labels = None
        token_labels = None
        choice_labels = None
        if self.use_labels:
            sequence_labels = ids_tensor([self.batch_size], self.type_sequence_label_size)
            token_labels = ids_tensor([self.batch_size, self.seq_length], self.num_labels)
            choice_labels = ids_tensor([self.batch_size], self.num_choices)

        config = self.get_config()

        return config, input_ids, input_mask, sequence_labels, token_labels, choice_labels

    def get_config(self):
        return JambaConfig(
            vocab_size=self.vocab_size,
            hidden_size=self.hidden_size,
            num_hidden_layers=self.num_hidden_layers,
            attn_layer_offset=self.attn_layer_offset,
            attn_layer_period=self.attn_layer_period,
            num_attention_heads=self.num_attention_heads,
            num_key_value_heads=self.num_key_value_heads,
            intermediate_size=self.intermediate_size,
            hidden_act=self.hidden_act,
            hidden_dropout_prob=self.hidden_dropout_prob,
            attention_probs_dropout_prob=self.attention_probs_dropout_prob,
            max_position_embeddings=self.max_position_embeddings,
            type_vocab_size=self.type_vocab_size,
            is_decoder=True,
            initializer_range=self.initializer_range,
            use_mamba_kernels=False,
            num_experts=2,
            calc_logits_for_entire_prompt=True,
        )

    def prepare_config_and_inputs_for_decoder(self):
        (
            config,
            input_ids,
            input_mask,
            sequence_labels,
            token_labels,
            choice_labels,
        ) = self.prepare_config_and_inputs()

        config.is_decoder = True

        return (
            config,
            input_ids,
            input_mask,
            sequence_labels,
            token_labels,
            choice_labels,
        )

    def create_and_check_model(self, config, input_ids, input_mask, sequence_labels, token_labels, choice_labels):
        model = JambaModel(config=config)
        model.to(torch_device)
        model.eval()
        result = model(input_ids, attention_mask=input_mask)
        result = model(input_ids)
        self.parent.assertEqual(result.last_hidden_state.shape, (self.batch_size, self.seq_length, self.hidden_size))

    def create_and_check_for_causal_lm(
        self,
        config,
        input_ids,
        input_mask,
        sequence_labels,
        token_labels,
        choice_labels,
    ):
        model = JambaForCausalLM(config=config)
        model.to(torch_device)
        model.eval()
        result = model(input_ids, attention_mask=input_mask, labels=token_labels)
        result = model(input_ids, attention_mask=input_mask)
        result = model(input_ids, labels=token_labels)
        result = model(input_ids)
        self.parent.assertEqual(result.logits.shape, (self.batch_size, self.seq_length, self.vocab_size))

    def create_and_check_decoder_model_past_large_inputs(
        self,
        config,
        input_ids,
        input_mask,
        sequence_labels,
        token_labels,
        choice_labels,
    ):
        config.is_decoder = True
        config.add_cross_attention = True
        model = JambaForCausalLM(config=config)
        model.to(torch_device)
        model.eval()

        # first forward pass
        outputs = model(
            input_ids,
            attention_mask=input_mask,
            use_cache=True,
        )
        past_key_values = outputs.past_key_values

        # create hypothetical multiple next token and extent to next_input_ids
        next_tokens = ids_tensor((self.batch_size, 3), config.vocab_size)
        next_mask = ids_tensor((self.batch_size, 3), vocab_size=2)

        # append to next input_ids and
        next_input_ids = torch.cat([input_ids, next_tokens], dim=-1)
        next_attention_mask = torch.cat([input_mask, next_mask], dim=-1)

        output_from_no_past = model(
            next_input_ids,
            attention_mask=next_attention_mask,
            output_hidden_states=True,
        )["hidden_states"][0]
        output_from_past = model(
            next_tokens,
            attention_mask=next_attention_mask,
            past_key_values=past_key_values,
            output_hidden_states=True,
        )["hidden_states"][0]

        # select random slice
        random_slice_idx = ids_tensor((1,), output_from_past.shape[-1]).item()
        output_from_no_past_slice = output_from_no_past[:, -3:, random_slice_idx].detach()
        output_from_past_slice = output_from_past[:, :, random_slice_idx].detach()

        self.parent.assertTrue(output_from_past_slice.shape[1] == next_tokens.shape[1])

        # test that outputs are equal for slice
        self.parent.assertTrue(torch.allclose(output_from_past_slice, output_from_no_past_slice, atol=1e-3))

    def create_and_check_for_sequence_classification(
        self, config, input_ids, input_mask, sequence_labels, token_labels, choice_labels
    ):
        config.num_labels = self.num_labels
        model = JambaForSequenceClassification(config)
        model.to(torch_device)
        model.eval()
        result = model(input_ids, attention_mask=input_mask, labels=sequence_labels)
        self.parent.assertEqual(result.logits.shape, (self.batch_size, self.num_labels))

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        (
            config,
            input_ids,
            input_mask,
            sequence_labels,
            token_labels,
            choice_labels,
        ) = config_and_inputs
        inputs_dict = {"input_ids": input_ids, "attention_mask": input_mask}
        return config, inputs_dict


@require_torch
class JambaModelTest(ModelTesterMixin, GenerationTesterMixin, PipelineTesterMixin, unittest.TestCase):
    all_model_classes = (
        (
            JambaModel,
            JambaForCausalLM,
            JambaForSequenceClassification,
        )
        if is_torch_available()
        else ()
    )
    all_generative_model_classes = (JambaForCausalLM,) if is_torch_available() else ()
    pipeline_model_mapping = (
        {
            "feature-extraction": JambaModel,
            "text-classification": JambaForSequenceClassification,
            "text-generation": JambaForCausalLM,
            "zero-shot": JambaForSequenceClassification,
        }
        if is_torch_available()
        else {}
    )
    test_headmasking = False
    test_pruning = False

    def setUp(self):
        self.model_tester = JambaModelTester(self)
        self.config_tester = ConfigTester(self, config_class=JambaConfig, hidden_size=37)

    def test_config(self):
        self.config_tester.run_common_tests()

    def test_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model(*config_and_inputs)

    def test_for_casual_lm(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_for_causal_lm(*config_and_inputs)

    def test_for_sequence_classification(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_for_sequence_classification(*config_and_inputs)

    def test_decoder_model_past_with_large_inputs(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs_for_decoder()
        self.model_tester.create_and_check_decoder_model_past_large_inputs(*config_and_inputs)

    def test_load_balancing_loss(self):
        r"""
        Let's make sure we can actually compute the loss and do a backward on it.
        """
        config, input_dict = self.model_tester.prepare_config_and_inputs_for_common()
        config.num_labels = 3
        config.num_experts = 16
        config.output_router_logits = True
        input_ids = input_dict["input_ids"]
        attention_mask = input_ids.ne(config.pad_token_id).to(torch_device)
        model = JambaForCausalLM(config)
        model.to(torch_device)
        model.eval()
        result = model(input_ids, attention_mask=attention_mask)
        bs, seqlen = input_ids.shape
        self.assertEqual(result.router_logits[0].shape, (bs * seqlen, config.num_experts))
        torch.testing.assert_close(result.aux_loss.cpu(), torch.tensor(2, dtype=torch.float32), rtol=1e-2, atol=1e-2)

        # First, we make sure that adding padding tokens doesn't change the loss
        # loss(input_ids, attention_mask=None) == loss(input_ids + padding, attention_mask=attention_mask_with_padding)
        pad_length = 1000
        # Add padding tokens to input_ids
        padding_block = config.pad_token_id * torch.ones(input_ids.shape[0], pad_length, dtype=torch.int32).to(
            torch_device
        )
        padded_input_ids = torch.cat((padding_block, input_ids), dim=1)  # this is to simulate padding to the left
        padded_attention_mask = padded_input_ids.ne(config.pad_token_id).to(torch_device)

        padded_result = model(padded_input_ids, attention_mask=padded_attention_mask)
        torch.testing.assert_close(result.aux_loss.cpu(), padded_result.aux_loss.cpu(), rtol=1e-4, atol=1e-4)

        # We make sure that the loss of including padding tokens != the loss without padding tokens
        # if attention_mask=None --> we don't exclude padding tokens
        include_padding_result = model(padded_input_ids, attention_mask=None)

        # This is to mimic torch.testing.assert_not_close
        self.assertNotAlmostEqual(include_padding_result.aux_loss.item(), result.aux_loss.item())

    def test_greedy_generate_with_logits_only_for_last_prompt_token(self):
        r"""
        Adapted from test_greedy_generate of GenerationTesterMixin, just changing config.calc_logits_for_entire_prompt
        to `False`
        """
        for model_class in self.all_generative_model_classes:
            config, input_ids, attention_mask, max_length = self._get_input_ids_and_config()
            config.calc_logits_for_entire_prompt = False

            model = model_class(config).to(torch_device).eval()
            output_generate = self._greedy_generate(
                model=model, input_ids=input_ids, attention_mask=attention_mask, max_length=max_length
            )

            self.assertTrue(output_generate.shape[-1] == max_length)

    def test_initialization(self):
        r"""
        Overriding the test_initialization test as the A_log and D params of the Mamba block are initialized differently
        """
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        configs_no_init = _config_zero_init(config)
        for model_class in self.all_model_classes:
            model = model_class(config=configs_no_init)
            for name, param in model.named_parameters():
                if param.requires_grad:
                    if "A_log" in name:
                        A = torch.arange(1, config.mamba_d_state + 1, dtype=torch.float32)[None, :]
                        self.assertTrue(torch.allclose(param.data, torch.log(A), atol=1e-5, rtol=1e-5))
                    elif "D" in name:
                        # check if it's a ones like
                        self.assertTrue(torch.allclose(param.data, torch.ones_like(param.data), atol=1e-5, rtol=1e-5))
                    else:
                        self.assertIn(
                            ((param.data.mean() * 1e9).round() / 1e9).item(),
                            [0.0, 1.0],
                            msg=f"Parameter {name} of model {model_class} seems not properly initialized",
                        )

    def test_mismatched_shapes_have_properly_initialized_weights(self):
        r"""
        Overriding the test_mismatched_shapes_have_properly_initialized_weights test because A_log and D params of the
        Mamba block are initialized differently and we tested that in test_initialization
        """
        self.skipTest("Cumbersome and redundant for Jamba")

    def test_attention_outputs(self):
        r"""
        Overriding the test_attention_outputs test as the Jamba model outputs attention only for its attention layers
        """
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        config.return_dict = True

        seq_len = getattr(self.model_tester, "seq_length", None)
        encoder_seq_length = getattr(self.model_tester, "encoder_seq_length", seq_len)
        encoder_key_length = getattr(self.model_tester, "key_length", encoder_seq_length)

        expected_num_attentions = math.ceil(
            (self.model_tester.num_hidden_layers - self.model_tester.attn_layer_offset)
            / self.model_tester.attn_layer_period
        )

        for model_class in self.all_model_classes:
            inputs_dict["output_attentions"] = True
            inputs_dict["output_hidden_states"] = False
            config.return_dict = True
            model = model_class(config)
            model.to(torch_device)
            model.eval()

            with torch.no_grad():
                outputs = model(**self._prepare_for_class(inputs_dict, model_class))
            attentions = outputs.attentions
            self.assertEqual(len(attentions), expected_num_attentions)

            # check that output_attentions also work using config
            del inputs_dict["output_attentions"]
            config.output_attentions = True
            model = model_class(config)
            model.to(torch_device)
            model.eval()
            with torch.no_grad():
                outputs = model(**self._prepare_for_class(inputs_dict, model_class))
            attentions = outputs.attentions
            self.assertEqual(len(attentions), expected_num_attentions)

            self.assertListEqual(
                list(attentions[0].shape[-3:]),
                [self.model_tester.num_attention_heads, encoder_seq_length, encoder_key_length],
            )
            out_len = len(outputs)

            # Check attention is always last and order is fine
            inputs_dict["output_attentions"] = True
            inputs_dict["output_hidden_states"] = True
            model = model_class(config)
            model.to(torch_device)
            model.eval()
            with torch.no_grad():
                outputs = model(**self._prepare_for_class(inputs_dict, model_class))

            added_hidden_states = 1
            self.assertEqual(out_len + added_hidden_states, len(outputs))

            self_attentions = outputs.attentions

            self.assertEqual(len(self_attentions), expected_num_attentions)
            self.assertListEqual(
                list(self_attentions[0].shape[-3:]),
                [self.model_tester.num_attention_heads, encoder_seq_length, encoder_key_length],
            )

    def test_past_key_values_format(self):
        r"""
        Overriding the test_past_key_values_format test as the Jamba model has a non-standard KV cache format: (1) it
        is a GQA model (2) it has mamba layers with different cache shapes
        """
        for model_class in self.all_generative_model_classes:
            config, inputs = self.model_tester.prepare_config_and_inputs_for_common()

            # If it doesn't support cache, pass the test
            if not hasattr(config, "use_cache"):
                self.skipTest("This model doesn't support caching")

            model = model_class(config).to(torch_device)
            if "use_cache" not in inputs:
                inputs["use_cache"] = True
            outputs = model(**inputs)

            # If "past_key_values" is not returned, pass the test (e.g. RWKV uses a different cache name and format)
            if "past_key_values" not in outputs:
                self.skipTest("This model doesn't return `past_key_values`")

            num_hidden_layers = (
                getattr(config, "decoder_layers", None)
                or getattr(config, "num_decoder_layers", None)
                or config.num_hidden_layers
            )
            num_attention_heads = getattr(config, "decoder_attention_heads", config.num_attention_heads)
            num_kv_heads = config.num_key_value_heads
            embed_dim = getattr(config, "d_model", config.hidden_size)
            per_head_embed_dim = embed_dim // num_attention_heads

            mamba_d_inner = embed_dim * config.mamba_expand
            mamba_d_state = config.mamba_d_state
            mamba_d_conv = config.mamba_d_conv

            past_kv = outputs["past_key_values"]
            self.assertEqual(len(past_kv), num_hidden_layers)

            # Decoder-only checks
            batch_size, seq_length = inputs["input_ids"].shape
            for i in range(num_hidden_layers):
                self.assertEqual(len(past_kv[0]), 2)  # K V for the decoder = 2
                if isinstance(model.model.layers[i], JambaAttentionDecoderLayer):
                    self.assertEqual(past_kv[i][0].shape, (batch_size, num_kv_heads, seq_length, per_head_embed_dim))
                    self.assertEqual(past_kv[i][1].shape, (batch_size, num_kv_heads, seq_length, per_head_embed_dim))
                elif isinstance(model.model.layers[i], JambaMambaDecoderLayer):
                    self.assertEqual(past_kv[i][0].shape, (batch_size, mamba_d_inner, 1, mamba_d_conv))
                    self.assertEqual(past_kv[i][1].shape, (batch_size, mamba_d_inner, 1, mamba_d_state))
                else:
                    self.fail(f"Unexpected layer type {model.model.layers[i]}")

    def test_left_padding_compatibility(self):
        r"""
        Overriding the test_left_padding_compatibility test as the mamba layers accentuate the numerical differences
        effect of the left padding discussed in the issue in the note. Using a more permissive tolerance value.
        """
        import inspect
        # NOTE: left-padding results in small numerical differences. This is expected.
        # See https://github.com/huggingface/transformers/issues/25420#issuecomment-1775317535

        # First, filter out models that don't support left padding - generative and decoder-only.
        # Jamba is a decoder-only architecture
        decoder_only_classes = self.all_generative_model_classes

        # Then, test left-padding
        def _prepare_model_kwargs(input_ids, attention_mask, signature):
            model_kwargs = {"input_ids": input_ids, "attention_mask": attention_mask}
            if "position_ids" in signature:
                position_ids = torch.cumsum(attention_mask, dim=-1) - 1
                position_ids.masked_fill_(attention_mask == 0, 1)
                model_kwargs["position_ids"] = position_ids
            if "cache_position" in signature:
                cache_position = torch.arange(input_ids.shape[-1], device=torch_device)
                model_kwargs["cache_position"] = cache_position
            return model_kwargs

        for model_class in decoder_only_classes:
            config, input_ids, attention_mask, _ = self._get_input_ids_and_config()
            model = model_class(config).to(torch_device).eval()
            signature = inspect.signature(model.forward).parameters.keys()

            # Without padding
            model_kwargs = _prepare_model_kwargs(input_ids, attention_mask, signature)
            next_logits_wo_padding = model(**model_kwargs).logits[:, -1, :]

            # With left-padding (length 32)
            pad_size = (input_ids.shape[0], 32)
            padding = torch.ones(pad_size, dtype=input_ids.dtype, device=torch_device) * config.pad_token_id
            padded_input_ids = torch.cat((padding, input_ids), dim=1)
            padded_attention_mask = torch.cat((torch.zeros_like(padding), attention_mask), dim=1)
            model_kwargs = _prepare_model_kwargs(padded_input_ids, padded_attention_mask, signature)
            next_logits_with_padding = model(**model_kwargs).logits[:, -1, :]

            # They should result in very similar logits
            self.assertTrue(torch.allclose(next_logits_wo_padding, next_logits_with_padding, atol=3e-3))

    def _check_past_key_values_for_generate(self, batch_size, past_key_values, seq_length, config, num_beam_groups=1):
        r"""
        Overriding the _check_past_key_values_for_generate function test as the Jamba model has a non-standard KV cache
        format - it has mamba layers with different cache shapes
        """
        self.assertIsInstance(past_key_values, tuple)
        self.assertListEqual(
            [isinstance(iter_past_key_values, tuple) for iter_past_key_values in past_key_values],
            [True] * len(past_key_values),
        )

        # (batch, head, seq_length, head_features)
        expected_attn_shape = (
            batch_size * num_beam_groups,
            config.num_key_value_heads if hasattr(config, "num_key_value_heads") else config.num_attention_heads,
            seq_length,
            config.hidden_size // config.num_attention_heads,
        )
        # (batch, mamba_inner, 1, d_conv)
        expected_mamba_conv_shape = (
            batch_size * num_beam_groups,
            config.hidden_size * config.mamba_expand,
            1,
            config.mamba_d_conv,
        )
        # (batch, mamba_inner, 1, d_state)
        expected_mamba_state_shape = (
            batch_size * num_beam_groups,
            config.hidden_size * config.mamba_expand,
            1,
            config.mamba_d_state,
        )

        def _is_attn_layer(idx, config):
            if (idx - config.attn_layer_offset) % config.attn_layer_period == 0:
                return True
            return False

        mamba_layer_idx = [_is_attn_layer(i, config) for i in range(len(past_key_values))].index(False)
        if past_key_values[mamba_layer_idx][0].shape[2] > 1:
            # special treatment for contrastive decoding which uses standard cache format also for mamba layers
            past_key_values = JambaModel._convert_to_jamba_cache(past_key_values)

        # check shape key, value
        self.assertListEqual(
            [layer_past_key_values[0].shape for layer_past_key_values in past_key_values],
            [
                expected_attn_shape if _is_attn_layer(i, config) else expected_mamba_conv_shape
                for i in range(len(past_key_values))
            ],
        )
        self.assertListEqual(
            [layer_past_key_values[1].shape for layer_past_key_values in past_key_values],
            [
                expected_attn_shape if _is_attn_layer(i, config) else expected_mamba_state_shape
                for i in range(len(past_key_values))
            ],
        )

    @require_flash_attn
    @require_torch_gpu
    @require_bitsandbytes
    @pytest.mark.flash_attn_test
    @slow
    def test_flash_attn_2_fp32_ln(self):
        r"""
        Overriding the test_flash_attn_2_fp32_ln test as the Jamba model, like Mixtral, doesn't support
        right padding + use cache with FA2
        """
        for model_class in self.all_generative_model_classes:
            config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
            model = model_class(config)

            with tempfile.TemporaryDirectory() as tmpdirname:
                model.save_pretrained(tmpdirname)

                dummy_input = inputs_dict[model.main_input_name]
                dummy_attention_mask = inputs_dict.get("attention_mask", torch.ones_like(dummy_input))
                # NOTE: Jamba does not support right padding + use_cache with FA2.
                dummy_attention_mask[:, -1] = 1

                model = model_class.from_pretrained(
                    tmpdirname,
                    torch_dtype=torch.float16,
                    attn_implementation="flash_attention_2",
                    low_cpu_mem_usage=True,
                    load_in_4bit=True,
                )

                for _, param in model.named_parameters():
                    # upcast only layer norms
                    if (param.dtype == torch.float16) or (param.dtype == torch.bfloat16):
                        param.data = param.data.to(torch.float32)

                _ = model(dummy_input)
                # with attention mask
                _ = model(dummy_input, attention_mask=dummy_attention_mask)

    @require_flash_attn
    @require_torch_gpu
    @pytest.mark.flash_attn_test
    @slow
    def test_flash_attn_2_generate_padding_right(self):
        r"""
        Overriding the test_flash_attn_2_generate_padding_right test as the Jamba model, like Mixtral, doesn't support
        right padding + use cache with FA2
        """
        import torch

        for model_class in self.all_generative_model_classes:
            config, _ = self.model_tester.prepare_config_and_inputs_for_common()
            model = model_class(config)

            with tempfile.TemporaryDirectory() as tmpdirname:
                model.save_pretrained(tmpdirname)
                model = model_class.from_pretrained(tmpdirname, torch_dtype=torch.float16, low_cpu_mem_usage=True).to(
                    torch_device
                )

                dummy_input = torch.LongTensor([[0, 2, 3, 4], [0, 2, 3, 4]]).to(torch_device)
                dummy_attention_mask = torch.LongTensor([[1, 1, 1, 1], [1, 1, 1, 0]]).to(torch_device)

                model.generate(dummy_input, attention_mask=dummy_attention_mask, max_new_tokens=1, do_sample=False)

                model = model_class.from_pretrained(
                    tmpdirname,
                    torch_dtype=torch.float16,
                    attn_implementation="flash_attention_2",
                    low_cpu_mem_usage=True,
                ).to(torch_device)

                with self.assertRaises(ValueError):
                    _ = model.generate(
                        dummy_input, attention_mask=dummy_attention_mask, max_new_tokens=1, do_sample=False
                    )

    @require_flash_attn
    @require_torch_gpu
    @pytest.mark.flash_attn_test
    @slow
    def test_flash_attn_2_generate_use_cache(self):
        r"""
        Overriding the test_flash_attn_2_generate_use_cache test as the Jamba model, like Mixtral, doesn't support
        right padding + use cache with FA2
        """
        import torch

        max_new_tokens = 30

        for model_class in self.all_generative_model_classes:
            config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

            dummy_input = inputs_dict[model_class.main_input_name]
            if dummy_input.dtype in [torch.float32, torch.bfloat16]:
                dummy_input = dummy_input.to(torch.float16)

            # make sure that all models have enough positions for generation
            if hasattr(config, "max_position_embeddings"):
                config.max_position_embeddings = max_new_tokens + dummy_input.shape[1] + 1

            model = model_class(config)

            with tempfile.TemporaryDirectory() as tmpdirname:
                model.save_pretrained(tmpdirname)

                dummy_attention_mask = inputs_dict.get("attention_mask", torch.ones_like(dummy_input))
                # NOTE: Jamba does not support right padding + use_cache with FA2.
                dummy_attention_mask[:, -1] = 1

                model = model_class.from_pretrained(
                    tmpdirname,
                    torch_dtype=torch.float16,
                    attn_implementation="flash_attention_2",
                    low_cpu_mem_usage=True,
                ).to(torch_device)

                # Just test that a large cache works as expected
                _ = model.generate(
                    dummy_input,
                    attention_mask=dummy_attention_mask,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    use_cache=True,
                )

    @require_flash_attn
    @require_torch_gpu
    @pytest.mark.flash_attn_test
    @slow
    def test_flash_attn_2_inference_padding_right(self):
        r"""
        Overriding the test_flash_attn_2_inference_padding_right test as the Jamba model, like Mixtral, doesn't support
        right padding + use cache with FA2
        """
        self.skipTest("Jamba flash attention does not support right padding")


@require_torch
@unittest.skip("Update once we have a tiny Jamba model")
class JambaModelIntegrationTest(unittest.TestCase):
    @slow
    def test_inference_masked_lm(self):
        model = JambaForCausalLM.from_pretrained("...")
        input_ids = torch.tensor([[0, 1, 2, 3, 4, 5]])
        output = model(input_ids)[0]

        # TODO Replace vocab size
        vocab_size = 32000

        expected_shape = torch.Size((1, 6, vocab_size))
        self.assertEqual(output.shape, expected_shape)

        # TODO Replace values below with what was printed above.
        expected_slice = torch.tensor(
            [[[-0.0483, 0.1188, -0.0313], [-0.0606, 0.1435, 0.0199], [-0.0235, 0.1519, 0.0175]]]
        )

        self.assertTrue(torch.allclose(output[:, :3, :3], expected_slice, atol=1e-4))
