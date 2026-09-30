#include "wrapper_gen.hpp"
#include <linux/limits.h>
#include <map>
#include <set>
#include <string>
#include <vector>
#include <limits.h>
#include <libgen.h>
#include <sys/utsname.h>
#include <iostream>
#include "help_data.h"
#include <fstream>
#include <algorithm>
#include <unordered_set>
#include <cstring>
#include <dlfcn.h>
#include "utils.h"

#define STR1(x) #x
#define STR2(x) STR1(x)
#define CUDA_VER_MAJOR_STR STR2(CUDA_VER_MAJOR)
#define CUDA_VER_MINOR_STR STR2(CUDA_VER_MINOR)
#define CUDA_VER_BUILD_STR STR2(CUDA_VER_BUILD)
#define CUDA_VERSION_STR STR2(CUDA_VERSION)

using namespace Wrapper;

static int OriArgc;
static char **OriArgv;

static void printVersion() {
  std::cout << "nvcc: NVIDIA (R) Cuda compiler driver" << std::endl
            << "Copyright (c) 2005-2024 NVIDIA Corporation" << std::endl
            << "Built on Thu_Jun__6_02:18:23_PDT_2024" << std::endl
            << "Cuda compilation tools, release " << CUDA_VER_MAJOR_STR << "."
            << CUDA_VER_MINOR_STR << ", V" << CUDA_VER_MAJOR_STR << "."
            << CUDA_VER_MINOR_STR << "." << CUDA_VER_BUILD_STR << std::endl;
}

class NVCCArgHandler : public ArgHandlerBase {

  struct ParseResult {
    std::string Key;
    std::string Value;
    int TokenConsumed = 0;
  };

  std::map<std::string, std::string> ArchMap;
  std::string WrapperMode;

  bool PrintHGCCOnly = false;
  std::string Arch;
  std::set<std::string> Codes;
  std::set<GenCodeValue> GenCodes;
  bool IsCUFile = false;
  bool IsRDC = false;
  bool Verbose = false;
  bool NoHGGCEmbedBC = false;
  std::string Target;
  std::string CudaRoot;
  std::string RealCudaRoot;
  bool ListArch = false;
  bool ListCode = false;
  bool PrintHelp = false;
  bool PrintVer = false;
  bool HostRelocatableLink = false;
  bool DeviceDebug = false;
  bool DoptExplicit = false;
  std::string DoptValue;

  // return ture if Res can be dealt as arch options
  bool dealArchArgs(ParseResult &Res, std::vector<std::string> &args);

  ParseResult parseKV(const char **argv) const;

  void appendArchArgs(std::vector<std::string> &args);
  void appendMacroDefs(std::vector<std::string> &args);
  void appendLibs(std::vector<std::string> &args);
  void appendIncludes(std::vector<std::string> &args);
  void appendDefaultOutputFile(std::vector<std::string> &args);
  std::string mapArchToPPUArch(const std::string &Arch) const;

public:
  NVCCArgHandler();

  std::string locateTarget() override;

  int dealUnknownArg(std::vector<std::string> &args,
                     const char **argv) override;
  int dealUnknownValueMapping(std::vector<std::string> &args,
                              const std::string &opt_src,
                              const std::string &opt_dst,
                              const char *argv) override;
  void beforeExec(std::vector<std::string> &args) override;

  void handleReturnCode(int code) override;

private:
  bool HasOutputOption = false;

  std::string getDefaultOutputName(const std::string &inputFile, const std::string &compilePhase) const;
};

void NVCCArgHandler::handleReturnCode(int code) {
  if (code == 0) {
    ArgHandlerBase::handleReturnCode(code);
    return;
  }
  if (char *env = std::getenv("NVCC_FAIL_LOG")) {
    std::string LogName = std::string(env) + "_" + std::to_string(getpid());
    std::ofstream OFS(LogName, std::ios::app | std::ios::ate);
    if (const char *AppendEnv = getenv("NVCC_PREPEND_FLAGS")) {
      std::vector<std::string> AppendArgs;
      parseArgsFromStr(AppendEnv, AppendArgs);
      OFS << "PREPEND ENV: ";
      for (const auto &A : AppendArgs) {
        OFS << "\'" << A << "\' ";
      }
      OFS << "\n";
    }
    for (int I = 0; I < OriArgc; ++I) {
      OFS << "'";
      OFS << OriArgv[I];
      OFS << " ";
      OFS << "'";
    }
    OFS << "\n";
    if (const char *AppendEnv = getenv("NVCC_APPEND_FLAGS")) {
      std::vector<std::string> AppendArgs;
      parseArgsFromStr(AppendEnv, AppendArgs);
      OFS << "APPEND ENV: ";
      for (const auto &A : AppendArgs) {
        OFS << "\'" << A << "\'";
      }
      OFS << "\n";
    }
    OFS.close();
  } else {
    ArgHandlerBase::handleReturnCode(code);
  }

  // nvcc always exit with 1 for error
  exit(1);
}

