# coding=utf-8
# Copyright 2023 HuggingFace Inc.
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

import tempfile

import numpy as np

from ..utils import is_soundfile_availble, is_torch_available, is_vision_available, logging


logger = logging.get_logger(__name__)

if is_vision_available():
    import PIL.Image
    from PIL import Image
    from PIL.Image import Image as ImageType
else:
    ImageType = object

if is_torch_available():
    import torch

if is_soundfile_availble():
    import soundfile as sf


class AgentType:
    """
    Abstract class to be reimplemented to define types that can be returned by agents.

    These objects serve three purposes:

    - They behave as they were the type they're meant to be, e.g., a string for text, a PIL.Image for images
    - They can be stringified: str(object) in order to return a string defining the object
    - They should be displayed correctly in ipython notebooks/colab/jupyter
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.to_string()

    def to_raw(self):
        logger.error(
            "This is a raw AgentType of unknown type. Display in notebooks and string conversion will be unreliable"
        )
        return self.value

    def to_string(self) -> str:
        logger.error(
            "This is a raw AgentType of unknown type. Display in notebooks and string conversion will be unreliable"
        )
        return str(self.value)


class AgentText(AgentType, str):
    """
    Text type returned by the agent. Behaves as a string.
    """

    def to_raw(self):
        return self.value

    def to_string(self):
        return self.value


class AgentImage(AgentType, ImageType):
    """
    Image type returned by the agent. Behaves as a PIL.Image.
    """

    def __init__(self, value):
        super().__init__(value)

        if not is_vision_available():
            raise ImportError("PIL must be installed in order to handle images.")

        self._path = None
        self._raw = None
        self._tensor = None

        if isinstance(value, ImageType):
            self._raw = value
        elif isinstance(value, str):
            self._path = value
        elif isinstance(value, torch.Tensor):
            self._tensor = value
        else:
            raise ValueError(f"Unsupported type for {self.__class__.__name__}: {type(value)}")

    def _ipython_display_(self, include=None, exclude=None):
        """
        Displays correctly this type in an ipython notebook (ipython, colab, jupyter, ...)
        """
        from IPython.display import Image, display

        display(Image(self.to_string()))

    def to_raw(self):
        """
        Returns the "raw" version of that object. In the case of an AgentImage, it is a PIL.Image.
        """
        if self._raw is not None:
            return self._raw

        if self._path is not None:
            return Image.open(self._path)

    def to_string(self):
        """
        Returns the stringified version of that object. In the case of an AgentImage, it is a path to the serialized
        version of the image.
        """
        if self._path is not None:
            return self._path

        if self._raw is not None:
            temp = tempfile.NamedTemporaryFile(suffix=".png")
            self._path = temp.name
            self._raw.save(self._path)

            return self._path

        if self._tensor is not None:
            array = self._tensor.cpu().detach().numpy()
            array[array <= 0] = 0
            array[array > 0] = 1

            # There is likely simpler than load into image into save
            img = Image.fromarray((array * 255).astype(np.uint8))
            temp = tempfile.NamedTemporaryFile(suffix=".png")
            img.save(temp.name)


class AgentAudio(AgentType):
    """
    Audio type returned by the agent.
    """

    def __init__(self, value, samplerate=16_000):
        super().__init__(value)

        if not is_soundfile_availble():
            raise ImportError("soundfile must be installed in order to handle audio.")

        self._path = None
        self._tensor = None

        self.samplerate = samplerate

        if isinstance(value, str):
            self._path = value
        elif isinstance(value, torch.Tensor):
            self._tensor = value
        else:
            raise ValueError(f"Unsupported audio type: {type(value)}")

    def _ipython_display_(self, include=None, exclude=None):
        from IPython.display import Audio, display

        display(Audio(self.to_string(), rate=self.samplerate))

    def to_raw(self):
        if self._tensor is not None:
            return self._tensor

        if self._path is not None:
            return sf.read(self._path, samplerate=self.samplerate)

    def to_string(self):
        if self._path is not None:
            return self._path

        if self._tensor is not None:
            temp = tempfile.NamedTemporaryFile(suffix=".wav")
            self._path = temp.name
            sf.write(self._path, self._tensor, samplerate=self.samplerate)
            return self._path


AGENT_TYPE_MAPPING = {"text": AgentText, "image": AgentImage, "audio": AgentAudio}
INSTANCE_TYPE_MAPPING = {str: AgentText}

if is_vision_available():
    INSTANCE_TYPE_MAPPING[PIL.Image] = AgentImage


def handle_agent_inputs(*args, **kwargs):
    args = [(arg.to_raw() if isinstance(arg, AgentType) else arg) for arg in args]
    kwargs = {k: (v.to_raw() if isinstance(v, AgentType) else v) for k, v in kwargs.items()}
    return args, kwargs


def handle_agent_outputs(outputs, output_types=None):
    if isinstance(outputs, dict):
        decoded_outputs = {}
        for i, (k, v) in enumerate(outputs.items()):
            if output_types is not None:
                # If the class has defined outputs, we can map directly according to the class definition
                if output_types[i] in AGENT_TYPE_MAPPING:
                    decoded_outputs[k] = AGENT_TYPE_MAPPING[output_types[i]](v)
                else:
                    decoded_outputs[k] = AgentType(v)

            else:
                # If the class does not have defined output, then we map according to the type
                for _k, _v in INSTANCE_TYPE_MAPPING.items():
                    if isinstance(v, _k):
                        decoded_outputs[k] = _v(v)
                if k not in decoded_outputs:
                    decoded_outputs[k] = AgentType[v]

    elif isinstance(outputs, (list, tuple)):
        decoded_outputs = type(outputs)()
        for i, v in enumerate(outputs):
            if output_types is not None:
                # If the class has defined outputs, we can map directly according to the class definition
                if output_types[i] in AGENT_TYPE_MAPPING:
                    decoded_outputs.append(AGENT_TYPE_MAPPING[output_types[i]](v))
                else:
                    decoded_outputs.append(AgentType(v))
            else:
                # If the class does not have defined output, then we map according to the type
                found = False
                for _k, _v in INSTANCE_TYPE_MAPPING.items():
                    if isinstance(v, _k):
                        decoded_outputs.append(_v(v))
                        found = True

                if not found:
                    decoded_outputs.append(AgentType(v))

    else:
        if output_types[0] in AGENT_TYPE_MAPPING:
            # If the class has defined outputs, we can map directly according to the class definition
            decoded_outputs = AGENT_TYPE_MAPPING[output_types[0]](outputs)

        else:
            # If the class does not have defined output, then we map according to the type
            for _k, _v in INSTANCE_TYPE_MAPPING.items():
                if isinstance(outputs, _k):
                    return _v(outputs)
            return AgentType(outputs)

    return decoded_outputs
