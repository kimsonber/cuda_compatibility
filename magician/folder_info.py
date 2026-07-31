import os
from utils import exec_command, copy_files, copy_libs
import shutil, fnmatch, itertools
import tempfile, subprocess
import configparser


def removeprefix(s: str, prefix: str) -> str:
    if prefix and s.startswith(prefix):
        return s[len(prefix):]
    return s


def removesuffix(s: str, suffix: str) -> str:
    if suffix and s.endswith(suffix):
        return s[:-len(suffix)]
    return s


class DirInfo(object):
    config = configparser.ConfigParser()
    all_libs = None
    lib_out_dir = 'lib64'

    def __init__(self, path, dirdb):
        self.path = path
        self.dirdb = dirdb
        self.blacklist = []
        if 'ignore_dir' in dirdb:
            self.blacklist = dirdb['ignore_dir'].split('\n')


class LibInfo(object):
    def __init__(self, libPath, libName, basePath, soName=None, needed_libs=None):
        self.path = libPath
        self.name = libName
        self.base = basePath
        self.soname = soName and soName or libName
        if needed_libs == None:
            self.needed_libs = []
        else:
            self.needed_libs = needed_libs
        if soName == None and needed_libs == None:
            self.library_analyze()

    def library_analyze(self):
        Command = "objdump -p "
        Command += os.path.join(self.path, self.name)
        symbols = exec_command(Command)[0]
        if symbols is None:
            print(Command)
            return
        symbols = symbols.decode("utf-8").split('\n')
        for line in symbols:
            if "SONAME" in line:
                self.soname = line.split()[1]
            if "NEEDED" in line:
                self.needed_libs.append(line.split()[1])

    def need_pthread(self):
        for so in self.needed_libs:
            if 'pthread' in so:
                return True
        return False

    @classmethod
    def load(self, o, basePath=None):
        if basePath:
            ret = LibInfo(os.path.join(basePath, o['path']),
                          o['name'],
                          os.path.join(basePath, o['base']),
                          o['soname'],
                          o['needed_libs'])
        else:
            ret = LibInfo(o['path'],
                          o['name'],
                          o['base'],
                          o['soname'],
                          o['needed_libs'])
        return ret



