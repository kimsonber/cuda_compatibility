from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, IO
from folder_info import (
    FolderInfo,
    LibInfo,
)
import argparse
import os
import configparser
import shutil
from utils import exec_command, copy_files, copy_file, touch_file, append_file
import json


def get_major_minor_version(full_version: str) -> Tuple[int, int]:
    last = full_version.strip().split("-")[-1]
    major_s, minor_s = last.split(".")[:2]
    return (int(major_s), int(minor_s))


class CudaSdkInfo(object):
    def __init__(self, full_version: str) -> None:
        version = get_major_minor_version(full_version)
        self._cuda_major: int = version[0]
        self._cuda_minor: int = version[1]
        print(f"version is {self._cuda_major}.{self._cuda_minor}")

    @property
    def cuda_major(self) -> int:
        return self._cuda_major

    @property
    def cuda_minor(self) -> int:
        return self._cuda_minor


def generate_api_wrapper_src(
    new_wrapper_config_path: str,
    new_wrapper_output_path: str,
    lib_name: str,
    cuda_sdk_info: CudaSdkInfo,
    wrapper_indexs: List[int],
    lib_install_dir: Optional[str] = None,
    new_wrapper_insts_file: Optional[IO] = None,
    root_paths_map: Optional[Dict[str, str]] = None,
) -> None:
    api_wrapper_src_path = os.path.join(new_wrapper_output_path, lib_name)
    cuda_ver_str = f"{cuda_sdk_info.cuda_major}.{cuda_sdk_info.cuda_minor}.1"
    json_files = [
        f"{new_wrapper_config_path}/{lib_name}{index_suffix}_{cuda_ver_str}_config.yaml"
        for index_suffix in [
            "" if index == 0 else f"_{index}" for index in wrapper_indexs
        ]
    ]
    json_files_str = " ".join(json_files)
    root_path_str = ";".join([f"\\{k}:{v}" for k, v in root_paths_map.items()])
    root_path_str = f' --root-paths "{root_path_str}"' if root_path_str else ""
    command = (
        f"cd {new_wrapper_output_path} && api-wrapper-generator {json_files_str} --output-dir {api_wrapper_src_path} --install-dir {lib_install_dir}{root_path_str}"
    )
    print(command)
    if new_wrapper_insts_file:
        new_wrapper_insts_file.write(command + "\n")
    exec_command(command, exit_failed=True, use_shell=True)


def generate_api_wrapper_lib(
    api_wrapper_output_path: str,
    lib_name: str,
    should_install: bool,
    make_target: str = "all",
    new_wrapper_insts_file: Optional[IO] = None,
) -> None:
    api_wrapper_src_path = os.path.join(api_wrapper_output_path, lib_name)
    install_prefix = ""
    if should_install:
        install_prefix = "install-"
    command = f"cd {api_wrapper_src_path} && make {install_prefix}{make_target}"
    print(command)
    if new_wrapper_insts_file:
        new_wrapper_insts_file.write(command + "\n")
    exec_command(command, exit_failed=True, use_shell=True)

def auto_patch_header_files_before(dstDir: str, config_dir: str, cuda_sdk_info: CudaSdkInfo, src_path: str) -> None:
    CUDA_MAJOR = str(cuda_sdk_info.cuda_major)
    CUDA_MINOR = str(cuda_sdk_info.cuda_minor)
    config_file = os.path.join(config_dir, "config", "config.json")
    addfile_config_path = os.path.join(config_dir, "addfile_config_before")
    addfile_config_file = os.path.join(addfile_config_path, "config.json")
    hggc_include_path = os.path.join(src_path, "include")
    command = (
        "file_wrapper "
        + " --version "
        + CUDA_MAJOR
        + "."
        + CUDA_MINOR
        + " --rootdir "
        + dstDir
        + " --config "
        + config_file
        + " --addfile-config "
        + addfile_config_file
        + " --addfile-path "
        + addfile_config_path
        + " "
        + hggc_include_path
    )
    exec_command(command, exit_failed=True)


