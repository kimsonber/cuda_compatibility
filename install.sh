#!/bin/bash
#
# Wrapper tool build and install.
#
# Usage:
#   curl -LsSf https://xxx/install.sh | bash
#
# Or run directly:
#   ./install.sh
#
# Environment variables:
#   PPU_TARGET_ARCH           - Target architecture (default: uname -m)
#   PPU_HOST_ARCH             - Host architecture (default: uname -m)
#   PPU_INSTALL_TYPE          - For cross-arch install: "native" or others (default: native)
#   OPEN_WRAPPER_CLONE_BRANCH - Git branch for Open Wrapper (default: master)
#   CONFIGS_TAG               - Git tag for Open Wrapper Configs (default: ${CUDA_VERSION}+ppu${RELEASE_VERSION})
#   CUDA_SDK_CONFIGS_REPO          - Repo name for CUDA SDK configs (default: cuda_compatibility)
#   BASE_URL                  - Base URL for all repositories
set -e

OPEN_WRAPPER_CLONE_BRANCH=${OPEN_WRAPPER_CLONE_BRANCH:-"main"}
CUDA_SDK_CONFIGS_REPO=${CUDA_SDK_CONFIGS_REPO:-"cuda_compatibility.git"}
CONFIG_BASE_REPO_URL=${BASE_URL:-"https://github.com/kimsonber"}
WRAPPER_BASE_REPO_URL=${BASE_URL:-"https://github.com/rtc17"}
NOT_CHECK_SDK_COMPATIBILITY=${NOT_CHECK_SDK_COMPATIBILITY:-false}
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

info() {
  printf '\n%s\n' "$*" >&2
}

warn() {
  printf '\nwarning: %s\n' "$*" >&2
}

error() {
  printf '\nerror: %s\n' "$*" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
  cat <<EOF
install.sh — Build/install/clean wrapper tooling

USAGE:
    ./install.sh [OPTIONS]

OPTIONS:
    --command <cmd>                Command to run (default: build_and_install)
                                  Commands:
                                    build_and_install  - Compiles and installs the project
                                    build              - Compiles the project
                                    install            - Installs the compiled project
                                    clean              - Removes build artifacts

    --cuda_version <version>       CUDA version (default: cuda-11.6)
    --ppu_sdk_path <path>          PPU SDK path (required for build/install; same as original behavior)
    --cuda_sdk_files_path <path>   Use local CUDA SDK files path, don't download them (optional)

ENVIRONMENT VARIABLES:
    PPU_TARGET_ARCH   Target architecture (default: uname -m)
    PPU_HOST_ARCH     Host architecture (default: uname -m)
    PPU_INSTALL_TYPE  Install type for cross-arch ("native" uses build-cross binaries; default: native)
    CUDA_SDK_FILES_PATH   Specify local CUDA SDK files path to be used

EOF
}
# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------

get_workspace() {
  (cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)
}

get_target_arch() {
  echo "${PPU_TARGET_ARCH:-$(uname -m)}"
}

get_host_arch() {
  echo "${PPU_HOST_ARCH:-$(uname -m)}"
}

get_install_type() {
  echo "${PPU_INSTALL_TYPE:-native}"
}

get_cuda_version() {
  echo "${CUDA_VERSION}"
}

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --command)
        COMMAND="${2:-}"; shift 2 ;;
      --cuda_version)
        CUDA_VERSION="${2:-}"; shift 2 ;;
      --ppu_sdk_path)
        PPU_SDK_PATH="${2:-}"; shift 2 ;;
      # optional
      --cuda_sdk_files_path)
        CUDA_SDK_FILES_PATH="${2:-}"; shift 2 ;;
      --version_config_path)
        VERSION_CONFIG_PATH="${2:-}"; shift 2 ;;
      --help|-h)
        usage; exit 0 ;;
      *)
        shift ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# download and clone
# ---------------------------------------------------------------------------
has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

check_downloader() {
  if has_cmd curl; then
    return 0
  elif has_cmd wget; then
    return 0
  else
    error "either 'curl' or 'wget' is required to download files"
  fi
}

download() {
  _url="$1"
  _output="$2"

  if has_cmd curl; then
    curl -fLsS --retry 3 -o "$_output" "$_url"
  elif has_cmd wget; then
    wget -q --tries=3 -O "$_output" "$_url"
  fi
}

