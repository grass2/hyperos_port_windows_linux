import os
import sys
import xml.etree.ElementTree as ET


def main(file):
    if not os.path.exists(file) or not os.path.isfile(file):
        print('90')
    fps_list_element = ET.parse(file).getroot().find(".//integer-array[@name='fpsList']")
    if fps_list_element is not None:
        # 从 fpsList 元素中提取所有 item 元素的值
        items = [int(item.text) for item in fps_list_element.findall("item")]
        sorted_items = sorted(items, reverse=True)
        if sorted_items:
            print(max(sorted_items))
        else:
            print("90")
    else:
        print("90")


if __name__ == '__main__':
    main(sys.argv[1])
