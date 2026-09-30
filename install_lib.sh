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
#   CONFIGS_TAG               - Git tag for Open Wrapper Configs (default: ${LIB_VERSION}+ppu${RELEASE_VERSION})
#   CUDA_SDK_CONFIGS_REPO          - Repo name for CUDA SDK configs (default: cuda_compatibility)
#   BASE_URL                  - Base URL for all repositories
set -e

OPEN_WRAPPER_CLONE_BRANCH=${OPEN_WRAPPER_CLONE_BRANCH:-"main"}
CUDA_SDK_CONFIGS_REPO=${CUDA_SDK_CONFIGS_REPO:-"cuda_compatibility.git"}
CONFIG_BASE_REPO_URL=${BASE_URL:-"https://github.com/kimsonber"}
WRAPPER_BASE_REPO_URL=${BASE_URL:-"https://github.com/rtc17"}
DOWNLOADER_BASE_URL=${DOWNLOADER_BASE_URL:-"https://raw.githubusercontent.com/kimsonber/cuda_compatibility/refs/heads/main"}
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

    --lib_version <version>        Version of wrapper lib to generate, support nccl-x.y.z so far.
    --lib_sdk_path <path>          PPU side Lib SDK path as wrapper target, support pccl so far. (required for build/install; same as original behavior)
    --ppu_sdk_path <path>          PPU SDK path (required for build/install; same as original behavior)
    --cuda_sdk_files_path <path>   Use local CUDA SDK files path, don't download them (optional)

ENVIRONMENT VARIABLES:
    PPU_TARGET_ARCH   Target architecture (default: uname -m)
    PPU_HOST_ARCH     Host architecture (default: uname -m)
    PPU_INSTALL_TYPE  Install type for cross-arch ("native" uses build-cross binaries; default: native)

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

get_lib_version() {
  echo "${LIB_VERSION}"
}

get_lib_version_with_dep() {
  echo "${LIB_VERSION}"
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
      --lib_version)
        LIB_VERSION="${2:-}"; shift 2 ;;
      --ppu_sdk_path)
        PPU_SDK_PATH="${2:-}"; shift 2 ;;
      --lib_sdk_path)
        LIB_SDK_PATH="${2:-}"; shift 2 ;;
      # optional
      --cuda_sdk_files_path)
        CUDA_SDK_FILES_PATH="${2:-}"; shift 2 ;;
      --version_config_path)
        VERSION_CONFIG_PATH="${2:-}"; shift 2 ;;
      --download_from_source)
        DOWNLOAD_FROM_SOURCE=1; shift 1 ;;
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
# get sdk info
# ---------------------------------------------------------------------------
get_sdk_info() {
  [ -f "$1/release.yaml" ] || return 0
  version=$(awk '/^[[:space:]]*version:[[:space:]]*/ {print $2; exit}' "$1/release.yaml")
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
# get each standalone lib list
# ---------------------------------------------------------------------------
get_lib_list_by_section() {
    local ini_file="$1"
    local sections_var_name="$2"
    local current_section=""
    local line

    eval "$sections_var_name=()"

    while IFS= read -r line || [ -n "$line" ]; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"

        [ -z "$line" ] && continue

        case "$line" in
            \#*|\;*) continue ;;
            \[*\])
                current_section="${line:1:${#line}-2}"
                current_section="${current_section%%:*}"
                eval "$sections_var_name+=(\"\$current_section\")"
                eval "$current_section=()"
                ;;
            *)
                if [ -n "$current_section" ]; then
                    eval "$current_section+=(\"\$line\")"
                fi
                ;;
        esac
    done < "$ini_file"
}

print_standalone_libs() {
  local array_name=$1
  local lib_ver_in=$2
  local ret_name=$3
  local -n _lib_array="$array_name"
  local -n _ret_ref="$ret_name"
  _ret_ref=""
  echo all supported libs:
  for libname in "${_lib_array[@]}"; do
      if [ "$libname" == "global" ]; then
          continue
      fi
      echo "[$libname]"
      local -n libvers="$libname"
      for libver in "${libvers[@]}"; do
          if [ "$libver" == "$lib_ver_in" ]; then
              _ret_ref="1"
          fi
          echo "    $libver"
      done
      echo
  done
}

