# Copyright 2021 The HuggingFace Team.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Steps to create and release the package on PyPI:

1. Create a release branch: `v<RELEASE>-release`, e.g., `v4.19-release`.
2. For patch releases, check out the current release branch.
3. Run `make pre-release` or `make pre-patch` for a patch release.
4. Commit the changes: "Release: <VERSION>" and push.
5. After tests are successful, tag the release: `git tag v<VERSION> -m 'Release <VERSION>'`.
6. Push the tag: `git push --tags origin v<RELEASE>-release`.
7. Build the package: `make build-release`.
8. Check the package using Test PyPI: `twine upload dist/* -r testpypi`.
9. After verification, upload to PyPI: `twine upload dist/* -r pypi`.
"""

import os
import re
import shutil
from pathlib import Path
from setuptools import Command, find_packages, setup

# Clean up any stale build artifacts.
stale_egg_info = Path(__file__).parent / "transformers.egg-info"
if stale_egg_info.exists():
    print(f"Removing stale build artifacts: {stale_egg_info}")
    shutil.rmtree(stale_egg_info)

# List of dependencies
_deps = [
    "Pillow>=10.0.1,<=15.0",
    "accelerate>=0.26.0",
    "av==9.2.0",  # Issue with audio stream in newer versions
    "beautifulsoup4",
    "codecarbon==1.2.0",
    "datasets!=2.5.0",
    "decord==0.6.0",
    "deepspeed>=0.9.3",
    "diffusers",
    "evaluate>=0.2.0",
    "filelock",
    "flax>=0.4.1,<=0.7.0",
    "huggingface-hub>=0.23.2,<1.0",
    "isort>=5.5.4",
    "jax>=0.4.1,<=0.4.13",
    "jinja2>=3.1.0",
    "keras>2.9,<2.16",
    "librosa",
    "numpy>=1.17",
    "onnxconverter-common",
    "onnxruntime>=1.4.0",
    "opencv-python",
    "optuna",
    "packaging>=20.0",
    "protobuf",
    "pytest>=7.2.0,<8.0.0",
    "pytest-timeout",
    "regex!=2019.12.17",
    "requests",
    "scikit-learn",
    "scipy<1.13.0",
    "sentencepiece>=0.1.91,!=0.1.92",
    "timm<=0.9.16",
    "tokenizers>=0.20,<0.21",
    "torch",
    "torchaudio",
    "torchvision",
    "tqdm>=4.27",
    "urllib3<2.0.0",
    "uvicorn",
    "tensorflow>2.9,<2.16",
    "tensorflow-text<2.16",
]

# Create a mapping of dependency names and their versions.
deps = {pkg.split("==")[0]: pkg for pkg in _deps}

# Helper function to select dependencies
def deps_list(*pkgs):
    return [deps[pkg] for pkg in pkgs]

# Command for updating the dependencies version table
class DepsTableUpdateCommand(Command):
    description = "Update dependency version table."
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        content = [
            "# THIS FILE HAS BEEN AUTOGENERATED. To update, run `make deps_table_update`.",
            "deps = {",
            "\n".join([f'    "{k}": "{v}",' for k, v in deps.items()]),
            "}",
        ]
        target = Path("src/transformers/dependency_versions_table.py")
        print(f"Updating {target}")
        target.write_text("\n".join(content), encoding="utf-8")

# Extra groups for optional dependencies
extras = {
    "vision": deps_list("Pillow"),
    "torch": deps_list("torch", "torchvision", "torchaudio"),
    "tensorflow": deps_list("tensorflow", "tensorflow-text"),
    "scikit-learn": deps_list("scikit-learn"),
    "onnx": deps_list("onnxconverter-common", "onnxruntime"),
    "nlp": deps_list("datasets", "tokenizers", "sentencepiece"),
    "dev": deps_list("pytest", "isort", "black", "huggingface-hub"),
}

# Installation requirements
install_requires = [
    deps["filelock"],
    deps["huggingface-hub"],
    deps["numpy"],
    deps["packaging"],
    deps["requests"],
    deps["tqdm"],
]

# Final setup configuration
setup(
    name="transformers",
    version="4.46.0.dev0",
    author="The Hugging Face team",
    author_email="transformers@huggingface.co",
    description="State-of-the-art Machine Learning for JAX, PyTorch, and TensorFlow",
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/huggingface/transformers",
    license="Apache 2.0 License",
    package_dir={"": "src"},
    packages=find_packages("src"),
    install_requires=install_requires,
    extras_require=extras,
    python_requires=">=3.8.0",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    entry_points={
        "console_scripts": ["transformers-cli=transformers.commands.transformers_cli:main"]
    },
    cmdclass={
        "deps_table_update": DepsTableUpdateCommand,
    },
    include_package_data=True,
    package_data={"": ["**/*.cu", "**/*.cpp", "**/*.cuh", "**/*.h", "**/*.pyx"]},
    zip_safe=False,
)
