import os.path
import sys


def main(file, name):
    if not os.path.exists(file) or not os.path.isfile(file):
        return ''
    with open(file, 'r+', encoding='utf-8') as f:
        for i in f.readlines():
            if i.startswith('#'):
                continue
            elif name in i:
                try:
                    return i.split("=")[1].strip()
                except IndexError:
                    return ''


if __name__ == '__main__':
    print(main(sys.argv[1], sys.argv[2]))
