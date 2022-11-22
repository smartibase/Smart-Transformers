import numpy as np 
from huggingface_hub import hf_hub_download

from transformers import VideoMAEFeatureExtractor
from src.transformers.models.videomae.modeling_tf_videomae import TFVideoMAEForVideoClassification


# We will verify our results on a video of eating spaghetti
# Frame indices used: [164 168 172 176 181 185 189 193 198 202 206 210 215 219 223 227]
def prepare_video():
    file = hf_hub_download(
        repo_id="hf-internal-testing/spaghetti-video", filename="eating_spaghetti.npy", repo_type="dataset"
    )
    video = np.load(file)
    return list(video)

model = TFVideoMAEForVideoClassification.from_pretrained("MCG-NJU/videomae-base-finetuned-kinetics", from_pt=True)

feature_extractor = VideoMAEFeatureExtractor(image_mean=[0.5, 0.5, 0.5], image_std=[0.5, 0.5, 0.5])
video = prepare_video()
inputs = feature_extractor(video, return_tensors="tf")

outputs = model(**inputs)
print(outputs.logits.shape == (1, 400))

expected_slice = np.array([0.3669, -0.0688, -0.2421])

print(np.allclose(outputs.logits[0, :3].numpy(), expected_slice, atol=1e-4))
print(outputs.logits[0, :3].numpy())