NVCCArgHandler::NVCCArgHandler() {
  std::string ExecName = OriArgv[0];
  std::string ExePath = getExecutablePath();
  RealCudaRoot = dirname(dirname(&ExePath[0]));
  // If the exec specify the relative or absolute path, use the path;
  // else find the absolute path.
  if (ExecName != "nvcc") {
    CudaRoot = dirname(dirname(&ExecName[0]));
    if (!startsWith(CudaRoot, "/")) {
      CudaRoot = "/proc/self/cwd/" + CudaRoot;
    }
  } else {
    CudaRoot = RealCudaRoot;
  }

  utsname UInfo;
  if (uname(&UInfo) == 0) {
    Target = std::string(UInfo.machine) + "-linux";
  } else {
    perror("uname");
    exit(1);
  }
  // load config
  ArchMap = Wrapper::loadArchMapConfig(CudaRoot + "/bin/nvcc_wrapper.cfg", WrapperMode);
}

std::string NVCCArgHandler::locateTarget() {
  return CudaRoot + "/bin/" + Config::TARGET_EXE;
}

NVCCArgHandler::ParseResult NVCCArgHandler::parseKV(const char **Argv) const {
  ParseResult Res;
  if (!Argv || !*Argv || !startsWith(*Argv, "-")) {
    return Res;
  }

  std::string ArgStr = std::string(*Argv);
  size_t Pos = ArgStr.find_first_of("=");
  if (Pos != std::string::npos) {
    Res.Key = ArgStr.substr(0, Pos);
    Res.Value = ArgStr.substr(Pos + 1);
    ++Res.TokenConsumed;
    return Res;
  } else {
    Res.Key = ArgStr;
    ++Res.TokenConsumed;
    ++Argv;
    if (!Argv || !*Argv) {
      return Res;
    }
    if (startsWith(*Argv, "-")) {
      // next token is another arg
      return Res;
    }
    Res.Value = *Argv;
    ++Res.TokenConsumed;
    return Res;
  }
}

bool NVCCArgHandler::dealArchArgs(ParseResult &Res,
                                  std::vector<std::string> &Args) {
  // TODO: need some check?
  if (Res.Key == "--gpu-architecture" || Res.Key == "-arch") {
    // overwrite early one
    Arch = Res.Value;
    return true;
  }
  if (Res.Key == "--gpu-code" || Res.Key == "-code") {
    splitString(Res.Value, ",", Codes);
    return true;
  }

  if (Res.Key == "--generate-code" || Res.Key == "-gencode") {
    auto newCodes = GenCodeDecoder::GetGenCodeValues(Res.Key, Res.Value, Args);
    GenCodes.insert(newCodes.begin(), newCodes.end());
    if (!GenCodes.empty()) {
      return true;
    }
  }

  return false;
}

