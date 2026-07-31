#include "utils.h"
#include <limits.h>
#include <unistd.h>
#include <cstring>
#include <string>
#include <memory>
#include <iostream>
#include <fstream>
#include <sstream>
#include <map>

std::string Wrapper::getExecutablePath() {
  char Buffer[PATH_MAX];
  ssize_t Len = readlink("/proc/self/exe", Buffer, sizeof(Buffer) - 1);
  if (Len != -1) {
    Buffer[Len] = '\0';
    return std::string(Buffer);
  }
  return "";
}

bool Wrapper::startsWith(const std::string &Str, const std::string &Prefix) {
  if (Str.size() < Prefix.size()) {
    return false;
  }
  return Str.compare(0, Prefix.size(), Prefix) == 0;
}

bool Wrapper::endsWith(const std::string &Str, const std::string &Suffix) {
  if (Str.size() < Suffix.size()) {
    return false;
  }
  return Str.compare(Str.size() - Suffix.size(), Suffix.size(), Suffix) == 0;
}

void Wrapper::splitString(const std::string &Str, const std::string &Delim,
                          std::set<std::string> &SplitVec) {
  if (Str.empty()) {
    return;
  }

  if (Delim.empty()) {
    SplitVec.insert(Str);
    return;
  }

  std::vector<std::string> Vec = splitString(Str, Delim, false);
  SplitVec.insert(Vec.begin(), Vec.end());
}

std::vector<std::string> Wrapper::splitString(const std::string& Str,
                                              const std::string& Delimiters,
                                              bool KeepEmpty/* = false*/) {
  std::vector<std::string> Result;
  if (Str.empty()) {
    return Result;
  }

  if (Delimiters.empty()) {
    Result.emplace_back(Str);
    return Result;
  }

  size_t LastPos = 0;
  size_t Pos = 0;

  while ((Pos = Str.find_first_of(Delimiters, LastPos)) != std::string::npos) {
      std::string Token = Str.substr(LastPos, Pos - LastPos);
      if (KeepEmpty || !Token.empty()) {
          Result.push_back(Token);
      }
      LastPos = Pos + 1;
  }

  if (LastPos <= Str.length()) {
    std::string LastToken = Str.substr(LastPos);
    if (KeepEmpty || !LastToken.empty()) {
        Result.push_back(LastToken);
    }
  }

  return Result;
}

void Wrapper::parseArgsFromStr(const std::string &Str,
                               std::vector<std::string> &Args) {
  std::string CurToken;
  bool InSingleQuote = false;
  bool InDoubleQuote = false;
  bool EscapeNext = false;

  for (char Ch : Str) {
    if (EscapeNext) {
      CurToken.push_back(Ch);
      EscapeNext = false;
      continue;
    }

    if (Ch == '\\') {
      EscapeNext = true;
      continue;
    }

    if (InSingleQuote) {
      if (Ch == '\'') {
        InSingleQuote = false;
      } else {
        CurToken.push_back(Ch);
      }
      continue;
    }

    if (InDoubleQuote) {
      if (Ch == '"') {
        InDoubleQuote = false;
      } else {
        CurToken.push_back(Ch);
      }
      continue;
    }

    if (Ch == '\'') {
      InSingleQuote = true;
      continue;
    }

    if (Ch == '"') {
      InDoubleQuote = true;
      continue;
    }

    if (std::isspace(static_cast<unsigned char>(Ch))) {
      if (!CurToken.empty()) {
        Args.push_back(CurToken);
        CurToken.clear();
      }
      continue;
    }

    CurToken.push_back(Ch);
  }

  if (EscapeNext) {
    CurToken.push_back('\\');
  }

  if (!CurToken.empty()) {
    Args.push_back(CurToken);
  }
}

