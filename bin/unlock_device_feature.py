import lxml.etree as ET
import sys


def main(file, comment, feature_type, feature_name, feature_value):
    tree = ET.parse(file)
    root = tree.getroot()
    xpath_expr = f"//{feature_type}[@name='{feature_name}']"
    element = tree.find(xpath_expr)
    comment_c = None
    if element is None:
        element = ET.SubElement(root, feature_type)
        comment_c = ET.Comment(comment)
    element.set('name', feature_name)
    element.text = feature_value
    if comment_c is not None:
        root.append(comment_c)
    root.append(element)
    xml_string = ET.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=True).replace(b"><", b">\n<")
    with open(file, "wb") as f:
        f.write(xml_string)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
