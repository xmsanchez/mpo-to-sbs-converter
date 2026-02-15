# mpo-to-sbs-converter

## Description

ℹ️ Keep in mind that this was primarily done to use with **Xreal Glasses**.

_Disclaimer: This tool was vibe-coded in 10 minutes using Gemini 3 Pro. Took me more time writing this README than writing the script._

This tool will allow you to convert old _*MPO_ and _AVI_ 3D files to a format compatible with newer VR Headsets (Meta Quest) and XR Glasses (Xreal, Viture).

_*MPO was the native format in Fujifilm W3, 3DS and some older cameras and smartphones_

Features:

- Convert MPO 3D files to JPEG side-by-side
- Convert AVI 3D files (two streams) to MP4 side-by-side
- Clone original metadata (date, location, camera...)
- Rename files using the format expected by Xreal (to auto-switch to 3D)

## Requirements

### Python dependencies

> It is recommended to use a virtual environment

Install requirements with pip:

```bash
pip install -r requirements.txt
```

### fmpeg

For the video conversion we rely in fmpeg. We can install it in Linux with apt:

```bash
sudo apt update
sudo apt install ffmpeg
```

## Using the script

By default it will search both images and video files (recursively) in a folder called "input".

We can override this with the _-i _ flag:

```bash
python main.py -i <another_folder>
```

By default, all converted files will be created in an _output_ folder. In this folder, the subfolders _images_ and _videos_ will be created.

## Other options

Use the _--help_ flag to see all the available options:

```bash
> python main.py --help
usage: main.py [-h] [-i INPUT] [-o OUTPUT] [--ffmpeg FFMPEG] [--skip-photos] [--skip-videos]

Convert Fujifilm W3 Photos (MPO) and Videos (AVI) to XREAL format (Recursive).

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Input folder containing files (searches recursively).
  -o OUTPUT, --output OUTPUT
                        Base output folder.
  --ffmpeg FFMPEG       Path to ffmpeg executable.
  --skip-photos         Do not process .MPO photos.
  --skip-videos         Do not process .AVI videos.
```