std::set<Wrapper::GenCodeValue> Wrapper::GenCodeDecoder::GetGenCodeValues(const std::string& gencodeKey,
  const std::string& gencodeValue, std::vector<std::string> &Args) {
  std::set<Wrapper::GenCodeValue> GenCodes;

  if (gencodeKey != "--generate-code" && gencodeKey != "-gencode") {
    return GenCodes;
  }

  // such as -gencode arch=sm_80,code=compute_80
  // or -gencode arch=compute_89,code=[sm_89,compute_89]
  // or -gencode arch=[compute_89],code=[sm_89,compute_89]
  std::size_t CommaPos = gencodeValue.find(',');
  if (CommaPos == std::string::npos) {
    return GenCodes;
  }

  // lambda to parse array format: "item" or "[item1,item2,..]"
  auto parseList = [](const std::string &Str) {
    std::set<std::string> Result;
    if (Str.length() > 2 && Str.front() == '[' && Str.back() == ']') {
      std::string Array = Str.substr(1, Str.length() - 2);
      splitString(Array, ",", Result);
    } else {
      Result.insert(Str);
    }
    return Result;
  };

  std::string ArchPart = gencodeValue.substr(0, CommaPos);
  std::string CodePart = gencodeValue.substr(CommaPos + 1);
  size_t ArchLen = std::strlen("arch=");
  size_t CodeLen = std::strlen("code=");

  if (ArchPart.length() > ArchLen && CodePart.length() > CodeLen) {
    std::string Arch = ArchPart.substr(ArchLen);
    std::string Code = CodePart.substr(CodeLen);
    std::set<std::string> ArchList = parseList(Arch);
    std::set<std::string> CodeList = parseList(Code);
    // generate all combinations of arch and code
    for (const auto &A : ArchList) {
      if (A.empty()) continue;
      for (const auto &C : CodeList) {
        if (C.empty()) continue;
        GenCodes.insert({A, C});
      }
    }
  }

  return GenCodes;
}

void parseArgsFromStr(const std::string &Str, std::vector<std::string> &Args) {
  std::string CurToken;
  bool InSingleQuote = false;
  bool InDoubleQuote = false;
  bool EscapeNext = false;

  for (char Ch : Str) {
    if (EscapeNext) {
      CurToken.push_back(Ch);
      EscapeNext = false;
      continue;
    }

    if (Ch == '\\') {
      EscapeNext = true;
      continue;
    }

    if (InSingleQuote) {
      if (Ch == '\'') {
        InSingleQuote = false;
      } else {
        CurToken.push_back(Ch);
      }
      continue;
    }

    if (InDoubleQuote) {
      if (Ch == '"') {
        InDoubleQuote = false;
      } else {
        CurToken.push_back(Ch);
      }
      continue;
    }

    if (Ch == '\'') {
      InSingleQuote = true;
      continue;
    }

    if (Ch == '"') {
      InDoubleQuote = true;
      continue;
    }

    if (std::isspace(static_cast<unsigned char>(Ch))) {
      if (!CurToken.empty()) {
        Args.push_back(CurToken);
        CurToken.clear();
      }
      continue;
    }

    CurToken.push_back(Ch);
  }

  if (EscapeNext) {
    CurToken.push_back('\\');
  }

  if (!CurToken.empty()) {
    Args.push_back(CurToken);
  }
}

