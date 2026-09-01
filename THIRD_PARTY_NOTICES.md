# Third-party notices

This repository contains original orchestration, prompting, reconstruction, and WebXR export code.
It does **not** redistribute model weights or source code from MiniMax H3, OpenAI models,
Nerfstudio, COLMAP, Three.js, or Spark.

## MiniMax H3

MiniMax H3 is accessed through the MiniMax API by default. Local H3 weights may be used by a
future provider, but they are not included here. Review the current MiniMax H3 Community License
before downloading, deploying, fine-tuning, or commercially using H3. In particular, the license
contains territory, revenue, attribution, use-restriction, and output-training clauses. This notice
is not legal advice.

- Project: https://github.com/MiniMax-AI/MiniMax-H3
- License: https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE

## OpenAI image models

The optional image provider calls OpenAI's Image API. No OpenAI model weights are included.
Use is subject to the applicable OpenAI terms and policies.

## Nerfstudio and COLMAP

Nerfstudio and COLMAP are external executables. The user installs them separately and is
responsible for their respective licenses.

## Spark and Three.js

Generated viewers load Three.js and Spark from public CDNs at runtime. Their code is not copied
into this repository. Spark and Three.js are distributed under their respective licenses.
