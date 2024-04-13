#!/usr/bin/env python

import os


def main(file):
    try:
        fd = os.open(file, os.O_RDWR)
    except OSError:
        print("Patch Fail!")
        pass
    if os.read(fd, 4) != b"AVB0":
        fd.close()
        print("Error: The provided image is not a valid vbmeta image.\nFile not modified. Exiting...")
    try:
        os.lseek(fd, 123, os.SEEK_SET)
        os.write(fd, b'\x03')
    except OSError:
        fd.close()
        print("Error: Failed when patching the vbmeta image.\nExiting...")
    os.close(fd)
    print("Patching successful.")
