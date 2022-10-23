import argparse

import torch

from transformers import CLIPSegConfig, CLIPSegForImageSegmentation


def get_clipseg_config():
    config = CLIPSegConfig()
    return config


def rename_key(name):
    # update prefixes
    if "clip_model" in name:
        name = name.replace("clip_model", "clipseg")
    if "transformer" in name:
        if "visual" in name:
            name = name.replace("visual.transformer", "vision_model")
        else:
            name = name.replace("transformer", "text_model")
    if "resblocks" in name:
        name = name.replace("resblocks", "encoder.layers")
    if "ln_1" in name:
        name = name.replace("ln_1", "layer_norm1")
    if "ln_2" in name:
        name = name.replace("ln_2", "layer_norm2")
    if "mlp.fc1" in name:
        name = name.replace("mlp.fc1", "intermediate.dense")
    if "mlp.fc2" in name:
        name = name.replace("mlp.fc2", "output.dense")
    if "ln_final" in name:
        name = name.replace("ln_final", "final_layer_norm")
    # text encoder
    if "token_embedding" in name:
        name = name.replace("token_embedding", "text_model.embeddings.token_embedding")
    if "positional_embedding" in name:
        name = name.replace("positional_embedding", "text_model.embeddings.token_embedding.weight")
    # vision encoder
    if "visual.class_embedding" in name:
        name = name.replace("visual.class_embedding", "vision_model.embeddings.class_embedding")
    if "visual.positional_embedding" in name:
        name = name.replace("visual.positional_embedding", "vision_model.embeddings.position_embedding")
    if "ln_pre" in name:
        name = name.replace("ln_pre", "pre_layrnorm")

    return name


def convert_state_dict(orig_state_dict, config):
    for key in orig_state_dict.copy().keys():
        val = orig_state_dict.pop(key)

        if "attn" in key:
            # TODO
            pass
        else:
            orig_state_dict[rename_key(key)] = val

    return orig_state_dict


def convert_clipseg_checkpoint(checkpoint_path, pytorch_dump_folder_path):
    config = get_clipseg_config()
    model = CLIPSegForImageSegmentation(config)
    model.eval()

    state_dict = torch.load(checkpoint_path, map_location="cpu")
    state_dict = convert_state_dict(state_dict, config)
    model.load_state_dict(state_dict)

    # TODO assert values
    # url = "http://images.cocodataset.org/val2017/000000039769.jpg"

    # feature_extractor = AutoFeatureExtractor.from_pretrained("microsoft/{}".format(model_name.replace("_", "-")))
    # image = Image.open(requests.get(url, stream=True).raw)
    # inputs = feature_extractor(images=image, return_tensors="pt")

    # timm_outs = timm_model(inputs["pixel_values"])
    # hf_outs = model(**inputs).logits

    # assert torch.allclose(timm_outs, hf_outs, atol=1e-3)

    if pytorch_dump_folder_path is not None:
        print(f"Saving model to {pytorch_dump_folder_path}")
        model.save_pretrained(pytorch_dump_folder_path)

        # print(f"Saving feature extractor to {pytorch_dump_folder_path}")
        # feature_extractor.save_pretrained(pytorch_dump_folder_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Required parameters
    parser.add_argument(
        "--checkpoint_path",
        default="/Users/nielsrogge/Downloads/clipseg_weights/rd64-uni.pth",
        type=str,
        help="Path to the original checkpoint.",
    )
    parser.add_argument(
        "--pytorch_dump_folder_path", default=None, type=str, help="Path to the output PyTorch model directory."
    )

    args = parser.parse_args()
    convert_clipseg_checkpoint(args.checkpoint_path, args.pytorch_dump_folder_path)