clone() {
  _url="$1"
  _output="$2"
  _branch="${3:-}"  # optional

  if has_cmd git; then
    if [ -d $_output ]; then
      rm -rf $_output
    fi
    if [ -n "$_branch" ]; then
      git clone --single-branch -b "$_branch" "$_url" "$_output"
    else
      git clone "$_url" "$_output"
    fi
  else
    error "git is required to clone repositories, please install git and re-run."
  fi
}

# ---------------------------------------------------------------------------
# Check wrapper tools env
# ---------------------------------------------------------------------------
check_env() {
  info "check env for tools."
}

# ---------------------------------------------------------------------------
# Work in virtual python env
# ---------------------------------------------------------------------------
work_in_virtual_env() {
  info "create a new python env."
  cd ${WORKSPACE}
  python -m venv .venv
  info "activate new python env."
  source .venv/bin/activate
  python -m pip install -U pip
}

# ---------------------------------------------------------------------------
# Deactivate and delete virtual env 
# ---------------------------------------------------------------------------
deactivate_env() {
  deactivate
  rm -rf ${WORKSPACE}/.venv
}

# ---------------------------------------------------------------------------
# Install requirement
# ---------------------------------------------------------------------------
install_requirement() {
  info "install api_wrapper_generator"
  pip install -e ${OPEN_WRAPPER_PATH}/api_wrapper_generator
  info "install file_wrapper"
  pip install -e ${OPEN_WRAPPER_PATH}/file_wrapper
}

# ---------------------------------------------------------------------------
# Get full version
# ---------------------------------------------------------------------------
get_libs_by_section() {
  ini=$1
  section=$2

  awk -v sec="$section" '
    function trim(s){ sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }

    BEGIN { in_sec=0 }

    $0 ~ "^[ \t]*\\[" sec "\\][ \t]*([;#].*)?$" { in_sec=1; next }

    $0 ~ "^[ \t]*\\[" { in_sec=0 }

    in_sec {
      line=$0
      sub(/[ \t]*[;#].*$/, "", line)
      line=trim(line)
      if (line ~ /^lib[0-9]+=/) {
        split(line, kv, "=")
        key=kv[1]; val=kv[2]
        sub(/^lib/, "", key)
        n=key+0
        libs[n]=trim(val)
      }
    }

    END {
      for (i=1; i<=4; i++) {
        if (i in libs) print libs[i]
        else print ""
      }
    }
  ' "$ini"
}

# ---------------------------------------------------------------------------
# check ppu sdk compatibility
# ---------------------------------------------------------------------------
check_sdk_compatibility() {
  if [[ -f "$PPU_SDK_PATH/VERSION.txt" ]]; then
      hggcrt_ver=$(grep -o "hggcrt_version:[^[:space:]]*" "$PPU_SDK_PATH/VERSION.txt" | cut -d':' -f2 | tr -d '[:space:]\r')
  fi

  if [[ -n "$hggcrt_ver" ]]; then
      cuda_major=$(echo "$CUDA_VERSION" | grep -oE '[0-9]+' | head -n1)
      case "$cuda_major" in
          11|12) [[ "$hggcrt_ver" == "v2" ]] || { echo "Error: Need PPU SDK HGGCRT v2"; exit 1; } ;;
          13)    [[ "$hggcrt_ver" == "v3" ]] || { echo "Error: Need PPU SDK HGGCRT v3"; exit 1; } ;;
      esac
  fi
}

# ---------------------------------------------------------------------------
# get sdk info
# ---------------------------------------------------------------------------
get_sdk_info() {
  [ -f "$1/release.yaml" ] || return 0
  version=$(awk -F: '/version/{
  v=$2
  gsub(/^[[:space:]]+/, "", v)
  gsub(/[[:space:]]+$/, "", v)
  print v
  exit
}' "$1/release.yaml")

version=$(printf '%s' "$version" | tr -d '\r' | xargs)

  case "$version" in
    [0-9]*.[0-9]*.[0-9]*-*) ;;
    *) return 0 ;;
  esac

  clean_ver="${version%%-*}"
  IFS=. read -r major minor patch <<< "$clean_ver"
  branch_name="${major}v${minor}"
  printf '%s %s\n' "$branch_name" "$version"
}

