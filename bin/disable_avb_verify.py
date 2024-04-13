import os.path
import sys
import re
from bin.echo import yellow, blue


def main(fstab):
    blue(f"Disabling avb_verify: {fstab}")
    if not os.path.exists(fstab):
        yellow(f"{fstab} not found, please check it manually")
        sys.exit()
    with open(fstab, "r") as sf:
        details = re.sub(",avb_keys=.*avbpubkey", "", sf.read())
    details = re.sub(",avb=vbmeta_system", ",", details)
    details = re.sub(",avb=vbmeta_vendor", "", details)
    details = re.sub(",avb=vbmeta", "", details)
    details = re.sub(",avb", "", details)
    with open(fstab, "w") as tf:
        tf.write(details)


if __name__ == '__main__':
    main(sys.argv[1])
