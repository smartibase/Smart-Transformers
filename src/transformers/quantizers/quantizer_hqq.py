# Copyright 2024 The HuggingFace Team. All rights reserved.
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

from typing import TYPE_CHECKING, Any, Dict, List

from .base import HfQuantizer


if TYPE_CHECKING:
    from ..modeling_utils import PreTrainedModel

from ..integrations import prepare_for_hqq_linear
from ..utils import is_accelerate_available, is_hqq_available, is_torch_available, logging
from ..utils.hqq_utils import find_parent
from .quantizers_utils import get_module_from_name


if is_accelerate_available():
    from accelerate.hooks import remove_hook_from_module

if is_torch_available():
    import torch

logger = logging.get_logger(__name__)


class HQQHfQuantizer(HfQuantizer):
    """
    HQQ quantizer base HF class.
    nn.Linear modules are first tagged with quant_config in _process_model_before_weight_loading().
    The actually quantization and offloading to the GPU is done in check_quantized_param().
    self.show_progress (bool) is used to show quantization progress in each shard.
    """

    use_keep_in_fp32_modules = False
    requires_parameters_quantization = True
    requires_calibration = False
    required_packages = ["hqq"]

    def __init__(self, quantization_config, **kwargs):
        super().__init__(quantization_config, **kwargs)
        self.show_progress = quantization_config.show_progress
        self.torch_dtype = None
        self.using_multi_gpu = False

    def validate_environment(self, *args, **kwargs):
        if not (is_hqq_available()):
            raise ImportError(
                "HQQ is not available. Please follow the instructions to install it: `https://github.com/mobiusml/hqq/`"
            )

        if kwargs.get("from_tf", False) or kwargs.get("from_flax", False):
            raise ValueError(
                "Converting weights from tf/flax weights is currently not supported, please make"
                " sure the weights are in PyTorch format."
            )

        if not torch.cuda.is_available():
            raise RuntimeError("No GPU found. A GPU is needed for quantization.")

        if self.torch_dtype is None:
            self.torch_dtype = kwargs.get("torch_dtype", torch.float16)

        if self.using_multi_gpu is False:
            if "device_map" in kwargs:
                if isinstance(kwargs["device_map"], dict):
                    target_devices = {item[1] for item in kwargs["device_map"].items()} - set({"cpu", "disk"})
                    self.using_multi_gpu = len(target_devices) > 1

    def check_quantized_param(
        self,
        model: "PreTrainedModel",
        param_value: "torch.Tensor",
        param_name: str,
        state_dict: Dict[str, Any],
        **kwargs,
    ) -> bool:
        module, tensor_name = get_module_from_name(model, param_name)

        return isinstance(module, torch.nn.Linear)

    def create_quantized_param(
        self,
        model: "PreTrainedModel",
        param_value: "torch.Tensor",
        param_name: str,
        target_device: "torch.device",
        state_dict: Dict[str, Any],
        unexpected_keys: List[str],
    ):
        """
        Each nn.Linear layer is processsed here.
        We first check if the corresponding module state_dict contains already HQQ quantized parameters.
        If not, we create a temp linear layer with the module state_dict params and use it for quantization
        """

        if is_hqq_available():
            from hqq.core.quantize import HQQLinear

        module, tensor_name = get_module_from_name(model, param_name)

        # We only quantize torch.nn.Linear, other layers will be skipped
        if type(module) is not torch.nn.Linear:
            return

        layer_name = param_name.replace(".weight", "").replace(".bias", "")
        parent_module = find_parent(model, layer_name)
        node = layer_name.split(".")[-1]

        # Step 0: set module state_dict
        module_state_dict = {key.split(".")[-1]: state_dict[key] for key in state_dict if layer_name in key}

        # Step 1: populate module with weight/bias from module state dict
        for key in module_state_dict:
            setattr(module, key, torch.nn.Parameter(module_state_dict[key]))

        """
        Step 2: Replace module with either HQQLinear or move it to device. We do this via setattr on the parent as doing on it on the module
        directly doesn't work.
        """

        if hasattr(module, "quant_config"):
            hqq_layer = HQQLinear(
                module,
                module.quant_config,
                compute_dtype=self.torch_dtype,
                device=target_device,
                del_orig=True,
            )

            if hqq_layer.bias is not None:
                if isinstance(hqq_layer.bias, torch.Tensor):
                    hqq_layer.bias = torch.nn.Parameter(hqq_layer.bias)

            if self.using_multi_gpu:
                hqq_layer = self._patch_layer_for_multigpu(hqq_layer)

            setattr(
                parent_module,
                node,
                hqq_layer,
            )

        else:
            module = module.to(dtype=self.torch_dtype, device=target_device)
            setattr(parent_module, node, module)

        torch.cuda.empty_cache()

    # Remove accelerate hook and uses a simpler forward pass. Otherwise, this breaks with multi-gpu
    def _patch_layer_for_multigpu(self, hqq_layer):
        hqq_layer = remove_hook_from_module(hqq_layer)

        def forward_with_device(self, x):
            out = torch.matmul(x.to(self.device), self.dequantize().t())
            if self.bias is not None:
                out += self.bias
            return out

        hqq_layer.forward = lambda x: forward_with_device(hqq_layer, x)
        return hqq_layer

    def _process_model_before_weight_loading(
        self,
        model: "PreTrainedModel",
        device_map,
        keep_in_fp32_modules: List[str] = [],
        **kwargs,
    ):
        # Add the corresponding quant_config to each valid module. This allows us to do the actual nn.Linear > HQQLinear in create_quantized_param()
        model = prepare_for_hqq_linear(model, quantization_config=self.quantization_config)

        # model.config.quantization_config is done inside prepare_for_hqq_linear

    def _process_model_after_weight_loading(self, model: "PreTrainedModel", **kwargs):
        model.is_hqq_quantized = True
        model.is_hqq_serializable = self.is_serializable
        return model

    @property
    def is_serializable(self):
        return False

    @property
    def is_trainable(self) -> bool:
        return False