int NVCCArgHandler::dealUnknownArg(std::vector<std::string> &Args,
                                   const char **Argv) {
  ParseResult Res = parseKV(Argv);
  if (Res.Key.empty()) {
    if (Argv && *Argv) {
      // this is input file
      std::string FileName(*Argv);
      if (endsWith(FileName, ".cu")) {
        IsCUFile = true;
      }
    }
    return ArgHandlerBase::dealUnknownArg(Args, Argv);
  }

  if (startsWith(Res.Key, "-D") || startsWith(Res.Key, "-U")) {
    // definition, do not split it, pass it as a whole
    Args.push_back(*Argv);
    return 1;
  }

  if (Res.Key == "--device-debug" || Res.Key == "-G") {
    DeviceDebug = true;
    Args.push_back("-G");
    Args.push_back("-D__CUDACC_DEBUG__");
    return 1;
  }

  if (Res.Key == "--dopt" || Res.Key == "-dopt") {
    if (Res.Value.empty()) {
      std::cerr << "Missing value for option: " << Res.Key << std::endl;
      return 0;
    }
    DoptExplicit = true;
    DoptValue = Res.Value;
    std::string mappedValue = DoptValue;
    if (DoptValue == "off") {
      mappedValue = "0";
    } else if (DoptValue == "on") {
      mappedValue = "3";
    }
    Args.push_back("-dopt");
    Args.push_back(mappedValue);
    return Res.TokenConsumed;
  }

  if (Res.Key == "--cudart" || Res.Key == "-cudart") {
    if (Res.Value == "shared") {
      Args.push_back("-lcudart");
    } else if (Res.Value == "static") {
      Args.push_back("-lcudart_static");
    } else if (Res.Value == "none") {
    } else {
      std::cerr << "nvcc fatal   : Value '" << Res.Value << "' is not defined for option 'cudart'" << std::endl;
      exit(1);
    }
    return Res.TokenConsumed;
  }

  if (Res.Key == "-o" || Res.Key == "--output-file") {
    HasOutputOption = true;
    Args.push_back(Res.Key);
    Args.push_back(Res.Value);
    return Res.TokenConsumed;
  }

  if (Res.Key == "-x" || Res.Key == "--x") {
    if (Res.Value == "cu") {
      IsCUFile = true;
    }
  }

  if (Res.Key == "-v" || Res.Key == "--verbose" || Res.Key == "-dryrun" ||
      Res.Key == "--dryrun") {
    Verbose = true;
  }

  if (((Res.Key == "--relocatable-device-code" || Res.Key == "-rdc") &&
       Res.Value == "true") ||
      Res.Key == "--device-c" || Res.Key == "-dc") {
    IsRDC = true;
  }

  if (Res.Key == "-V" || Res.Key == "--version") {
    PrintVer = true;
  }

  if (Res.Key == "--print-hgcc-only") {
    PrintHGCCOnly = true;
    Res.TokenConsumed = 1;
    return Res.TokenConsumed;
  }

  if (Res.Key == "--host-relocatable-link" || Res.Key == "--relocatable-link" || Res.Key == "-r" ) {
    HostRelocatableLink = true;
    Args.push_back("-r");
    return Res.TokenConsumed;
  }

  if (Res.Key == "--list-gpu-code" || Res.Key == "-code-ls") {
    ListCode = true;
  }

  if (Res.Key == "--list-gpu-arch" || Res.Key == "-arch-ls") {
    ListArch = true;
  }

  if (Res.Key == "--no-hggc-embed-bc" || Res.Key == "-no-hggc-embed-bc") {
    std::cerr << "nvcc wrapper warning : --no-hggc-embed-bc option is "
                 "deprecated and will be ignored in future version"
              << std::endl;
    NoHGGCEmbedBC = true;
    return 1;
  }

  if (Res.Key == "--help" || Res.Key == "-h") {
    PrintHelp = true;
  }

  if (dealArchArgs(Res, Args)) {
    return Res.TokenConsumed;
  }

  // just pass the unknown argument to hgcc
  return ArgHandlerBase::dealUnknownArg(Args, Argv);
}

