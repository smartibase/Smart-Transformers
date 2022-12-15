# Copyright 2022 The Loop Team and the HuggingFace Team. All rights reserved.
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

import re
from typing import List, Optional, Tuple, Union

import numpy as np

from ..utils import (
    ExplicitEnum,
    add_end_docstrings,
    is_pytesseract_available,
    is_torch_available,
    is_vision_available,
    logging,
)
from .base import PIPELINE_INIT_ARGS, Pipeline

if is_vision_available():
    from PIL import Image

    from ..image_utils import load_image

if is_torch_available():
    import torch

    from ..models.auto.modeling_auto import MODEL_FOR_DOCUMENT_TOKEN_CLASSIFICATION_MAPPING

TESSERACT_LOADED = False
if is_pytesseract_available():
    TESSERACT_LOADED = True
    import pytesseract

logger = logging.get_logger(__name__)


# normalize_bbox() and apply_tesseract() are derived from apply_tesseract in models/layoutlmv3/feature_extraction_layoutlmv3.py.
# However, because the pipeline may evolve from what layoutlmv3 currently does, it's copied (vs. imported) to avoid creating an
# unecessary dependency.
def normalize_box(box, width, height):
    return [
        int(1000 * (box[0] / width)),
        int(1000 * (box[1] / height)),
        int(1000 * (box[2] / width)),
        int(1000 * (box[3] / height)),
    ]


def apply_tesseract(image: "Image.Image", lang: Optional[str], tesseract_config: Optional[str]):
    """Applies Tesseract OCR on a document image, and returns recognized words + normalized bounding boxes."""
    # apply OCR
    data = pytesseract.image_to_data(image, lang=lang, output_type="dict", config=tesseract_config)
    words, left, top, width, height = data["text"], data["left"], data["top"], data["width"], data["height"]

    # filter empty words and corresponding coordinates
    irrelevant_indices = [idx for idx, word in enumerate(words) if not word.strip()]
    words = [word for idx, word in enumerate(words) if idx not in irrelevant_indices]
    left = [coord for idx, coord in enumerate(left) if idx not in irrelevant_indices]
    top = [coord for idx, coord in enumerate(top) if idx not in irrelevant_indices]
    width = [coord for idx, coord in enumerate(width) if idx not in irrelevant_indices]
    height = [coord for idx, coord in enumerate(height) if idx not in irrelevant_indices]

    # turn coordinates into (left, top, left+width, top+height) format
    actual_boxes = []
    for x, y, w, h in zip(left, top, width, height):
        actual_box = [x, y, x + w, y + h]
        actual_boxes.append(actual_box)

    image_width, image_height = image.size

    # finally, normalize the bounding boxes
    normalized_boxes = []
    for box in actual_boxes:
        normalized_boxes.append(normalize_box(box, image_width, image_height))

    if len(words) != len(normalized_boxes):
        raise ValueError("Not as many words as there are bounding boxes")

    return words, normalized_boxes


class ModelType(ExplicitEnum):
    LayoutLMv3 = "layoutlmv3"


