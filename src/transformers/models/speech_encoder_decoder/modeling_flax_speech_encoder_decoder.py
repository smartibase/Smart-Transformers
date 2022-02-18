# coding=utf-8
# Copyright 2022 The HuggingFace Inc. team.
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
""" Classes to support Flax Speech-Encoder-Decoder architectures"""

import os
from typing import Optional, Tuple, Union

import flax.linen as nn
import jax
import jax.numpy as jnp
from flax.core.frozen_dict import FrozenDict, unfreeze
from jax import lax
from jax.random import PRNGKey

from ...configuration_utils import PretrainedConfig
from ...file_utils import add_start_docstrings, add_start_docstrings_to_model_forward, replace_return_docstrings
from ...modeling_flax_outputs import FlaxBaseModelOutput, FlaxCausalLMOutputWithCrossAttentions, FlaxSeq2SeqLMOutput
from ...modeling_flax_utils import FlaxPreTrainedModel
from ...utils import logging
from ..auto.configuration_auto import AutoConfig
from ..auto.modeling_flax_auto import FlaxAutoModel, FlaxAutoModelForCausalLM
from .configuration_speech_encoder_decoder import SpeechEncoderDecoderConfig


logger = logging.get_logger(__name__)

_CONFIG_FOR_DOC = "SpeechEncoderDecoderConfig"

SPEECH_ENCODER_DECODER_START_DOCSTRING = r"""
    This class can be used to initialize a speech-sequence-to-text-sequence model with any pretrained speech
    autoencoding model as the encoder and any pretrained text autoregressive model as the decoder. The encoder is
    loaded via [`~AutoModel.from_pretrained`] function and the decoder is loaded via
    [`~AutoModelForCausalLM.from_pretrained`] function. Cross-attention layers are automatically added to the decoder
    and should be fine-tuned on a downstream generative task, like summarization.

    The effectiveness of initializing sequence-to-sequence models with pretrained checkpoints for sequence generation
    tasks was shown in [Leveraging Pre-trained Checkpoints for Sequence Generation
    Tasks](https://arxiv.org/abs/1907.12461) by Sascha Rothe, Shashi Narayan, Aliaksei Severyn. Michael Matena, Yanqi
    Zhou, Wei Li, Peter J. Liu.

    Additionally, in [Large-Scale Self- and Semi-Supervised Learning for Speech
    Translation](https://arxiv.org/abs/2104.06678) it is shown how leveraging large pretrained speech models for speech
    translation yields a significant performance improvement.

    After such an Speech-Encoder Decoder model has been trained/fine-tuned, it can be saved/loaded just like any other
    models (see the examples for more information).

    This model inherits from [`FlaxPreTrainedModel`]. Check the superclass documentation for the generic methods the
    library implements for all its model (such as downloading or saving, resizing the input embeddings, pruning heads
    etc.)

    This model is also a Flax Linen
    [flax.nn.Module](https://flax.readthedocs.io/en/latest/_autosummary/flax.nn.module.html) subclass. Use it as a
    regular Flax Module and refer to the Flax documentation for all matter related to general usage and behavior.

    Parameters:
        config ([`SpeechEncoderDecoderConfig`]): Model configuration class with all the parameters of the model.
            Initializing with a config file does not load the weights associated with the model, only the
            configuration. Check out the [`~FlaxPreTrainedModel.from_pretrained`] method to load the model weights.
        dtype (`jax.numpy.dtype`, *optional*, defaults to `jax.numpy.float32`):
            The data type of the computation. Can be one of `jax.numpy.float32`, `jax.numpy.float16` (on GPUs) and
            `jax.numpy.bfloat16` (on TPUs).

            This can be used to enable mixed-precision training or half-precision inference on GPUs or TPUs. If
            specified all the computation will be performed with the given `dtype`.

            **Note that this only specifies the dtype of the computation and does not influence the dtype of model
            parameters.**

            If you wish to change the dtype of the model parameters, see [`~FlaxPreTrainedModel.to_fp16`] and
            [`~FlaxPreTrainedModel.to_bf16`].
"""

