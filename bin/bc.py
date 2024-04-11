import sys


def main(n, n2):
    v = float(n) + float(n2)
    n1 = int(v)
    if n1 == v:
        return n1
    else:
        return n1+1


if __name__ == '__main__':
    print(main(sys.argv[1], sys.argv[2]))