@add_end_docstrings(PIPELINE_INIT_ARGS)
class DocumentTokenClassificationPipeline(Pipeline):
    # TODO: Update task_summary docs to include an example with document QA and then update the first sentence
    """
    Document Token Classification pipeline using any `AutoModelForDocumentTokenClassification`. The inputs/outputs are
    similar to the (extractive) Token Classification pipeline; however, the pipeline takes an image (and optional OCR'd
    words/boxes) as input instead of text context.

    This Document Token Classification pipeline can currently be loaded from [`pipeline`] using the following task
    identifier: `"document-token-classification"`.

    The models that this pipeline can use are models that have been fine-tuned on a Document Token Classification task.
    See the up-to-date list of available models on
    [huggingface.co/models](https://huggingface.co/models?filter=document-token-classification).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.check_model_type(MODEL_FOR_DOCUMENT_TOKEN_CLASSIFICATION_MAPPING)
        if self.model.config.model_type=="layoutlmv3":
            self.model_type = ModelType.LayoutLMv3

    def _sanitize_parameters(
        self,
        padding=None,
        doc_stride=None,
        lang: Optional[str] = None,
        tesseract_config: Optional[str] = None,
        max_seq_len=None,
        **kwargs,
    ):
        preprocess_params, postprocess_params = {}, {}
        if padding is not None:
            preprocess_params["padding"] = padding
        if doc_stride is not None:
            preprocess_params["doc_stride"] = doc_stride
        if max_seq_len is not None:
            preprocess_params["max_seq_len"] = max_seq_len
        if lang is not None:
            preprocess_params["lang"] = lang
        if tesseract_config is not None:
            preprocess_params["tesseract_config"] = tesseract_config

        return preprocess_params, {}, postprocess_params

    def __call__(
        self,
        image: Union["Image.Image", str],
        word_boxes: Tuple[str, List[float]] = None,
        words: List[str] = None,
        boxes: List[List[float]] = None,
        **kwargs,
    ):
        """
        Classifies the list of tokens (word_boxes) given a document. A document is defined as an image and an
        optional list of (word, box) tuples which represent the text in the document. If the `word_boxes` are not
        provided, it will use the Tesseract OCR engine (if available) to extract the words and boxes automatically for
        LayoutLM-like models which require them as input.

        You can invoke the pipeline several ways:

        - `pipeline(image=image, word_boxes=word_boxes)`
        - `pipeline(image=image, words=words, boxes=boxes)`
        - `pipeline(image=image)`

        Args:
            image (`str` or `PIL.Image`):
                The pipeline handles three types of images:

                - A string containing a http link pointing to an image
                - A string containing a local path to an image
                - An image loaded in PIL directly

                The pipeline accepts either a single image or a batch of images. If given a single image, it can be
                broadcasted to multiple questions.
            word_boxes (`List[str, Tuple[float, float, float, float]]`, *optional*):
                A list of words and bounding boxes (normalized 0->1000). If you provide this optional input, then the
                pipeline will use these words and boxes instead of running OCR on the image to derive them for models
                that need them (e.g. LayoutLM). This allows you to reuse OCR'd results across many invocations of the
                pipeline without having to re-run it each time.
            words (`List[str]`, *optional*):
                A list of words. If you provide this optional input, then the pipeline will use these words instead of
                running OCR on the image to derive them for models that need them (e.g. LayoutLM). This allows you to
                reuse OCR'd results across many invocations of the pipeline without having to re-run it each time.
            boxes (`List[Tuple[float, float, float, float]]`, *optional*):
                A list of bounding boxes (normalized 0->1000). If you provide this optional input, then the pipeline will
                use these boxes instead of running OCR on the image to derive them for models that need them (e.g.
                LayoutLM). This allows you to reuse OCR'd results across many invocations of the pipeline without having
                to re-run it each time.
            TODO doc_stride (`int`, *optional*, defaults to 128):
                If the words in the document are too long to fit with the question for the model, it will be split in
                several chunks with some overlap. This argument controls the size of that overlap.
            TODO max_seq_len (`int`, *optional*, defaults to 384):
                The maximum length of the total sentence (context + question) in tokens of each chunk passed to the
                model. The context will be split in several chunks (using `doc_stride` as overlap) if needed.
            TODO max_question_len (`int`, *optional*, defaults to 64):
                The maximum length of the question after tokenization. It will be truncated if needed.
            lang (`str`, *optional*):
                Language to use while running OCR. Defaults to english.
            tesseract_config (`str`, *optional*):
                Additional flags to pass to tesseract while running OCR.

        Return:
            A `dict` or a list of `dict`: Each result comes as a dictionary with the following keys:

            - **logits** - (`List[float]`) - The list of raw logits for each word in the document.
            - **labels** - (`List[str]`) - The list of predicted labels for each word in the document.
        """
        if word_boxes is not None:
            inputs = {
                "image": image,
                "word_boxes": word_boxes,
            }
        else:
            inputs = image
        return super().__call__(inputs, **kwargs)

    def preprocess(self, input, lang=None, tesseract_config=""):
        image = None
        if input.get("image", None) is not None:
            image = load_image(input["image"])

        words, boxes = None, None
        if "words" in input and "boxes" in input:
            words = input["words"]
            boxes = input["boxes"]
        elif "word_boxes" in input:
            words = [x[0] for x in input["word_boxes"]]
            boxes = [x[1] for x in input["word_boxes"]]
        elif image is not None:
            if not TESSERACT_LOADED:
                raise ValueError(
                    "If you provide an image without word_boxes, then the pipeline will run OCR using Tesseract,"
                    " but pytesseract is not available"
                )
            if TESSERACT_LOADED:
                words, boxes = apply_tesseract(image, lang=lang, tesseract_config=tesseract_config)
        else:
            raise ValueError(
                "You must provide an image or word_boxes. If you provide an image, the pipeline will automatically"
                " run OCR to derive words and boxes"
            )
        
        encoding = None
        if self.model_type == ModelType.LayoutLMv3:
            from ..models.layoutlmv3.processing_layoutlmv3 import LayoutLMv3Processor as processor
            images = image
            words = words
            boxes = boxes
            encoding = processor(images, words, boxes=boxes,truncation=True, padding="max_length")

        return encoding

    def _forward(self, model_inputs):
        word_ids = model_inputs.pop("word_ids", None)
        words = model_inputs.pop("words", None)

        model_outputs = self.model(**model_inputs)

        model_outputs["word_ids"] = word_ids
        model_outputs["words"] = words
        model_outputs["attention_mask"] = model_inputs.get("attention_mask", None)
        return model_outputs

    def postprocess(self, model_outputs, **kwargs):
        
        return model_outputs