SPEECH_ENCODER_DECODER_INPUTS_DOCSTRING = r"""
    Args:
        inputs (`jnp.ndarray` of shape `(batch_size, sequence_length)` or `(batch_size, sequence_length, feature_dim)`, *optional*):
            Float values of input raw speech waveform or speech features. Values can be obtained by loading a *.flac*
            or *.wav* audio file into an array of type *List[float]* or a *numpy.ndarray*, *e.g.* via the soundfile
            library (*pip install soundfile*). To prepare the array into *inputs*, either the [`Wav2Vec2Processor`] or
            [`Speech2TextProcessor`] should be used for padding and conversion into a tensor of type
            *torch.FloatTensor*.
        attention_mask (`jnp.ndarray` of shape `(batch_size, sequence_length)`, *optional*):
            Mask to avoid performing attention on padding token indices. Mask values selected in `[0, 1]`:

            - 1 for tokens that are **not masked**,
            - 0 for tokens that are **masked**.

            [What are attention masks?](../glossary#attention-mask)
        decoder_input_ids (`jnp.ndarray` of shape `(batch_size, target_sequence_length)`, *optional*):
            Indices of decoder input sequence tokens in the vocabulary.

            Indices can be obtained using [`PreTrainedTokenizer`]. See [`PreTrainedTokenizer.encode`] and
            [`PreTrainedTokenizer.__call__`] for details.

            [What are input IDs?](../glossary#input-ids)

            If `past_key_values` is used, optionally only the last `decoder_input_ids` have to be input (see
            `past_key_values`).

            For training, `decoder_input_ids` are automatically created by the model by shifting the `labels` to the
            right, replacing -100 by the `pad_token_id` and prepending them with the `decoder_start_token_id`.
        decoder_attention_mask (`jnp.ndarray` of shape `(batch_size, target_sequence_length)`, *optional*):
            Default behavior: generate a tensor that ignores pad tokens in `decoder_input_ids`. Causal mask will also
            be used by default.

        TODO
"""

SPEECH_ENCODER_DECODER_ENCODE_INPUTS_DOCSTRING = """TODO"""

SPEECH_ENCODER_DECODER_DECODE_INPUTS_DOCSTRING = """TODO"""


# def shift_tokens_right necessary?
def shift_tokens_right():
    return


class FlaxSpeechEncoderDecoderModule(nn.Module):
    config: SpeechEncoderDecoderConfig
    dtype: jnp.dtype = jnp.float32

    def setup(self):
        encoder_config = self.config.encoder
        decoder_config = self.config.decoder

        # Copied from `modeling_hybrid_clip.py` with modifications.
        from ...models.auto.modeling_flax_auto import FLAX_MODEL_FOR_CAUSAL_LM_MAPPING, FLAX_MODEL_MAPPING

        encoder_module = FLAX_MODEL_MAPPING[encoder_config.__class__].module_class
        decoder_module = FLAX_MODEL_FOR_CAUSAL_LM_MAPPING[decoder_config.__class__].module_class

        self.encoder = encoder_module(encoder_config, dtype=self.dtype)
        self.decoder = decoder_module(decoder_config, dtype=self.dtype)

        # encoder outputs might need to be projected to different dimension for decoder
        if (
            self.encoder.config.hidden_size != self.decoder.config.hidden_size
            and self.decoder.config.cross_attention_hidden_size is None
        ):
            self.enc_to_dec_proj = nn.Dense(
                self.decoder.config.hidden_size,
                kernel_init=jax.nn.initializers.normal(self.decoder.config.initializer_range),
                dtype=self.dtype,
            )
        else:
            self.enc_to_dec_proj = None

    def _get_encoder_module(self):
        return self.encoder

    def _get_projection_module(self):
        return self.enc_to_dec_proj

    def _get_decoder_module(self):
        return self.decoder

    def freeze_feature_encoder(self):
        """
        Calling this function will disable the gradient computation for the feature encoder of the speech encoder
        in order that its parameters are not updated during training.
        """
        self.encoder.freeze_feature_encoder()

    def __call__(
        self,
        input_ids,
        attention_mask,
        decoder_input_ids,
        decoder_attention_mask,
        decoder_position_ids,
        mask_time_indices=None,
        output_attentions: bool = False,
        output_hidden_states: bool = False,
        return_dict: bool = True,
        deterministic: bool = True,
    ):

        encoder_outputs = self.encoder(
            input_ids,
            attention_mask=attention_mask,
            mask_time_indices=mask_time_indices,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            deterministic=deterministic,
        )

        encoder_hidden_states = encoder_outputs[0]

        # optionally project encoder_hidden_states
        if self.enc_to_dec_proj is not None:
            encoder_hidden_states = self.enc_to_dec_proj(encoder_hidden_states)

        # compute correct encoder attention mask? requires function _get_feature_vector_attention_mask to be added to the
        # flax script modeling_flax_wav2vec2.py
        decoder_outputs = self.decoder(
            input_ids=decoder_input_ids,
            attention_mask=decoder_attention_mask,
            position_ids=decoder_position_ids,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=attention_mask,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            deterministic=deterministic,
        )

        if not return_dict:
            return decoder_outputs + encoder_outputs

        return FlaxSeq2SeqLMOutput(
            logits=decoder_outputs.logits,
            decoder_hidden_states=decoder_outputs.hidden_states,
            decoder_attentions=decoder_outputs.attentions,
            cross_attentions=decoder_outputs.cross_attentions,
            encoder_last_hidden_state=encoder_outputs.last_hidden_state,
            encoder_hidden_states=encoder_outputs.hidden_states,
            encoder_attentions=encoder_outputs.attentions,
        )