def auto_patch_header_files_after(dstDir: str, config_dir: str, binary_config: str, cuda_sdk_info: CudaSdkInfo, src_path: str) -> None:
    CUDA_MAJOR = str(cuda_sdk_info.cuda_major)
    CUDA_MINOR = str(cuda_sdk_info.cuda_minor)
    addfile_config_path = os.path.join(config_dir, "addfile_config_after")
    addfile_config_file = os.path.join(addfile_config_path, "config.json")
    command = (
        "file_wrapper "
        + " --version "
        + CUDA_MAJOR
        + "."
        + CUDA_MINOR
        + " --rootdir "
        + dstDir
        + " --addfile-config "
        + addfile_config_file
        + " --addfile-path "
        + addfile_config_path
        + " "
        + binary_config
        + " "
        + src_path
    )
    exec_command(command, exit_failed=True)


def find_in_lib(sec_name: str, folder_info: FolderInfo) -> Tuple[bool, Optional[LibInfo]]:
    for lib_info in folder_info.libraries:
        if sec_name + ".so" in lib_info.name:
            return True, lib_info
    print(f"Skipped dynamic library lib{sec_name}.so\n")
    return False, None


def find_in_static_lib(sec_name: str, folder_info: FolderInfo) -> Optional[str]:
    for lib_name in folder_info.libraries_static.keys():
        if "lib" + sec_name + "_static.a" == lib_name:
            return lib_name
    return None


def find_in_static_irregular_lib(config: configparser.ConfigParser, lib_name: str, folder_info: FolderInfo) -> Optional[str]:
    irregular_static_lib_name = config.get(lib_name, "source_static_lib", fallback=None)
    if (
        irregular_static_lib_name
        and irregular_static_lib_name in folder_info.libraries_static_irregular.keys()
    ):
        return irregular_static_lib_name
    return None

def generate_extras(OutputPath: str, cuda_sdk_info: CudaSdkInfo, config: configparser.ConfigParser) -> None:
    lib_path = os.path.join(OutputPath, "lib64")
    stub_path = os.path.join(OutputPath, "lib64", "stubs")
    os.makedirs(stub_path)
    stub_files = ["libnvidia-ml.so", "libcuda.so", "libnvrtc.so"]
    stub_files_version = ["nvJitLink"]

    for file in stub_files:
        copy_file(os.path.join(lib_path, file), os.path.join(stub_path, file))

    for file in stub_files_version:
        since_cuda_ver = config.get(file, "since_cuda_ver", fallback=None)
        if since_cuda_ver:
            cuda_version_install = (
                cuda_sdk_info.cuda_major * 10 + cuda_sdk_info.cuda_minor
            )
            ver = get_major_minor_version(since_cuda_ver)
            since_cuda_ver_num = ver[0] * 10 + ver[1]
            if cuda_version_install < since_cuda_ver_num:
                print(
                    f"Skipped stub library {file} by version: {cuda_version_install} < {since_cuda_ver}"
                )
                continue
        lib_name = config.get(file, "source_lib", fallback=None)
        copy_file(os.path.join(lib_path, lib_name), os.path.join(stub_path, lib_name))

    copy_file(
        os.path.join(lib_path, "libcuda.so"), os.path.join(lib_path, "libcuda.so.1")
    )
    copy_file(
        os.path.join(lib_path, "libnvidia-ml.so"),
        os.path.join(lib_path, "libnvidia-ml.so.1"),
    )

    for file in os.listdir(lib_path):
        if file.startswith("libcupti"):
            copy_file(
                os.path.join(lib_path, file),
                os.path.join(OutputPath, "extras", "CUPTI", "lib64"),
            )
        if file.startswith("libnvvm"):
            copy_file(
                os.path.join(lib_path, file), os.path.join(OutputPath, "nvvm", "lib64")
            )
        if file.startswith("libcheckpoint"):
            copy_file(
                os.path.join(lib_path, file),
                os.path.join(OutputPath, "extras", "CUPTI", "lib64"),
            )
        if file.startswith("libnvperf"):
            copy_file(
                os.path.join(lib_path, file),
                os.path.join(OutputPath, "extras", "CUPTI", "lib64"),
            )
        if file.startswith("libpcsamplingutil"):
            copy_file(
                os.path.join(lib_path, file),
                os.path.join(OutputPath, "extras", "CUPTI", "lib64"),
            )


