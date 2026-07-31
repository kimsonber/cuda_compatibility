#include "wrapper_gen.hpp"
#include <iostream>
#include <libgen.h>
#include <linux/limits.h>
#include <string>
#include <vector>
#include <linux/limits.h>
#include <sys/utsname.h>

#define STR1(x) #x
#define STR2(x) STR1(x)
#define CUDA_VER_MAJOR_STR STR2(CUDA_VER_MAJOR)
#define CUDA_VER_MINOR_STR STR2(CUDA_VER_MINOR)
#define CUDA_VER_BUILD_STR STR2(CUDA_VER_BUILD)
#define CUDA_VERSION_STR STR2(CUDA_VERSION)

static void printVersion() {
  std::cout << "nvlink: NVIDIA (R) Cuda linker" << std::endl
            << "Copyright (c) 2005-2024 NVIDIA Corporation" << std::endl
            << "Built on Fri_Jun_14_16:34:21_PDT_2024" << std::endl
            << "Cuda compilation tools, release " << CUDA_VER_MAJOR_STR << "."
            << CUDA_VER_MINOR_STR << ", V" << CUDA_VER_MAJOR_STR << "."
            << CUDA_VER_MINOR_STR << "." << CUDA_VER_BUILD_STR << std::endl;
}

class nvlinkArgHandler : public ArgHandlerBase {
  bool PrintVersion = false;

public:
  nvlinkArgHandler() {}

  int dealUnknownArg(std::vector<std::string> &args,
                     const char **argv) override {
    if (!argv || !*argv) {
      return ArgHandlerBase::dealUnknownArg(args, argv);
    }

    std::string ArgStr = std::string(*argv);

    // Handle -V and --version for version printing
    if (ArgStr == "-V" || ArgStr == "--version") {
      PrintVersion = true;
      return 1;
    }

    // Pass unknown arguments as-is
    return ArgHandlerBase::dealUnknownArg(args, argv);
  }

  void beforeExec(std::vector<std::string> &args) override {
    if (PrintVersion) {
      printVersion();
      exit(0);
    }
  }

  // Override to capture the output file when -o is processed
  int dealUnknownValueMapping(std::vector<std::string> &args,
                              const std::string &opt_src,
                              const std::string &opt_dst,
                              const char *argv) override {
    return ArgHandlerBase::dealUnknownValueMapping(args, opt_src, opt_dst, argv);
  }
};

ArgHandlerBase *createArgHandler() { return new nvlinkArgHandler(); }

int main(int argc, char *argv[]) { return wrapperMain(argc, argv); }