@add_start_docstrings(SPEECH_ENCODER_DECODER_START_DOCSTRING)
class FlaxSpeechEncoderDecoderModel(FlaxPreTrainedModel):
    r"""
    [`FlaxSpeechEncoderDecoderModel`] is a generic model class that will be instantiated as a transformer architecture with
    the module (flax.nn.Module) of one of the base model classes of the library as encoder module and another one as
    decoder module when created with the :meth*~transformers.FlaxAutoModel.from_pretrained* class method for the
    encoder and :meth*~transformers.FlaxAutoModelForCausalLM.from_pretrained* class method for the decoder.
    """

    config_class = SpeechEncoderDecoderConfig
    base_model_prefix: str = "speech_encoder_decoder"
    module_class = FlaxSpeechEncoderDecoderModule

    def __init__(
        self,
        config: SpeechEncoderDecoderConfig,
        input_shape: Optional[Tuple] = None,
        seed: int = 0,
        dtype: jnp.dtype = jnp.float32,
        **kwargs
    ):
        if input_shape is None:
            input_shape = ((1, 1024), (1, 1024))

        if config.decoder.cross_attention_hidden_size is not None:
            # Raise ValueError or option to project enc to dec hidden_size (eg EncAdapterLayer)
            if config.decoder.cross_attention_hidden_size != config.encoder.hidden_size:
                raise ValueError(
                    "If `cross_attention_hidden_size` is specified in the decoder's configuration, "
                    "it has to be equal to the encoder's `hidden_size`. "
                    f"Got {config.decoder.cross_attention_hidden_size} for `config.decoder.cross_attention_hidden_size` "
                    f"and {config.encoder.hidden_size} for `config.encoder.hidden_size`."
                )

        module = self.module_class(config=config, dtype=dtype, **kwargs)
        super().__init__(config, module, input_shape=input_shape, seed=seed, dtype=dtype)

    def init_weights(self, rng: jax.random.PRNGKey, input_shape: Tuple) -> FrozenDict:
        encoder_input_shape, decoder_input_shape = input_shape

        # init input tensors
        input_ids = jnp.zeros(encoder_input_shape, dtype="i4")
        attention_mask = jnp.ones_like(input_ids)
        decoder_input_ids = jnp.zeros(decoder_input_shape, dtype="i4")
        decoder_attention_mask = jnp.ones_like(decoder_input_ids)

        batch_size, sequence_length = input_ids.shape

        decoder_batch_size, decoder_sequence_length = decoder_input_ids.shape
        if not decoder_batch_size == batch_size:
            raise ValueError(
                f"The inputs of encoder and decoder should have the same batch size, but got {batch_size} for encoder and {decoder_batch_size} for decoder."
            )
        decoder_position_ids = jnp.broadcast_to(
            jnp.arange(decoder_sequence_length)[None, :], (decoder_batch_size, decoder_sequence_length)
        )

        params_rng, dropout_rng = jax.random.split(rng)
        rngs = {"params": params_rng, "dropout": dropout_rng}

        return self.module.init(
            rngs, input_ids, attention_mask, decoder_input_ids, decoder_attention_mask, decoder_position_ids,
        )["params"]

    def init_cache(self, batch_size, max_length, encoder_outputs):
        r"""
        Args:
            batch_size (`int`):
                batch_size used for fast auto-regressive decoding. Defines the batch size of the initialized cache.
            max_length (`int`):
                maximum possible length for auto-regressive decoding. Defines the sequence length of the initialized
                cache.
            encoder_outputs (`Union[FlaxBaseModelOutput, tuple(tuple(jnp.ndarray)]`):
                `encoder_outputs` consists of (`last_hidden_state`, *optional*: `hidden_states`, *optional*:
                `attentions`). `last_hidden_state` of shape `(batch_size, sequence_length, hidden_size)`, *optional*)
                is a sequence of hidden-states at the output of the last layer of the encoder. Used in the
                cross-attention of the decoder.
        """
        # init input variables to retrieve cache
        decoder_input_ids = jnp.ones((batch_size, max_length), dtype="i4")
        decoder_attention_mask = jnp.ones_like(decoder_input_ids)
        decoder_position_ids = jnp.broadcast_to(
            jnp.arange(jnp.atleast_2d(decoder_input_ids).shape[-1]), decoder_input_ids.shape
        )

        def _decoder_forward(module, decoder_input_ids, decoder_attention_mask, decoder_position_ids, **kwargs):
            decoder_module = module._get_decoder_module()
            return decoder_module(
                input_ids=decoder_input_ids,
                attention_mask=decoder_attention_mask,
                position_ids=decoder_position_ids,
                **kwargs,
            )

        init_variables = self.module.init(
            jax.random.PRNGKey(0),
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
            decoder_position_ids=decoder_position_ids,
            encoder_hidden_states=encoder_outputs[0],
            init_cache=True,
            method=_decoder_forward,  # we only need to call the decoder to init the cache
        )
        return unfreeze(init_variables["cache"])

    @add_start_docstrings(SPEECH_ENCODER_DECODER_ENCODE_INPUTS_DOCSTRING)
    @replace_return_docstrings(output_type=FlaxBaseModelOutput, config_class=_CONFIG_FOR_DOC)
    def encode(
        self,
        input_ids: jnp.ndarray,
        attention_mask: Optional[jnp.ndarray] = None,
        mask_time_indices: Optional[jnp.ndarray] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        train: bool = False,
        params: dict = None,
        dropout_rng: PRNGKey = None,
    ):
        r"""
        Returns:

        Example:

        ```python
        >>> from transformers import FlaxSpeechEncoderDecoderModel

        >>> # initialize a wav2vec2-2-bart from pretrained wav2vec2 and bart models. Note that the cross-attention layers will be randomly initialized
        >>> model = FlaxSpeechEncoderDecoderModel.from_encoder_decoder_pretrained("facebook/wav2vec2-large-lv60", "facebook/bart-large")

        >>> inputs = jnp.ones((2, 5000), dtype=jnp.float32)
        >>> encoder_outputs = model.encode(inputs)
        ```"""
        output_attentions = output_attentions if output_attentions is not None else self.config.output_attentions
        output_hidden_states = (
            output_hidden_states if output_hidden_states is not None else self.config.output_hidden_states
        )
        return_dict = return_dict if return_dict is not None else self.config.return_dict

        if attention_mask is None:
            attention_mask = jnp.ones_like(input_ids)

        # Handle any PRNG if needed
        rngs = {}
        if dropout_rng is not None:
            rngs["dropout"] = dropout_rng

        def _encoder_forward(module, input_ids, attention_mask, **kwargs):
            encode_module = module._get_encoder_module()
            return encode_module(input_ids, attention_mask, **kwargs)

        outputs = self.module.apply(
            {"params": params or self.params},
            input_ids=jnp.array(input_ids, dtype="i4"),
            attention_mask=jnp.array(attention_mask, dtype="i4"),
            mask_time_indices=jnp.array(mask_time_indices, dtype="i4"),
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            deterministic=not train,
            rngs=rngs,
            method=_encoder_forward,
        )

        if return_dict:
            outputs = FlaxBaseModelOutput(
                last_hidden_state=outputs.last_hidden_state,
                hidden_states=outputs.hidden_states,
                attentions=outputs.attentions,
            )

        return outputs

    @add_start_docstrings(SPEECH_ENCODER_DECODER_DECODE_INPUTS_DOCSTRING)
    @replace_return_docstrings(output_type=FlaxCausalLMOutputWithCrossAttentions, config_class=_CONFIG_FOR_DOC)
    def decode(
        self,
        decoder_input_ids,
        encoder_outputs,
        encoder_attention_mask: Optional[jnp.ndarray] = None,
        decoder_attention_mask: Optional[jnp.ndarray] = None,
        decoder_position_ids: Optional[jnp.ndarray] = None,
        past_key_values: dict = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        train: bool = False,
        params: dict = None,
        dropout_rng: PRNGKey = None,
    ):
        r"""
        Returns:

        Example:

        ```python
        >>> from transformers import FlaxSpeechEncoderDecoderModel
        >>> import jax.numpy as jnp

        >>> # initialize a wav2vec2-2-bart from pretrained wav2vec2 and bart models. Note that the cross-attention layers will be randomly initialized
        >>> model = FlaxSpeechEncoderDecoderModel.from_encoder_decoder_pretrained("facebook/wav2vec2-large-lv60", "facebook/bart-large")

        >>> inputs = jnp.ones((2, 5000), dtype=jnp.float32)
        >>> encoder_outputs = model.encode(inputs)

        >>> decoder_start_token_id = model.config.decoder.bos_token_id
        >>> decoder_input_ids = jnp.ones((input_ids.shape[0], 1), dtype="i4") * decoder_start_token_id

        >>> outputs = model.decode(decoder_input_ids, encoder_outputs)
        >>> logits = outputs.logits
        ```"""
        output_attentions = output_attentions if output_attentions is not None else self.config.output_attentions
        output_hidden_states = (
            output_hidden_states if output_hidden_states is not None else self.config.output_hidden_states
        )
        return_dict = return_dict if return_dict is not None else self.config.return_dict

        encoder_hidden_states = encoder_outputs[0]
        if encoder_attention_mask is None:
            batch_size, sequence_length = encoder_hidden_states.shape[:2]
            encoder_attention_mask = jnp.ones((batch_size, sequence_length))

        batch_size, sequence_length = decoder_input_ids.shape
        if decoder_attention_mask is None:
            decoder_attention_mask = jnp.ones((batch_size, sequence_length))

        if decoder_position_ids is None:
            if past_key_values is not None:
                raise ValueError("Make sure to provide `decoder_position_ids` when passing `past_key_values`.")

            decoder_position_ids = jnp.broadcast_to(
                jnp.arange(sequence_length)[None, :], (batch_size, sequence_length)
            )

        # Handle any PRNG if needed
        rngs = {}
        if dropout_rng is not None:
            rngs["dropout"] = dropout_rng

        inputs = {"params": params or self.params}

        # if past_key_values are passed then cache is already initialized a private flag init_cache has to be
        # passed down to ensure cache is used. It has to be made sure that cache is marked as mutable so that
        # it can be changed by FlaxBartAttention module
        if past_key_values:
            inputs["cache"] = past_key_values
            mutable = ["cache"]
        else:
            mutable = False

        def _decoder_forward(
            module, decoder_input_ids, decoder_attention_mask, decoder_position_ids, encoder_hidden_states, **kwargs
        ):

            projection_module = module._get_projection_module()
            decoder_module = module._get_decoder_module()

            # optionally project encoder_hidden_states
            if projection_module is not None:
                encoder_hidden_states = projection_module(encoder_hidden_states)

            return decoder_module(
                decoder_input_ids, decoder_attention_mask, decoder_position_ids, encoder_hidden_states, **kwargs,
            )

        outputs = self.module.apply(
            inputs,
            decoder_input_ids=jnp.array(decoder_input_ids, dtype="i4"),
            decoder_attention_mask=jnp.array(decoder_attention_mask, dtype="i4"),
            decoder_position_ids=jnp.array(decoder_position_ids, dtype="i4"),
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=jnp.array(encoder_attention_mask, dtype="i4"),
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            deterministic=not train,
            rngs=rngs,
            mutable=mutable,
            method=_decoder_forward,
        )

        # add updated cache to model output
        if past_key_values is not None and return_dict:
            outputs, past = outputs
            outputs["past_key_values"] = unfreeze(past["cache"])
            return outputs
        elif past_key_values is not None and not return_dict:
            outputs, past = outputs
            outputs = outputs[:1] + (unfreeze(past["cache"]),) + outputs[1:]

        return outputs

    @add_start_docstrings_to_model_forward(SPEECH_ENCODER_DECODER_INPUTS_DOCSTRING)
    @replace_return_docstrings(output_type=FlaxSeq2SeqLMOutput, config_class=_CONFIG_FOR_DOC)
    def __call__(
        self,
        input_ids: jnp.ndarray,
        attention_mask: Optional[jnp.ndarray] = None,
        mask_time_indices: Optional[jnp.ndarray] = None,
        decoder_input_ids: Optional[jnp.ndarray] = None,
        decoder_attention_mask: Optional[jnp.ndarray] = None,
        decoder_position_ids: Optional[jnp.ndarray] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        train: bool = False,
        params: dict = None,
        dropout_rng: PRNGKey = None,
    ):
        r"""
        Returns:

        Examples:

        ```python
        >>> from transformers import FlaxSpeechEncoderDecoderModel, BartTokenizer

        >>> # load a fine-tuned wav2vec2-2-bart model
        >>> model = FlaxSpeechEncoderDecoderModel.from_pretrained("patrickvonplaten/wav2vec2-2-bart-large")
        >>> # load output tokenizer
        >>> tokenizer_output = BartTokenizer.from_pretrained("facebook/bart-large")

        >>> inputs = jnp.ones((2, 5000), dtype=jnp.float32)

        >>> # use bart's special bos, pad and eos tokens
        >>> model.config.decoder_start_token_id = model.decoder.config.bos_token_id
        >>> model.config.pad_token_id = model.decoder.config.pad_token_id
        >>> model.config.eos_token_id = model.decoder.config.eos_token_id

        >>> outputs = model.generate(inputs)
        # Assert something? More interesting input? dtype correct?
        ```
        """

        output_attentions = output_attentions if output_attentions is not None else self.config.output_attentions
        output_hidden_states = (
            output_hidden_states if output_hidden_states is not None else self.config.output_hidden_states
        )
        return_dict = return_dict if return_dict is not None else self.config.return_dict

        # prepare encoder inputs
        if attention_mask is None:
            attention_mask = jnp.ones_like(input_ids)

        # prepare decoder inputs
        if decoder_attention_mask is None:
            decoder_attention_mask = jnp.ones_like(decoder_input_ids)
        if decoder_position_ids is None:
            batch_size, sequence_length = decoder_input_ids.shape
            decoder_position_ids = jnp.broadcast_to(
                jnp.arange(sequence_length)[None, :], (batch_size, sequence_length)
            )

        # Handle any PRNG if needed
        rngs = {"dropout": dropout_rng} if dropout_rng is not None else {}

        return self.module.apply(
            {"params": params or self.params},
            input_ids=jnp.array(input_ids, dtype="i4"),
            attention_mask=jnp.array(attention_mask, dtype="i4"),
            mask_time_indices=jnp.array(mask_time_indices, dtype="i4"),
            decoder_input_ids=jnp.array(decoder_input_ids, dtype="i4"),
            decoder_attention_mask=jnp.array(decoder_attention_mask, dtype="i4"),
            decoder_position_ids=jnp.array(decoder_position_ids, dtype="i4"),
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            deterministic=not train,
            rngs=rngs,
        )

    def prepare_inputs_for_generation(
        self,
        decoder_input_ids,
        max_length,
        attention_mask: Optional[jnp.DeviceArray] = None,
        decoder_attention_mask: Optional[jnp.DeviceArray] = None,
        encoder_outputs=None,
        **kwargs
    ):
        # initializing the cache
        batch_size, seq_length = decoder_input_ids.shape

        past_key_values = self.init_cache(batch_size, max_length, encoder_outputs)
        # Note that usually one would have to put 0's in the attention_mask for x > input_ids.shape[-1] and x < cache_length.
        # But since the decoder uses a causal mask, those positions are masked anyways.
        # Thus we can create a single static attention_mask here, which is more efficient for compilation
        extended_attention_mask = jnp.ones((batch_size, max_length), dtype="i4")
        if decoder_attention_mask is not None:
            decoder_position_ids = decoder_attention_mask.cumsum(axis=-1) - 1
            extended_attention_mask = lax.dynamic_update_slice(extended_attention_mask, decoder_attention_mask, (0, 0))
        else:
            decoder_position_ids = jnp.broadcast_to(
                jnp.arange(seq_length, dtype="i4")[None, :], (batch_size, seq_length)
            )

        return {
            "past_key_values": past_key_values,
            "encoder_outputs": encoder_outputs,
            "encoder_attention_mask": attention_mask,
            "decoder_attention_mask": extended_attention_mask,
            "decoder_position_ids": decoder_position_ids,
        }

    def update_inputs_for_generation(self, model_outputs, model_kwargs):
        model_kwargs["past_key_values"] = model_outputs.past_key_values
        model_kwargs["decoder_position_ids"] = model_kwargs["decoder_position_ids"][:, -1:] + 1
        return model_kwargs

    @classmethod
    def from_encoder_decoder_pretrained(
        cls,
        encoder_pretrained_model_name_or_path: Optional[Union[str, os.PathLike]] = None,
        decoder_pretrained_model_name_or_path: Optional[Union[str, os.PathLike]] = None,
        *model_args,
        **kwargs
    ) -> FlaxPreTrainedModel:
        r"""
        Instantiate an encoder and a decoder from one or two base classes of the library from pretrained model
        checkpoints.

        Params:
            encoder_pretrained_model_name_or_path (`Union[str, os.PathLike]`, *optional*):
                Information necessary to initiate the encoder. Can be either:

                    - A string, the *model id* of a pretrained model hosted inside a model repo on huggingface.co.
                      Valid model ids can be located at the root-level, like `bert-base-uncased`, or namespaced under a
                      user or organization name, like `dbmdz/bert-base-german-cased`.
                    - A path to a *directory* containing model weights saved using
                      [`~FlaxPreTrainedModel.save_pretrained`], e.g., `./my_model_directory/`.

            decoder_pretrained_model_name_or_path (`Union[str, os.PathLike]`, *optional*, defaults to `None`):
                Information necessary to initiate the decoder. Can be either:

                    - A string, the *model id* of a pretrained model hosted inside a model repo on huggingface.co.
                      Valid model ids can be located at the root-level, like `bert-base-uncased`, or namespaced under a
                      user or organization name, like `dbmdz/bert-base-german-cased`.
                    - A path to a *directory* containing model weights saved using
                      [`~FlaxPreTrainedModel.save_pretrained`], e.g., `./my_model_directory/`.

            model_args (remaining positional arguments, *optional*):
                All remaning positional arguments will be passed to the underlying model's `__init__` method.

            kwargs (remaining dictionary of keyword arguments, *optional*):
                Can be used to update the configuration object (after it being loaded) and initiate the model (e.g.,
                `output_attentions=True`).

                - To update the encoder configuration, use the prefix *encoder_* for each configuration parameter.
                - To update the decoder configuration, use the prefix *decoder_* for each configuration parameter.
                - To update the parent model configuration, do not use a prefix for each configuration parameter.

                Behaves differently depending on whether a `config` is provided or automatically loaded.

        Example:

        ```python
        >>> from transformers import FlaxSpeechEncoderDecoderModel

        >>> # initialize a wav2vec2-2-bart from pretrained wav2vec2 and bart models. Note that the cross-attention layers will be randomly initialized
        >>> model = FlaxSpeechEncoderDecoderModel.from_encoder_decoder_pretrained("facebook/wav2vec2-large-lv60", "facebook/bart-large")
        >>> # saving model after fine-tuning
        >>> model.save_pretrained("./wav2vec2-2-bart-large")
        >>> # load fine-tuned model
        >>> model = FlaxSpeechEncoderDecoderModel.from_pretrained("./wav2vec2-2-bart-large")
        ```"""

        kwargs_encoder = {
            argument[len("encoder_") :]: value for argument, value in kwargs.items() if argument.startswith("encoder_")
        }

        kwargs_decoder = {
            argument[len("decoder_") :]: value for argument, value in kwargs.items() if argument.startswith("decoder_")
        }

        # remove encoder, decoder kwargs from kwargs
        for key in kwargs_encoder.keys():
            del kwargs["encoder_" + key]
        for key in kwargs_decoder.keys():
            del kwargs["decoder_" + key]

        # Load and initialize the encoder and decoder
        # The distinction between encoder and decoder at the model level is made
        # by the value of the flag `is_decoder` that we need to set correctly.
        encoder = kwargs_encoder.pop("model", None)
        if encoder is None:
            if encoder_pretrained_model_name_or_path is None:
                raise ValueError(
                    "If `encoder_model` is not defined as an argument, a `encoder_pretrained_model_name_or_path` has "
                    "to be defined."
                )

            if "config" not in kwargs_encoder:
                encoder_config = AutoConfig.from_pretrained(encoder_pretrained_model_name_or_path)
                if encoder_config.is_decoder is True or encoder_config.add_cross_attention is True:
                    logger.info(
                        f"Initializing {encoder_pretrained_model_name_or_path} as a encoder model "
                        "from a decoder model. Cross-attention and casual mask are disabled."
                    )
                    encoder_config.is_decoder = False
                    encoder_config.add_cross_attention = False

                kwargs_encoder["config"] = encoder_config

            encoder = FlaxAutoModel.from_pretrained(
                encoder_pretrained_model_name_or_path, *model_args, **kwargs_encoder
            )

        decoder = kwargs_decoder.pop("model", None)
        if decoder is None:
            if decoder_pretrained_model_name_or_path is None:
                raise ValueError(
                    "If `decoder_model` is not defined as an argument, a `decoder_pretrained_model_name_or_path` has "
                    "to be defined."
                )

            if "config" not in kwargs_decoder:
                decoder_config = AutoConfig.from_pretrained(decoder_pretrained_model_name_or_path)
                if decoder_config.is_decoder is False or decoder_config.add_cross_attention is False:
                    logger.info(
                        f"Initializing {decoder_pretrained_model_name_or_path} as a decoder model. "
                        f"Cross attention layers are added to {decoder_pretrained_model_name_or_path} "
                        f"and randomly initialized if {decoder_pretrained_model_name_or_path}'s architecture allows for "
                        "cross attention layers."
                    )
                    decoder_config.is_decoder = True
                    decoder_config.add_cross_attention = True

                kwargs_decoder["config"] = decoder_config

            if kwargs_decoder["config"].is_decoder is False or kwargs_decoder["config"].add_cross_attention is False:
                logger.warning(
                    f"Decoder model {decoder_pretrained_model_name_or_path} is not initialized as a decoder. "
                    f"In order to initialize {decoder_pretrained_model_name_or_path} as a decoder, "
                    "make sure that the attributes `is_decoder` and `add_cross_attention` of `decoder_config` "
                    "passed to `.from_encoder_decoder_pretrained(...)` are set to `True` or do not pass a "
                    "`decoder_config` to `.from_encoder_decoder_pretrained(...)`"
                )

            decoder = FlaxAutoModelForCausalLM.from_pretrained(decoder_pretrained_model_name_or_path, **kwargs_decoder)

        # instantiate config with corresponding kwargs
        dtype = kwargs.pop("dtype", jnp.float32)
        config = SpeechEncoderDecoderConfig.from_encoder_decoder_configs(encoder.config, decoder.config, **kwargs)

        # init model
        model = cls(config, dtype=dtype)
        model.params["encoder"] = encoder.params
        model.params["decoder"] = decoder.params

        return model
