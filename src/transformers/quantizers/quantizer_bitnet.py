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
from typing import TYPE_CHECKING, List

from .base import HfQuantizer

if TYPE_CHECKING:
    from ..modeling_utils import PreTrainedModel

from ..utils import is_accelerate_available, is_torch_available, logging, is_bitblas_available

if is_torch_available():
    import torch


logger = logging.get_logger(__name__)


class BitNetHfQuantizer(HfQuantizer):
    """
    1.58-bit quantization from BitNet quantization method:
    before loading: converts transformer layers into BitLinear158 during loading.
    """

    requires_parameters_quantization = False
    requires_calibration = True

    required_packages = ["accelerate"]

    def __init__(self, quantization_config, **kwargs):
        super().__init__(quantization_config, **kwargs)
        self.quantization_config = quantization_config

    def validate_environment(self, *args, **kwargs):
        # if not is_bitblas_available():
        #     raise ImportError(
        #         "Using bitnet quantization requires bitblas kernel."
        #         "Please install the latest version of bitblas from : https://github.com/microsoft/BitBLAS"
        #     )

        if not is_accelerate_available():
            raise ImportError("Loading an BitNet quantized model requires accelerate (`pip install accelerate`)")

        if kwargs.get("from_tf", False) or kwargs.get("from_flax", False):
            raise ValueError(
                "Converting into 8-bit weights from tf/flax weights is currently not supported, please make"
                " sure the weights are in PyTorch format."
            )

        if not torch.cuda.is_available():
            raise RuntimeError("No GPU found. A GPU is needed for quantization.")

        device_map = kwargs.get("device_map", None)
        if device_map is None:
            logger.warning_once(
                "You have loaded an BitNet model on CPU and have a CUDA device available, make sure to set "
                "your model on a GPU device in order to run your model."
            )
        elif device_map is not None:
            if isinstance(device_map, dict) and ("cpu" in device_map.values() or "disk" in device_map.values()):
                raise ValueError(
                    "You are attempting to load an BitNet model with a device_map that contains a CPU or disk device."
                    " This is not supported. Please remove the CPU or disk device from the device_map."
                )

    def _process_model_after_weight_loading(self, model: "PreTrainedModel", **kwargs):
        return model

    def _process_model_before_weight_loading(
        self,
        model: "PreTrainedModel",
        device_map,
        keep_in_fp32_modules: List[str] = [],
        **kwargs,
    ):
        from ..integrations import get_keys_to_not_convert, replace_with_bitnet_linear

        self.modules_to_not_convert = get_keys_to_not_convert(model)

        if self.quantization_config.modules_to_not_convert is not None:
            self.modules_to_not_convert.extend(self.quantization_config.modules_to_not_convert)

        model = replace_with_bitnet_linear(
            model,
            modules_to_not_convert=self.modules_to_not_convert,
            quantization_config=self.quantization_config,
            pre_quantized=self.pre_quantized,
        )
        
    @property
    def is_serializable(self):
        return True

    @property
    def is_trainable(self) -> bool:
        return False