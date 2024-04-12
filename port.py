import argparse
import os
import platform
import sys

from _socket import gethostname

from bin import downloader
from bin.echo import blue, red
import bin.check
from bin.read_config import main as read_config


def main(baserom, portrom):
    if not os.path.exists(os.path.basename(baserom)):
        if 'http' in baserom:
            blue("底包为一个链接，正在下载\nDownload link detected, start downloding.")
            try:
                downloader.download([baserom], os.getcwd())
            except:
                red("Download error!")
                sys.exit()
            baserom = baserom.split("?")[0]
        else:
            red("BASEROM: Invalid parameter")
            sys.exit()
    if not os.path.exists(os.path.basename(portrom)):
        if 'http' in portrom:
            blue("移植包为一个链接，正在下载\nDownload link detected, start downloding.")
            try:
                downloader.download([portrom], os.getcwd())
            except:
                red("Download error!")
                sys.exit()
            portrom = os.path.basename(portrom.split("?")[0])
        else:
            red("PORTROM: Invalid parameter")
            sys.exit()
    with open("bin/call", 'w', encoding='utf-8', newline='\n') as f:
        f.write(f"baserom='{baserom}'\n")
        f.write(f"portrom='{portrom}'\n")
        f.write(f"port_partition='{read_config('bin/port_config', 'partition_to_port')}'\n")
        f.write(f"repackext4='{read_config('bin/port_config', 'repack_with_ext4')}'\n")
        f.write(f"brightness_fix_method='{read_config('bin/port_config', 'brightness_fix_method')}'\n")
        f.write(f"compatible_matrix_matches_enabled='{read_config('bin/port_config', 'compatible_matrix_matches_check')}'\n")
        f.write(f"work_dir='{os.getcwd()}'\n")
        f.write(f"tools_dir='{os.getcwd()}/bin/{platform.system()}/{platform.machine()}'\n")
        f.write(f"OSTYPE='{platform.system()}'\n")
        f.write(f"build_host='{gethostname()}'\n")
        f.write(f"source $1\n")
    os.system(f"bash ./bin/call ./port.sh")


if __name__ == '__main__':
    bin.check.main()
    parser = argparse.ArgumentParser(description='HyperOS stock/xiaomi.eu ROM port for Android 13 based ROM')
    parser.add_argument('baserom', type=str, help='baserom')
    parser.add_argument('portrom', type=str, help='portrom')
    args = parser.parse_args()
    main(args.baserom, args.portrom)
