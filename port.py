import argparse
import os
import sys

from bin import downloader
from bin.echo import blue, red


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
    os.system(f"bash ./port.sh {baserom} {portrom}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HyperOS stock/xiaomi.eu ROM port for Android 13 based ROM')
    parser.add_argument('baserom', type=str, help='baserom')
    parser.add_argument('portrom', type=str, help='portrom')
    args = parser.parse_args()
    main(args.baserom, args.portrom)
