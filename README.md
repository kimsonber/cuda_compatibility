# CUDA Compatibility

> Cross-SDK compatibility through auto-generated wrappers — run applications built for one SDK on alternative hardware without source changes.

Built on [open_wrapper](https://github.com/rtc17/open_wrapper), this project bridges the gap between heterogeneous computing SDKs. By auto-generating API wrappers from configuration files, it enables applications written for one SDK to run transparently on another — no source modifications required.

The framework is SDK-agnostic: API mapping rules between a source and target SDK are defined in configs, and wrapper code is auto-generated to intercept and forward calls at both the library level (`dlopen`/`dlsym`) and the command-line tool level (`fork`/`execvp`).

**Current implementation**: CUDA SDK → SAIL SDK (a.k.a. PPU SDK), covering CUDA runtime, cuDNN, cuBLAS, cuFFT, cuSPARSE, NPP, NCCL, and more. Additional SDK pairs can be added by following the same configuration pattern.

This repository provides pre-generated configurations and build orchestration scripts that work with open_wrapper's code generation tools to deliver an end-to-end build and install experience.

## How It Works

### Two-Layer Wrapper Architecture

The wrapper layer sits between the application and the target SDK, operating at two levels:

- **API Wrapper** — Intercepts runtime library calls from the source SDK (e.g., CUDA's `libcudart`, `libcublas`, `libcudnn`) and dynamically loads the corresponding target SDK libraries via `dlopen`/`dlsym`. Applications link against wrapper libraries (`.so`/`.a`) with no awareness of the underlying SDK switch.
- **Binary Wrapper** — Wraps command-line tools from the source SDK (e.g., `nvcc`, `nvlink`, `nvprune`, `ptxas`) and forwards invocations to the target SDK's toolchain via `fork`/`execvp`, preserving build pipeline compatibility.

## Quick Start

### Prerequisites

| Dependency | Description |
|------------|-------------|
| Linux x86_64 / aarch64 | Required for POSIX APIs (`dlopen`/`dlsym`/`fork`/`execvp`) |
| Python 3.8+ | Configuration generation and build orchestration |
| CMake 3.18+ | Compiling Binary Wrappers |
| GCC / G++ | C/C++ compiler |
| Git | Cloning dependency repositories |
| curl or wget | Downloading SDK files |
| CUDA SDK | Installed source SDK |
| PPU SDK (SAIL SDK) | Installed target SDK |

### Installation

This repository uses branches to manage configurations for different CUDA versions (e.g., `cuda-11.0`, `cuda-12.8`, `cuda-13.0`). `install.sh` automatically fetches the branch matching the specified `--cuda_version` — no manual branch switching needed.

```bash
# Build and install (default: /usr/local/PPU_SDK)
./install.sh --cuda_version cuda-13.0 --ppu_sdk_path /path/to/PPU_SDK

# Clean build artifacts
./install.sh --command clean
```

### Post-Install Setup

After installation, a `CUDA_SDK/` subdirectory and an `envsetup.sh` script are generated. Source `envsetup.sh` to set up `CUDA_PATH`, `CUDA_HOME`, `PATH`, `LD_LIBRARY_PATH`, and other environment variables — CUDA applications will then transparently use the wrapper libraries.

## Project Structure

```
cuda_compatibility/
├── install.sh                          # Installation entry script
├── configs/                            # Pre-generated compatibility configurations
│   ├── api_config/                     # API mapping (config.txt + private headers)
│   ├── binary_config/                  # Binary Wrapper config (nvcc/nvlink/nvprune/ptxas)
│   ├── patch_config/                   # Header patches (pre/post-build injection)
│   ├── envsetup.sh                     # Environment setup script
│   └── input_lib_version.ini           # Version mapping table
├── magician/                           # Build orchestration (Python)
│   ├── main.py                         # Main orchestration entry
│   ├── folder_info.py                  # SDK directory structure analysis
│   ├── utils.py                        # Utility functions
│   └── cuda_redist_downloader.py       # CUDA SDK header downloader
└── README.md                           # This document
```

## Core Components

### install.sh

Entry point for the entire build and install pipeline. Supports `build_and_install`, `build`, `install`, and `clean` commands.

> Run `./install.sh --help` for the full list of options.

### configs/

Pre-generated configurations that drive wrapper code generation:

- **api_config/config.txt** — Library-level API mapping rules: header file correspondences and API name matching between source and target SDK libraries
- **binary_config/** — CMake build config for Binary Wrappers (currently `nvcc`, `nvlink`, `nvprune`, `ptxas`)
- **patch_config/** — Source SDK header patches: pre/post-build file injection and file-level patch rules
- **input_lib_version.ini** — Version mapping table; `install.sh` uses this to download the correct SDK components
- **envsetup.sh** — Post-install environment setup; supports CUDA compatibility mode (default) and target SDK native mode

### magician/

Python scripts that orchestrate API Wrapper generation:

- **main.py** — Main orchestrator; invokes open_wrapper's `api-wrapper-generator` over each library in `config.txt` to generate and compile wrapper source

## Relationship with open_wrapper

[open_wrapper](https://github.com/rtc17/open_wrapper) is the general-purpose wrapper generation toolkit behind this project. It provides three tools:

- **api_wrapper_generator** — Generates C++ wrapper source from YAML/JSON configs (API mapping, type conversion, custom code injection)
- **binary_wrapper** — Generates C++ wrapper code for command-line tools from JSON configs (argument forwarding via `fork`/`execvp`)
- **file_wrapper** — File-level patching tool for header modifications

This repository is the first real-world application of open_wrapper, providing pre-generated configs and orchestration for the CUDA → PPU SDK scenario. Additional SDK pairs can be integrated by following the same structure.

| Responsibility | open_wrapper | cuda_compatibility |
|----------------|-------------|-------------------|
| API Wrapper generation | ✓ (api_wrapper_generator) | — |
| Binary Wrapper generation | ✓ (binary_wrapper) | — |
| File patching tool | ✓ (file_wrapper) | — |
| API mapping configuration | — | ✓ (config.txt + YAML) |
| Binary Wrapper config & source | — | ✓ (binary_config/) |
| Build orchestration | — | ✓ (magician/) |
| Installation entry | — | ✓ (install.sh) |
| Version management | — | ✓ (input_lib_version.ini) |

## License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.