# ---------------------------------------------------------------------------
# Build steps
# ---------------------------------------------------------------------------

build_project() {

  compiler_cc="gcc"
  if [ "${TARGET_ARCH}" != "${HOST_ARCH}" ]; then
    compiler_cc="${TARGET_ARCH}-linux-gnu-gcc"
  fi

  cd "${OPEN_WRAPPER_PATH}"

  sdk_files_in="${WORKSPACE}/cuda_sdk_files"
  if [ -n "${CUDA_SDK_FILES_PATH}" ]; then
    sdk_files_in="${CUDA_SDK_FILES_PATH}"
  fi

  # build include and lib
  CMD="python magician/main.py --lib_version ${LIB_VERSION} --lib_dep_version ${DEPEND_API_VERSION} --ppu ${PPU_SDK_PATH} --ppu_lib ${LIB_SDK_PATH} --output ${OUTPUT_DIR} \
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
  info "install to: ${LIB_SDK_PATH}"
  mkdir -p "${LIB_SDK_PATH}"
  local SDK_NAME="${LIB_NAME}_wrapper"
  echo install to SDK_NAME: $SDK_NAME

  rm -rf "${LIB_SDK_PATH}/${SDK_NAME}"
  cp -avr "${OUTPUT_DIR}" "${LIB_SDK_PATH}/${SDK_NAME}"

  if [[ -f "${OPEN_WRAPPER_PATH}/configs/envsetup.sh" ]]; then
    cp "${OPEN_WRAPPER_PATH}/configs/envsetup.sh" "${LIB_SDK_PATH}"
  fi
}

