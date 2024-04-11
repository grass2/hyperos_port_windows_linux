import datetime


def red(message):
    timestamp = datetime.datetime.now().strftime('%m%d-%H:%M:%S')
    colored_message = f'\033[1;31m{message}\033[0m'
    output = f'[{timestamp}] {colored_message}'
    print(output)


def blue(message):
    timestamp = datetime.datetime.now().strftime('%m%d-%H:%M:%S')
    colored_message = f'\033[1;34m{message}\033[0m'
    output = f'[{timestamp}] {colored_message}'
    print(output)


def yellow(message):
    timestamp = datetime.datetime.now().strftime('%m%d-%H:%M:%S')
    colored_message = f'\033[1;33m{message}\033[0m'
    output = f'[{timestamp}] {colored_message}'
    print(output)