# Touch an libcusolver_lapack_static.a to solve compilation dependency issues
def generate_internal_static_lib(OutputPath: str, folder_info: FolderInfo) -> None:
    for lib_name, generated in folder_info.libraries_static.items():
        if not generated:
            print(f"generate an internal lib: {lib_name}")
            cmd = "ar rcs " + os.path.join(OutputPath, "lib64", lib_name)
            exec_command(cmd, exit_failed=True, suppress_log=False, use_shell=True)

    for lib_name_irregular, generated in folder_info.libraries_static_irregular.items():
        if not generated:
            print(f"generate an internal lib: {lib_name_irregular}")
            cmd = "ar rcs " + os.path.join(OutputPath, "lib64", lib_name_irregular)
            exec_command(cmd, exit_failed=True, suppress_log=False, use_shell=True)

def remove_path(path_str):
    path = Path(path_str)
    if not path.exists():
        return
    if path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cuda_version", help="Specify Cuda Version")
    parser.add_argument("--ppu", help="Specify PPU SDK Path")
    parser.add_argument("--output", help="Specify Output Directory")
    parser.add_argument("--config_dir_path", help="Specify config dir path")
    parser.add_argument("--gcc", default='gcc', help="Specify compiler")
    parser.add_argument("--sdk_src_path", help="Specify sdk source path")

    args = parser.parse_args()

    # input path check
    cuda_version = args.cuda_version if args.cuda_version is not None else ""
    ppu_path = os.path.abspath(args.ppu) if args.ppu is not None else ""
    output_path = args.output if args.output is not None else ""
    config_dir_path = (
        os.path.abspath(args.config_dir_path)
        if args.config_dir_path is not None
        else ""
    )
    lib_config_path = os.path.abspath(
        os.path.join(config_dir_path, "api_config", "config.txt")
    )
    private_header_path = os.path.abspath(
        os.path.join(config_dir_path, "api_config", "PrivateHeader")
    )
    api_wrapper_config_path = os.path.abspath(
        os.path.join(config_dir_path, cuda_version, "new_wrapper")
    )
    # args.sdk_src_path can be None

    if not cuda_version:
        print("Need specify cuda version, like cuda-13.0.")
        exit(1)

    if not ppu_path or not os.path.exists(ppu_path):
        print("Need to specify config dir path.")
        exit(1)

    if not output_path:
        print("Need specify output dir.")
        exit(1)

    if not config_dir_path or not os.path.exists(config_dir_path):
        print("Need to specify config dir path.")
        exit(1)

    if not os.path.exists(lib_config_path):
        print("Need configuration file in Config dir path.")
        exit(1)

    if not os.path.exists(private_header_path):
        print("Need private_header dir in Config dir path.")
        exit(1)

    if not os.path.exists(api_wrapper_config_path):
        print("Need wrapper config dir in Config dir path.")
        exit(0)

    # arch check
    arch = os.getenv("PPU_TARGET_ARCH", "x86_64")
    if arch != "x86_64" and arch != "aarch64":
        print("only x86_64 and aarch64 is legal!")
        exit(1)

    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    os.makedirs(output_path)

    config = configparser.ConfigParser()
    config.read(lib_config_path)

    if args.sdk_src_path:
        folder_config_path = os.path.join(
            config_dir_path, cuda_version, "FolderInfoCfg.json"
        )
    else:
        folder_config_path = os.path.join(
            config_dir_path, cuda_version, "FolderInfoCfgAbsPath.json"
        )

    folder_info = None
    with open(folder_config_path, "r", encoding="utf-8") as f:
        folder_info = FolderInfo.load(json.load(f), args.sdk_src_path)

    folder_info.copy_files(output_path)
    folder_info.folder_analyze(private_header_path, output_path)

    cuda_sdk_info = CudaSdkInfo(cuda_version)

    auto_patch_header_files_before(
        os.path.join(output_path, "include"),
        os.path.join(config_dir_path, "patch_config"),
        cuda_sdk_info,
        ppu_path,
    )

    # prepare for api-wrapper-generator
    api_wrapper_output_path = os.path.join(output_path, "new_wrapper")
    if not os.path.exists(api_wrapper_output_path):
        os.makedirs(api_wrapper_output_path)

    new_wrapper_insts_file_path = os.path.join(output_path, "new_wrapper_insts.txt")
    new_wrapper_insts_file = open(new_wrapper_insts_file_path, "w")

    root_paths_map = {
        "$config": os.path.join(config_dir_path, "api_config"),
        "$ppu": os.path.abspath(ppu_path),
        "$lib1": os.path.abspath(output_path),
        "$lib2": os.path.abspath(output_path),
        "$lib3": os.path.abspath(output_path),
        "$lib4": os.path.abspath(output_path),
        "$output": os.path.abspath(output_path),
    }

    ad_header_path = os.path.join(output_path, "targets", "x86_64-linux", "include")
    if arch == "aarch64":
        ad_header_path = os.path.join(output_path, "targets", "sbsa-linux", "include")

    # add auto-generated cuda_ad.h when available
    ad_header_cuda_ad = os.path.join(ad_header_path, "cuda_ad.h")
    if os.path.exists(ad_header_cuda_ad):
        print(f"cuda_ad.h is available: {ad_header_cuda_ad}")
        folder_info.add_file(ad_header_path, "cuda_ad.h", None, output_path)
        root_paths_map["$cu_ad"] = os.path.abspath(ad_header_path)
    else:
        print(f"cuda_ad.h is not available: {ad_header_cuda_ad}")
        exit(1)

    # iterate libs for calling api-wrapper-generator
    for lib_name in config.sections():
        since_cuda_ver = config.get(lib_name, "since_cuda_ver", fallback=None)
        if since_cuda_ver:
            cuda_version_install = (
                cuda_sdk_info.cuda_major * 10 + cuda_sdk_info.cuda_minor
            )
            ver = get_major_minor_version(since_cuda_ver)
            since_cuda_ver_num = ver[0] * 10 + ver[1]
            if cuda_version_install < since_cuda_ver_num:
                print(
                    f"Skipped stub library {lib_name} by version: {cuda_version_install} < {since_cuda_ver}"
                )
                continue

        found_in_lib, lib = find_in_lib(lib_name, folder_info)
        static_lib_name = find_in_static_lib(lib_name, folder_info)
        irregular_static_lib_name = find_in_static_irregular_lib(
            config, lib_name, folder_info
        )
        if found_in_lib or static_lib_name or irregular_static_lib_name:
            lib_config = config[lib_name]

            lib_output_path = os.path.join(output_path, "lib64")
            lib_path = "lib_path"
            if lib_path in lib_config:
                lib_output_path = os.path.join(output_path, lib_config[lib_path])

            if not os.path.exists(lib_output_path):
                os.makedirs(lib_output_path)

            wrapper_indexs = []
            for index in range(0, 11):
                cuda_header_key = f"cuda_header{str(index) if index > 0 else ''}"
                if cuda_header_key in lib_config:
                    wrapper_indexs.append(index)

            generate_api_wrapper_src(
                api_wrapper_config_path,
                api_wrapper_output_path,
                lib_name,
                cuda_sdk_info,
                wrapper_indexs,
                lib_install_dir=lib_output_path,
                new_wrapper_insts_file=new_wrapper_insts_file,
                root_paths_map=root_paths_map,
            )

            if found_in_lib:
                generate_api_wrapper_lib(
                    api_wrapper_output_path,
                    lib_name,
                    True,
                    "shared",
                    new_wrapper_insts_file,
                )
            if static_lib_name or irregular_static_lib_name:
                generate_api_wrapper_lib(
                    api_wrapper_output_path,
                    lib_name,
                    True,
                    "static",
                    new_wrapper_insts_file,
                )
                if static_lib_name:
                    folder_info.libraries_static[static_lib_name] = True
                elif irregular_static_lib_name:
                    folder_info.libraries_static_irregular[
                        irregular_static_lib_name
                    ] = True

    new_wrapper_insts_file.close()

    # remove temp files of api wrapper
    remove_path(api_wrapper_output_path)
    remove_path(new_wrapper_insts_file_path)
    auto_patch_header_files_after(
        output_path,
        os.path.join(config_dir_path, "patch_config"),
        os.path.join(config_dir_path, "binary_config"),
        cuda_sdk_info,
        ppu_path,
    )
    generate_internal_static_lib(output_path, folder_info)

    try:
        generate_extras(output_path, cuda_sdk_info, config)
    except Exception as e:
        print(f"Caught Exception:{e}")
