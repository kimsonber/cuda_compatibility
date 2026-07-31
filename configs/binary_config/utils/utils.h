#pragma once

#include <string>
#include <vector>
#include <set>
#include <map>
#include <memory>

namespace Wrapper {

std::string getExecutablePath();

std::map<std::string, std::string> loadArchMapConfig(const std::string &FileName, std::string &WrapperMode);

std::pair<int, std::unique_ptr<char*[]>> parseArgsFromOptionFile(int argc, char *argv[]);

void parseArgsFromStr(const std::string &Str, std::vector<std::string> &Args);

bool startsWith(const std::string &Str, const std::string &Prefix);

bool endsWith(const std::string &Str, const std::string &Suffix);

void splitString(const std::string &Str, const std::string &Delim,
                 std::set<std::string> &SplitVec);

std::vector<std::string> splitString(const std::string& Str,
                                     const std::string& Delimiters,
                                     bool KeepEmpty = false);

struct GenCodeValue {
  std::string Arch;
  std::string Code;
  bool operator<(const GenCodeValue &Other) const {
    if (Arch != Other.Arch) {
      return Arch < Other.Arch;
    }
    return Code < Other.Code;
  }
};

class GenCodeDecoder {
public:
  static std::string getArchNum(const std::string &Arch) {
    std::size_t Pos = Arch.find('_');
    return Arch.substr(Pos + 1);
  }

  static bool isVirtualArch(const std::string &Arch) {
    return startsWith(Arch, "compute_");
  }

  static bool isRealArch(const std::string &Arch) {
    return startsWith(Arch, "sm_");
  }

  static std::string getRealArchFromNum(const std::string &ArchNum) {
    return "sm_" + ArchNum;
  }

  static std::string getVirtualArchFromNum(const std::string &ArchNum) {
    return "compute_" + ArchNum;
  }

  static std::set<GenCodeValue> GetGenCodeValues(const std::string& gencodeKey,
  const std::string& gencodeValue, std::vector<std::string> &Args);
};

} // namespace Wrapper