build_and_install_project() {
  build_project
  install_project
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
  PPU_SDK_PATH="/usr/local/PPU_SDK"
  VERSION_CONFIG_PATH=""

  # Parse CLI args
  parse_args "$@"
  LIB_VERSION="$(get_lib_version)"
  LIB_NAME="${LIB_VERSION%%-*}"

  # Clean
  if [[ ${COMMAND} == "clean" ]]; then
    clean_project
  fi

  if [ -z "${COMMAND}" ]; then
    COMMAND="build_and_install"
  fi

  DEP_RELEASE_BRANCH=""
  DEP_RELEASE_VERSION=""
  info "${PPU_SDK_PATH}"
  if [ -d "${PPU_SDK_PATH}" ]; then
    info "PPU SDK is ready!"
    # || true prevents set -e from exiting the script.
    read -r DEP_RELEASE_BRANCH DEP_RELEASE_VERSION < <(get_sdk_info "${PPU_SDK_PATH}") || true
    echo "PPU SDK is $DEP_RELEASE_BRANCH version!"
  else
    error "PPU SDK is not exist!"
  fi

  RELEASE_BRANCH=""
  RELEASE_VERSION=""
  info "${LIB_SDK_PATH}"
  if [ -d "${LIB_SDK_PATH}" ]; then
    info "LIB SDK is ready!"
    # || true prevents set -e from exiting the script.
    read -r RELEASE_BRANCH RELEASE_VERSION < <(get_sdk_info "${LIB_SDK_PATH}") || true
    echo "PPU SDK is $RELEASE_BRANCH version!"
  else
    error "PPU SDK is not exist!"
  fi

  info "check lib version!"
  if [ -n "${LIB_VERSION}" ]; then
    info "Lib version is ${LIB_VERSION}!"
  else
    error "Lib version is not specified!"
  fi

  check_downloader

  OPEN_WRAPPER_PATH=${WORKSPACE}/open_wrapper

  info "check lib's depending API version"
  if [[ "$LIB_VERSION" == *-v13 ]]; then
    LIB_DEP_SDK_VERSION="cuda-13.1.0"
    DEPEND_API_VERSION=13
    info depending sdk version is $LIB_DEP_SDK_VERSION
  else
    LIB_DEP_SDK_VERSION="cuda-12.9.0"
    info depending sdk version is $LIB_DEP_SDK_VERSION
    DEPEND_API_VERSION=12
  fi

  if [ -z "$NOT_CLONE_REPO" ]; then
    cd ${WORKSPACE}
    info "downloading open_wrapper ..."
    clone "${WRAPPER_BASE_REPO_URL}/open_wrapper" ${OPEN_WRAPPER_PATH} ${OPEN_WRAPPER_CLONE_BRANCH}

    info "downloading common cuda_sdk_configs ..."
    if [ -z "$CONFIGS_TAG" ]; then
      CONFIGS_TAG="${LIB_VERSION}+ppu${RELEASE_VERSION}"
    fi
    clone "${CONFIG_BASE_REPO_URL}/${CUDA_SDK_CONFIGS_REPO}" "${WORKSPACE}/cuda_sdk_configs" "${CONFIGS_TAG}"
    mv ${WORKSPACE}/cuda_sdk_configs/configs ${OPEN_WRAPPER_PATH}
    mv ${WORKSPACE}/cuda_sdk_configs/magician ${OPEN_WRAPPER_PATH}
    rm -rf ${WORKSPACE}/cuda_sdk_configs

    info "downloading depending cuda_sdk_configs ..."
    if [ -z "$DEP_CONFIGS_TAG" ]; then
      DEP_CONFIGS_TAG="${LIB_DEP_SDK_VERSION%.*}+ppu${DEP_RELEASE_VERSION}"
    fi

    clone "${CONFIG_BASE_REPO_URL}/${CUDA_SDK_CONFIGS_REPO}" "${WORKSPACE}/cuda_sdk_configs" "${DEP_CONFIGS_TAG}"
    cp -rn ${WORKSPACE}/cuda_sdk_configs/configs ${OPEN_WRAPPER_PATH}
    cp -rn ${WORKSPACE}/cuda_sdk_configs/magician ${OPEN_WRAPPER_PATH}
    rm -rf ${WORKSPACE}/cuda_sdk_configs

    LIB_VERSION_WITH_DEP="$(get_lib_version_with_dep)"
    info lib version with depending API: $LIB_VERSION_WITH_DEP
    get_lib_list_by_section "${OPEN_WRAPPER_PATH}/configs/lib_version_${LIB_NAME}.ini" all_libs
    print_standalone_libs all_libs $LIB_VERSION_WITH_DEP LIB_VERSION_SUPPORTED
    if [ -z "$LIB_VERSION_SUPPORTED" ]; then
      error $LIB_VERSION_WITH_DEP is not supported
    fi

    info "downloading common cuda_sdk_configs for specified version..."
    # only for internel use
    if [ -n "${VERSION_CONFIG_PATH}" ] && [ -s "$VERSION_CONFIG_PATH" ]; then
      info "using version configs that user provides."
      cp -r ${VERSION_CONFIG_PATH}/${LIB_DEP_SDK_VERSION} ${OPEN_WRAPPER_PATH}/configs
      cp -r ${VERSION_CONFIG_PATH}/${LIB_VERSION_WITH_DEP} ${OPEN_WRAPPER_PATH}/configs
    fi
  fi

  info "downloading cuda_sdk_files ..."
  if [[ -n "${CUDA_SDK_FILES_PATH}" ]]; then
    echo "skip download sdk files, use CUDA_SDK_FILES_PATH=${CUDA_SDK_FILES_PATH}"
  else
    curl -o ${OPEN_WRAPPER_PATH}/magician/cuda_redist_downloader.py ${DOWNLOADER_BASE_URL}/cuda_redist_downloader.py

    ver="${LIB_DEP_SDK_VERSION#*-}"
    CMD="python ${WORKSPACE}/open_wrapper/magician/cuda_redist_downloader.py $ver -o ${WORKSPACE}/cuda_sdk_files --components cuda"
    info "${CMD}"
    eval "${CMD}"
    CMD="python ${WORKSPACE}/open_wrapper/magician/cuda_redist_downloader.py --${LIB_NAME} ${LIB_VERSION#*-} -o ${WORKSPACE}/cuda_sdk_files --components ${LIB_NAME}"
    info "${CMD}"
    eval "${CMD}"
  fi

  OUTPUT_DIR="${OPEN_WRAPPER_PATH}/build/Output/${LIB_VERSION_WITH_DEP}"

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
