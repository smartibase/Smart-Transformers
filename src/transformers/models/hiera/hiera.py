# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.

# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
# --------------------------------------------------------
#
# Hiera: A Hierarchical Vision Transformer without the Bells-and-Whistles
#
# Chaitanya Ryali, Yuan-Ting Hu, Daniel Bolya, Chen Wei, Haoqi Fan,
# Po-Yao Huang, Vaibhav Aggarwal, Arkabandhu Chowdhury, Omid Poursaeed,
# Judy Hoffman, Jitendra Malik, Yanghao Li, Christoph Feichtenhofer.
#
# Paper: https://arxiv.org/abs/2306.00989/
#
# References:
# slowfast: https://github.com/facebookresearch/SlowFast
# timm: https://github.com/rwightman/pytorch-image-models/tree/master/timm
# --------------------------------------------------------

import math
from functools import partial
from typing import List, Tuple, Callable, Optional, Union
from .configuration_hiera import HieraConfig
import torch
import torch.nn as nn
import torch.nn.functional as F
from dataclasses import dataclass

from timm.models.layers import DropPath, Mlp
from ...modeling_utils import PreTrainedModel
from ...modeling_outputs import BaseModelOutput
from ...utils import (
    ModelOutput,
    add_start_docstrings,
    add_start_docstrings_to_model_forward,
    logging,
    replace_return_docstrings,
)

from .hiera_utils import conv_nd, do_pool, do_masked_conv, Unroll, Reroll

@dataclass
class HieraModelOutput(ModelOutput):
    """
    Base class for HieraModel model's outputs, conforming to Hugging Face's ModelOutput.

    Args:
        last_hidden_state (torch.FloatTensor of shape (batch_size, sequence_length, hidden_size)): 
            Last layer hidden-states.
        attentions (Tuple[torch.FloatTensor], optional, returned when output_attentions=True): 
            Attentions weights from the model, one for each layer.
        hidden_states (Tuple[torch.FloatTensor], optional, returned when output_hidden_states=True): 
            Hidden states of the model at the output of each layer.
        intermediates (List[torch.Tensor], optional): 
            Intermediate representations or features from the model, if applicable.
    """
    last_hidden_state: torch.FloatTensor
    intermediates: Optional[List[torch.Tensor]] = None


class MaskUnitAttention(nn.Module):
    """
    Computes either Mask Unit or Global Attention. Also is able to perform q pooling.

    Note: this assumes the tokens have already been flattened and unrolled into mask units.
    See `Unroll` for more details.
    """

    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        number_of_heads: int,
        q_stride: int = 1,
        window_size: int = 0,
        use_mask_unit_attention: bool = False,
    ):
        """
        Args:
        - input_dim, output_dim: The input and output feature dimensions.
        - number_of_heads: The number of attention number_of_heads.
        - q_stride: If greater than 1, pool q with this stride. The stride should be flattened (e.g., 2x2 = 4).
        - window_size: The current (flattened) size of a mask unit *after* pooling (if any).
        - use_mask_unit_attention: Use Mask Unit or Global Attention.
        """
        super().__init__()

        self.input_dim = input_dim
        self.output_dim = output_dim
        self.number_of_heads = number_of_heads
        self.q_stride = q_stride

        self.head_dim = output_dim // number_of_heads
        self.scale = (self.head_dim) ** -0.5

        self.qkv = nn.Linear(input_dim, 3 * output_dim)
        self.projection = nn.Linear(output_dim, output_dim)

        self.window_size = window_size
        self.use_mask_unit_attention = use_mask_unit_attention

    def forward(self, embeddings: torch.Tensor) -> torch.Tensor:
        """ Input should be of shape [batch, tokens, channels]. """
        batch_size , num_channels , _ = embeddings.shape
        num_windows = (
            (num_channels  // (self.q_stride * self.window_size)) if self.use_mask_unit_attention else 1
        )

        qkv = (
            self.qkv(embeddings)
            .reshape(batch_size , -1, num_windows, 3, self.number_of_heads, self.head_dim)
            .permute(3, 0, 4, 2, 1, 5)
        )
        q, k, v = qkv[0], qkv[1], qkv[2]

        if self.q_stride > 1:
            # Refer to Unroll to see how this performs a maxpool-Nd
            q = (
                q.view(batch_size , self.number_of_heads, num_windows, self.q_stride, -1, self.head_dim)
                .max(dim=3)
                .values
            )

        if hasattr(F, "scaled_dot_product_attention"):
            # Note: the original paper did *not* use SDPA, it's a free boost!
            embeddings = F.scaled_dot_product_attention(q, k, v)
        else:
            attention = (q * self.scale) @ k.transpose(-1, -2)
            attention = attention.softmax(dim=-1)
            embeddings = (attention @ v)

        embeddings = embeddings.transpose(1, 3).reshape(batch_size , -1, self.output_dim)
        embeddings = self.projection(embeddings)
        return embeddings


class HieraBlock(nn.Module):
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        number_of_heads: int,
        mlp_ratio: float = 4.0,
        drop_path: float = 0.0,
        norm_layer: nn.Module = nn.LayerNorm,
        act_layer: nn.Module = nn.GELU,
        q_stride: int = 1,
        window_size: int = 0,
        use_mask_unit_attention: bool = False,
    ):
        super().__init__()

        self.input_dim = input_dim
        self.output_dim = output_dim

        self.norm1 = norm_layer(input_dim)
        self.attention = MaskUnitAttention(
            input_dim, output_dim, number_of_heads, q_stride, window_size, use_mask_unit_attention
        )

        self.norm2 = norm_layer(output_dim)
        self.mlp = Mlp(output_dim, int(output_dim * mlp_ratio), act_layer=act_layer)

        self.drop_path = DropPath(drop_path) if drop_path > 0 else nn.Identity()
        if input_dim != output_dim:
            self.projection = nn.Linear(input_dim, output_dim)

    def forward(self, embeddings: torch.Tensor) -> torch.Tensor:
        # Attention + Q Pooling
        normalized_embeddings = self.norm1(embeddings)
        if self.input_dim != self.output_dim:
            embeddings = do_pool(self.projection(normalized_embeddings), stride=self.attention.q_stride)
        embeddings = embeddings + self.drop_path(self.attention(normalized_embeddings))

        # MLP
        embeddings = embeddings + self.drop_path(self.mlp(self.norm2(embeddings)))
        return embeddings


