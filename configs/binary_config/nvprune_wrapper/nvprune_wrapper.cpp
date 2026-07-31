
#include "wrapper_gen.hpp"
#include "help_data.h"
#include "utils.h"
#include <iostream>
#include <libgen.h>
#include <linux/limits.h>
#include <string>
#include <vector>
#include <map>
#include <set>
#include <linux/limits.h>
#include <sys/utsname.h>
#include <cstring>
#include <memory>


using namespace Wrapper;

#define STR1(x) #x
#define STR2(x) STR1(x)
#define CUDA_VER_MAJOR_STR STR2(CUDA_VER_MAJOR)
#define CUDA_VER_MINOR_STR STR2(CUDA_VER_MINOR)
#define CUDA_VER_BUILD_STR STR2(CUDA_VER_BUILD)

static void printVersion() {
  std::cout << "nvprune: NVIDIA (R) prune object or library to one architecture" << std::endl
            << "Copyright (c) 2005-2022 NVIDIA Corporation" << std::endl
            << "Built on Thu_Jun__6_02:18:23_PDT_2024" << std::endl
            << "Cuda compilation tools, release " << CUDA_VER_MAJOR_STR << "."
            << CUDA_VER_MINOR_STR << ", V" << CUDA_VER_MAJOR_STR << "."
            << CUDA_VER_MINOR_STR << "." << CUDA_VER_BUILD_STR << std::endl;
}

class NVpruneArgHandler : public ArgHandlerBase {

  struct ParseResult {
    std::string Key;
    std::string Value;
    int TokenConsumed = 0;
  };
  bool Verbose = false;
  std::string CudaRoot = "";
  std::map<std::string, std::string> ArchMap;

  std::set<GenCodeValue> dealArchArgs(ParseResult &Res, std::vector<std::string> &args);
  ParseResult parseKV(const char **argv) const;
  std::string mapNVTargetToPPUTarget(const std::string& NVTarget);

public:
  NVpruneArgHandler();
  ~NVpruneArgHandler() = default;

  int dealUnknownArg(std::vector<std::string> &args,
                     const char **argv) override;
  int dealUnknownValueMapping(std::vector<std::string> &args,
                              const std::string &opt_src,
                              const std::string &opt_dst,
                              const char *argv) override;
  void beforeExec(std::vector<std::string> &args) override;
};

NVpruneArgHandler::NVpruneArgHandler() {
  std::string ExePath = getExecutablePath();
  std::string ExeParent = dirname(&ExePath[0]);
  // dirname may change the data of ExeParent, make a copy
  CudaRoot = dirname(&ExeParent[0]);
  std::string WrapperMode;
  ArchMap = Wrapper::loadArchMapConfig(CudaRoot + "/bin/nvcc_wrapper.cfg", WrapperMode);
}

std::string NVpruneArgHandler::mapNVTargetToPPUTarget(const std::string& NVTarget) {

  auto iter = ArchMap.find(GenCodeDecoder::getRealArchFromNum(GenCodeDecoder::getArchNum(NVTarget)));
  if (iter == ArchMap.end() || GenCodeDecoder::getArchNum(iter->second) == "10") {
    return GenCodeDecoder::isRealArch(NVTarget) ? ("hggc-ppu-ppu001") : ("hgvm-ppu-ppu001");
  }

  return GenCodeDecoder::isRealArch(NVTarget) ?
        ("hggc-ppu-ppu00" + GenCodeDecoder::getArchNum(iter->second)) :
        ("hgvm-ppu-ppu00" + GenCodeDecoder::getArchNum(iter->second));
}

int NVpruneArgHandler::dealUnknownArg(std::vector<std::string> &Args,
                    const char **Argv) {
  ParseResult Res = parseKV(Argv);
  if (Res.Key.empty()) {
    return ArgHandlerBase::dealUnknownArg(Args, Argv);
  }

  if (Res.Key == "-V" || Res.Key == "--version") {
    printVersion();
    exit(EXIT_SUCCESS);
  }

  if (Res.Key == "--help" || Res.Key == "-h") {
    std::cout << help_data << std::endl;
    exit(EXIT_SUCCESS);
  }

  if (Res.Key == "--verbose" || Res.Key == "-v") {
    Verbose = true;
  }

  if (Res.Key == "-arch" || Res.Key == "--arch") {
    Args.push_back(Res.Key);
    Args.push_back(mapNVTargetToPPUTarget(Res.Value));
    // multi arch support for sm_80
    if (Res.Value  == "sm_80") {
      Args.push_back(Res.Key);
      Args.push_back(mapNVTargetToPPUTarget("sm_89"));
    }
    return Res.TokenConsumed;
  }

  if (Res.Key == "--generate-code" || Res.Key == "-gencode") {
    std::set<GenCodeValue> GenCodes = GenCodeDecoder::GetGenCodeValues(Res.Key, Res.Value, Args);
    for (auto &GenCode : GenCodes) {
      Args.push_back("--generate-code");
      Args.push_back("code=" + mapNVTargetToPPUTarget(GenCode.Code));
      // multi arch support for sm_80
      if (GenCodeDecoder::getRealArchFromNum(GenCodeDecoder::getArchNum(GenCode.Code)) == "sm_80") {
        Args.push_back("--generate-code");
        Args.push_back("code=" + (GenCodeDecoder::isRealArch(GenCode.Code) ?
                                mapNVTargetToPPUTarget("sm_89") :
                                mapNVTargetToPPUTarget("compute_89")));
      }
    }
    return Res.TokenConsumed;
  }

  // Pass unknown arguments as-is
  return ArgHandlerBase::dealUnknownArg(Args, Argv);
}

void NVpruneArgHandler::beforeExec(std::vector<std::string> &Args) {
  if (Verbose) {
    for (const auto &arg : Args) {
      std::cout << arg << " ";
    }
    std::cout << std::endl;
  }
}

int NVpruneArgHandler::dealUnknownValueMapping(std::vector<std::string> &args,
                              const std::string &opt_src,
                              const std::string &opt_dst,
                              const char *argv) {
  if (!argv || !*argv) {
    return ArgHandlerBase::dealUnknownValueMapping(args, opt_src, opt_dst, argv);
  }

  return ArgHandlerBase::dealUnknownValueMapping(args, opt_src, opt_dst, argv);
}

ArgHandlerBase *createArgHandler() {
  return new NVpruneArgHandler();
}

NVpruneArgHandler::ParseResult NVpruneArgHandler::parseKV(const char **Argv) const {
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

int main(int argc, char **argv) {
  auto result = parseArgsFromOptionFile(argc, argv);
  int new_argc = result.first;
  auto new_argv = std::move(result.second);
  if (!new_argv) {
    return 1;
  }

  return wrapperMain(new_argc, new_argv.get());
}