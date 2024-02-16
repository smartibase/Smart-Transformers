from typing import TYPE_CHECKING

from ...utils import (
    OptionalDependencyNotAvailable,
    _LazyModule,
    is_torch_available,
)


_import_structure = {
    "configuration_hiera": [
        "HIREA_PRETRAINED_CONFIG_ARCHIVE_MAP",
        "HireaConfig",
    ],
}

try:
    if not is_torch_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["hirea"] = [
        "HIREA_PRETRAINED_MODEL_ARCHIVE_LIST",
        "Hirea",
        "Head",
        "HieraBlock",
        "MaskUnitAttention"
        ""
    ]

if TYPE_CHECKING:
    from .configuration_hiera import (
        HIERA_PRETRAINED_CONFIG_ARCHIVE_MAP,
        HieraConfig,
    )

    try:
        if not is_torch_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .hiera import (
            HieraModel,
            Head,
            HieraBlock,
            MaskUnitAttention,
        )
        from .hiera_image_processor import (
            HieraImageProcessor
        )

else:
    import sys

    sys.modules[__name__] = _LazyModule(__name__, globals()["__file__"], _import_structure, module_spec=__spec__)

####### PREV:
    
# Copyright 2020 The HuggingFace Team. All rights reserved.
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
# from typing import TYPE_CHECKING

# from ...utils import (
#     OptionalDependencyNotAvailable,
#     _LazyModule,
#     is_flax_available,
#     is_tf_available,
#     is_torch_available,
# )


# _import_structure = {"configuration_vit_mae": ["VIT_MAE_PRETRAINED_CONFIG_ARCHIVE_MAP", "ViTMAEConfig"]}

# try:
#     if not is_torch_available():
#         raise OptionalDependencyNotAvailable()
# except OptionalDependencyNotAvailable:
#     pass
# else:
#     _import_structure["modeling_vit_mae"] = [
#         "VIT_MAE_PRETRAINED_MODEL_ARCHIVE_LIST",
#         "ViTMAEForPreTraining",
#         "ViTMAELayer",
#         "ViTMAEModel",
#         "ViTMAEPreTrainedModel",
#     ]

# try:
#     if not is_tf_available():
#         raise OptionalDependencyNotAvailable()
# except OptionalDependencyNotAvailable:
#     pass
# else:
#     _import_structure["modeling_tf_vit_mae"] = [
#         "TFViTMAEForPreTraining",
#         "TFViTMAEModel",
#         "TFViTMAEPreTrainedModel",
#     ]

# if TYPE_CHECKING:
#     from .configuration_vit_mae import VIT_MAE_PRETRAINED_CONFIG_ARCHIVE_MAP, ViTMAEConfig

#     try:
#         if not is_torch_available():
#             raise OptionalDependencyNotAvailable()
#     except OptionalDependencyNotAvailable:
#         pass
#     else:
#         from .modeling_vit_mae import (
#             VIT_MAE_PRETRAINED_MODEL_ARCHIVE_LIST,
#             ViTMAEForPreTraining,
#             ViTMAELayer,
#             ViTMAEModel,
#             ViTMAEPreTrainedModel,
#         )

#     try:
#         if not is_tf_available():
#             raise OptionalDependencyNotAvailable()
#     except OptionalDependencyNotAvailable:
#         pass
#     else:
#         from .modeling_tf_vit_mae import TFViTMAEForPreTraining, TFViTMAEModel, TFViTMAEPreTrainedModel


# else:
#     import sys

#     sys.modules[__name__] = _LazyModule(__name__, globals()["__file__"], _import_structure, module_spec=__spec__)