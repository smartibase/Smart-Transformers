# coding=utf-8
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
"""Image processor class for LLaVa-NeXT."""

from typing import List, Optional, Tuple, Union

import numpy as np
import torch

from ...image_processing_utils import BaseImageProcessor, BatchFeature, select_best_resolution
from ...image_transforms import (
    convert_to_rgb,
    resize,
    to_channel_dimension_format,
)
from ...image_utils import (
    ChannelDimension,
    ImageInput,
    PILImageResampling,
    get_image_size,
    to_numpy_array,
)
from ...utils import TensorType, is_vision_available, logging


logger = logging.get_logger(__name__)


if is_vision_available():
    from PIL import Image, ImageOps


def divide_to_patches(image: np.array, patch_size: int, input_data_format) -> List[np.array]:
    """
    Divides an image into patches of a specified size.

    Args:
        image (`np.array`):
            The input image.
        patch_size (`int`):
            The size of each patch.
        input_data_format (`ChannelDimension` or `str`):
            The channel dimension format of the input image.

    Returns:
        list: A list of np.array representing the patches.
    """
    patches = []
    height, width = get_image_size(image, channel_dim=input_data_format)
    for i in range(0, height, patch_size):
        for j in range(0, width, patch_size):
            if input_data_format == ChannelDimension.LAST:
                patch = image[i : i + patch_size, j : j + patch_size]
            else:
                patch = image[:, i : i + patch_size, j : j + patch_size]
            patches.append(patch)

    return patches



def keep_ratio_resize_and_pixel_mask(img: ImageInput, max_size, min_size=336, padding_value=0):
    """
    Resize an image while maintaining aspect ratio and create a pixel mask.

    Args:
        img (ImageInput): Input image.
        max_size (int): Maximum size for the larger dimension of the image.
        min_size (int, optional): Minimum size for the smaller dimension. Defaults to 336.
        padding_value (int, optional): Value used for padding. Defaults to 0.

    Returns:
        tuple: A tuple containing:
            - ImageInput: Resized and padded image.
            - torch.Tensor: Boolean pixel mask. This mask is a 2D tensor of shape (max_size, max_size) where:
                - True (1) values indicate pixels that belong to the original resized image.
                - False (0) values indicate pixels that are part of the padding.
              The mask helps distinguish between actual image content and padded areas in subsequent processing steps.
    """
    img = img.convert("RGB")
    # rescale the given image, keep the aspect ratio
    scale = max_size / max(img.size)

    w, h = img.size
    if w >= h:
        new_size = (max_size, max(int(h * scale), min_size))  # w, h
    else:
        new_size = (max(int(w * scale), min_size), max_size)  # w, h

    img_resized = img.resize(new_size, resample=Image.Resampling.BICUBIC)

    # padding the right/bottom
    padding_right, padding_bottom = max_size - new_size[0], max_size - new_size[1]
    img_padded = ImageOps.expand(img_resized, (0, 0, padding_right, padding_bottom), fill=padding_value)

    # Create a pixel mask
    pixel_mask = torch.zeros(max_size, max_size, dtype=bool)
    pixel_mask[: new_size[1], : new_size[0]] = 1
    return img_padded, pixel_mask


