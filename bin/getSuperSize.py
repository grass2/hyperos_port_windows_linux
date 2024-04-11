import sys


def main(device):
    device = device.upper()
    # 13 13Pro 13Ultra RedmiNote12Turbo |K60Pro |MIXFold
    if device in ['FUXI', 'NUWA', 'ISHTAR', 'MARBLE', 'SOCRATES', 'BABYLO']:
        return 9663676416
    # Redmi Note 12 5G
    elif device == 'SUNSTONE':
        return 9122611200
    # PAD6Max
    elif device == 'YUDI':
        return 11811160064
    # Others
    else:
        return 9126805504


# pipa 9126805504 |Pad6
# liuqin 9126805504 |Pad6Pro
# sunstone 9126805504 or 9122611200 |Note 12 5G
# rembrandt 9126805504 |K60E
# redwood 9126805504 |Note12ProSpeed
# mondrian 9126805504 |K60
# yunluo 9126805504 |RedmiPad
# ruby 9126805504 |Note 12 Pro

if __name__ == '__main__':
    print(main(sys.argv[0]))
