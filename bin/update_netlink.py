import os.path
import sys
from bin.read_config import main as read
from bin.echo import blue
import re


def main(netlink_version, prop_file):
    if not os.path.exists(prop_file):
        return ''
    if not read(prop_file, 'ro.millet.netlink'):
        blue(
            f"找到ro.millet.netlink修改值为{netlink_version}\nmillet_netlink propery found, changing value to {netlink_version}")
        with open(prop_file, "r") as sf:
            details = re.sub("ro.millet.netlink=.*", f"ro.millet.netlink={netlink_version}", sf.read())
        with open(prop_file, "w") as tf:
            tf.write(details)
    else:
        blue(
            f"PORTROM未找到ro.millet.netlink值,添加为{netlink_version}\n millet_netlink not found in portrom, adding new value {netlink_version}")
        with open(prop_file, "r") as tf:
            details = tf.readlines()
            details.append(f"ro.millet.netlink={netlink_version}\n")
        with open(prop_file, "w") as tf:
            tf.writelines(details)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