std::pair<int, std::unique_ptr<char *[]>>
Wrapper::parseArgsFromOptionFile(int argc, char *argv[]) {
  std::vector<std::string> args;
  std::vector<std::string> extraOpts;

  args.push_back(argv[0]);
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--options-file" || arg == "-optf") {
      if (i + 1 >= argc) {
        std::cerr << "command fatal   : argument expected after '--options-file'" << std::endl;
        return {0, nullptr};
      }

      std::string filename = argv[++i];
      std::ifstream file(filename);
      if (!file.is_open()) {
        std::cerr << "command fatal   : Could not open options file '" + filename + "'" << std::endl;
        return {0, nullptr};
      }

      std::string line;
      while (std::getline(file, line)) {
        std::istringstream iss(line);
        std::string opt;
        while (iss >> opt) {
          parseArgsFromStr(opt, extraOpts);
        }
      }
      file.close();
    } else {
      args.push_back(arg);
    }
  }

  args.insert(args.begin() + 1, extraOpts.begin(), extraOpts.end());
  int new_argc = static_cast<int>(args.size());
  auto new_argv = std::make_unique<char*[]>(new_argc + 1);

  for (int i = 0; i < new_argc; ++i) {
    new_argv[i] = new char[args[i].size() + 1];
    std::strcpy(new_argv[i], args[i].c_str());
  }

  return {new_argc, std::move(new_argv)};
}

std::map<std::string, std::string> Wrapper::loadArchMapConfig(const std::string &FileName, std::string &WrapperMode) {

  // default config
  std::map<std::string, std::string> ArchMap =
             {{"sm_80", "ppu_10"},     {"sm_89", "ppu_15"},
             {"sm_90", "ppu_15"},     {"sm_90a", "ppu_15"},
             {"compute_80", "vm_10"}, {"compute_89", "vm_15"},
             {"compute_90", "vm_15"}, {"compute_90a", "vm_15"},
             {"lto_80", "vm_10"},     {"lto_89", "vm_15"},
             {"lto_90", "vm_15"},     {"lto_90a", "vm_15"}};
  WrapperMode = "default";

  std::ifstream File(FileName);
  if (!File.is_open()) {
    std::cerr << "Failed to load config file " << FileName << " , using default configuration"
              << std::endl;
    return ArchMap;
  }

  std::string Line;
  while (std::getline(File, Line)) {
    if (Line.empty() || Line[0] == '#') {
      continue;
    }

    size_t EqualPos = Line.find('=');
    if (EqualPos == std::string::npos) {
      std::cerr << "Warning: Invalid line in config file (missing '='): "
                << Line << std::endl;
      continue;
    }

    std::string Keyword = Line.substr(0, EqualPos);
    // strip whitespace
    size_t KeyStart = Keyword.find_first_not_of(" \t");
    size_t KeyEnd = Keyword.find_last_not_of(" \t");
    if (KeyStart == std::string::npos) {
      std::cerr << "Warning: Invalid line in config file (empty keyword): "
                << Line << std::endl;
      continue;
    }
    Keyword = Keyword.substr(KeyStart, KeyEnd - KeyStart + 1);

    std::string Content = Line.substr(EqualPos + 1);
    size_t Start = Content.find_first_not_of(" \t");
    size_t End = Content.find_last_not_of(" \t");
    if (Start == std::string::npos) {
      std::cerr << "Warning: Invalid line in config file (empty content): "
                << Line << std::endl;
      continue;
    }
    Content = Content.substr(Start, End - Start + 1);

    if (Keyword == "archmap") {
      size_t CommaPos = Content.find(',');
      if (CommaPos != std::string::npos) {
        std::string Key = Content.substr(0, CommaPos);
        std::string Value = Content.substr(CommaPos + 1);
        Key.erase(0, Key.find_first_not_of(" \t"));
        Key.erase(Key.find_last_not_of(" \t") + 1);
        Value.erase(0, Value.find_first_not_of(" \t"));
        Value.erase(Value.find_last_not_of(" \t") + 1);
        ArchMap[Key] = Value;
      } else {
        std::cerr << "Warning: Invalid archmap format: " << Line << std::endl;
      }
    } else if (Keyword == "wrapper_mode") {
      WrapperMode = Content;
    } else {
      std::cerr << "Error: Unknown keyword in config file: " << Keyword
                << " using default configuration" << std::endl;
    }
  }
  File.close();

  if (getenv("NVCC_WRAPPER_MODE")) {
    WrapperMode = getenv("NVCC_WRAPPER_MODE");
  }

  return ArchMap;
}