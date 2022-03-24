# This file is autogenerated by the command `make fix-copies`, do not edit.
# flake8: noqa
from ..utils import DummyObject, requires_backends


class ImageFeatureExtractionMixin(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class BeitFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class CLIPFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class CLIPProcessor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class ConvNextFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class DeiTFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class DetrFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class GLPNFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class ImageGPTFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class LayoutLMv2FeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class LayoutLMv2Processor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class LayoutXLMProcessor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class MaskFormerFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class PerceiverFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class PoolFormerFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class SegformerFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class ViltFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class ViltProcessor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])


class ViTFeatureExtractor(metaclass=DummyObject):
    _backends = ["vision"]

    def __init__(self, *args, **kwargs):
        requires_backends(self, ["vision"])