class Head(nn.Module):
    def __init__(
        self,
        input_dim: int,
        num_classes: int,
        dropout_rate: float = 0.0,
        act_func: Callable[[torch.Tensor], torch.Tensor] = lambda x: x.softmax(dim=-1),
    ):
        super().__init__()
        self.dropout = nn.Dropout(dropout_rate) if dropout_rate > 0 else nn.Identity()
        self.projection = nn.Linear(input_dim, num_classes)
        # act_fun for eval and testing only
        self.act_func = act_func

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.dropout(x)
        x = self.projection(x)
        if not self.training:
            x = self.act_func(x)
        return x


class PatchEmbedding(nn.Module):
    """Patch embedding that supports any number of spatial dimensions (1d, 2d, 3d)."""

    def __init__(
        self,
        dim_in: int,
        output_dim: int,
        kernel: Tuple[int, ...],
        stride: Tuple[int, ...],
        padding: Tuple[int, ...],
    ):
        super().__init__()

        # Support any number of spatial dimensions
        self.spatial_dims = len(kernel)
        self.projection = conv_nd(self.spatial_dims)(
            dim_in,
            output_dim,
            kernel_size=kernel,
            stride=stride,
            padding=padding,
        )

    def forward(
        self, pixel_values: torch.Tensor, mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        embeddings = do_masked_conv(pixel_values, self.projection, mask)
        embeddings = embeddings.reshape(embeddings.shape[0], embeddings.shape[1], -1).transpose(2, 1)
        return embeddings


class HireaModel(PreTrainedModel):
    """
    Hiera: A Hierarchical Vision Transformer without the Bells-and-Whistles.

    This model is a PyTorch implementation of the Hiera architecture for image classification.

    The model can be used as follows:

    Args:
        config (HieraConfig): Configuration class instance for `Hiera`.

    Example usage:
        >>> from your_model_file import Hiera, HieraConfig
        >>> config = HieraConfig(embedding_dimension=96, number_of_heads=1, stages=(2, 3, 16, 3), **kwargs)

        >>> model = Hiera(config)
        >>> inputs = torch.rand((1, 3, 224, 224))
        >>> outputs = model(inputs)
    """

    config_class = HieraConfig
    base_model_prefix = "hiera"
    main_input_name = "pixel_values"
    supports_gradient_checkpointing = True

    def __init__(self, config: HieraConfig):
        self.input_size = config.input_size
        self.in_chans = config.in_chans
        self.embedding_dimension = config.embedding_dimension
        self.number_of_heads = config.number_of_heads
        self.num_classes = config.num_classes
        self.stages = config.stages
        self.q_pool = config.q_pool
        self.q_stride = config.q_stride
        self.mask_unit_size = config.mask_unit_size
        self.mask_unit_attn = config.mask_unit_attn
        self.dim_mul = config.dim_mul
        self.head_mul = config.head_mul
        self.patch_kernel = config.patch_kernel
        self.patch_stride = config.patch_stride
        self.patch_padding = config.patch_padding
        self.mlp_ratio = config.mlp_ratio
        self.drop_path_rate = config.drop_path_rate
        self.head_dropout = config.head_dropout
        self.head_init_scale = config.head_init_scale
        self.sep_position_embeddings = config.sep_position_embeddings

        super().__init__(config)
        self.config = config
        norm_layer = partial(nn.LayerNorm, eps=1e-6)  # Example, adjust as needed
        depth = sum(self.stages)
        self.tokens_spatial_shape = [i // s for i, s in zip(self.input_size, self.patch_stride)]
        num_tokens = math.prod(self.tokens_spatial_shape)
        flat_mu_size = math.prod(self.mask_unit_size)
        flat_q_stride = math.prod(self.q_stride)

        assert self.q_pool < len(self.stages)
        self.q_pool, self.q_stride = self.q_pool, self.q_stride
        self.mu_size, self.mask_unit_size = flat_mu_size, self.mask_unit_size
        self.mask_spatial_shape = [
            i // s for i, s in zip(self.tokens_spatial_shape, self.mask_unit_size)
        ]
        self.stage_ends = [sum(self.stages[:i]) - 1 for i in range(1, len(self.stages) + 1)]

        self.patch_embedding = PatchEmbedding(
            self.in_chans, self.embedding_dimension, self.patch_kernel, self.patch_stride, self.patch_padding
        )

        if self.sep_position_embeddings:
            self.position_embeddings_spatial = nn.Parameter(
                torch.zeros(
                    1,
                    self.tokens_spatial_shape[1] * self.tokens_spatial_shape[2],
                    self.embedding_dimension,
                )
            )
            self.position_embeddings_temporal = nn.Parameter(
                torch.zeros(1, self.tokens_spatial_shape[0], self.embedding_dimension)
            )
        else:
            self.position_embeddings = nn.Parameter(torch.zeros(1, num_tokens, self.embedding_dimension))

        # Setup roll and reroll modules
        self.unroll = Unroll(
            self.input_size, self.patch_stride, [self.q_stride] * len(self.stage_ends[:-1])
        )
        self.reroll = Reroll(
            self.input_size,
            self.patch_stride,
            [self.q_stride] * len(self.stage_ends[:-1]),
            self.stage_ends,
            self.q_pool,
        )
        # q_pool locations
        q_pool_blocks = [x + 1 for x in self.stage_ends[:self.q_pool]]
        # stochastic depth decay rule
        dpr = [x.item() for x in torch.linspace(0, self.drop_path_rate, depth)]

        # Transformer blocks
        cur_stage = 0
        self.blocks = nn.ModuleList()

        for i in range(depth):
            output_dim = self.embedding_dimension
            # Mask unit or global attention.
            # Lag by 1 block, so that global attention,
            # applied post pooling on lower resolution
            use_mask_unit_attention = self.mask_unit_attn[cur_stage]

            if i - 1 in self.stage_ends:
                output_dim = int(self.embedding_dimension * self.dim_mul)
                number_of_heads = int(self.number_of_heads * self.head_mul)
                cur_stage += 1
                if i in q_pool_blocks:
                    flat_mu_size //= flat_q_stride
            else:
                number_of_heads = self.number_of_heads

            block = HieraBlock(
                input_dim=self.embedding_dimension,
                output_dim=output_dim,
                number_of_heads=number_of_heads,
                mlp_ratio=self.mlp_ratio,
                drop_path=dpr[i],
                norm_layer=norm_layer,
                q_stride=(flat_q_stride if i in q_pool_blocks else 1),
                window_size=flat_mu_size,
                use_mask_unit_attention=use_mask_unit_attention,
            )

            self.embedding_dimension = output_dim
            self.blocks.append(block)

        self.norm = norm_layer(self.embedding_dimension)
        self.head = Head(self.embedding_dimension, self.num_classes, dropout_rate=self.head_dropout)

        # Initialize everything
        if self.sep_position_embeddings:
            nn.init.trunc_normal_(self.position_embeddings_spatial, std=0.02)
            nn.init.trunc_normal_(self.position_embeddings_temporal, std=0.02)
        else:
            nn.init.trunc_normal_(self.position_embeddings, std=0.02)
        self.apply(partial(self._init_weights))
        self.head.projection.weight.data.mul_(self.head_init_scale)
        self.head.projection.bias.data.mul_(self.head_init_scale)
        self.post_init()

    def _init_weights(self, m, init_bias=0.02):
        if isinstance(m, (nn.Linear, nn.Conv1d, nn.Conv2d, nn.Conv3d)):
            nn.init.trunc_normal_(m.weight, std=0.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, init_bias)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, init_bias)
            nn.init.constant_(m.weight, 1.0)

    @torch.jit.ignore
    def no_weight_decay(self):
        if self.sep_position_embeddings:
            return ["position_embeddings_spatial", "position_embeddings_temporal"]
        else:
            return ["position_embeddings"]

    def get_random_mask(self, x: torch.Tensor, mask_ratio: float) -> torch.Tensor:
        """
        Generates a random mask, mask_ratio fraction are dropped.
        1 is *keep*, 0 is *remove*. Useful for MAE, FLIP, etc.
        """
        batch_size  = x.shape[0]
        # Tokens selected for masking at mask unit level
        num_windows = math.prod(self.mask_spatial_shape)  # num_mask_units
        len_keep = int(num_windows * (1 - mask_ratio))
        noise = torch.rand(batch_size , num_windows, device=x.device)

        # Sort noise for each sample
        ids_shuffle = torch.argsort(
            noise, dim=1
        )  # ascend: small is keep, large is remove
        ids_restore = torch.argsort(ids_shuffle, dim=1)

        # Generate the binary mask: 1 is *keep*, 0 is *remove*
        # Note this is opposite to original MAE
        mask = torch.zeros([batch_size , num_windows], device=x.device)
        mask[:, :len_keep] = 1
        # Unshuffle to get the binary mask
        mask = torch.gather(mask, dim=1, index=ids_restore)

        return mask.bool()

    def get_position_embeddings(self) -> torch.Tensor:
        if self.sep_position_embeddings:
            return self.position_embeddings_spatial.repeat(
                1, self.tokens_spatial_shape[0], 1
            ) + torch.repeat_interleave(
                self.position_embeddings_temporal,
                self.tokens_spatial_shape[1] * self.tokens_spatial_shape[2],
                dim=1,
            )
        else:
            return self.position_embeddings

    def forward(
        self,
        pixel_values: torch.Tensor,
        mask: torch.Tensor = None,
        return_dict: Optional[bool] = True,
        return_intermediates: bool = False,
    ) -> Union[Tuple[torch.Tensor], HieraModelOutput]:
        """
        mask should be a boolean tensor of shape [batch_size , #MUt*#MUy*#MUx] where #MU are the number of mask units in that input_dim.
        Note: 1 in mask is *keep*, 0 is *remove*; mask.sum(dim=-1) should be the same across the batch.
        """
        # Slowfast training passes in a list
        if isinstance(pixel_values, list):
            pixel_values = pixel_values[0]
        intermediates = []

        pached_embeddings = self.patch_embedding(
            pixel_values,
            mask=mask.view(
                pixel_values.shape[0], 1, *self.mask_spatial_shape
            )  # batch_size , C, *mask_spatial_shape
            if mask is not None
            else None,
        )
        embeddings = pached_embeddings + self.get_position_embeddings()
        embeddings = self.unroll(embeddings)

        # Discard masked tokens
        if mask is not None:
            embeddings = embeddings[mask[..., None].tile(1, self.mu_size, embeddings.shape[2])].view(
                embeddings.shape[0], -1, embeddings.shape[-1]
            )

        for i, block in enumerate(self.blocks):
            embeddings = block(embeddings)

            if return_intermediates and i in self.stage_ends:
                intermediates.append(self.reroll(embeddings, i, mask=mask))

        if mask is None:
            embeddings = embeddings.mean(dim=1)
            embeddings = self.norm(embeddings)
            embeddings = self.head(embeddings)

        # embeddings may not always be in spatial order here.
        # e.g. if q_pool = 2, mask_unit_size = (8, 8), and
        # q_stride = (2, 2), not all unrolls were consumed,
        # intermediates[-1] is embeddings in spatial order
        if not return_dict:
            return tuple(v for v in [embeddings, intermediates] if v is not None)
        
        return HieraModelOutput(
            last_hidden_state=embeddings,
            intermediates=intermediates if return_intermediates else None,
        )