int NVCCArgHandler::dealUnknownValueMapping(std::vector<std::string> &Args,
                                            const std::string &OptSrc,
                                            const std::string &OptDst,
                                            const char *Argv) {
  if (!Argv || !*Argv) {
    return ArgHandlerBase::dealUnknownValueMapping(Args, OptSrc, OptDst, Argv);
  }

  if (OptSrc == "--nvlink-options" || OptSrc == "-Xnvlink") {
    // For suppress-stack-size-warning, we need to emit -mllvm prefix
    // instead of --hglink-options to pass it through to LLVM
    const char *ArgvTmp[] = {
        Argv,
        NULL
    };
    ParseResult Res = parseKV(ArgvTmp);
    if (Res.Key == "-suppress-stack-size-warning" || Res.Key == "--suppress-stack-size-warning") {
      Args.push_back("-mllvm");
      Args.push_back("-ppu-suppress-stack-size-warning");
      return Res.TokenConsumed;
    }

    return ArgHandlerBase::dealUnknownValueMapping(Args, OptSrc, OptDst, Argv);
  }

  if (OptSrc == "-Xptxas" || OptSrc == "--ptxas-options") {
    const char *ArgvTmp[] = {
        Argv,
        NULL
    };
    ParseResult Res = parseKV(ArgvTmp);
    if (Res.Key == "-maxntid" || Res.Key == "--maxntid") {
      Args.push_back(OptDst);
      Args.push_back("-ppu-maxntid=" + Res.Value);
      return Res.TokenConsumed;
    } else if (Res.Key == "-minnctapersm" || Res.Key == "--minnctapersm") {
      Args.push_back(OptDst);
      Args.push_back("-ppu-minblockscu=" + Res.Value);
      return Res.TokenConsumed;
    } else if (Res.Key == "-maxrregcount" || Res.Key == "--maxrregcount") {
      Args.push_back(OptDst);
      Args.push_back("-ppu-max-vreg-count=" + Res.Value);
      return Res.TokenConsumed;
    } else if (Res.Key == "--position-independent-code" || Res.Key == "-pic") {
      return Res.TokenConsumed;
    } else if (Res.Key == "--allow-expensive-optimizations" ||
               Res.Key == "-allow-expensive-optimizations") {
      return Res.TokenConsumed;
    } else if (Res.Key == "--register-usage-level" ||
               Res.Key == "-register-usage-level") {
      return Res.TokenConsumed;
    } else if (Res.Key == "--warning-as-error" || Res.Key == "-Werror") {
      Args.push_back(OptDst);
      Args.push_back("--warning-as-error");
      return Res.TokenConsumed;
    }
    // Not a known -Xptxas option; let caller decide via default_value_mapping
    return 0;
  }

  return ArgHandlerBase::dealUnknownValueMapping(Args, OptSrc, OptDst, Argv);
}

std::string NVCCArgHandler::mapArchToPPUArch(const std::string &Arch) const {
  std::string NormalizedArch = Arch;
  if (endsWith(Arch, "a")) {
    NormalizedArch = Arch.substr(0, Arch.size() - 1);
  }
  if (ArchMap.count(NormalizedArch) > 0) {
    return ArchMap.at(NormalizedArch);
  }
  return "";
}

std::string NVCCArgHandler::getDefaultOutputName(const std::string &inputFile, const std::string &compilePhase) const {
  // Get base name without path
  std::string baseName = inputFile;
  size_t lastSlash = baseName.find_last_of("/\\");
  if (lastSlash != std::string::npos) {
    baseName = baseName.substr(lastSlash + 1);
  }

  // Remove .cu extension
  std::string stem = baseName;
  if (stem.size() > 3 && stem.compare(stem.size() - 3, 3, ".cu") == 0) {
    stem = stem.substr(0, stem.size() - 3);
  }

  return stem + "." + compilePhase;
}

// Helper function to detect compile phase from original argv
static std::string getCompilePhaseFromOriginalArgs(int argc, char *argv[]) {
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg.empty() || arg[0] != '-') continue;

    size_t eqPos = arg.find('=');
    std::string key = (eqPos != std::string::npos) ? arg.substr(0, eqPos) : arg;

    if (key == "-ptx" || key == "--ptx") return "ptx";
    if (key == "-cubin" || key == "--cubin") return "cubin";
    if (key == "-fatbin" || key == "--fatbin") return "fatbin";
    if (key == "-c" || key == "-dc" || key == "--device-c") return "o";
  }
  return "";
}

void NVCCArgHandler::appendDefaultOutputFile(std::vector<std::string> &Args) {
  if (HasOutputOption) {
    return;
  }

  std::string phase = getCompilePhaseFromOriginalArgs(OriArgc, OriArgv);
  if (phase.empty()) {
    return;
  }

  std::vector<std::string> cuFiles;
  for (const auto &arg : Args) {
    if (endsWith(arg, ".cu")) {
      cuFiles.push_back(arg);
    }
  }

  if (cuFiles.empty()) {
    return;
  }

  if (cuFiles.size() > 1 && !phase.empty()) {
    return;
  }

  Args.push_back("-o");
  Args.push_back(getDefaultOutputName(cuFiles[0], phase));
}