# ---------------------------------------------------------------------------
# Build steps
# ---------------------------------------------------------------------------
build_binary_wrapper() {
  info "build: binary wrappers"
  cd "${BINARY_CONFIG_PATH}"
  mkdir -p build && cd build
  cmake .. ${NVCC_WRAPPER_OPTIONS} -DCMAKE_INSTALL_PREFIX=${PPU_SDK_PATH}/CUDA_SDK/bin \
                                   -DCUDA_FULL_VERSION=${CUDA_FULL_VERSION}
  make -j"${CPU_NUM}"

  compiler_cc="gcc"

  if [ "${TARGET_ARCH}" != "${HOST_ARCH}" ]; then
    info "cross build: wrappers (${TARGET_ARCH} != ${HOST_ARCH})"

    # Build cross-compiled binaries
    cd "${BINARY_CONFIG_PATH}"
    mkdir -p build-cross && cd build-cross
    cmake .. ${NVCC_WRAPPER_OPTIONS} -DCMAKE_C_COMPILER=${TARGET_ARCH}-linux-gnu-gcc  \
                                     -DCMAKE_CXX_COMPILER=${TARGET_ARCH}-linux-gnu-g++ \
                                     -DCMAKE_INSTALL_PREFIX=${PPU_SDK_PATH}/CUDA_SDK/bin
    make -j${CPU_NUM}

    compiler_cc="${TARGET_ARCH}-linux-gnu-gcc"
  fi
}

build_project() {

  # build binary
  build_binary_wrapper

  cd "${OPEN_WRAPPER_PATH}"

  sdk_files_in="${WORKSPACE}/cuda_sdk_files"
  if [ -n "${CUDA_SDK_FILES_PATH}" ]; then
    sdk_files_in="${CUDA_SDK_FILES_PATH}"
  fi

  # build include and lib
  CMD="python magician/main.py --cuda_version ${CUDA_VERSION} --ppu ${PPU_SDK_PATH} --output ${OUTPUT_DIR} \
         --gcc ${compiler_cc} --config_dir_path ${OPEN_WRAPPER_PATH}/configs \
         --sdk_src_path ${sdk_files_in}"

  info "${CMD}"
  eval "${CMD}"
}

clean_project() {
  info "clean project."
  cd "${WORKSPACE}"
  rm -rf cuda_sdk_configs
  if [ -z "${CUDA_SDK_FILES_PATH}" ]; then
    rm -rf cuda_sdk_files
  fi
  rm -rf open_wrapper
  exit 0
}

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install_project() {
  info "install to: ${PPU_SDK_PATH}"
  mkdir -p "${PPU_SDK_PATH}"
  rm -rf "${PPU_SDK_PATH}/CUDA_SDK"
  cp -avr "${OUTPUT_DIR}" "${PPU_SDK_PATH}/CUDA_SDK"

  cd "${PPU_SDK_PATH}/CUDA_SDK/targets"
  if [ "${TARGET_ARCH}" = "aarch64" ]; then
    mv sbsa-linux "${TARGET_ARCH}-linux"
  fi

  cd "${PPU_SDK_PATH}/CUDA_SDK"
  rm -f include lib64
  ln -s "targets/${TARGET_ARCH}-linux/include" include
  ln -s "targets/${TARGET_ARCH}-linux/lib" lib64

  if [ "${TARGET_ARCH}" != "${HOST_ARCH}" ]; then
      if [ "${INSTALL_TYPE}" == "native" ]; then
          cd ${BINARY_CONFIG_PATH}/build-cross
          make install && cd -
      else
          cd ${BINARY_CONFIG_PATH}/build
          make install && cd -
      fi
  fi

  rm -rf "${PPU_SDK_PATH}/CUDA_SDK/JsonFiles" "${PPU_SDK_PATH}/CUDA_SDK/wrapper_src"
  cp "${OPEN_WRAPPER_PATH}/configs/envsetup.sh" "${PPU_SDK_PATH}/CUDA_SDK"
}

build_and_install_project() {
  build_project
  install_project
}