class AriaVisionProcessor(BaseImageProcessor):
    """
    A vision processor for the Aria model that handles image preprocessing.
    """

    def __init__(
        self,
        max_image_size=980,
        min_image_size=336,
        image_mean=None,
        image_std=None,
        **kwargs,
    ):
        """
        Initialize the AriaVisionProcessor.

        Args:
            max_image_size (int, optional): Maximum image size. Defaults to 980.
            min_image_size (int, optional): Minimum image size. Defaults to 336.
            mean (list, optional): Mean values for normalization. Defaults to [0.5, 0.5, 0.5].
            std (list, optional): Standard deviation values for normalization. Defaults to [0.5, 0.5, 0.5].
        """
        super().__init__(**kwargs)

        if image_mean is None:
            image_mean = [0.5, 0.5, 0.5]
        if image_std is None:
            image_std = [0.5, 0.5, 0.5]
        self.max_image_size = max_image_size
        self.min_image_size = min_image_size
        self.image_mean = image_mean
        self.image_std = image_std

        # we make the transform a property so that it is lazily initialized,
        # this could avoid the error "TypeError: Object of type Normalize is not JSON serializable"
        # when we used save_pretrained or from_pretrained.
        self._transform = None
        self._set_processor_class("AriaProcessor")

    def preprocess(
        self,
        images: Union[ImageInput, List[ImageInput]],
        max_image_size: Optional[int] = 980,
        min_image_size: Optional[int] = 336,
        return_tensors: Optional[Union[str, TensorType]] = "pt",
        split_image: Optional[bool] = False,
        split_ratio: Optional[List[Tuple[int]]] = None,
        do_convert_rgb: Optional[bool] = True,
        do_normalize: Optional[bool] = True,
    ):
        """
        Process a list of images.

        Args:
            images (list): List of ImageInput objects.
            max_image_size (int, optional): Override the default max image size. Defaults to None.
            return_tensors (str or TensorType, optional): The type of tensor to return. Defaults to "pt".
            split_image (bool, optional): Whether to split the image. Defaults to False.
            split_ratio (list, optional): The ratio for splitting the image. Defaults to a list of common split ratios as tuples.
        Returns:
            BatchFeature: A BatchFeature object containing:
                - 'pixel_values': Tensor of processed image pixel values.
                - 'pixel_mask': Boolean pixel mask. This mask is a 2D tensor of shape (max_size, max_size) where:
                    - True (1) values indicate pixels that belong to the original resized image.
                    - False (0) values indicate pixels that are part of the padding.
                  The mask helps distinguish between actual image content and padded areas in subsequent processing steps.
                - 'num_crops': Tensor of the number of crops for each image.
        """
        if split_ratio is None:
            split_ratio = [
                (1, 2),
                (1, 3),
                (1, 4),
                (1, 5),
                (1, 6),
                (1, 7),
                (1, 8),
                (2, 4),
                (2, 3),
                (2, 2),
                (2, 1),
                (3, 1),
                (3, 2),
                (4, 1),
                (4, 2),
                (5, 1),
                (6, 1),
                (7, 1),
                (8, 1),
            ]
        max_size = self.max_image_size if max_image_size is None else max_image_size
        min_size = self.min_image_size if min_image_size is None else min_image_size

        if max_size not in [490, 980]:
            raise ValueError("max_image_size must be either 490 or 980")

        if not isinstance(images, list):
            images = [images]

        pixel_values = []
        pixel_masks = []
        num_crops = None

        for image in images:
            if split_image:
                crop_images = self.get_image_patches(image, split_ratio, max_size, max_size)[1:]
            else:
                crop_images = [image]
            if num_crops is None or len(crop_images) > num_crops:
                num_crops = len(crop_images)
            for crop_image in crop_images:
                img_padded, pixel_mask = keep_ratio_resize_and_pixel_mask(crop_image, max_size, min_size)
                if do_convert_rgb:
                    img_padded = convert_to_rgb(img_padded)
                img_padded = to_numpy_array(img_padded).T
                if do_normalize:
                    img_padded = self.normalize(img_padded, self.image_mean, self.image_std)
                pixel_values.append(img_padded)
                pixel_masks.append(pixel_mask)
        return BatchFeature(
            data={
                "pixel_values": np.stack(pixel_values, axis=0),
                "pixel_mask": np.stack(pixel_masks, axis=0),
                "num_crops": num_crops,
            },
            tensor_type=return_tensors,
        )

    def get_image_patches(
        self,
        image: np.array,
        grid_pinpoints,
        size: tuple,
        patch_size: int,
        resample: PILImageResampling,
        data_format: ChannelDimension,
        input_data_format: ChannelDimension,
    ) -> List[np.array]:
        """
        Process an image with variable resolutions by dividing it into patches.

        Args:
            image (np.array):
                The input image to be processed.
            grid_pinpoints (List):
                A string representation of a list of possible resolutions.
            size (`tuple`):
                Size to resize the original image to.
            patch_size (`int`):
                Size of the patches to divide the image into.
            resample (`PILImageResampling`):
                Resampling filter to use if resizing the image.
            data_format (`ChannelDimension` or `str`):
                The channel dimension format for the output image.
            input_data_format (`ChannelDimension` or `str`):
                The channel dimension format of the input image.

        Returns:
            List[np.array]: A list of NumPy arrays containing the processed image patches.
        """
        if not isinstance(grid_pinpoints, list):
            raise TypeError("grid_pinpoints must be a list of possible resolutions.")

        possible_resolutions = grid_pinpoints

        image_size = get_image_size(image, channel_dim=input_data_format)
        best_resolution = select_best_resolution(image_size, possible_resolutions)
        resized_image = self._resize_for_patching(
            image, best_resolution, resample=resample, input_data_format=input_data_format
        )
        padded_image = self._pad_for_patching(resized_image, best_resolution, input_data_format=input_data_format)

        patches = divide_to_patches(padded_image, patch_size=patch_size, input_data_format=input_data_format)

        # make sure that all patches are in the input data format
        patches = [
            to_channel_dimension_format(patch, channel_dim=data_format, input_channel_dim=input_data_format)
            for patch in patches
        ]

        resized_original_image = resize(
            image,
            size=size,
            resample=resample,
            data_format=data_format,
            input_data_format=input_data_format,
        )

        image_patches = [resized_original_image] + patches

        return image_patches