void NVCCArgHandler::appendArchArgs(std::vector<std::string> &Args) {
  // Direct pass-through for -arch=native
  if (Arch == "native") {
    Args.push_back("-arch=native");
    return;
  }

  if (!Codes.empty() && Arch.empty()) {
    std::cerr << "nvcc fatal   : -arch option not specified" << std::endl;
    exit(1);
  }

  if (!Codes.empty() && !GenCodeDecoder::isVirtualArch(Arch)) {
    std::cerr << "nvcc fatal   : Value of -arch option ('" << Arch
              << "') must be a virtual "
                 "code architecture"
              << std::endl;
    exit(1);
  }

  // add arch specified via -arch & -code
  for (const auto &Code : Codes) {
    GenCodes.insert({Arch, Code});
  }

  // no -code is sepcified, -arch can be a real arch
  if (Codes.empty() && !Arch.empty()) {
    if (!GenCodeDecoder::isVirtualArch(Arch)) {
      GenCodes.insert({GenCodeDecoder::getVirtualArchFromNum(GenCodeDecoder::getArchNum(Arch)), Arch});
    } else {
      GenCodes.insert({Arch, Arch});
    }
  }

  // embed ppu_15 implicitly will cause compilation failure
  bool NoMultiArch = false;
  for (const auto &Arg : Args) {
    if (Arg == "-hgbin" || Arg == "-opt-bc") {
      NoMultiArch = true;
      break;
    }
  }

  bool Dolto = false;
  for (const auto &GenCode : GenCodes) {
    // skip virtual arch if --no-hggc-embed-bc is specified
    if (NoHGGCEmbedBC && GenCodeDecoder::isVirtualArch(GenCode.Code)) {
      continue;
    }
    if (startsWith(GenCode.Code, "lto_")) {
      Dolto = true;
    }
    // TODO: check that arch matches the code
    auto PPUArch = mapArchToPPUArch(GenCode.Code);
    if (!PPUArch.empty()) {
      Args.push_back("-arch=" + mapArchToPPUArch(GenCode.Code));
    }
    if (GenCode.Code == "sm_80" && !NoMultiArch) {
      Args.push_back("-arch=ppu_15");
    }
  }
  if (Dolto) {
    Args.push_back("-dlto");
  }
}

void NVCCArgHandler::appendMacroDefs(std::vector<std::string> &Args) {
  if (IsCUFile) {
    Args.push_back("-Xpreprocess");
    Args.push_back("-D__CUDACC__");
  }
  if (IsRDC) {
    Args.push_back("-Xpreprocess");
    Args.push_back("-D__CUDACC_RDC__");
  }
  Args.push_back("-D__NVCC__");
  Args.push_back(std::string("-D__CUDACC_VER_MAJOR__=") + CUDA_VER_MAJOR_STR);
  Args.push_back(std::string("-D__CUDACC_VER_MINOR__=") + CUDA_VER_MINOR_STR);
  Args.push_back(std::string("-D__CUDACC_VER_BUILD__=") + CUDA_VER_BUILD_STR);
  Args.push_back(std::string("-D__CUDA_API_VER_MAJOR__=") + CUDA_VER_MAJOR_STR);
  Args.push_back(std::string("-D__CUDA_API_VER_MINOR__=") + CUDA_VER_MINOR_STR);
  Args.push_back("-DUSE_HGGC");
}

void NVCCArgHandler::appendLibs(std::vector<std::string> &Args) {
  Args.push_back("-L" + CudaRoot + "/targets/" + Target + "/lib/stubs");
  Args.push_back("-L" + CudaRoot + "/targets/" + Target + "/lib");
  if (!HostRelocatableLink) {
    Args.push_back("-lcudart_static");
    Args.push_back("-lcuda");
  }
  Args.push_back("-lrt");
  Args.push_back("-lpthread");
  Args.push_back("-ldl");
}

void NVCCArgHandler::appendIncludes(std::vector<std::string> &Args) {
  std::vector<std::string> ArgsGrp1, ArgsGrp2;
  ArgsGrp1.push_back("-I" + CudaRoot + "/targets/" + Target +
                 "/include/hgrt/__patch_include__");

  Args.insert(Args.begin()+1, ArgsGrp1.begin(), ArgsGrp1.end());

  ArgsGrp2.push_back("-I" + CudaRoot + "/targets/" + Target + "/include");
  ArgsGrp2.push_back("-isystem");
  ArgsGrp2.push_back(CudaRoot + "/targets/" + Target + "/include/cccl");

  Args.insert(Args.end(), ArgsGrp2.begin(), ArgsGrp2.end());
}

