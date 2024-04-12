import shutil
from bin.echo import red
import sys
import os


def main():
    for i in ['unzip', '7z', 'zip', 'java', 'zipalign', 'python3' if os.name == 'posix' else 'nt', 'zstd']:
        if not shutil.which(i):
            red(f"--> Missing {i} abort! please run ./setup.sh first (sudo is required on Linux system)")
            red(f"--> 命令 {i} 缺失!请重新运行setup.sh (Linux系统sudo ./setup.sh)")
            sys.exit(1)


if __name__ == '__main__':
    main()
