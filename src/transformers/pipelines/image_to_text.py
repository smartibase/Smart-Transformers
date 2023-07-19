from typing import List, Union

from ..utils import (
    add_end_docstrings,
    is_torch_available,
    is_vision_available,
    logging,
    requires_backends,
)
from .base import PIPELINE_INIT_ARGS, Pipeline


if is_vision_available():
    from PIL import Image

    from ..image_utils import load_image

if is_torch_available():
    import torch


logger = logging.get_logger(__name__)


@add_end_docstrings(PIPELINE_INIT_ARGS)
class ImageToTextPipeline(Pipeline):
    """
    Image To Text pipeline using a `AutoModelForVision2Seq`. This pipeline predicts a caption for a given image.

    Example:

    ```python
    >>> from transformers import pipeline

    >>> captioner = pipeline(model="ydshieh/vit-gpt2-coco-en")
    >>> captioner("https://huggingface.co/datasets/Narsil/image_dummy/raw/main/parrots.png")
    [{'generated_text': 'two birds are standing next to each other '}]
    ```

    Learn more about the basics of using a pipeline in the [pipeline tutorial](../pipeline_tutorial)

    This image to text pipeline can currently be loaded from pipeline() using the following task identifier:
    "image-to-text".

    See the list of available models on
    [huggingface.co/models](https://huggingface.co/models?pipeline_tag=image-to-text).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        requires_backends(self, "vision")

    def _sanitize_parameters(self, max_new_tokens=None, generate_kwargs=None, prompt=None):
        forward_kwargs = {}
        preprocess_params = {}

        if prompt is not None:
            preprocess_params["prompt"] = prompt

        if generate_kwargs is not None:
            forward_kwargs["generate_kwargs"] = generate_kwargs
        if max_new_tokens is not None:
            if "generate_kwargs" not in forward_kwargs:
                forward_kwargs["generate_kwargs"] = {}
            if "max_new_tokens" in forward_kwargs["generate_kwargs"]:
                raise ValueError(
                    "'max_new_tokens' is defined twice, once in 'generate_kwargs' and once as a direct parameter,"
                    " please use only one"
                )
            forward_kwargs["generate_kwargs"]["max_new_tokens"] = max_new_tokens
        return preprocess_params, forward_kwargs, {}

    def __call__(self, images: Union[str, List[str], "Image.Image", List["Image.Image"]], **kwargs):
        """
        Assign labels to the image(s) passed as inputs.

        Args:
            images (`str`, `List[str]`, `PIL.Image` or `List[PIL.Image]`):
                The pipeline handles three types of images:

                - A string containing a HTTP(s) link pointing to an image
                - A string containing a local path to an image
                - An image loaded in PIL directly

                The pipeline accepts either a single image or a batch of images.

            max_new_tokens (`int`, *optional*):
                The amount of maximum tokens to generate. By default it will use `generate` default.

            generate_kwargs (`Dict`, *optional*):
                Pass it to send all of these arguments directly to `generate` allowing full control of this function.

        Return:
            A list or a list of list of `dict`: Each result comes as a dictionary with the following key:

            - **generated_text** (`str`) -- The generated text.
        """
        return super().__call__(images, **kwargs)

    def preprocess(self, image, prompt=None):
        image = load_image(image)

        if prompt is not None:
            if not isinstance(prompt, str):
                raise ValueError(
                    f"Received an invalid text input, got - {type(prompt)} - but expected a single string. "
                    "Note also that one single text can be provided for conditional image to text generation."
                )

            model_type = self.model.config.model_type

            if model_type == "git":
                model_inputs = self.image_processor(images=image, return_tensors=self.framework)
                input_ids = self.tokenizer(text=prompt, add_special_tokens=False).input_ids
                input_ids = [self.tokenizer.cls_token_id] + input_ids
                input_ids = torch.tensor(input_ids).unsqueeze(0)
                model_inputs.update({"input_ids": input_ids})

            elif model_type == "pix2struct":
                model_inputs = self.image_processor(images=image, header_text=prompt, return_tensors=self.framework)

            elif model_type != "vision-encoder-decoder":
                # vision-encoder-decoder does not support conditional generation
                model_inputs = self.image_processor(images=image, return_tensors=self.framework)
                text_inputs = self.tokenizer(prompt, return_tensors=self.framework)
                model_inputs.update(text_inputs)

            else:
                raise ValueError(f"Model type {model_type} does not support conditional text generation")

        else:
            model_inputs = self.image_processor(images=image, return_tensors=self.framework)

        if self.model.config.model_type == "git" and prompt is None:
            model_inputs["input_ids"] = None

        return model_inputs

    def _forward(self, model_inputs, generate_kwargs=None):
        # Git model sets `model_inputs["input_ids"] = None` in `preprocess` (when `prompt=None`). In batch model, the
        # pipeline will group them into a list of `None`, which fail `_forward`. Avoid this by checking it first.
        if (
            "input_ids" in model_inputs
            and isinstance(model_inputs["input_ids"], list)
            and all(x is None for x in model_inputs["input_ids"])
        ):
            model_inputs["input_ids"] = None

        if generate_kwargs is None:
            generate_kwargs = {}
        # FIXME: We need to pop here due to a difference in how `generation.py` and `generation.tf_utils.py`
        #  parse inputs. In the Tensorflow version, `generate` raises an error if we don't use `input_ids` whereas
        #  the PyTorch version matches it with `self.model.main_input_name` or `self.model.encoder.main_input_name`
        #  in the `_prepare_model_inputs` method.
        inputs = model_inputs.pop(self.model.main_input_name)
        model_outputs = self.model.generate(inputs, **model_inputs, **generate_kwargs)
        return model_outputs

    def postprocess(self, model_outputs):
        records = []
        for output_ids in model_outputs:
            record = {
                "generated_text": self.tokenizer.decode(
                    output_ids,
                    skip_special_tokens=True,
                )
            }
            records.append(record)
        return records