void NVCCArgHandler::beforeExec(std::vector<std::string> &Args) {
  if (WrapperMode == "legacy") {
    void *LegacyCC =
        dlopen((RealCudaRoot + "/lib64/libcc_wrapper.so").c_str(), RTLD_LAZY);
    if (!LegacyCC) {
      std::cerr << "dlopen failed: " << dlerror() << std::endl;
      exit(1);
    }
    using WrapperEntry = int(*)(int, char **);
    auto entry = (WrapperEntry)dlsym(LegacyCC, "wrapper_main");
    setenv("CUDA_VERSION", CUDA_VERSION_STR, 1);
    setenv("CUDA_SDK_ROOT", CudaRoot.c_str(), 1);
    int ret = entry(OriArgc, OriArgv);
    exit(ret);
  }

  char *Env = std::getenv("PPU_OPTION");
  if (Env) {
    std::cout << "PPU_OPTION is only supported for legacy nvcc wrapper! Some "
                 "options are ignored: " << Env
              << std::endl;
  }

  if (PrintVer) {
    printVersion();
    exit(0);
  }

  if (PrintHelp) {
    std::cout << help_data << std::endl;
    exit(0);
  }

  if (ListArch) {
    for (const auto It : ArchMap) {
      if (GenCodeDecoder::isVirtualArch(It.first)) {
        std::cout << It.first << std::endl;
      }
    }
  }

  if (ListCode) {
    for (const auto It : ArchMap) {
      if (GenCodeDecoder::isRealArch(It.first)) {
        std::cout << It.first << std::endl;
      }
    }
  }

  Args.push_back("--compatible-mode");
  Args.push_back("-Xllvm");
  Args.push_back(std::string("-compatible-sdk-version=") + CUDA_VER_MAJOR_STR +
                 CUDA_VER_MINOR_STR);

  appendLibs(Args);
  appendIncludes(Args);
  appendArchArgs(Args);
  appendMacroDefs(Args);
  appendDefaultOutputFile(Args);

  // Apply default dopt value
  if (!DoptExplicit) {
    if (DeviceDebug) {
      Args.push_back("-dopt");
      Args.push_back("0");
    } else {
      Args.push_back("-dopt");
      Args.push_back("3");
   }
  }
  // For arguments with escaped double quotes \", we need to convert them to regular double quotes "
  // for hgcc (which receives args directly via execvp).
  std::vector<std::string> OriginalArgs = Args;
  for (auto &Arg : Args) {
    size_t pos = 0;
    while ((pos = Arg.find("\\\"", pos)) != std::string::npos) {
      Arg.replace(pos, 2, "\"");
      pos += 1;
    }
  }

  // But for --print-hgcc-only output, we want to preserve \\" so users can
  // copy-paste the command. So we store original args for output.
  if (PrintHGCCOnly) {
    std::cout << "#$ hgcc command: ";
    for (const auto &Arg : OriginalArgs) {
      std::cout << Arg << " ";
    }
    std::cout << std::endl;
    exit(0);
  }

  if (Verbose) {
    // make cmake happy
    std::cerr << "#$ _NVVM_BRANCH_=nvvm" << std::endl;
    std::cerr << "#$ _SPACE_=" << std::endl;
    std::cerr << "#$ _CUDART_=cudart" << std::endl;
    std::cerr << "#$ _HERE_=" << CudaRoot << "/bin" << std::endl;
    std::cerr << "#$ _THERE_=" << CudaRoot << "/bin" << std::endl;
    std::cerr << "#$ _TARGET_SIZE_=" << std::endl;
    std::cerr << "#$ _TARGET_DIR_=" << std::endl;
    std::cerr << "#$ TOP=" << CudaRoot << "/bin/.." << std::endl;
    std::cerr << "#$ NVVMIR_LIBRARY_DIR=" << CudaRoot
              << "/bin/../nvvm/libdevice" << std::endl;
    std::cerr << "#$ INCLUDES= \"-I" << CudaRoot << "/targets/" << Target
              << "/include\"" << std::endl;
    std::cerr << "#$ LIBRARIES= -L" << CudaRoot << "/targets/" << Target
              << "/lib/stubs -L" << CudaRoot << "/targets/" << Target << "/lib"
              << std::endl;
    std::cerr << "#$ CUDAFE_FLAGS=" << std::endl;
    std::cerr << "#$ PTXAS_FLAGS=" << std::endl;
    if (GenCodes.empty()) {
      std::cerr << "-arch compute_52" << std::endl;
    } else {
      for (const auto &GenCode : GenCodes) {
        std::cerr << "-arch " << GenCode.Arch << std::endl;
      }
    }
  }

  if (ListArch || ListCode) {
    exit(0);
  }

  return;
}

