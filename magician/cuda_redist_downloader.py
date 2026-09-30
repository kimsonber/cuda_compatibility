#!/usr/bin/env python3
"""
CUDA Redistributable Header Downloader (Simplified)

Downloads CUDA SDK component header files from multiple sources and places them
in a standard directory structure.

Sources:
  - CUDA 11.4+: NVIDIA redist JSON (tar.xz)
  - CUDA 11.0~11.3: Ubuntu deb packages (ar + tar.xz)
  - cuDNN 8.5+: NVIDIA redist JSON (tar.xz)
  - cuDNN 8.0~8.4: NVIDIA old CDN paths (.tgz / .tar.xz)
  - NCCL 2.17+: PyPI wheels (zip)
  - NCCL 2.8~2.12: NVIDIA CDN (.txz)
  - Video Codec SDK: FFmpeg/nv-codec-headers (tar.gz + content conversion)
"""

from __future__ import annotations

import errno
import hashlib
import io
import json
import logging
import lzma
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
import zipfile

logger = logging.getLogger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================

class DownloadError(Exception):
    """Base exception for download-related errors."""
    pass


class NetworkError(DownloadError):
    """Network connectivity or timeout errors."""
    pass


class HTTPError(DownloadError):
    """HTTP protocol errors (404, 500, etc.)."""
    def __init__(self, message: str, status_code: int = None, url: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class ValidationError(DownloadError):
    """File validation errors (size mismatch, checksum failure, etc.)."""
    def __init__(self, message: str, expected: str = None, actual: str = None):
        super().__init__(message)
        self.expected = expected
        self.actual = actual


# =============================================================================
# Constants
# =============================================================================

CUDA_REDIST_BASE_URL = "https://developer.download.nvidia.cn/compute/cuda/redist"
CUDNN_REDIST_BASE_URL = "https://developer.download.nvidia.cn/compute/cudnn/redist"
NCCL_PYPI_BASE_URL = "https://pypi.nvidia.cn/nvidia-nccl-cu12"
NCCL_CDN_BASE_URL = "https://developer.download.nvidia.cn/compute/redist/nccl"
CUDNN_OLD_BASE_URL = "https://developer.download.nvidia.cn/compute/redist/cudnn"
DEB_BASE_URL = "https://developer.download.nvidia.cn/compute/cuda/repos"
GITHUB_BASE_URL = "https://github.com"

# Version mapping from input_lib_version.ini
VERSION_MAP = {
    "11.0": {"cuda": "11.0.3", "cudnn": "8.0.2", "nccl": "2.8.3", "video": "12.1.14"},
    "11.1": {"cuda": "11.1.1", "cudnn": "8.0.5", "nccl": "2.8.3", "video": "12.1.14"},
    "11.2": {"cuda": "11.2.1", "cudnn": "8.1.1", "nccl": "2.8.4", "video": "12.1.14"},
    "11.3": {"cuda": "11.3.1", "cudnn": "8.2.1", "nccl": "2.9.9", "video": "12.1.14"},
    "11.4": {"cuda": "11.4.2", "cudnn": "8.2.4", "nccl": "2.11.4", "video": "12.1.14"},
    "11.5": {"cuda": "11.5.0", "cudnn": "8.3.1", "nccl": "2.11.4", "video": "12.1.14"},
    "11.6": {"cuda": "11.6.2", "cudnn": "8.4.0", "nccl": "2.12.10", "video": "12.1.14"},
    "11.7": {"cuda": "11.7.1", "cudnn": "8.5.0", "nccl": "2.17.1", "video": "12.1.14"},
    "11.8": {"cuda": "11.8.0", "cudnn": "8.6.0", "nccl": "2.17.1", "video": "12.1.14"},
    "12.0": {"cuda": "12.0.1", "cudnn": "8.7.0", "nccl": "2.17.1", "video": "12.1.14"},
    "12.1": {"cuda": "12.1.1", "cudnn": "8.9.3", "nccl": "2.18.3", "video": "12.1.14"},
    "12.2": {"cuda": "12.2.2", "cudnn": "8.9.5", "nccl": "2.19.3", "video": "12.1.14"},
    "12.3": {"cuda": "12.3.0", "cudnn": "8.9.5", "nccl": "2.19.3", "video": "12.1.14"},
    "12.4": {"cuda": "12.4.1", "cudnn": "8.9.5", "nccl": "2.21.5", "video": "13.0.19"},
    "12.5": {"cuda": "12.5.1", "cudnn": "8.9.5", "nccl": "2.22.3", "video": "13.0.19"},
    "12.6": {"cuda": "12.6.0", "cudnn": "8.9.5", "nccl": "2.22.3", "video": "13.0.19"},
    "12.8": {"cuda": "12.8.0", "cudnn": "8.9.5", "nccl": "2.27.3", "video": "13.0.19"},
    "12.9": {"cuda": "12.9.0", "cudnn": "8.9.5", "nccl": "2.27.3", "video": "13.0.19"},
    "13.0": {"cuda": "13.0.0", "cudnn": "8.9.5", "nccl": "2.27.3", "video": "13.0.19"},
    "13.1": {"cuda": "13.1.0", "cudnn": "8.9.5", "nccl": "2.27.3", "video": "13.0.19"},
    "13.2": {"cuda": "13.2.0", "cudnn": "8.9.5", "nccl": "2.27.3", "video": "13.0.19"},
    "13.3": {"cuda": "13.3.0", "cudnn": "8.9.5", "nccl": "2.27.3", "video": "13.0.19"},
}

# CUDA components to download
CUDA_COMPONENTS = [
    "cccl", "cuda_cccl", "cuda_crt", "cuda_cudart", "cuda_cupti", "cuda_cuxxfilt", "cuda_gdb",
    "cuda_nvcc", "cuda_nvml_dev", "cuda_nvprof", "cuda_nvrtc", "cuda_nvtx",
    "cuda_opencl", "cuda_profiler_api", "cuda_sandbox_dev", "cuda_sanitizer_api",
    "libcublas", "libcufft", "libcufile", "libcurand",
    "libcusolver", "libcusparse", "libnpp", "libnvfatbin", "libcuobjclient", "libnvjitlink", "libnvjpeg", "libnvptxcompiler",
    "libnvvm",
]

# Special components with non-standard extraction paths
# Format: list of (tar_path_pattern, target_subdir)
# - tar_path_pattern: pattern to match in tar archive path
# - target_subdir: directory under sdk_dir to extract to
SPECIAL_COMPONENTS = {
    "cuda_nvcc": [
        ("nvvm/include", "nvvm/include"),  # nvvm/include/*.h → nvvm/include/*.h
        ("include", "targets/x86_64-linux/include"),  # include/*.h → targets/x86_64-linux/include/*.h
    ],
    "cuda_sanitizer_api": [("compute-sanitizer/include", "compute-sanitizer/include")],
    "cuda_cupti": [("include", "extras/CUPTI/include")],
    "cuda_gdb": [("extras/Debugger/include", "extras/Debugger/include")],
    "libnvvm": [("nvvm/include", "nvvm/include")],
}

# Components where headers are at the END of the tar archive.
# These must be fully downloaded — streaming early-stop won't help.
HEADERS_AT_END = {"cudnn", "libcufile"}

# Components known to have NO header files — skip download entirely.
NO_HEADERS = set()  # cuda_nvprof has headers (cudaProfiler.h) in 11.4-12.x

# Components that require full download (headers at end of archive).
# libcufile has headers at the very end, so streaming won't help.
# SPECIAL_COMPONENTS also require full download — streaming may miss headers
# that appear at different positions in the tar archive (e.g., nvvm.h in cuda_nvcc).
FULL_DOWNLOAD = HEADERS_AT_END | set(SPECIAL_COMPONENTS.keys())

# For "headers at front" components, limit streaming download to a small
# prefix of the compressed file.  16 MB covers most standard components.
# SPECIAL_COMPONENTS need larger limits (64 MB) due to deeper header locations.
DEFAULT_STREAM_LIMIT = 16 * 1024 * 1024
SPECIAL_STREAM_LIMIT = 64 * 1024 * 1024

# Architecture mapping
ARCH_MAP = {
    "linux-x86_64": "x86_64-linux",
    "linux-aarch64": "aarch64-linux",
    "linux-sbsa": "sbsa-linux",
    "windows-x86_64": "x86_64-win",
}

# Video file mapping
VIDEO_FILE_MAPPING = {
    "nvEncodeAPI.h": "nvEncodeAPI.h",
    "dynlink_cuviddec.h": "cuviddec.h",
    "dynlink_nvcuvid.h": "nvcuvid.h",
}

# cuDNN old versions (8.0~8.4)
CUDNN_OLD = {
    "8.0.2": {"cuda": "11.0", "full": "8.0.2.39", "format": "tgz"},
    "8.0.5": {"cuda": "11.1", "full": "8.0.5.39", "format": "tgz"},
    "8.1.1": {"cuda": "11.2", "full": "8.1.1.33", "format": "tgz"},
    "8.2.1": {"cuda": "11.3", "full": "8.2.1.32", "format": "tgz"},
    "8.2.4": {"cuda": "11.4", "full": "8.2.4.15", "format": "tgz"},
    "8.3.1": {"cuda": "11.5", "full": "8.3.1.22", "format": "tar.xz",
              "path": "local_installers/11.5/cudnn-linux-x86_64-8.3.1.22_cuda11.5-archive.tar.xz"},
    "8.4.0": {"cuda": "11.6", "full": "8.4.0.27", "format": "tar.xz",
              "path": "local_installers/11.6/cudnn-linux-x86_64-8.4.0.27_cuda11.6-archive.tar.xz"},
}

# NCCL old versions (2.8~2.12)
NCCL_OLD = {
    "2.8.3": {"path": "v2.8/nccl_2.8.3-1+cuda11.0_x86_64.txz"},
    "2.8.4": {"path": "v2.8/nccl_2.8.4-1+cuda11.0_x86_64.txz"},
    "2.9.9": {"path": "v2.9/nccl_2.9.9-1+cuda11.0_x86_64.txz"},
    "2.11.4": {"path": "v2.11/nccl_2.11.4-1+cuda11.0_x86_64.txz"},
    "2.12.10": {"path": "v2.12/nccl_2.12.10-1+cuda11.0_x86_64.txz"},
}

# NCCL wheel mapping
NCCL_WHEELS = {
    "2.17.1": ("nvidia_nccl_cu12-2.17.1-py3-none-manylinux1_x86_64.whl",
               "0e8c73799b5cfa35fd4fb04c7a358ea6943b206de34ec83594fd0b0bf665387f"),
    "2.18.3": ("nvidia_nccl_cu12-2.18.3-py3-none-manylinux1_x86_64.whl",
               "89cf220910c43e53df992f54f7aa2a35c6d606b077c9ae95b1f17c544d3ad3f3"),
    "2.19.3": ("nvidia_nccl_cu12-2.19.3-py3-none-manylinux1_x86_64.whl",
               "802756f02c43c0613dc83f48a76f702462b0f1f618411768748bba9c805fce19"),
    "2.21.5": ("nvidia_nccl_cu12-2.21.5-py3-none-manylinux2014_x86_64.whl",
               "8579076d30a8c24988834445f8d633c697d42397e92ffc3f63fa26766d25e0a0"),
    "2.22.3": ("nvidia_nccl_cu12-2.22.3-py3-none-manylinux2014_x86_64.whl",
               "f9f5e03c00269dee2cd1aa57019f9a024478a74ae6e9b32d5341c849fe6f6302"),
    "2.27.3": ("nvidia_nccl_cu12-2.27.3-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
               "adf27ccf4238253e0b826bce3ff5fa532d65fc42322c8bfdfaf28024c0fbe039"),
}

# NCCL versions that should only have nccl.h (not nccl_net.h)
NCCL_NCCL_ONLY = {"2.8.3", "2.8.4", "2.27.3"}

# CUDA deb packages for CUDA 11.0~11.3
DEB_PACKAGES = {
    "11.0": [
        "cuda-cudart-dev-11-0_11.0.221-1_amd64.deb",
        "cuda-nvcc-11-0_11.0.221-1_amd64.deb",
        "cuda-nvprof-11-0_11.0.221-1_amd64.deb",
        "cuda-cupti-dev-11-0_11.0.221-1_amd64.deb",
        "cuda-sanitizer-11-0_11.0.221-1_amd64.deb",
        "cuda-gdb-11-0_11.0.221-1_amd64.deb",
        "cuda-nvml-dev-11-0_11.0.167-1_amd64.deb",
        "cuda-nvrtc-dev-11-0_11.0.221-1_amd64.deb",
        "cuda-nvtx-11-0_11.0.167-1_amd64.deb",
        "libcublas-dev-11-0_11.2.0.252-1_amd64.deb",
        "libcufft-dev-11-0_10.2.1.245-1_amd64.deb",
        "libcurand-dev-11-0_10.2.1.245-1_amd64.deb",
        "libcusolver-dev-11-0_10.6.0.245-1_amd64.deb",
        "libcusparse-dev-11-0_11.1.1.245-1_amd64.deb",
        "libnpp-dev-11-0_11.1.0.245-1_amd64.deb",
        "libnvjpeg-dev-11-0_11.1.1.245-1_amd64.deb",
    ],
    "11.1": [
        "cuda-cudart-dev-11-1_11.1.74-1_amd64.deb",
        "cuda-nvcc-11-1_11.1.74-1_amd64.deb",
        "cuda-nvprof-11-1_11.1.69-1_amd64.deb",
        "cuda-cupti-dev-11-1_11.1.69-1_amd64.deb",
        "cuda-sanitizer-11-1_11.1.105-1_amd64.deb",
        "cuda-gdb-11-1_11.1.69-1_amd64.deb",
        "cuda-nvml-dev-11-1_11.1.74-1_amd64.deb",
        "cuda-nvrtc-dev-11-1_11.1.74-1_amd64.deb",
        "cuda-nvtx-11-1_11.1.74-1_amd64.deb",
        "libcublas-dev-11-1_11.3.0.106-1_amd64.deb",
        "libcufft-dev-11-1_10.3.0.105-1_amd64.deb",
        "libcurand-dev-11-1_10.2.2.105-1_amd64.deb",
        "libcusolver-dev-11-1_11.0.1.105-1_amd64.deb",
        "libcusparse-dev-11-1_11.3.0.10-1_amd64.deb",
        "libnpp-dev-11-1_11.1.2.301-1_amd64.deb",
        "libnvjpeg-dev-11-1_11.3.0.105-1_amd64.deb",
    ],
    "11.2": [
        "cuda-cudart-dev-11-2_11.2.146-1_amd64.deb",
        "cuda-nvcc-11-2_11.2.142-1_amd64.deb",
        "cuda-nvprof-11-2_11.2.135-1_amd64.deb",
        "cuda-cupti-dev-11-2_11.2.135-1_amd64.deb",
        "cuda-sanitizer-11-2_11.2.135-1_amd64.deb",
        "cuda-gdb-11-2_11.2.135-1_amd64.deb",
        "cuda-nvml-dev-11-2_11.2.67-1_amd64.deb",
        "cuda-nvrtc-dev-11-2_11.2.142-1_amd64.deb",
        "cuda-nvtx-11-2_11.2.67-1_amd64.deb",
        "libcublas-dev-11-2_11.4.1.1026-1_amd64.deb",
        "libcufft-dev-11-2_10.4.0.135-1_amd64.deb",
        "libcurand-dev-11-2_10.2.3.135-1_amd64.deb",
        "libcusolver-dev-11-2_11.1.0.135-1_amd64.deb",
        "libcusparse-dev-11-2_11.4.0.135-1_amd64.deb",
        "libnpp-dev-11-2_11.3.2.139-1_amd64.deb",
        "libnvjpeg-dev-11-2_11.4.0.135-1_amd64.deb",
    ],
    "11.3": [
        "cuda-cudart-dev-11-3_11.3.109-1_amd64.deb",
        "cuda-nvcc-11-3_11.3.109-1_amd64.deb",
        "cuda-nvprof-11-3_11.3.58-1_amd64.deb",
        "cuda-cupti-dev-11-3_11.3.111-1_amd64.deb",
        "cuda-sanitizer-11-3_11.3.58-1_amd64.deb",
        "cuda-gdb-11-3_11.3.109-1_amd64.deb",
        "cuda-nvml-dev-11-3_11.3.58-1_amd64.deb",
        "cuda-nvrtc-dev-11-3_11.3.109-1_amd64.deb",
        "cuda-nvtx-11-3_11.3.58-1_amd64.deb",
        "cuda-thrust-11-3_11.3.109-1_amd64.deb",
        "libcublas-dev-11-3_11.5.1.109-1_amd64.deb",
        "libcufft-dev-11-3_10.4.2.109-1_amd64.deb",
        "libcurand-dev-11-3_10.2.4.109-1_amd64.deb",
        "libcusolver-dev-11-3_11.1.2.109-1_amd64.deb",
        "libcusparse-dev-11-3_11.6.0.109-1_amd64.deb",
        "libnpp-dev-11-3_11.3.3.95-1_amd64.deb",
        "libnvjpeg-dev-11-3_11.5.0.109-1_amd64.deb",
    ],
}

# Library Ubuntu deb packages for CUDA 11.4+
LIB_UBUNTU_DEB = {
    # CUDA 11.4
    ("11.4", "libcublas"): {"ubuntu": "2004", "package": "libcublas-dev-11-4_11.6.1.51-1_amd64.deb"},
    ("11.4", "libcufft"): {"ubuntu": "2004", "package": "libcufft-dev-11-4_10.5.2.100-1_amd64.deb"},
    ("11.4", "libcurand"): {"ubuntu": "2004", "package": "libcurand-dev-11-4_10.2.5.100-1_amd64.deb"},
    ("11.4", "libcusolver"): {"ubuntu": "2004", "package": "libcusolver-dev-11-4_11.2.0.100-1_amd64.deb"},
    ("11.4", "libcusparse"): {"ubuntu": "2004", "package": "libcusparse-dev-11-4_11.6.0.100-1_amd64.deb"},
    ("11.4", "libnpp"): {"ubuntu": "2004", "package": "libnpp-dev-11-4_11.4.0.100-1_amd64.deb"},
    ("11.4", "libnvjpeg"): {"ubuntu": "2004", "package": "libnvjpeg-dev-11-4_11.5.0.100-1_amd64.deb"},
    # CUDA 11.5
    ("11.5", "libcublas"): {"ubuntu": "2004", "package": "libcublas-dev-11-5_11.7.3.1-1_amd64.deb"},
    ("11.5", "libcufft"): {"ubuntu": "2004", "package": "libcufft-dev-11-5_10.6.0.107-1_amd64.deb"},
    ("11.5", "libcurand"): {"ubuntu": "2004", "package": "libcurand-dev-11-5_10.2.6.107-1_amd64.deb"},
    ("11.5", "libcusolver"): {"ubuntu": "2004", "package": "libcusolver-dev-11-5_11.2.1.107-1_amd64.deb"},
    ("11.5", "libcusparse"): {"ubuntu": "2004", "package": "libcusparse-dev-11-5_11.6.0.107-1_amd64.deb"},
    ("11.5", "libnpp"): {"ubuntu": "2004", "package": "libnpp-dev-11-5_11.5.1.107-1_amd64.deb"},
    ("11.5", "libnvjpeg"): {"ubuntu": "2004", "package": "libnvjpeg-dev-11-5_11.5.1.107-1_amd64.deb"},
    # CUDA 11.6
    ("11.6", "libcublas"): {"ubuntu": "2004", "package": "libcublas-dev-11-6_11.8.1.74-1_amd64.deb"},
    ("11.6", "libcufft"): {"ubuntu": "2004", "package": "libcufft-dev-11-6_10.7.2.74-1_amd64.deb"},
    ("11.6", "libcurand"): {"ubuntu": "2004", "package": "libcurand-dev-11-6_10.2.7.74-1_amd64.deb"},
    ("11.6", "libcusolver"): {"ubuntu": "2004", "package": "libcusolver-dev-11-6_11.3.0.74-1_amd64.deb"},
    ("11.6", "libcusparse"): {"ubuntu": "2004", "package": "libcusparse-dev-11-6_11.7.0.74-1_amd64.deb"},
    ("11.6", "libnpp"): {"ubuntu": "2004", "package": "libnpp-dev-11-6_11.6.3.74-1_amd64.deb"},
    ("11.6", "libnvjpeg"): {"ubuntu": "2004", "package": "libnvjpeg-dev-11-6_11.6.0.74-1_amd64.deb"},
}

# cuDNN Ubuntu deb mapping
CUDNN_UBUNTU_DEB = {
    # CUDA 11.1 (cuDNN 8.0.5 — Ubuntu deb avoids 1.5 GB .tgz download)
    ("11.1", "8.0.5"): {"ubuntu": "2004", "package": "libcudnn8-dev"},
    # CUDA 11.2 (cuDNN 8.1.1 — Ubuntu deb avoids 1.2 GB .tgz download)
    ("11.2", "8.1.1"): {"ubuntu": "2004", "package": "libcudnn8-dev"},
    # CUDA 11.3 (cuDNN 8.2.1 — Ubuntu deb avoids 1.8 GB .tgz download)
    ("11.3", "8.2.1"): {"ubuntu": "2004", "package": "libcudnn8-dev"},
    # CUDA 11.4
    ("11.4", "8.2.4"): {"ubuntu": "2004", "package": "libcudnn8-dev"},
    # CUDA 11.5
    ("11.5", "8.3.1"): {"ubuntu": "2004", "package": "libcudnn8-dev"},
    # CUDA 11.6
    ("11.6", "8.4.0"): {"ubuntu": "2004", "package": "libcudnn8-dev"},
    # CUDA 11.7
    ("11.7", "8.5.0"): {"ubuntu": "2004", "package": "libcudnn8-dev"},
    # CUDA 11.8
    ("11.8", "8.6.0"): {"ubuntu": "2004", "package": "libcudnn8-dev"},
    # CUDA 12.0
    ("12.0", "8.7.0"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    # CUDA 12.1
    ("12.1", "8.9.3"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    # CUDA 12.2+ with cuDNN 8.9.5
    # Note: cuDNN 8.9.5 only has libcudnn8-dev for CUDA 11.8 and 12.2 in repo.
    # For CUDA 12.3+, we use the CUDA 12.2 package as it's the closest available.
    ("12.2", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("12.3", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("12.4", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("12.5", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("12.6", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("12.8", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("12.9", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("13.0", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("13.1", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("13.2", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
    ("13.3", "8.9.5"): {"ubuntu": "2204", "package": "libcudnn8-dev"},
}


# =============================================================================
# Utility Functions
# =============================================================================

def _parse_major_minor(version: str) -> str:
    """Parse major.minor from version string."""
    parts = version.split(".")
    return f"{parts[0]}.{parts[1]}"


def _get_arch_dir(arch: str) -> str:
    """Get architecture directory name."""
    return ARCH_MAP.get(arch, arch)


def _make_request(url: str, timeout: int = 300) -> urllib.request.Request:
    """Create a request with User-Agent header."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "CUDA-Redist-Downloader/2.0")
    return req


def http_get(url: str, retries: int = 3) -> bytes:
    """Download URL with retries."""
    last_error = None
    for attempt in range(retries):
        try:
            req = _make_request(url)
            with urllib.request.urlopen(req, timeout=300) as resp:
                return resp.read()
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                delay = 2 ** attempt
                logger.warning("Download failed (attempt %d/%d): %s. Retrying in %ds...",
                              attempt + 1, retries, e, delay)
                time.sleep(delay)
    raise NetworkError(f"Failed to download {url} after {retries} attempts: {last_error}")


def http_range_get(url: str, start: int, end: int) -> bytes:
    """Download a byte range from URL."""
    req = _make_request(url)
    req.add_header("Range", f"bytes={start}-{end}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 416:  # Range not satisfiable
            return b''
        raise HTTPError(f"Range request failed: {e.code} {e.reason}", e.code, url)


def download_file(url: str, dest: str, retries: int = 3, expected_sha256: str = None) -> bool:
    """Download file with retries and optional SHA256 verification."""
    import random

    for attempt in range(retries):
        try:
            req = _make_request(url)
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = resp.read()

                # Verify SHA256 if provided
                if expected_sha256:
                    actual_sha256 = hashlib.sha256(data).hexdigest()
                    if actual_sha256 != expected_sha256:
                        raise ValidationError(
                            f"SHA256 mismatch for {os.path.basename(dest)}",
                            expected_sha256, actual_sha256
                        )

                # Write to destination
                with open(dest, 'wb') as f:
                    f.write(data)

                logger.debug("  Downloaded %.2f MB", len(data) / (1024 * 1024))
                return True

        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                delay = 2 ** attempt + random.uniform(0, 1)
                logger.warning("Download failed (attempt %d/%d): %s. Retrying in %.1fs...",
                              attempt + 1, retries, e, delay)
                time.sleep(delay)

    raise DownloadError(f"Failed to download {url} after {retries} attempts: {last_error}")


# =============================================================================
# Unified Archive Extraction Functions
# =============================================================================

def extract_tar_headers(archive_data: bytes, target_dir: str,
                       exclude_filter: str = None,
                       path_filter: str = None, strip_prefix: str = None,
                       filter_to_include: bool = False) -> int:
    """
    Extract header files from tar archive.

    Args:
        archive_data: Raw tar archive bytes (compressed or uncompressed)
        target_dir: Target directory for extracted headers
        path_filter: Optional filter - only extract files matching this substring
        strip_prefix: Optional prefix to strip from archive paths
        filter_to_include: When True with strip_prefix, only extract files
                          that have /include/ in the stripped path

    Returns:
        Number of files extracted
    """
    os.makedirs(target_dir, exist_ok=True)
    count = 0

    try:
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode='r:*') as tf:
            # Use next() for streaming extraction (works with partial tar streams)
            while True:
                try:
                    m = tf.next()
                    if m is None:
                        break
                    if not m.isfile():
                        continue

                    # Apply path filter
                    if path_filter and path_filter not in m.name:
                        continue

                    # Apply exclude filter (skip files matching this pattern)
                    if exclude_filter and exclude_filter in m.name:
                        continue

                    # Skip samples and special directories
                    if any(x in m.name for x in ['/samples/', '/libnvvm-samples/', '/nvvm-prev/']):
                        continue

                    # Extract header files and related config/build files
                    _, ext = os.path.splitext(m.name)
                    _HEADER_EXTS = ('.h', '.hpp', '.cuh', '.inl')
                    _CONFIG_EXTS = ('.cmake', '.txt', '.modulemap', '.in', '.md')
                    if ext in _HEADER_EXTS:
                        pass  # Always extract header files
                    elif ext in _CONFIG_EXTS:
                        # Only extract config files if in include/ directory
                        if '/include/' not in m.name and not m.name.startswith('include/'):
                            continue
                    elif ext:
                        # Has extension but not a recognized type — skip
                        continue
                    else:
                        # No extension - only extract if in include/ directory (extensionless C++ headers)
                        if '/include/' not in m.name and not m.name.startswith('include/'):
                            continue

                    # Handle prefix stripping
                    if strip_prefix:
                        if not m.name.startswith(strip_prefix):
                            continue
                        rel_path = m.name[len(strip_prefix):]
                        if filter_to_include and '/include/' not in rel_path and not rel_path.startswith('include/'):
                            continue
                    else:
                        # Find include/ directory and extract everything after it
                        parts = m.name.split('/')
                        try:
                            include_idx = parts.index('include')
                            rel_path = '/'.join(parts[include_idx + 1:])
                        except ValueError:
                            continue

                    if not rel_path:
                        continue

                    # Extract file
                    dest_path = os.path.join(target_dir, rel_path)
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    with tf.extractfile(m) as src:
                        with open(dest_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                    count += 1
                except (EOFError, tarfile.ReadError) as e:
                    # Expected for partial tar streams - stop extraction
                    break
                except Exception as e:
                    logger.warning("Error extracting %s: %s", m.name if 'm' in locals() else 'unknown', e)
                    continue

    except Exception as e:
        # If we already extracted some files, that's fine
        if count == 0:
            logger.warning("Failed to extract tar archive: %s", e)
            return 0

    return count


def extract_deb_headers(deb_data: bytes, target_dir: str, cuda_path: str,
                       path_filter: str = None, strip_prefix: str = None,
                       filter_to_include: bool = False) -> int:
    """
    Extract header files from deb package.

    Args:
        deb_data: Raw deb file bytes
        target_dir: Target directory for extracted headers
        cuda_path: CUDA version path (e.g., "11.0", "11.1")
        path_filter: Optional filter - only extract files matching this substring
        strip_prefix: Optional prefix to strip from archive paths
        filter_to_include: When True with strip_prefix, only extract files
                          that have /include/ in the stripped path

    Returns:
        Number of files extracted
    """
    # Parse ar archive
    if not deb_data.startswith(b'!<arch>\n'):
        raise ValueError("Not a valid deb archive")

    offset = 8
    data_tar = None
    tar_name = None

    while offset < len(deb_data):
        # Parse ar header (60 bytes)
        if offset + 60 > len(deb_data):
            break

        name = deb_data[offset:offset+16].decode().strip().rstrip('/')
        size = int(deb_data[offset+48:offset+58].decode().strip())

        if name.startswith('data.tar'):
            data_tar = deb_data[offset+60:offset+60+size]
            tar_name = name
            break

        offset += 60 + size
        if offset % 2:
            offset += 1

    if data_tar is None:
        return 0

    # Decompress
    if tar_name.endswith('.xz'):
        payload = lzma.decompress(data_tar)
    elif tar_name.endswith('.gz'):
        import gzip
        payload = gzip.decompress(data_tar)
    else:
        payload = data_tar

    # Extract headers. When strip_prefix is set (CUDA toolkit debs), preserve
    # the full directory structure under the prefix. When not set (cuDNN debs),
    # auto-detect the include/ directory pattern to handle:
    # - cuDNN deb: ./usr/include/x86_64-linux-gnu/
    count = extract_tar_headers(payload, target_dir, path_filter=path_filter,
                               strip_prefix=strip_prefix,
                               filter_to_include=filter_to_include)

    # Post-process: move headers from x86_64-linux-gnu/ subdirectory to target_dir
    # (cuDNN deb packages use this structure)
    arch_subdir = os.path.join(target_dir, 'x86_64-linux-gnu')
    if os.path.exists(arch_subdir):
        for fname in os.listdir(arch_subdir):
            src = os.path.join(arch_subdir, fname)
            dst = os.path.join(target_dir, fname)
            if os.path.isfile(src):
                shutil.move(src, dst)
        try:
            os.rmdir(arch_subdir)
        except OSError:
            pass

    return count


def extract_deb_headers_range(deb_url: str, target_dir: str, cuda_path: str,
                             range_size: int = 524288) -> int:
    """
    Extract headers from deb package using HTTP Range requests.

    Only downloads the first range_size bytes of data.tar.xz (enough for headers).
    Falls back to full download if Range fails.
    """
    try:
        # Get ar header to find data.tar.xz offset
        ar_header = http_range_get(deb_url, 0, 8192)

        offset = 8
        dt_offset = None
        dt_size = None

        while offset < len(ar_header):
            if offset + 60 > len(ar_header):
                break

            name = ar_header[offset:offset+16].decode().strip().rstrip('/')
            size = int(ar_header[offset+48:offset+58].decode().strip())

            if name.startswith('data.tar.xz'):
                dt_offset = offset + 60
                dt_size = size
                break

            offset += 60 + size
            if offset % 2:
                offset += 1

        if dt_offset is None:
            logger.warning("data.tar.xz not found in ar header")
            return 0

        # Range download data.tar.xz prefix
        end = min(dt_offset + range_size, dt_offset + dt_size)
        chunk = http_range_get(deb_url, dt_offset, end)

        # Streaming decompress (handles partial data)
        dec = lzma.LZMADecompressor()
        try:
            payload = dec.decompress(chunk)
        except lzma.LZMAError:
            # Expected for partial streams - we got what we could decompress
            pass

        if not payload:
            logger.warning("Decompression produced no data")
            return 0

        # Extract headers - don't use strip_prefix to handle both:
        # - CUDA toolkit deb: ./usr/local/cuda-{version}/include/
        # - cuDNN deb: ./usr/include/x86_64-linux-gnu/
        count = extract_tar_headers(payload, target_dir)

        if count > 0:
            # Post-process: move headers from x86_64-linux-gnu/ subdirectory
            arch_subdir = os.path.join(target_dir, 'x86_64-linux-gnu')
            if os.path.exists(arch_subdir):
                for fname in os.listdir(arch_subdir):
                    src = os.path.join(arch_subdir, fname)
                    dst = os.path.join(target_dir, fname)
                    if os.path.isfile(src):
                        shutil.move(src, dst)
                try:
                    os.rmdir(arch_subdir)
                except OSError:
                    pass

            logger.debug("  Range: extracted %d headers from %d KB", count, len(chunk) // 1024)

        return count

    except Exception as e:
        logger.warning("Range extraction failed: %s", e)
        return 0


def extract_tar_headers_streaming(archive_url: str, target_dir: str,
                                  max_bytes: int = None,
                                  special_patterns: list = None) -> tuple:
    """
    Streaming extraction of headers from tar.xz archive.

    Downloads and decompresses data incrementally via a pipe, stopping when
    max_bytes of compressed data is reached.  Works well for components
    where headers are at the beginning of the tar stream.

    Args:
        archive_url: URL of the tar.xz archive
        target_dir: Target directory for extracted headers
        max_bytes: Maximum bytes to download (Range request)
        special_patterns: Optional list of (pattern, target_subdir) tuples
                         for SPECIAL_COMPONENTS with non-standard paths

    Returns:
        Tuple of (header_count, bytes_downloaded)
    """
    import threading

    os.makedirs(target_dir, exist_ok=True)

    # Create pipe for streaming decompressed data
    read_fd, write_fd = os.pipe()

    bytes_downloaded = [0]
    write_error = [None]

    def download_and_decompress():
        """Background thread: download xz data, decompress, write to pipe."""
        try:
            req = _make_request(archive_url)
            if max_bytes:
                req.add_header('Range', f'bytes=0-{max_bytes - 1}')

            with urllib.request.urlopen(req, timeout=300) as resp:
                dec = lzma.LZMADecompressor()
                chunk_size = 64 * 1024  # 64KB chunks

                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break

                    bytes_downloaded[0] += len(chunk)

                    try:
                        data = dec.decompress(chunk)
                        if data:
                            os.write(write_fd, data)
                    except lzma.LZMAError:
                        # Expected when stream is incomplete (Range request)
                        break

                    if dec.eof:
                        break

        except (OSError, IOError) as e:
            # Expected when reader closes pipe early (all headers found)
            if e.errno != errno.EPIPE:
                write_error[0] = e
        except Exception as e:
            write_error[0] = e
        finally:
            try:
                os.close(write_fd)
            except OSError:
                pass

    # Start download thread
    writer = threading.Thread(target=download_and_decompress, daemon=True)
    writer.start()

    # Read from pipe and extract headers
    count = 0
    reader_file = os.fdopen(read_fd, 'rb')

    try:
        with tarfile.open(fileobj=reader_file, mode='r|') as tf:
            while True:
                try:
                    m = tf.next()
                    if m is None:
                        break
                    if not m.isfile():
                        continue

                    # Skip samples and special directories
                    if any(x in m.name for x in ['/samples/', '/libnvvm-samples/', '/nvvm-prev/']):
                        continue

                    # Extract header files and related config/build files
                    _, ext = os.path.splitext(m.name)
                    _HEADER_EXTS = ('.h', '.hpp', '.cuh', '.inl')
                    _CONFIG_EXTS = ('.cmake', '.txt', '.modulemap', '.in', '.md')
                    if ext in _HEADER_EXTS:
                        pass  # Always extract header files
                    elif ext in _CONFIG_EXTS:
                        # Only extract config files if in include/ directory
                        if '/include/' not in m.name and not m.name.startswith('include/'):
                            continue
                    elif ext:
                        # Has extension but not a recognized type — skip
                        continue
                    else:
                        # No extension - only extract if in include/ directory (extensionless C++ headers)
                        if '/include/' not in m.name and not m.name.startswith('include/'):
                            continue

                    # Extract based on pattern type
                    if special_patterns:
                        # SPECIAL_COMPONENTS: match against patterns
                        matched = False
                        for pattern, target_subdir in special_patterns:
                            if pattern in m.name:
                                # Extract path after the pattern
                                parts = m.name.split(pattern)
                                if len(parts) > 1:
                                    rel_path = parts[-1].lstrip('/')
                                    dest_dir = os.path.join(target_dir, target_subdir)
                                    dest_path = os.path.join(dest_dir, rel_path)
                                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                    with tf.extractfile(m) as src:
                                        with open(dest_path, 'wb') as dst:
                                            shutil.copyfileobj(src, dst)
                                    count += 1
                                    matched = True
                                    break
                        if not matched:
                            continue
                    else:
                        # Standard components: find include/ directory
                        parts = m.name.split('/')
                        try:
                            include_idx = parts.index('include')
                            rel_path = '/'.join(parts[include_idx + 1:])
                        except ValueError:
                            continue

                        if not rel_path:
                            continue

                        # Extract file
                        dest_path = os.path.join(target_dir, rel_path)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with tf.extractfile(m) as src:
                            with open(dest_path, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
                        count += 1

                except (EOFError, tarfile.ReadError):
                    # Expected for partial streams
                    break
                except Exception as e:
                    logger.debug("Error extracting %s: %s",
                               m.name if 'm' in locals() else 'unknown', e)
                    continue
    finally:
        reader_file.close()

    writer.join(timeout=5)

    if write_error[0]:
        logger.debug("Streaming download error: %s", write_error[0])

    if count > 0:
        logger.debug("  Stream: extracted %d headers from %d KB (%.1f MB)",
                   count, bytes_downloaded[0] // 1024,
                   bytes_downloaded[0] / 1048576)

    return count, bytes_downloaded[0]


def _extract_tgz_headers_range(url: str, target_dir: str,
                                strip_prefix: str = None,
                                max_bytes: int = 64 * 1024 * 1024) -> int:
    """Extract headers from .tgz archive using HTTP Range request.

    Downloads only the first max_bytes of the .tgz file, decompresses
    with gzip, and extracts headers. Falls back to full download on failure.
    """
    import zlib

    try:
        chunk = http_range_get(url, 0, max_bytes - 1)
        if not chunk:
            return 0

        dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            payload = dec.decompress(chunk)
        except zlib.error:
            pass  # Expected for partial gzip streams

        if not payload:
            logger.warning("gzip decompression produced no data")
            return 0

        count = extract_tar_headers(payload, target_dir, strip_prefix=strip_prefix)
        if count > 0:
            logger.debug("  tgz Range: extracted %d headers from %d KB",
                        count, len(chunk) // 1024)
        return count

    except Exception as e:
        logger.warning("tgz Range extraction failed: %s", e)
        return 0


def _download_and_extract_cudnn_old(url: str, target: str, strip_prefix: str,
                                     save_dir: str, result: dict,
                                     cudnn_version: str) -> int:
    """Full download fallback for old cuDNN CDN packages."""
    ctx = tempfile.TemporaryDirectory() if not save_dir else None
    with ctx or open(os.devnull):
        tmpdir = save_dir if save_dir else (ctx.name if ctx else "")
        archive_name = os.path.basename(url)
        archive_path = os.path.join(tmpdir, archive_name)

        try:
            download_file(url, archive_path)
        except DownloadError as e:
            result["skipped"].append(f"cudnn: {e}")
            return 0

        with open(archive_path, 'rb') as f:
            archive_data = f.read()

        if strip_prefix:
            return extract_tar_headers(archive_data, target, strip_prefix=strip_prefix)
        else:
            return extract_tar_headers(archive_data, target)


def download_cudnn_ubuntu_deb(cudnn_version: str, target_dir: str,
                             cuda_version: str, range_opt: bool = True) -> int:
    """
    Download cuDNN headers from Ubuntu deb packages.

    For cuDNN 8.x: Uses libcudnn8-dev with Range optimization
    For cuDNN 9.x: Uses libcudnn9-headers (pure headers package, ~34KB)
    """
    cuda_mm = _parse_major_minor(cuda_version)
    key = (cuda_mm, cudnn_version)

    if key not in CUDNN_UBUNTU_DEB:
        logger.warning("cuDNN %s not in Ubuntu deb mapping", cudnn_version)
        return 0

    info = CUDNN_UBUNTU_DEB[key]
    ubuntu_distro = info["ubuntu"]
    package_type = info["package"]

    # Construct base URL
    base_url = f"https://developer.download.nvidia.cn/compute/cuda/repos/ubuntu{ubuntu_distro}/x86_64"

    try:
        # Query repo to find exact package name
        repo_url = f"{base_url}/"
        req = _make_request(repo_url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8')

        # Find matching packages
        if package_type == "libcudnn8-dev":
            cuda_mm_ver = cuda_mm  # "12.2"
            pattern = rf"href='(libcudnn8-dev_{cudnn_version}[^']*\.deb)'"
        elif package_type == "libcudnn9-headers":
            cuda_major = cuda_version.split('.')[0]
            cudnn_prefix = cudnn_version.rsplit('.', 1)[0] if cudnn_version.count('.') >= 2 else cudnn_version
            pattern = rf"href='(libcudnn9-headers-cuda-{cuda_major}_{cudnn_prefix}[^']*\.deb)'"
        else:
            logger.warning("Unknown package type: %s", package_type)
            return 0

        matches = re.findall(pattern, html)
        if not matches:
            logger.warning("No matching Ubuntu deb package found for cuDNN %s", cudnn_version)
            return 0

        # Select the latest version (sort by version string)
        package_name = sorted(matches)[-1]
        deb_url = f"{base_url}/{package_name}"

        logger.debug("Downloading cuDNN %s from Ubuntu %s: %s", cudnn_version, ubuntu_distro, package_name)

        # For libcudnn9-headers (pure headers package), download entire file
        if package_type == "libcudnn9-headers":
            return _extract_cudnn9_headers(deb_url, target_dir)

        # For libcudnn8-dev, use Range optimization if enabled
        if range_opt:
            count = extract_deb_headers_range(deb_url, target_dir, cuda_mm)
            if count > 0:
                return count
            logger.warning("Range optimization failed for cuDNN %s, falling back to full download", cudnn_version)

        # Fallback: full download
        return _extract_cudnn8_headers_full(deb_url, target_dir, cuda_mm)

    except Exception as e:
        logger.warning("Failed to download cuDNN %s from Ubuntu: %s", cudnn_version, e)
        return 0


def _extract_cudnn9_headers(deb_url: str, target_dir: str) -> int:
    """Extract headers from libcudnn9-headers package (pure headers, ~34KB)."""
    try:
        # Download entire deb package (very small)
        req = _make_request(deb_url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            deb_data = resp.read()

        logger.debug("  Downloaded %d KB", len(deb_data) // 1024)

        # Parse ar archive
        offset = 8
        data_tar = None

        while offset < len(deb_data):
            if offset + 60 > len(deb_data):
                break

            name = deb_data[offset:offset+16].decode().strip().rstrip('/')
            size = int(deb_data[offset+48:offset+58].decode().strip())

            if name.startswith('data.tar'):
                data_tar = deb_data[offset+60:offset+60+size]
                tar_name = name
                break

            offset += 60 + size
            if offset % 2:
                offset += 1

        if data_tar is None:
            logger.warning("data.tar not found in cuDNN 9 headers package")
            return 0

        # Decompress
        if tar_name.endswith('.xz'):
            payload = lzma.decompress(data_tar)
        elif tar_name.endswith('.gz'):
            import gzip
            payload = gzip.decompress(data_tar)
        else:
            payload = data_tar

        # Extract headers (no prefix stripping for cuDNN 9)
        count = extract_tar_headers(payload, target_dir)
        logger.debug("  Extracted %d headers from cuDNN 9 headers package", count)
        return count

    except Exception as e:
        logger.warning("Failed to extract cuDNN 9 headers: %s", e)
        return 0


def _extract_cudnn8_headers_full(deb_url: str, target_dir: str, cuda_path: str) -> int:
    """Extract headers from libcudnn8-dev using full download (fallback)."""
    try:
        # Download entire deb package
        req = _make_request(deb_url)
        with urllib.request.urlopen(req, timeout=300) as resp:
            deb_data = resp.read()

        logger.debug("  Downloaded %d MB", len(deb_data) // (1024 * 1024))

        # Extract headers
        count = extract_deb_headers(deb_data, target_dir, cuda_path)
        logger.debug("  Extracted %d headers from full download", count)
        return count

    except Exception as e:
        logger.warning("Full extraction failed for cuDNN 8 dev: %s", e)
        return 0


# =============================================================================
# Library Ubuntu deb Download (CUDA 11.4+)
# =============================================================================

def download_library_ubuntu_deb(lib_name: str, cuda_version: str,
                               target_include: str, range_opt: bool = True) -> int:
    """
    Download library headers from Ubuntu deb packages using Range optimization.
    """
    cuda_mm = _parse_major_minor(cuda_version)
    key = (cuda_mm, lib_name)

    if key not in LIB_UBUNTU_DEB:
        logger.warning("Library %s for CUDA %s not in Ubuntu deb mapping", lib_name, cuda_version)
        return 0

    info = LIB_UBUNTU_DEB[key]
    ubuntu_distro = info["ubuntu"]
    package_name = info["package"]

    # Construct deb URL
    base_url = f"https://developer.download.nvidia.cn/compute/cuda/repos/ubuntu{ubuntu_distro}/x86_64"
    deb_url = f"{base_url}/{package_name}"

    logger.debug("Trying Ubuntu deb for %s (CUDA %s): %s", lib_name, cuda_version, package_name)

    try:
        if range_opt:
            count = extract_deb_headers_range(deb_url, target_include, cuda_mm)
            if count > 0:
                logger.debug("  Range: extracted %d headers from %s", count, lib_name)
                return count
            logger.warning("Range optimization failed for %s, falling back to full download", lib_name)

        # Full download fallback
        return _extract_lib_headers_full(deb_url, target_include, cuda_mm)

    except Exception as e:
        logger.warning("Failed to download %s from Ubuntu: %s", lib_name, e)
        return 0


def _extract_lib_headers_full(deb_url: str, target_dir: str, cuda_path: str) -> int:
    """Extract headers from library dev package using full download (fallback)."""
    try:
        # Download entire deb package
        req = _make_request(deb_url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            deb_data = resp.read()

        logger.debug("  Downloaded %d MB", len(deb_data) // (1024 * 1024))

        # Extract headers
        count = extract_deb_headers(deb_data, target_dir, cuda_path)
        logger.debug("  Extracted %d headers from full download", count)
        return count

    except Exception as e:
        logger.warning("Full extraction failed for library dev: %s", e)
        return 0


# =============================================================================
# Video Codec SDK Header Transformation
# =============================================================================

def _transform_cuviddec(content: str) -> str:
    """Transform dynlink_cuviddec.h to match official NVIDIA cuviddec.h."""
    lines = content.split('\n')
    out = []
    skip_macro_blank = False
    skip_culong_block = False

    for i, line in enumerate(lines):
        if line.strip().startswith('#include "dynlink_'):
            line = line.replace('dynlink_', '')

        if re.match(r'\s*typedef\s+\w+\s+CUDAAPI\s+tcuvid', line):
            line = re.sub(r'typedef\s+(\w+)\s+CUDAAPI\s+tcuvid(\w+)\(',
                         r'extern \1 CUDAAPI cuvid\2(', line)

        if line.strip() == '#define __CUDA_VIDEO_H__':
            out.append(line)
            out.append('')
            out.append('#ifndef __cuda_cuda_h__')
            out.append('#include <cuda.h>')
            out.append('#endif // __cuda_cuda_h__')
            continue

        if line.strip().startswith('#define NVDECAPI_'):
            skip_macro_blank = True
            continue
        if skip_macro_blank:
            if line.strip() == '':
                skip_macro_blank = False
                continue
            skip_macro_blank = False

        if line.strip() == '#if defined(__CYGWIN__)' and i + 1 < len(lines) and 'tcu_ulong' in lines[i + 1]:
            if out and out[-1].strip() == '':
                out.pop()
            skip_culong_block = True
            continue
        if skip_culong_block:
            if line.strip() == '#endif':
                skip_culong_block = False
            continue

        if 'tcu_ulong' in line:
            line = line.replace('tcu_ulong', 'unsigned long')

        line = line.replace('tcuvid', 'cuvid')

        if line.strip() == '}' and i + 1 < len(lines) and lines[i + 1].strip() == '#endif /* __cplusplus */':
            out.append(line)
            out.append('// Auto-lock helper for C++ applications')
            out.append('class CCtxAutoLock')
            out.append('{')
            out.append('private:')
            out.append('    CUvideoctxlock m_ctx;')
            out.append('public:')
            out.append('    CCtxAutoLock(CUvideoctxlock ctx):m_ctx(ctx) { cuvidCtxLock(m_ctx,0); }')
            out.append('    ~CCtxAutoLock() { cuvidCtxUnlock(m_ctx,0); }')
            out.append('};')
            continue

        out.append(line)

    return '\n'.join(out)


def _transform_nvcuvid(content: str) -> str:
    """Transform dynlink_nvcuvid.h to match official NVIDIA nvcuvid.h."""
    lines = content.split('\n')
    out = []

    for line in lines:
        if line.strip().startswith('#include "dynlink_'):
            line = line.replace('dynlink_', '')

        if re.match(r'\s*typedef\s+\w+\s+CUDAAPI\s+tcuvid', line):
            line = re.sub(r'typedef\s+(\w+)\s+CUDAAPI\s+tcuvid(\w+)\(',
                         r'\1 CUDAAPI cuvid\2(', line)

        if 'tcu_ulong' in line:
            line = line.replace('tcu_ulong', 'unsigned long')

        out.append(line)

    return '\n'.join(out)


def _transform_nvenc(content: str) -> str:
    """Transform nvEncodeAPI.h from FFmpeg to match official NVIDIA SDK."""
    # Restructure platform detection block
    old_block = (
        '#if defined(_WIN32) || defined(__CYGWIN__)\n'
        '#define NVENCAPI __stdcall\n'
        '#else\n'
        '#define NVENCAPI\n'
        '#endif\n'
        '\n'
        '#ifdef _WIN32\n'
        'typedef RECT NVENC_RECT;\n'
        '#else\n'
        '// =========================================================================================\n'
        '#if !defined(GUID) && !defined(GUID_DEFINED)\n'
        '#define GUID_DEFINED'
    )
    new_block = (
        '#ifdef _WIN32\n'
        '#define NVENCAPI     __stdcall\n'
        'typedef RECT NVENC_RECT;\n'
        '#else\n'
        '#define NVENCAPI\n'
        '// =========================================================================================\n'
        '#ifndef GUID_DEFINED\n'
        '#define GUID_DEFINED'
    )
    content = content.replace(old_block, new_block)

    # Replace 1u<<31 with 1<<31
    content = content.replace('1u<<31', '1<<31')

    return content


# =============================================================================
# Main Download Functions
# =============================================================================

def download_cuda(cuda_version: str, output_dir: str,
                local_dir: str = None, save_dir: str = None,
                range_opt: bool = True, no_verify: bool = False) -> dict:
    """Download CUDA SDK headers."""
    result = {"downloaded": [], "skipped": []}
    major_minor = _parse_major_minor(cuda_version)
    sdk_dir = os.path.join(output_dir, f"cuda-{cuda_version}")
    arch_dir = _get_arch_dir("linux-x86_64")
    target_include = os.path.join(sdk_dir, "targets", arch_dir, "include")

    # Auto-create directories
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    if major_minor in ("11.0", "11.1", "11.2", "11.3"):
        # Use deb packages
        result_deb = _download_cuda_deb(major_minor, cuda_version, sdk_dir,
                                       target_include, local_dir, save_dir,
                                       range_opt, no_verify)
        result["downloaded"].extend(result_deb["downloaded"])
        result["skipped"].extend(result_deb["skipped"])
    else:
        # Use redist JSON
        result_redist = _download_cuda_redist(cuda_version, sdk_dir,
                                             target_include, local_dir, save_dir,
                                             range_opt, no_verify)
        result["downloaded"].extend(result_redist["downloaded"])
        result["skipped"].extend(result_redist["skipped"])

    return result


def _download_cuda_deb(major_minor: str, cuda_version: str, sdk_dir: str,
                      target_include: str, local_dir: str, save_dir: str,
                      range_opt: bool, no_verify: bool) -> dict:
    """Download CUDA headers from Ubuntu deb packages (11.0~11.3)."""
    result = {"downloaded": [], "skipped": []}
    cuda_path = major_minor  # e.g. "11.0"
    packages = DEB_PACKAGES.get(major_minor, [])

    if not packages:
        result["skipped"].append(f"cuda: no deb packages for CUDA {major_minor}")
        return result

    ctx = tempfile.TemporaryDirectory() if not save_dir else None
    with ctx or open(os.devnull):
        tmpdir = save_dir if save_dir else (ctx.name if ctx else "")

        for pkg_name in packages:
            url = f"{DEB_BASE_URL}/ubuntu2004/x86_64/{pkg_name}"

            # Full download
            if local_dir and os.path.isdir(local_dir):
                archive_path = os.path.join(local_dir, pkg_name)
                if not os.path.isfile(archive_path):
                    logger.warning("Local archive not found: %s, will download", archive_path)
                    archive_path = os.path.join(tmpdir, pkg_name)
                    need_download = True
                else:
                    logger.debug("Using local archive: %s", archive_path)
                    need_download = False
            else:
                if local_dir:
                    logger.warning("Local directory does not exist: %s", local_dir)
                archive_path = os.path.join(tmpdir, pkg_name)
                need_download = True

            if need_download:
                try:
                    download_file(url, archive_path)
                except DownloadError as e:
                    logger.error("Failed to download %s: %s", pkg_name, e)
                    result["skipped"].append(f"{pkg_name}: {e}")
                    continue

            # Extract headers
            with open(archive_path, 'rb') as f:
                deb_data = f.read()

            count = extract_deb_headers(deb_data, sdk_dir, cuda_path,
                                       strip_prefix=f"./usr/local/cuda-{major_minor}/",
                                       filter_to_include=True)
            if count > 0:
                result["downloaded"].append(pkg_name.replace(".deb", ""))
                logger.debug("Extracted %d headers from %s (full)", count, pkg_name)
            else:
                result["skipped"].append(f"{pkg_name}: no headers found")

    # Post-process: relocate CUPTI headers and rename sanitizer directory
    _relocate_cupti_headers(sdk_dir, arch_dir=_get_arch_dir("linux-x86_64"))
    _rename_sanitizer_dir(sdk_dir, major_minor)

    return result


def _relocate_cupti_headers(sdk_dir: str, arch_dir: str = "x86_64-linux"):
    """Move CUPTI headers from targets/<arch>/include/ to extras/CUPTI/include/."""
    cupti_names = {
        "cupti.h", "cupti_activity.h", "cupti_callbacks.h", "cupti_driver_cbid.h",
        "cupti_events.h", "cupti_metrics.h", "cupti_nvtx_cbid.h",
        "cupti_pcsampling.h", "cupti_pcsampling_util.h",
        "cupti_profiler_target.h", "cupti_result.h", "cupti_runtime_cbid.h",
        "cupti_target.h", "cupti_version.h", "cuda_stdint.h",
        "nvperf_cuda_host.h", "nvperf_host.h", "nvperf_target.h",
        "generated_cudaGL_meta.h", "generated_cudaVDPAU_meta.h",
        "generated_cuda_gl_interop_meta.h", "generated_cuda_meta.h",
        "generated_cuda_runtime_api_meta.h", "generated_cuda_vdpau_interop_meta.h",
        "generated_nvtx_meta.h",
    }

    src_dir = os.path.join(sdk_dir, "targets", arch_dir, "include")
    dst_dir = os.path.join(sdk_dir, "extras", "CUPTI", "include")

    if not os.path.exists(src_dir):
        return

    os.makedirs(dst_dir, exist_ok=True)

    for name in list(os.listdir(src_dir)):
        if name in cupti_names:
            src_path = os.path.join(src_dir, name)
            dst_path = os.path.join(dst_dir, name)
            if os.path.isfile(src_path):
                shutil.move(src_path, dst_path)
                logger.debug("Relocated CUPTI header: %s", name)

    # Move CUPTI subdirectories (Openacc/, Openmp/) to extras/CUPTI/include/
    for subdir in ("Openacc", "Openmp"):
        src_sub = os.path.join(src_dir, subdir)
        if os.path.isdir(src_sub):
            dst_sub = os.path.join(dst_dir, subdir)
            shutil.move(src_sub, dst_sub)
            logger.debug("Relocated CUPTI subdirectory: %s/", subdir)


def _rename_sanitizer_dir(sdk_dir: str, major_minor: str = None):
    """Rename Sanitizer/ to compute-sanitizer/ for CUDA 11.1+."""
    if major_minor == "11.0":
        return
    sanitizer_dir = os.path.join(sdk_dir, "Sanitizer")
    cs_dir = os.path.join(sdk_dir, "compute-sanitizer")
    if not os.path.exists(sanitizer_dir):
        return
    if os.path.exists(cs_dir):
        for root, dirs, files in os.walk(sanitizer_dir):
            rel_root = os.path.relpath(root, sanitizer_dir)
            dst_root = os.path.join(cs_dir, rel_root) if rel_root != '.' else cs_dir
            os.makedirs(dst_root, exist_ok=True)
            for f in files:
                shutil.move(os.path.join(root, f), os.path.join(dst_root, f))
        shutil.rmtree(sanitizer_dir)
    else:
        os.rename(sanitizer_dir, cs_dir)
    logger.debug("Renamed Sanitizer/ -> compute-sanitizer/")


def _download_cuda_redist(cuda_version: str, sdk_dir: str,
                         target_include: str, local_dir: str, save_dir: str,
                         range_opt: bool, no_verify: bool) -> dict:
    """Download CUDA headers from redist JSON (11.4+)."""
    result = {"downloaded": [], "skipped": []}
    arch = "linux-x86_64"

    # Resolve to full version
    version_info = resolve_version(cuda_version)
    if version_info:
        full_version = version_info["cuda"]
    else:
        full_version = cuda_version

    json_url = f"{CUDA_REDIST_BASE_URL}/redistrib_{full_version}.json"

    try:
        data = http_get(json_url)
        redist_data = json.loads(data)
    except Exception as e:
        result["skipped"].append(f"cuda: failed to fetch redistrib JSON: {e}")
        return result

    logger.debug("CUDA %s redistrib loaded (release_date: %s)",
                cuda_version, redist_data.get("release_date", "unknown"))

    # Parse version for component filtering
    version_parts = cuda_version.split(".")
    major = int(version_parts[0]) if len(version_parts) > 0 else 0
    minor = int(version_parts[1]) if len(version_parts) > 1 else 0

    # Auto-create directories
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    ctx = tempfile.TemporaryDirectory() if not save_dir else None
    with ctx or open(os.devnull):
        tmpdir = save_dir if save_dir else (ctx.name if ctx else "")

        for comp_key in CUDA_COMPONENTS:
            # Skip libcufile for CUDA < 11.7 (cufile.h not available)
            if comp_key == "libcufile" and (major < 11 or (major == 11 and minor < 7)):
                result["skipped"].append(f"{comp_key}: not available for CUDA < 11.7")
                continue
            if comp_key not in redist_data:
                # Try Ubuntu deb fallback for CUDA 11.4-11.6 library components
                lib_key = (f"{major}.{minor}", comp_key)
                if lib_key in LIB_UBUNTU_DEB:
                    count = download_library_ubuntu_deb(comp_key, cuda_version,
                                                       target_include, range_opt)
                    if count > 0:
                        result["downloaded"].append(comp_key)
                        continue
                result["skipped"].append(f"{comp_key}: not in redistrib JSON")
                continue

            comp_info = redist_data[comp_key]
            if arch not in comp_info:
                result["skipped"].append(f"{comp_key}: arch {arch} not available")
                continue

            pkg = comp_info[arch]
            rel_path = pkg["relative_path"]
            archive_name = os.path.basename(rel_path)
            download_url = f"{CUDA_REDIST_BASE_URL}/{rel_path}"

            # Get archive
            if local_dir and os.path.isdir(local_dir):
                archive_path = os.path.join(local_dir, archive_name)
                if not os.path.isfile(archive_path):
                    logger.warning("Local archive not found: %s, will download", archive_path)
                    archive_path = os.path.join(tmpdir, archive_name)
                    need_download = True
                else:
                    logger.debug("Using local archive: %s", archive_path)
                    need_download = False
            else:
                if local_dir:
                    logger.warning("Local directory does not exist: %s", local_dir)
                archive_path = os.path.join(tmpdir, archive_name)
                need_download = True

            if need_download:
                if comp_key in NO_HEADERS:
                    # Component has no headers, skip download
                    result["skipped"].append(f"{comp_key}: no headers")
                    logger.debug("Skipped %s: no headers", comp_key)
                    continue
                if comp_key in FULL_DOWNLOAD:
                    # Full download required (headers at end or no headers)
                    try:
                        download_file(download_url, archive_path)
                    except DownloadError as e:
                        logger.error("Failed to download %s: %s", comp_key, e)
                        result["skipped"].append(f"{comp_key}: {e}")
                        continue
                else:
                    # Headers at front — use streaming download
                    if range_opt:
                        try:
                            # SPECIAL_COMPONENTS need pattern matching
                            if comp_key in SPECIAL_COMPONENTS:
                                special_patterns = SPECIAL_COMPONENTS[comp_key]
                                stream_target = sdk_dir
                                # Dynamically calculate stream limit based on file size
                                file_size = int(pkg.get("size", 0))
                                if file_size > 0:
                                    # Limit to 85% of file size to ensure early termination
                                    stream_limit = int(file_size * 0.85)
                                    stream_limit = max(stream_limit, DEFAULT_STREAM_LIMIT)
                                else:
                                    stream_limit = SPECIAL_STREAM_LIMIT

                                count, downloaded_bytes = extract_tar_headers_streaming(
                                    download_url, stream_target,
                                    max_bytes=stream_limit,
                                    special_patterns=special_patterns,
                                )
                                if count > 0:
                                    result["downloaded"].append(comp_key)
                                    continue
                            else:
                                # Adaptive streaming: try small first, fall back if needed
                                special_patterns = None
                                stream_target = target_include

                                # Phase 1: Try with minimal download (1 MB)
                                count, downloaded_bytes = extract_tar_headers_streaming(
                                    download_url, stream_target,
                                    max_bytes=1 * 1024 * 1024,  # 1 MB
                                    special_patterns=None,
                                )

                                # Phase 2: Try with larger download (16 MB)
                                count, downloaded_bytes = extract_tar_headers_streaming(
                                    download_url, stream_target,
                                    max_bytes=DEFAULT_STREAM_LIMIT,
                                    special_patterns=None,
                                )

                                if count > 0:
                                    result["downloaded"].append(comp_key)
                                    continue

                        except Exception as e:
                            logger.debug("Stream failed for %s: %s, falling back", comp_key, e)

                    # Full download fallback
                    try:
                        download_file(download_url, archive_path)
                    except DownloadError as e:
                        logger.error("Failed to download %s: %s", comp_key, e)
                        result["skipped"].append(f"{comp_key}: {e}")
                        continue

            # Extract headers
            with open(archive_path, 'rb') as f:
                archive_data = f.read()

            # Extract based on component type
            if comp_key in SPECIAL_COMPONENTS:
                # Track processed patterns to avoid extracting the same file
                # to multiple locations (e.g., nvvm/include/nvvm.h matching
                # both "nvvm/include" and "include" patterns).
                processed_patterns = []
                for pattern, target_subdir in SPECIAL_COMPONENTS[comp_key]:
                    if target_subdir == "targets":
                        target_dir = target_include
                    else:
                        target_dir = os.path.join(sdk_dir, target_subdir)

                    # Build exclude filter from previously processed patterns
                    # to prevent more specific patterns' files from being
                    # re-extracted by broader patterns.
                    exclude = None
                    for prev_pattern in processed_patterns:
                        if prev_pattern in pattern or pattern in prev_pattern:
                            # Overlapping patterns — use the more specific one as exclude
                            exclude = prev_pattern if len(prev_pattern) > len(pattern) else pattern
                            break

                    count = extract_tar_headers(archive_data, target_dir,
                                               exclude_filter=exclude,
                                               path_filter=pattern)
                    processed_patterns.append(pattern)
                    logger.debug("  %s -> %s: %d files", pattern, target_subdir, count)
            else:
                # Extract all headers
                count = extract_tar_headers(archive_data, target_include)

            if count > 0:
                result["downloaded"].append(comp_key)
                logger.debug("Extracted %d headers from %s (full)", count, comp_key)
            else:
                result["skipped"].append(f"{comp_key}: no headers found")

    return result


def download_cudnn(cudnn_version: str, output_dir: str, cuda_version: str = None,
                  cudnn_variant: str = None, local_dir: str = None, save_dir: str = None,
                  no_verify: bool = False, range_opt: bool = True) -> dict:
    """Download cuDNN headers."""
    result = {"downloaded": [], "skipped": []}
    arch = "linux-x86_64"
    cudnn_dir = os.path.join(output_dir, f"cudnn-{cudnn_version}")

    # Auto-create directories
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    target = os.path.join(cudnn_dir, "include")

    # Determine CUDA version for Ubuntu deb
    effective_cuda_version = cuda_version
    if not effective_cuda_version:
        for key in CUDNN_UBUNTU_DEB:
            if key[1] == cudnn_version:
                effective_cuda_version = key[0]
                break

    # Try Ubuntu deb first (available for 8.0.5+ — avoids 1.2-1.8 GB .tgz downloads)
    if effective_cuda_version and (effective_cuda_version, cudnn_version) in CUDNN_UBUNTU_DEB:
        logger.debug("Trying Ubuntu deb for cuDNN %s...", cudnn_version)
        count = download_cudnn_ubuntu_deb(cudnn_version, target, effective_cuda_version, range_opt)
        if count > 0:
            result["downloaded"].append(f"cudnn-{cudnn_version}")
            logger.debug("Extracted cuDNN %s: %d headers (Ubuntu deb)", cudnn_version, count)
            return result
        logger.warning("Ubuntu deb failed for cuDNN %s, falling back to CDN/redist", cudnn_version)

    if cudnn_version in CUDNN_OLD:
        # Old cuDNN (8.0~8.4) via CDN
        info = CUDNN_OLD[cudnn_version]
        cuda_param = info["cuda"]

        if info["format"] == "tgz":
            url_path = f"v{cudnn_version}/cudnn-{cuda_param}-linux-x64-v{info['full']}.tgz"
            strip_prefix = "cuda/include/"
        else:
            url_path = f"v{cudnn_version}/{info['path']}"
            strip_prefix = None

        url = f"{CUDNN_OLD_BASE_URL}/{url_path}"

        # Check for local archive
        archive_name = os.path.basename(url_path)
        local_archive = None
        if local_dir and os.path.isdir(local_dir):
            local_archive = os.path.join(local_dir, archive_name)
            if not os.path.isfile(local_archive):
                local_archive = None

        if local_archive:
            # Use local archive directly
            with open(local_archive, 'rb') as f:
                archive_data = f.read()
            if strip_prefix:
                count = extract_tar_headers(archive_data, target, strip_prefix=strip_prefix)
            else:
                count = extract_tar_headers(archive_data, target)
        elif range_opt and info["format"] == "tgz":
            # Range optimization: download ~64 MB prefix instead of 1.3+ GB
            count = _extract_tgz_headers_range(url, target, strip_prefix=strip_prefix)
            if count == 0:
                logger.warning("tgz Range failed for cuDNN %s, falling back to full download", cudnn_version)
                count = _download_and_extract_cudnn_old(url, target, strip_prefix, save_dir, result, cudnn_version)
        else:
            count = _download_and_extract_cudnn_old(url, target, strip_prefix, save_dir, result, cudnn_version)

        if count > 0:
            result["downloaded"].append(f"cudnn-{cudnn_version}")
            logger.debug("Extracted cuDNN %s -> %s", cudnn_version, target)
        elif f"cudnn-{cudnn_version}" not in [d for d in result.get("downloaded", [])]:
            if not any("cudnn" in s for s in result.get("skipped", [])):
                result["skipped"].append(f"cudnn: no headers found")

    else:
        # cuDNN 8.5+ via redist JSON (Ubuntu deb already tried above)

        cudnn_variant = cudnn_variant or "cuda12"
        json_url = f"{CUDNN_REDIST_BASE_URL}/redistrib_{cudnn_version}.json"

        try:
            data = http_get(json_url)
            redist_data = json.loads(data)
        except Exception as e:
            result["skipped"].append(f"cudnn: failed to fetch redistrib JSON: {e}")
            return result

        logger.debug("cuDNN %s redistrib loaded", cudnn_version)

        # Find the right package
        if "cudnn" not in redist_data:
            result["skipped"].append("cudnn: not in redistrib JSON")
            return result

        cudnn_info = redist_data["cudnn"]
        if arch not in cudnn_info:
            result["skipped"].append(f"cudnn: arch {arch} not available")
            return result

        arch_info = cudnn_info[arch]
        if cudnn_variant not in arch_info:
            for fallback in ("cuda11", "cuda10"):
                if fallback in arch_info:
                    cudnn_variant = fallback
                    break
            else:
                result["skipped"].append(f"cudnn: variant {cudnn_variant} not available")
                return result

        pkg = arch_info[cudnn_variant]
        rel_path = pkg["relative_path"]
        archive_name = os.path.basename(rel_path)
        download_url = f"{CUDNN_REDIST_BASE_URL}/{rel_path}"

        ctx = tempfile.TemporaryDirectory() if not save_dir else None
        with ctx or open(os.devnull):
            tmpdir = save_dir if save_dir else (ctx.name if ctx else "")
            archive_path = os.path.join(tmpdir, archive_name)

            if local_dir and os.path.isdir(local_dir):
                archive_path = os.path.join(local_dir, archive_name)
                if not os.path.isfile(archive_path):
                    logger.warning("Local archive not found: %s, will download", archive_path)
                    archive_path = os.path.join(tmpdir, archive_name)
                    need_download = True
                else:
                    logger.debug("Using local archive: %s", archive_path)
                    need_download = False
            else:
                if local_dir:
                    logger.warning("Local directory does not exist: %s", local_dir)
                archive_path = os.path.join(tmpdir, archive_name)
                need_download = True

            if need_download:
                # cuDNN headers are at end of archive — must download full
                try:
                    download_file(download_url, archive_path)
                except DownloadError as e:
                    result["skipped"].append(f"cudnn: {e}")
                    return result

            # Extract headers
            with open(archive_path, 'rb') as f:
                archive_data = f.read()

            count = extract_tar_headers(archive_data, target)
            if count > 0:
                result["downloaded"].append(f"cudnn-{cudnn_version}")
                logger.debug("Extracted cuDNN %s -> %s", cudnn_version, target)
            else:
                result["skipped"].append(f"cudnn: no headers found")

    return result


def download_nccl_headers_from_wheel(url: str, nccl_dir: str, nccl_version: str) -> bool:
    """
    Extract headers from NCCL wheel using ZIP central directory optimization.
    Only downloads the needed header files instead of the entire wheel.
    """
    try:
        # Get file size
        req = _make_request(url)
        req.method = 'HEAD'
        with urllib.request.urlopen(req, timeout=30) as resp:
            file_size = int(resp.headers.get('Content-Length', 0))

        if file_size == 0:
            return False

        # Download entire wheel (they're small, ~180MB uncompressed but compressed ~2MB)
        req = _make_request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            wheel_data = resp.read()

        logger.debug("  Downloaded %.2f MB", len(wheel_data) / (1024 * 1024))

        # Extract headers from wheel
        os.makedirs(nccl_dir, exist_ok=True)
        count = 0

        with zipfile.ZipFile(io.BytesIO(wheel_data), 'r') as zf:
            for name in zf.namelist():
                # Look for include files
                if 'include/' in name and (name.endswith('.h') or name.endswith('.hpp')):
                    # Extract filename
                    filename = os.path.basename(name)
                    dest_path = os.path.join(nccl_dir, filename)

                    with zf.open(name) as src:
                        with open(dest_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                    count += 1

        if count > 0:
            # For NCCL 2.8.3, 2.8.4, 2.27.3, only keep nccl.h
            if nccl_version in NCCL_NCCL_ONLY:
                nccl_net = os.path.join(nccl_dir, "nccl_net.h")
                if os.path.exists(nccl_net):
                    os.remove(nccl_net)
                    logger.debug("  Removed nccl_net.h (not needed for NCCL %s)", nccl_version)

            logger.debug("  Extracted %d headers from wheel", count)
            return True

        return False

    except Exception as e:
        logger.warning("Failed to extract NCCL headers from wheel: %s", e)
        return False


def download_nccl(nccl_version: str, output_dir: str,
                 local_dir: str = None, save_dir: str = None,
                 no_verify: bool = False) -> dict:
    """Download NCCL headers."""
    result = {"downloaded": [], "skipped": []}
    nccl_dir = os.path.join(output_dir, f"nccl-{nccl_version}", "include")

    # Auto-create directories
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    if nccl_version in NCCL_OLD:
        # Old NCCL (2.8~2.12) via CDN .txz
        info = NCCL_OLD[nccl_version]
        url = f"{NCCL_CDN_BASE_URL}/{info['path']}"

        ctx = tempfile.TemporaryDirectory() if not save_dir else None
        with ctx or open(os.devnull):
            tmpdir = save_dir if save_dir else (ctx.name if ctx else "")
            archive_name = os.path.basename(info['path'])
            archive_path = os.path.join(tmpdir, archive_name)

            if local_dir and os.path.isdir(local_dir):
                archive_path = os.path.join(local_dir, archive_name)
                if not os.path.isfile(archive_path):
                    logger.warning("Local archive not found: %s, will download", archive_path)
                    archive_path = os.path.join(tmpdir, archive_name)
                    need_download = True
                else:
                    logger.debug("Using local archive: %s", archive_path)
                    need_download = False
            else:
                if local_dir:
                    logger.warning("Local directory does not exist: %s", local_dir)
                archive_path = os.path.join(tmpdir, archive_name)
                need_download = True

            if need_download:
                try:
                    download_file(url, archive_path)
                except DownloadError as e:
                    result["skipped"].append(f"nccl: {e}")
                    return result

            # Extract headers
            with open(archive_path, 'rb') as f:
                archive_data = f.read()

            count = extract_tar_headers(archive_data, nccl_dir)

            # For NCCL 2.8.3, 2.8.4, 2.27.3, only keep nccl.h
            if nccl_version in NCCL_NCCL_ONLY:
                nccl_net = os.path.join(nccl_dir, "nccl_net.h")
                if os.path.exists(nccl_net):
                    os.remove(nccl_net)
                    logger.debug("  Removed nccl_net.h (not needed for NCCL %s)", nccl_version)

            if count > 0:
                result["downloaded"].append(f"nccl-{nccl_version}")
                logger.debug("Extracted NCCL %s -> %s", nccl_version, nccl_dir)
            else:
                result["skipped"].append(f"nccl: no headers found")

    elif nccl_version in NCCL_WHEELS:
        # NCCL via PyPI wheel
        whl_filename, expected_sha = NCCL_WHEELS[nccl_version]
        url = f"{NCCL_PYPI_BASE_URL}/{whl_filename}"

        # Try optimized wheel extraction first (only downloads headers)
        if not local_dir and not no_verify:
            logger.debug("Trying NCCL wheel optimization (headers only)...")
            if download_nccl_headers_from_wheel(url, nccl_dir, nccl_version):
                result["downloaded"].append(f"nccl-{nccl_version}")
                logger.debug("Extracted NCCL %s -> %s (optimized)", nccl_version, nccl_dir)
                return result
            logger.warning("Wheel optimization failed for NCCL %s, falling back to full download", nccl_version)

        # Fallback to full download
        ctx = tempfile.TemporaryDirectory() if not save_dir else None
        with ctx or open(os.devnull):
            tmpdir = save_dir if save_dir else (ctx.name if ctx else "")
            archive_path = os.path.join(tmpdir, whl_filename)

            if local_dir and os.path.isdir(local_dir):
                archive_path = os.path.join(local_dir, whl_filename)
                if not os.path.isfile(archive_path):
                    logger.warning("Local archive not found: %s, will download", archive_path)
                    archive_path = os.path.join(tmpdir, whl_filename)
                    need_download = True
                else:
                    logger.debug("Using local archive: %s", archive_path)
                    need_download = False
            else:
                if local_dir:
                    logger.warning("Local directory does not exist: %s", local_dir)
                archive_path = os.path.join(tmpdir, whl_filename)
                need_download = True

            if need_download:
                try:
                    download_file(url, archive_path, expected_sha256=expected_sha)
                except DownloadError as e:
                    result["skipped"].append(f"nccl: {e}")
                    return result

            # Extract headers from wheel (ZIP format, not tar)
            import zipfile
            with open(archive_path, 'rb') as f:
                archive_data = f.read()
            count = 0
            try:
                with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
                    for name in zf.namelist():
                        if '/include/' in name and (name.endswith('.h') or name.endswith('.hpp')):
                            # nccl_dir already ends with /include, extract just the filename
                            idx = name.index('/include/') + len('/include/')
                            rel_path = name[idx:]
                            if not rel_path:
                                continue
                            target_path = os.path.join(nccl_dir, rel_path)
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            with zf.open(name) as src:
                                with open(target_path, 'wb') as dst:
                                    dst.write(src.read())
                            count += 1
            except Exception as e:
                logger.error("Failed to extract NCCL wheel: %s", e)

            # For NCCL 2.8.3, 2.8.4, 2.27.3, only keep nccl.h
            if nccl_version in NCCL_NCCL_ONLY:
                nccl_net = os.path.join(nccl_dir, "nccl_net.h")
                if os.path.exists(nccl_net):
                    os.remove(nccl_net)
                    logger.debug("  Removed nccl_net.h (not needed for NCCL %s)", nccl_version)

            if count > 0:
                result["downloaded"].append(f"nccl-{nccl_version}")
                logger.debug("Extracted NCCL %s -> %s", nccl_version, nccl_dir)
            else:
                result["skipped"].append(f"nccl: no headers found")

    else:
        result["skipped"].append(f"nccl: version {nccl_version} not in mapping")

    return result


def download_video(video_version: str, output_dir: str,
                  local_dir: str = None, save_dir: str = None) -> dict:
    """Download Video Codec SDK headers from FFmpeg/nv-codec-headers."""
    result = {"downloaded": [], "skipped": []}
    video_dir = os.path.join(output_dir, f"video-{video_version}", "Interface")

    # Auto-create directories
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    # Video SDK sources: GitHub as primary (GitLab currently unavailable)
    video_sources = [
        f"{GITHUB_BASE_URL}/FFmpeg/nv-codec-headers/archive/refs/tags/n{video_version}.0.tar.gz",
    ]

    ctx = tempfile.TemporaryDirectory() if not save_dir else None
    with ctx or open(os.devnull):
        tmpdir = save_dir if save_dir else (ctx.name if ctx else "")
        archive_name = f"nv-codec-headers-n{video_version}.0.tar.gz"
        archive_path = os.path.join(tmpdir, archive_name)

        if local_dir and os.path.isdir(local_dir):
            archive_path = os.path.join(local_dir, archive_name)
            if not os.path.isfile(archive_path):
                logger.warning("Local archive not found: %s, will download", archive_path)
                archive_path = os.path.join(tmpdir, archive_name)
                need_download = True
            else:
                logger.debug("Using local archive: %s", archive_path)
                need_download = False
        else:
            if local_dir:
                logger.warning("Local directory does not exist: %s", local_dir)
            archive_path = os.path.join(tmpdir, archive_name)
            need_download = True

        if need_download:
            # Try GitLab first, then GitHub
            download_success = False
            last_error = None

            for source_url in video_sources:
                try:
                    logger.debug("Trying Video SDK source: %s", source_url)
                    download_file(source_url, archive_path)
                    download_success = True
                    logger.debug("Successfully downloaded from: %s", source_url)
                    break
                except DownloadError as e:
                    last_error = e
                    logger.warning("Download failed from %s: %s", source_url, e)
                    continue

            if not download_success:
                result["skipped"].append(f"video: {last_error}")
                return result

        # Extract and transform headers
        with open(archive_path, 'rb') as f:
            archive_data = f.read()

        # Extract headers with transformation
        prefix = f"nv-codec-headers-n{video_version}.0/include/ffnvcodec/"
        os.makedirs(video_dir, exist_ok=True)
        count = 0

        try:
            with tarfile.open(fileobj=io.BytesIO(archive_data), mode='r:gz') as tf:
                for m in tf.getmembers():
                    if not m.isfile():
                        continue

                    # Check if it's one of our target files
                    filename = os.path.basename(m.name)
                    if filename not in VIDEO_FILE_MAPPING:
                        continue

                    # Transform content
                    with tf.extractfile(m) as src:
                        content = src.read().decode('utf-8')

                    if filename == "dynlink_cuviddec.h":
                        content = _transform_cuviddec(content)
                    elif filename == "dynlink_nvcuvid.h":
                        content = _transform_nvcuvid(content)
                    elif filename == "nvEncodeAPI.h":
                        content = _transform_nvenc(content)

                    # Write with CRLF line endings
                    output_filename = VIDEO_FILE_MAPPING[filename]
                    output_path = os.path.join(video_dir, output_filename)
                    with open(output_path, 'w', newline='\r\n') as f:
                        f.write(content)
                    count += 1
                    logger.debug("  %s -> %s", filename, output_filename)

            if count > 0:
                result["downloaded"].append(f"video-{video_version}")
                logger.debug("Extracted Video SDK %s -> %s", video_version, video_dir)
            else:
                result["skipped"].append(f"video: no headers found")

        except Exception as e:
            result["skipped"].append(f"video: {e}")

    return result


def resolve_version(cuda_version: str) -> dict | None:
    """Resolve CUDA version to full version mapping."""
    if cuda_version in VERSION_MAP:
        return VERSION_MAP[cuda_version]

    # Try to find by major.minor
    major_minor = _parse_major_minor(cuda_version)
    if major_minor in VERSION_MAP:
        return VERSION_MAP[major_minor]

    return None


def download_all(cuda_version: str = None, output_dir: str = ".",
                components: list = None, cudnn_version: str = None,
                cudnn_variant: str = None, nccl_version: str = None,
                video_version: str = None, local_dir: str = None,
                save_dir: str = None, range_opt: bool = True,
                no_verify: bool = False) -> dict:
    """
    Download all requested components.

    Args:
        cuda_version: CUDA version (e.g., "12.6" or "12.6.0")
        output_dir: Output directory
        components: List of components to download (cuda, cudnn, nccl, video)
        cudnn_version: Specific cuDNN version
        cudnn_variant: cuDNN CUDA variant (cuda11/cuda12)
        nccl_version: Specific NCCL version
        video_version: Specific Video SDK version
        local_dir: Local directory with pre-downloaded archives
        save_dir: Directory to save downloaded archives
        range_opt: Enable Range optimization (default True)
        no_verify: Skip SHA256 verification

    Returns:
        Dict with "downloaded" and "skipped" lists
    """
    result = {"downloaded": [], "skipped": []}

    # Resolve CUDA version
    version_info = resolve_version(cuda_version) if cuda_version else None

    # Determine which components to download
    if components is None:
        # Default: download all components
        components = ["cuda", "cudnn", "nccl", "video"]

    # Auto-detect versions if not specified
    if version_info:
        if "cuda" in components and not cuda_version:
            cuda_version = version_info["cuda"]
        if "cudnn" in components and not cudnn_version:
            cudnn_version = version_info["cudnn"]
        if "nccl" in components and not nccl_version:
            nccl_version = version_info["nccl"]
        if "video" in components and not video_version:
            video_version = version_info["video"]

    # Download CUDA
    if "cuda" in components and cuda_version:
        logger.info("Downloading CUDA %s...", cuda_version)
        cuda_result = download_cuda(cuda_version, output_dir, local_dir, save_dir,
                                   range_opt, no_verify)
        result["downloaded"].extend(cuda_result["downloaded"])
        result["skipped"].extend(cuda_result["skipped"])

    # Download cuDNN
    if "cudnn" in components and cudnn_version:
        logger.info("Downloading cuDNN %s...", cudnn_version)
        cudnn_result = download_cudnn(cudnn_version, output_dir, cuda_version,
                                     cudnn_variant, local_dir, save_dir,
                                     no_verify, range_opt)
        result["downloaded"].extend(cudnn_result["downloaded"])
        result["skipped"].extend(cudnn_result["skipped"])

    # Download NCCL
    if "nccl" in components and nccl_version:
        logger.info("Downloading NCCL %s...", nccl_version)
        nccl_result = download_nccl(nccl_version, output_dir, local_dir, save_dir, no_verify)
        result["downloaded"].extend(nccl_result["downloaded"])
        result["skipped"].extend(nccl_result["skipped"])

    # Download Video SDK
    if "video" in components and video_version:
        logger.info("Downloading Video SDK %s...", video_version)
        video_result = download_video(video_version, output_dir, local_dir, save_dir)
        result["downloaded"].extend(video_result["downloaded"])
        result["skipped"].extend(video_result["skipped"])

    return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="CUDA Redistributable Header Downloader")
    parser.add_argument("version", nargs='?', help="CUDA version (e.g., 12.6 or 12.6.0)")
    parser.add_argument("-o", "--output", default=".", help="Output directory (default: .)")
    parser.add_argument("--components", nargs='+',
                       choices=["cuda", "cudnn", "nccl", "video"],
                       help="Components to download (default: all)")
    parser.add_argument("--cudnn", help="Specific cuDNN version")
    parser.add_argument("--cudnn-variant", choices=["cuda11", "cuda12"],
                       help="cuDNN CUDA variant")
    parser.add_argument("--nccl", help="Specific NCCL version")
    parser.add_argument("--video", help="Specific Video SDK version")
    parser.add_argument("--local-dir", help="Local directory with pre-downloaded archives")
    parser.add_argument("--save-dir", help="Directory to save downloaded archives")
    parser.add_argument("--no-range-optimization", action='store_true',
                       help="Disable Range optimization")
    parser.add_argument("--no-verify", action='store_true',
                       help="Skip SHA256 verification")
    parser.add_argument("-v", "--verbose", action='store_true', help="Verbose output")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(levelname)s: %(message)s'
    )

    # Validate arguments
    if not args.version and not (args.cudnn or args.nccl or args.video):
        parser.error("Must specify either CUDA version or at least one standalone component")

    # Determine versions
    cuda_version = args.version
    cudnn_version = args.cudnn
    nccl_version = args.nccl
    video_version = args.video

    # If CUDA version specified but no components specified, download all
    components = args.components if args.components else ["cuda", "cudnn", "nccl", "video"]

    # Download
    result = download_all(
        cuda_version=cuda_version,
        output_dir=args.output,
        components=components,
        cudnn_version=cudnn_version,
        cudnn_variant=args.cudnn_variant,
        nccl_version=nccl_version,
        video_version=video_version,
        local_dir=args.local_dir,
        save_dir=args.save_dir,
        range_opt=not args.no_range_optimization,
        no_verify=args.no_verify
    )

    # Print summary
    print(f"\nDownloaded: {len(result['downloaded'])} components")
    if result['skipped']:
        print(f"Skipped: {len(result['skipped'])} components")
        for skip in result['skipped']:
            print(f"  - {skip}")


if __name__ == "__main__":
    main()
