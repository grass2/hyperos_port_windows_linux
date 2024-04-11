import argparse
import os


def main(baserom, portrom):
    os.system(f"bash ./port.sh {baserom} {portrom}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HyperOS stock/xiaomi.eu ROM port for Android 13 based ROM')
    parser.add_argument('baserom', type=str, help='baserom')
    parser.add_argument('portrom', type=str, help='portrom')
    args = parser.parse_args()
    main(args.baserom, args.portrom)