ArgHandlerBase *createArgHandler() { return new NVCCArgHandler(); }

static std::vector<std::string> FormatForwardingOptions(
    const std::vector<std::string>& AllArgs) {
  static const std::unordered_set<std::string> ForwardingFlags = {
    "-Xptxas", "--ptxas-options",
    "-Xhglink", "--hglnk-options",
    "-Xllvm", "--llvm-options",
    "-Xpreprocessor", "--preprocessor-options",
  };

  auto ValueHandler = [](const std::string &ValPart,
                         const std::string &OptPart,
                         std::vector<std::string> &NormalizedArgs) {
    std::vector<std::string> Parts = splitString(ValPart, " ,");
    for (size_t i = 0; i < Parts.size(); ++i) {
      NormalizedArgs.emplace_back(OptPart + "=" + Parts[i]);
    }
  };

  std::vector<std::string> NormalizedArgs;

  for (size_t i = 0; i < AllArgs.size(); ++i) {
    std::string Cur{AllArgs[i]};

    // e.g., -Xptxas "-v -O3"
    if (ForwardingFlags.count(Cur) && (i + 1 < AllArgs.size())) {
      std::string OptPart = Cur;
      std::string ValPart = AllArgs[i + 1];
      ValueHandler(ValPart, OptPart, NormalizedArgs);

      ++i;
      continue;
    }

    // e.g., -Xptxas=-v,-O3
    std::size_t Pos = Cur.find('=');
    if (Pos != std::string::npos) {
      std::string OptPart = Cur.substr(0, Pos);
      std::string ValPart = Cur.substr(Pos + 1);
      if (ForwardingFlags.count(OptPart)) {
        ValueHandler(ValPart, OptPart, NormalizedArgs);
      } else {
        NormalizedArgs.emplace_back(Cur);
      }
      continue;
    }

    NormalizedArgs.emplace_back(Cur);
  }

  return NormalizedArgs;
}

int main(int argc, char *argv[]) {
  OriArgc = argc;
  OriArgv = argv;
  auto result = parseArgsFromOptionFile(argc, argv);
  argc = result.first;
  auto NewArgv = std::move(result.second);
  if (!NewArgv) {
    return 1;
  }
  argv = NewArgv.get();
  std::vector<std::string> PrependArgs;
  std::vector<std::string> AppendArgs;
  if (const char *AppendEnv = getenv("NVCC_PREPEND_FLAGS")) {
    parseArgsFromStr(AppendEnv, PrependArgs);
  }
  if (const char *AppendEnv = getenv("NVCC_APPEND_FLAGS")) {
    parseArgsFromStr(AppendEnv, AppendArgs);
  }

  std::vector<std::string> AllArgs;
  AllArgs.emplace_back(argv[0]); // program name
  for (int i = 0; i < PrependArgs.size(); ++i) {
    AllArgs.emplace_back(PrependArgs[i]);
  }

  for (int i = 1; i < argc; ++i) {
    AllArgs.emplace_back(argv[i]);
  }

  for (int i = 0; i < AppendArgs.size(); ++i) {
    AllArgs.emplace_back(AppendArgs[i]);
  }

  // format forwarding options
  std::vector<std::string> NormalizedArgs = FormatForwardingOptions(AllArgs);

  int FullArgc = NormalizedArgs.size();
  std::vector<char*> FullArgv(FullArgc + 1, nullptr);

  int idx = 0;
  for (size_t i = 0; i < NormalizedArgs.size(); ++i) {
    FullArgv[idx++] = &NormalizedArgs[i][0];
  }
  FullArgv[idx++] = nullptr;

  return wrapperMain(FullArgc, &FullArgv[0]);
}
