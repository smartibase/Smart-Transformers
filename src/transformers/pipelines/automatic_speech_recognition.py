import subprocess
from typing import TYPE_CHECKING, Union

import numpy as np

from ..utils import logging
from .base import Pipeline


if TYPE_CHECKING:
    from ..models.auto import AutoFeatureExtractor

logger = logging.get_logger(__name__)


def ffmpeg_read(bpayload: bytes, sampling_rate: int) -> np.array:
    """
    Helper function to read an audio file through ffmpeg.
    """
    ar = f"{sampling_rate}"
    ac = "1"
    format_for_conversion = "f32le"
    ffmpeg_command = [
        "ffmpeg",
        "-i",
        "pipe:0",
        "-ac",
        ac,
        "-ar",
        ar,
        "-f",
        format_for_conversion,
        "-hide_banner",
        "-loglevel",
        "quiet",
        "pipe:1",
    ]

    ffmpeg_process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    output_stream = ffmpeg_process.communicate(bpayload)
    out_bytes = output_stream[0]

    audio = np.frombuffer(out_bytes, np.float32)
    if audio.shape[0] == 0:
        raise ValueError("Malformed soundfile")
    return audio


class AutomaticSpeechRecognitionPipeline(Pipeline):
    """
    Pipeline that aims at extracting spoken text contained within some audio.

    The input can be either a raw waveform or a audio file. In case of the audio file, ffmpeg should
    be installed for the read function requires it (to support many formats).
    """

    def __init__(self, feature_extractor: "AutoFeatureExtractor", *args, **kwargs):
        """
        Arguments:
            model (:obj:`~transformers.PreTrainedModel` or :obj:`~transformers.TFPreTrainedModel`):
                The model that will be used by the pipeline to make predictions. This needs to be a model inheriting from
                :class:`~transformers.PreTrainedModel` for PyTorch and :class:`~transformers.TFPreTrainedModel` for
                TensorFlow.
            tokenizer (:obj:`~transformers.PreTrainedTokenizer`):
                The tokenizer that will be used by the pipeline to encode data for the model. This object inherits from
                :class:`~transformers.PreTrainedTokenizer`.
            feature_extractor (:obj:`~transformers.AutoFeatureExtractor`):
                The feature extractor that will be used by the pipeline to encode waveform for the model.
            modelcard (:obj:`str` or :class:`~transformers.ModelCard`, `optional`):
                Model card attributed to the model for this pipeline.
            framework (:obj:`str`, `optional`):
                The framework to use, either :obj:`"pt"` for PyTorch or :obj:`"tf"` for TensorFlow. The specified framework
                must be installed.

                If no framework is specified, will default to the one currently installed. If no framework is specified and
                both frameworks are installed, will default to the framework of the :obj:`model`, or to PyTorch if no model
                is provided.
            device (:obj:`int`, `optional`, defaults to -1):
                Device ordinal for CPU/GPU supports. Setting this to -1 will leverage CPU, a positive will run the model on
                the associated CUDA device id.
        """
        super().__init__(*args, **kwargs)
        self.feature_extractor = feature_extractor

    def __call__(
        self,
        inputs: Union[np.ndarray, bytes, str],
        **kwargs,
    ):
        """
        Classify the sequence(s) given as inputs. See the :obj:`~transformers.AutomaticSpeechRecognitionPipeline`
        documentation for more information.

        Args:
            inputs (:obj:`np.ndarray` or :obj:`bytes` or :obj:`str`):
                The inputs is either a raw waveform (:obj:`np.ndarray`) at the correct sampling rate (no further check will be done) or a :obj:`str` that is
                the filename of the audio file, the file will be read at the correct sampling rate to get the waveform using `ffmpeg`.
                This requires `ffmpeg` to be installed on the system. If `inputs` is :obj:`bytes` it is supposed to be the content of an audio file and is
                interpreted by `ffmpeg` in the same way.

        Return:
            A :obj:`dict` with the following keys:

            - **text** (:obj:`str`) -- The recognized text.
        """
        if isinstance(inputs, str):
            with open(inputs, "rb") as f:
                inputs = f.read()

        if isinstance(inputs, bytes):
            inputs = ffmpeg_read(inputs, self.feature_extractor.sampling_rate)

        processed = self.feature_extractor(
            inputs, sampling_rate=self.feature_extractor.sampling_rate, return_tensors="pt"
        )

        name = self.model.__class__.__name__
        if name.endswith("ForConditionalGeneration"):
            input_ids = processed["input_features"]
            tokens = self.model.generate(input_ids=input_ids)
            tokens = tokens.squeeze(0)
        elif name.endswith("ForCTC"):
            outputs = self.model(**processed)
            tokens = outputs.logits.squeeze(0).argmax(dim=-1)

        skip_special_tokens = False if "CTC" in self.tokenizer.__class__.__name__ else True
        recognized_string = self.tokenizer.decode(tokens, skip_special_tokens=skip_special_tokens)
        return {"text": recognized_string}