class FolderInfo(object):
    def __init__(self, folderPaths, arch=None, temp_path = None, blacklist=[]):
        self.dir_infos = folderPaths
        self.files = []
        self.headerpaths = []
        self.libdirs = {}
        self.libpaths = []
        self.libpaths_static = []
        self.libpaths_static_irregular = []
        self.libraries = []
        self.library_deps = {}
        self.libraries_static = {}
        self.libraries_static_irregular = {}
        self.symlinks = []
        self.blacklist = []
        self.lib_same_name = {}
        self.arch = arch
        self.lib_link_map = {}

        for dir_info in self.dir_infos:
            if os.path.exists(dir_info.path):
                self.blacklist = dir_info.blacklist
                self.folder_analyze(dir_info.path, dir_info.path)
                self.blacklist = []
            else:
                print("%s not exist." % dir_info.path)

        self.get_library_info()

    @classmethod
    def load(self, input, basePath=None):
        ret = FolderInfo([])
        if basePath:
            ret.files = []
            for file in input['files']:
                ret.files.append([os.path.join(basePath, file[0]),
                                  file[1], file[2],
                                  os.path.join(basePath, file[3])])
        else:
            ret.files = input['files']
        if basePath:
            ret.headerpaths = []
            for headerpath in input['headerpaths']:
                ret.headerpaths.append([headerpath[0],
                                  os.path.join(basePath, headerpath[1])])
        else:
            ret.headerpaths = input['headerpaths']
        if basePath:
            ret.libdirs = {}
            for lib, libdirs in input['libdirs'].items():
                ret.libdirs[lib] = []
                for d in libdirs:
                    ret.libdirs[lib].append(os.path.join(basePath, d))
        else:
            ret.libdirs = input['libdirs']
        if basePath:
            ret.libpaths = []
            for path in input['libpaths']:
                ret.libpaths.append([os.path.join(basePath, path[0]),
                                     path[1], path[2],
                                     os.path.join(basePath, path[3])])
        else:
            ret.libpaths = input['libpaths']
        if basePath:
            ret.libpaths_static = []
            for path in input['libpaths_static']:
                ret.libpaths_static.append([os.path.join(basePath, path[0]),
                                            path[1], path[2],
                                            os.path.join(basePath, path[3])])
        else:
            ret.libpaths_static = input['libpaths_static']
        if basePath:
            ret.libpaths_static_irregular = []
            for path in input['libpaths_static_irregular']:
                ret.libpaths_static_irregular.append([os.path.join(basePath, path[0]),
                                                      path[1], path[2],
                                                      os.path.join(basePath, path[3])])
        else:
            ret.libpaths_static_irregular = input['libpaths_static_irregular']
        ret.libraries = []
        for l in input['libraries']:
            ret.libraries.append(LibInfo.load(l, basePath))
        ret.library_deps = {}
        for k,v in input['library_deps'].items():
            assert len(v) >= 1
            ret.library_deps[k] = []
            for l in v:
                ret.library_deps[k].append(LibInfo.load(l, basePath))
        ret.libraries_static = input['libraries_static']
        ret.libraries_static_irregular = input['libraries_static_irregular']
        if basePath:
            ret.symlinks = []
            for link in input['symlinks']:
                ret.symlinks.append([os.path.join(basePath, link[0]),
                                     link[1], link[2],
                                     os.path.join(basePath, link[3])])
        else:
            ret.symlinks = input['symlinks']
        if basePath:
            ret.lib_same_name = {}
            for name, libs in input['lib_same_name'].items():
                ret.lib_same_name[name] = []
                for lib in libs:
                    ret.lib_same_name[name].append([os.path.join(basePath, lib[0]),
                                                    lib[1], lib[2],
                                                    os.path.join(basePath, lib[3])])
        else:
            ret.lib_same_name = input['lib_same_name']
        ret.arch = input['arch']
        return ret

    def find_in_all_lib(self, filename):
        sym_ret = self.find_in_symlink(filename)
        dyn_lib_ret = self.find_in_dyn_lib(filename)
        static_lib_ret = self.find_in_static_lib(filename)
        return sym_ret + dyn_lib_ret + static_lib_ret

    def find_in_symlink(self, filename):
        ret = []
        for link in self.symlinks:
            if link[1] == filename:
                ret.append(link)
        return ret

    def find_lib_link_target(self, lib_file_name):
        if not self.lib_link_map:
            for file in self.symlinks:
                if file[1] and file[2] and file[0].endswith("lib"):
                    self.lib_link_map[file[1]] = file[2].split("/")[-1]
        lib_link_target = lib_file_name
        while lib_link_target in self.lib_link_map:
            lib_link_target = self.lib_link_map[lib_link_target]
        return lib_link_target

    def find_in_dyn_lib(self, filename):
        ret = []
        for lib in self.libpaths:
            if lib[1] == filename:
                ret.append(lib)
        return ret

    def find_in_static_lib(self, filename):
        ret = []
        for lib in self.libpaths_static:
            if lib[1] == filename:
                ret.append(lib)
        for lib in self.libpaths_static_irregular:
            if lib[1] == filename:
                ret.append(lib)
        return ret

    def folder_analyze(self, root, outpath):
        if isinstance(root, os.DirEntry):
            folderpath = root.path
        else:
            folderpath = root

        for blackpath in self.blacklist:
            if fnmatch.fnmatchcase(os.path.basename(folderpath), blackpath):
                return

        if os.access(folderpath, os.R_OK):
            for entry in os.scandir(folderpath):
                filename = entry.name
                if filename.startswith('.'):
                    continue

                if entry.is_dir() and not entry.is_symlink():
                    try:
                        self.folder_analyze(entry.path, outpath)
                    except OSError as e:
                        print("OSError " + e + " for " + folderpath + "/" + filename)
                else:
                    try:
                        symlink = None if not entry.is_symlink() else os.readlink(entry.path)
                        path = os.path.dirname(entry.path)
                        item = [path, filename, symlink, outpath]
                        self.files.append(item)

                        if ".so" in filename:
                            arch_str = self.get_dyn_lib_arch(entry.path)
                            if not self.arch.lower() in arch_str:
                                continue
                        if filename.endswith('.a'):
                            arch_str = self.get_static_lib_arch(entry.path)
                            if not self.arch.lower() in arch_str:
                                continue

                        relpath = os.path.relpath(path, outpath)
                        if symlink is not None:
                            self.symlinks.append(item)
                        elif ".so" in filename:
                            self.libpaths.append(item)
                            if self.libdirs.get(relpath):
                                self.libdirs[relpath].add(path)
                            else:
                                self.libdirs[relpath]=set([path])
                        elif filename.endswith('_static.a'):
                            self.libpaths_static.append(item)
                            if self.libdirs.get(relpath):
                                self.libdirs[relpath].add(path)
                            else:
                                self.libdirs[relpath]=set([path])
                        elif filename.endswith('.a'):
                            self.libpaths_static_irregular.append(item)
                            if self.libdirs.get(relpath):
                                self.libdirs[relpath].add(path)
                            else:
                                self.libdirs[relpath]=set([path])
                        elif filename.endswith(".h"):
                            if path not in [hp[1] for hp in self.headerpaths]:
                                self.headerpaths.append([relpath, path])

                    except OSError as e:
                        print("OSError " + e + " for " + folderpath + "/" + filename)

    def add_file(self, path, filename, symlink, outpath):
        item = [path, filename, symlink, outpath]
        self.files.append(item)

    def get_library_deps(self):
        for lib in self.libraries:
            for dep in lib.needed_libs:
                if self.library_deps.get(dep) == None:
                    self.library_deps[dep] = []
                self.library_deps[dep].append(lib)

        for needed in list(self.library_deps.keys()):
            found = False
            for lib in self.libraries:
                if lib.soname == needed:
                    found = True
                    break
            if found: continue

            for link in self.symlinks:
                if link[1] == needed:
                    found = True
                    break
            if found: continue

            self.library_deps.pop(needed)

    def trim_header_paths(self):
        for x in list(self.headerpaths):
            for y in list(self.headerpaths):
                if (y[0].find(x[0]) == 0 and len(y[0]) > len(x[0])):
                    self.headerpaths.remove(y)

    def get_dyn_lib_arch(self, filepath):
        cmd1 = "readelf -h %s" % (filepath)
        out, err = exec_command(cmd1, exit_failed=True)
        for line in out.decode("utf-8").splitlines():
            if line.strip().startswith('Machine:'):
                machine = line.split(':', 1)[1].strip().lower()
                return machine.replace('x86-64', 'x86_64')
        raise ValueError("Machine not found in ELF header of %s" % ( filepath))

    def get_static_lib_arch(self, archive_path):
        """Extract machine type from the first object in an archive file"""

        if not os.path.exists(archive_path):
            raise IOError("Archive not found: {}".format(archive_path))

        result = subprocess.Popen(
            ['ar', 't', archive_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = result.communicate()

        if result.returncode != 0:
            raise RuntimeError("ar command failed: {}".format(stderr))

        members = stdout.strip().split()

        if not members:
            raise ValueError("Archive is empty: {}".format(archive_path))

        first_member = members[0]
        if not first_member:
            raise ValueError("First member name is empty")

        tmp_fd, tmp_path = tempfile.mkstemp(prefix="archive_member_")
        os.close(tmp_fd)

        try:
            extract_proc = subprocess.Popen(
                ['ar', 'p', archive_path, first_member],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = extract_proc.communicate()

            if extract_proc.returncode != 0:
                raise RuntimeError("Failed to extract member '{}': {}".format(
                    first_member, stderr))

            with open(tmp_path, 'wb') as f:
                f.write(stdout)

            readelf_proc = subprocess.Popen(
                ['readelf', '-h', tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = readelf_proc.communicate()

            if readelf_proc.returncode != 0:
                raise RuntimeError("readelf failed on member '{}': {}".format(
                    first_member, stderr))

            if isinstance(stdout, bytes):
                stdout = stdout.decode('utf-8')

            for line in stdout.splitlines():
                if line.strip().startswith('Machine:'):
                    machine = line.split(':', 1)[1].strip()
                    return machine.lower().replace('x86-64', 'x86_64')

            raise ValueError("Machine information not found in ELF header")

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def get_library_info(self):
        self.trim_header_paths()

        for lib in self.libpaths:
            libinfo = LibInfo(lib[0], lib[1], lib[3])
            self.libraries.append(libinfo)

        self.get_library_deps()

        for lib in self.libpaths_static:
            self.libraries_static[lib[1]]=False

        for lib in self.libpaths_static_irregular:
            fullpath = os.path.join(lib[0], lib[1])
            arch_str = self.get_static_lib_arch(fullpath)
            if not self.arch.lower() in arch_str:
                continue
            self.libraries_static_irregular[lib[1]]=False

        for lib in itertools.chain(self.libpaths, self.libpaths_static,
                                    self.libpaths_static_irregular):
            finding = self.find_in_all_lib(lib[1])
            if len(finding) > 1:
                fullname = os.path.join(lib[0], lib[1])
                if self.lib_same_name.get(lib[1]):
                    self.lib_same_name[lib[1]].extend(finding)
                else:
                    self.lib_same_name[lib[1]] = finding

    def copy_files(self, dst):
        if not os.path.isdir(dst):
            os.makedirs(dst)

        for file in self.files:
            relative_path = os.path.relpath(file[0], file[3])
            srcname = os.path.join(file[0], file[1])
            dstname = os.path.join(dst, relative_path, file[1])
            try:
                linkto = file[2]
                if linkto is not None:
                    dstfolder = os.path.dirname(dstname)
                    if not os.path.exists(dstfolder):
                        os.makedirs(dstfolder)
                    os.symlink(linkto, dstname)
                    continue

                for headerpath in self.headerpaths:
                    if relative_path.find(headerpath[0]) == 0:
                        dstfolder = os.path.dirname(dstname)
                        if not os.path.exists(dstfolder):
                            os.makedirs(dstfolder)
                        shutil.copy(srcname, dstname)
            except OSError as err:
                print(err)

        lib_out_path_full = os.path.join(dst, DirInfo.lib_out_dir)
        for libdir in self.libdirs:
            libdir_full = os.path.join(dst, libdir)
            if not os.path.exists(libdir_full):
                continue
            if os.path.realpath(libdir_full) == \
                os.path.realpath(lib_out_path_full):
                continue
            found_in_duplicate_lib = False
            for libs in self.lib_same_name.values():
                for lib in libs:
                    libdir_duplicate = os.path.relpath(lib[0], lib[3])
                    if libdir == libdir_duplicate:
                        found_in_duplicate_lib = True
                        break
                if found_in_duplicate_lib:
                    break
            if found_in_duplicate_lib:
                break

            copy_libs(libdir_full, lib_out_path_full)

        lib_path = os.path.join(dst, 'lib')
        if os.path.exists(lib_path):
            shutil.rmtree(lib_path)
        video_path = os.path.join(dst, 'Interface')
        if os.path.exists(video_path):
            copy_files(video_path, os.path.join(dst, 'include'))

        os.symlink('libnvidia-encode.so', os.path.join(lib_out_path_full, 'libnvidia-encode.so.1'))
        os.symlink('libnvcuvid.so', os.path.join(lib_out_path_full, 'libnvcuvid.so.1'))

