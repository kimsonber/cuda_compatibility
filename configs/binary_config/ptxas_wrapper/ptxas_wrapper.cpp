#include "wrapper_gen.hpp"
#include <iostream>
#include <libgen.h>
#include <linux/limits.h>
#include <string>
#include <vector>
#include "utils.h"

using namespace Wrapper;

#define STR1(x) #x
#define STR2(x) STR1(x)
#define CUDA_VER_MAJOR_STR STR2(CUDA_VER_MAJOR)
#define CUDA_VER_MINOR_STR STR2(CUDA_VER_MINOR)
#define CUDA_VER_BUILD_STR STR2(CUDA_VER_BUILD)

static void printVersion() {
  std::cout << "ptxas: Cuda compilation tools, release " << CUDA_VER_MAJOR_STR
            << "." << CUDA_VER_MINOR_STR << ", V" << CUDA_VER_MAJOR_STR << "."
            << CUDA_VER_MINOR_STR << "." << CUDA_VER_BUILD_STR << std::endl;
}

class PtxasArgHandler : public ArgHandlerBase {
  bool PrintVersion = false;
  bool PrintOnly = false;
  std::string ParentPath = "";

public:
  PtxasArgHandler() {
    std::string ExePath = getExecutablePath();
    std::string ExeParent = dirname(&ExePath[0]);
    // dirname may change the data of ExeParent, make a copy
    ParentPath = ExeParent;
  }

  std::string locateTarget() override {
    if (ParentPath.empty())
      return Config::TARGET_EXE;
    return ParentPath + "/" + Config::TARGET_EXE;
  };

  int dealUnknownArg(std::vector<std::string> &Args,
                     const char **Argv) override {
    if (!Argv || !*Argv) {
      return ArgHandlerBase::dealUnknownArg(Args, Argv);
    }

    std::string ArgStr = std::string(*Argv);

    if (!startsWith(ArgStr, "-")) {
      // regarded as input file, pass it as-is.
      return ArgHandlerBase::dealUnknownArg(Args, Argv);
    }

    if (ArgStr == "-V" || ArgStr == "--version") {
      PrintVersion = true;
      return 1;
    }

    if (ArgStr == "--print-only") {
      PrintOnly = true;
      return 1;
    }

    // Ignore unknown arguments
    return 1;
  }

  void beforeExec(std::vector<std::string> &Args) override {
    if (PrintVersion) {
      printVersion();
      exit(0);
    }
    if (PrintOnly) {
      std::cout << "#$ ptxas command: ";
      for (const auto &arg : Args) {
        std::cout << arg << " ";
      }
      std::cout << std::endl;
      exit(0);
    }
  }
};

ArgHandlerBase *createArgHandler() { return new PtxasArgHandler(); }

int main(int argc, char *Argv[]) { return wrapperMain(argc, Argv); }
