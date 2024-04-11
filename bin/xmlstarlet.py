import os
import sys
import xml.etree.ElementTree as ET


def main(file, rule, new_value):
    if not os.path.exists(file) or not os.path.isfile(file):
        return ''
    tree = ET.parse(file)
    root = tree.getroot()
    target_element = root.find(f".//integer[@name='{rule}']")
    if target_element is not None:
        target_element.text = new_value
    else:
        print("Target element not found.")

    tree.write(file)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
