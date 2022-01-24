# This file is autogenerated by the command `make fix-copies`, do not edit.
# flake8: noqa
from ..file_utils import DummyObject, requires_backends


QDQBERT_PRETRAINED_MODEL_ARCHIVE_LIST = None


class QDQBertForMaskedLM(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertForMultipleChoice(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertForNextSentencePrediction(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertForQuestionAnswering(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertForSequenceClassification(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertForTokenClassification(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertLayer(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertLMHeadModel(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertModel(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


class QDQBertPreTrainedModel(metaclass=DummyObject):
    _backends = ["pytorch_quantization", "torch"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["pytorch_quantization", "torch"])


def load_tf_weights_in_qdqbert(*args, **kwargs):
    requires_backends(load_tf_weights_in_qdqbert, ["pytorch_quantization", "torch"])