download_files() {
    ver="${CUDA_FULL_VERSION#cuda-}"
    CMD="python open_wrapper/magician/cuda_redist_downloader.py $ver -o ${WORKSPACE}/cuda_sdk_files"
    info "${CMD}"
    eval "${CMD}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {

  WORKSPACE="$(get_workspace)"

  TARGET_ARCH="$(get_target_arch)"
  HOST_ARCH="$(get_host_arch)"
  INSTALL_TYPE="$(get_install_type)"

  # Defaults
  COMMAND=""
  CUDA_VERSION="$(get_cuda_version)"
  PPU_SDK_PATH="/usr/local/PPU_SDK"
  VERSION_CONFIG_PATH=""

  # Parse CLI args
  parse_args "$@"

  # Clean
  if [[ ${COMMAND} == "clean" ]]; then
    clean_project
  fi

  if [ -z "${COMMAND}" ]; then
    COMMAND="build_and_install"
  fi

  RELEASE_BRANCH=""
  RELEASE_VERSION=""
  info "${PPU_SDK_PATH}"
  if [ -d "${PPU_SDK_PATH}" ]; then
    info "PPU SDK is ready!"
    # || true prevents set -e from exiting the script.
    read -r RELEASE_BRANCH RELEASE_VERSION < <(get_sdk_info "${PPU_SDK_PATH}") || true
    echo "PPU SDK is $RELEASE_BRANCH version!"
  else
    error "PPU SDK is not exist!"
  fi

  info "check cuda version!"
  if [ -n "${CUDA_VERSION}" ]; then
    info "Cuda version is ${CUDA_VERSION}!"
  else
    error "Cuda version is not specified!"
  fi

  check_downloader
  if [ "${NOT_CHECK_SDK_COMPATIBILITY}" = "false" ]; then
    check_sdk_compatibility
  fi

  OPEN_WRAPPER_PATH=${WORKSPACE}/open_wrapper

  if [ -z "$NOT_CLONE_REPO" ]; then
    cd ${WORKSPACE}
    info "downloading open_wrapper ..."
    clone "${WRAPPER_BASE_REPO_URL}/open_wrapper.git" ${OPEN_WRAPPER_PATH} ${OPEN_WRAPPER_CLONE_BRANCH}

    info "downloading common cuda_sdk_configs ..."
    if [ -z "$CONFIGS_TAG" ]; then
      CONFIGS_TAG="${CUDA_VERSION}+ppu${RELEASE_VERSION}"
    fi
    clone "${CONFIG_BASE_REPO_URL}/${CUDA_SDK_CONFIGS_REPO}" "${WORKSPACE}/cuda_sdk_configs" "${CONFIGS_TAG}"
    mv ${WORKSPACE}/cuda_sdk_configs/configs ${OPEN_WRAPPER_PATH}
    mv ${WORKSPACE}/cuda_sdk_configs/magician ${OPEN_WRAPPER_PATH}

    info "downloading common cuda_sdk_configs for specified version..."

    if [ -n "${VERSION_CONFIG_PATH}" ] && [ -s "$VERSION_CONFIG_PATH" ]; then
      info "using version configs that user provides."
      cp -r ${VERSION_CONFIG_PATH} ${OPEN_WRAPPER_PATH}/configs
    else
      if [ -d "${WORKSPACE}/cuda_sdk_configs/${CUDA_VERSION}" ]; then
        mv ${WORKSPACE}/cuda_sdk_configs/${CUDA_VERSION} ${OPEN_WRAPPER_PATH}/configs
      fi
    fi
    rm -rf ${WORKSPACE}/cuda_sdk_configs
  fi

  info "full versions are: "
  set -- $(get_libs_by_section ${OPEN_WRAPPER_PATH}/configs/input_lib_version.ini ${CUDA_VERSION})
  CUDA_FULL_VERSION=$1
  CUDNN_FULL_VERSION=$2
  NCCL_FULL_VERSION=$3
  VIDEO_FULL_VERSION=$4
  if [ -z "$CUDA_FULL_VERSION" ] || [ -z "$CUDNN_FULL_VERSION" ] ||
     [ -z "$NCCL_FULL_VERSION" ] || [ -z "$VIDEO_FULL_VERSION" ]; then
    error "missing full versions, cuda version: ${CUDA_VERSION} may not be supported."
  fi
  info "$CUDA_FULL_VERSION $CUDNN_FULL_VERSION $NCCL_FULL_VERSION $VIDEO_FULL_VERSION"

  if [ -n "${CUDA_SDK_FILES_PATH}" ]; then
    echo "skip download sdk files, use CUDA_SDK_FILES_PATH=${CUDA_SDK_FILES_PATH}"
  else
    info "downloading cuda_sdk_files ..."
    download_files
  fi

  OUTPUT_DIR="${OPEN_WRAPPER_PATH}/build/Output/${CUDA_VERSION}"
  NVCC_WRAPPER_OPTIONS="-DCUDA_VERSION=${CUDA_VERSION}"
  BINARY_CONFIG_PATH="${OPEN_WRAPPER_PATH}/configs/binary_config"

  check_env

  work_in_virtual_env

  install_requirement

  case "${COMMAND}" in
    build)
      build_project
      ;;
    install)
      install_project
      ;;
    build_and_install)
      build_and_install_project
      ;;
    *)
      error "Unknown command: ${COMMAND}"
      ;;
  esac

  deactivate_env
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Executed, not sourced
    main "$@"
fi
