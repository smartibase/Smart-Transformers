# flake8: noqa
# There's no way to ignore "F401 '...' imported but unused" warnings in this
# module, but to preserve other warnings. So, don't check this module at all.

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

from typing import TYPE_CHECKING

from ...file_utils import _LazyModule, is_detectron2_available, is_tokenizers_available


_import_structure = {
    "configuration_layoutlmv2": ["LayoutLMv2Config", "LayoutLMv2_PRETRAINED_CONFIG_ARCHIVE_MAP"],
    "tokenization_layoutlmv2": ["LayoutLMv2Tokenizer"],
}

if is_tokenizers_available():
    _import_structure["tokenization_layoutlmv2_fast"] = ["LayoutLMv2TokenizerFast"]

if is_detectron2_available():
    _import_structure["modeling_layoutlmv2"] = [
        "LayoutLMv2ForTokenClassification",
        "LayoutLMv2Layer",
        "LayoutLMv2Model",
        "LayoutLMv2PreTrainedModel",
        "LayoutLMv2_PRETRAINED_MODEL_ARCHIVE_LIST",
    ]

if TYPE_CHECKING:
    from .configuration_layoutlmv2 import LayoutLMv2_PRETRAINED_CONFIG_ARCHIVE_MAP, LayoutLMv2Config
    from .tokenization_layoutlmv2 import LayoutLMv2Tokenizer

    if is_tokenizers_available():
        from .tokenization_layoutlmv2_fast import LayoutLMv2TokenizerFast

    if is_detectron2_available():
        from .modeling_layoutlmv2 import (
            LayoutLMv2_PRETRAINED_MODEL_ARCHIVE_LIST,
            LayoutLMv2ForTokenClassification,
            LayoutLMv2Layer,
            LayoutLMv2Model,
            LayoutLMv2PreTrainedModel,
        )
else:
    import importlib
    import os
    import sys

    class _LazyModule(_BaseLazyModule):
        """
        Module class that surfaces all objects but only performs associated imports when the objects are requested.
        """

        __file__ = globals()["__file__"]
        __path__ = [os.path.dirname(__file__)]

        def _get_module(self, module_name: str):
            return importlib.import_module("." + module_name, self.__name__)

    sys.modules[__name__] = _LazyModule(__name__, _import_structure)
