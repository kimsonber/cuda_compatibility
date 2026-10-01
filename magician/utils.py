import subprocess
import shutil
import os
from pathlib import Path

def exec_command(command, exit_failed=False, suppress_log=False, use_shell=False):
    if use_shell:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        process = subprocess.Popen(command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0 :
        print("Execute Command: " + command + "\t\tResult: " + str(process.returncode))
        if not suppress_log:
            print(stdout.decode("utf-8"))
            print(stderr.decode("utf-8"))
        if exit_failed:
            exit(-1)
    return (stdout, stderr)

"""join cmd1 and cmd2 with pipe"""
def exec_command2(cmd1, cmd2):
    print(cmd1)
    print(cmd2)
    p1 = subprocess.Popen(cmd1, stdout=subprocess.PIPE, text=True)
    p2 = subprocess.Popen(cmd2, stdin=p1.stdout, stdout=subprocess.PIPE, text=True)
    p1.stdout.close()
    out, _ = p2.communicate()
    if p1.wait() != 0 or p2.returncode != 0: exit(-1)
    return out.strip()

def copy_files(src, dst):
    for file in os.listdir(src):
        srcfile = os.path.join(src, file)
        dstfile = os.path.join(dst, file)
        if os.path.islink(srcfile):
            linkto = os.readlink(srcfile)
            os.symlink(linkto, dstfile)
        else:
            shutil.copy(srcfile, dstfile)

def copy_file(src, dst):
    if os.path.isfile(src):
        shutil.copy(src, dst)
    else:
        raise Exception("{} not exist".format(src))

def copy_libs(src, dst):
    for file in os.listdir(src):
        if not ".so" in file and not file.endswith('.a'):
            continue
        srcfile = os.path.join(src, file)
        shutil.copy(srcfile, dst, follow_symlinks=False)

def move_libs(src, dst):
    for file in os.listdir(src):
        if not ".so" in file and not file.endswith('.a'):
            continue
        srcfile = os.path.join(src, file)
        shutil.move(srcfile, dst)

def touch_file(fname, mode=0o777):
    Path(fname).touch(mode=mode, exist_ok=True)

def append_file(fname, content):
    with open(fname, 'a+') as f:
        f.write(content)
