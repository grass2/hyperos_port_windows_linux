import argparse
import errno
import glob
import hashlib
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from _socket import gethostname
from bin import downloader
from bin.gettype import gettype
import zipfile
from bin.lpunpack import unpack as lpunpack, SparseImage
from imgextractor import Extractor
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import lxml.etree as ET2
from bin.fspatch import main as fspatch
from bin.contextpatch import main as context_patch
import locale
from rich.progress import track
from dumper import Dumper

javaOpts = "-Xmx1024M -Dfile.encoding=utf-8 -Djdk.util.zip.disableZip64ExtraFieldValidation=true -Djdk.nio.zipfs.allowDotZipEntry=true"
tools_dir = f'{os.getcwd()}/bin/{platform.system()}/{platform.machine()}/'
is_chinese_language = 'Chinese' in locale.getlocale()[0]


def sdat2img(TRANSFER_LIST_FILE, NEW_DATA_FILE, OUTPUT_IMAGE_FILE):
    def rangeset(src):
        num_set = [int(item) for item in src.split(',')]
        if len(num_set) != num_set[0] + 1:
            print('Error on parsing following data to rangeset:\n{}'.format(src))
            sys.exit(1)

        return tuple([(num_set[i], num_set[i + 1]) for i in range(1, len(num_set), 2)])

    def parse_transfer_list_file():
        trans_list = open(TRANSFER_LIST_FILE, 'r')

        # First line in transfer list is the version number
        version = int(trans_list.readline())

        # Second line in transfer list is the total number of blocks we expect to write
        new_blocks = int(trans_list.readline())

        if version >= 2:
            # Third line is how many stash entries are needed simultaneously
            trans_list.readline()
            # Fourth line is the maximum number of blocks that will be stashed simultaneously
            trans_list.readline()

        # Subsequent lines are all individual transfer commands
        commands = []
        for line in trans_list:
            line = line.split(' ')
            cmd = line[0]
            if cmd in ['erase', 'new', 'zero']:
                commands.append([cmd, rangeset(line[1])])
            else:
                # Skip lines starting with numbers, they are not commands anyway
                if not cmd[0].isdigit():
                    print('Command "{}" is not valid.'.format(cmd))
                    trans_list.close()
                    sys.exit(1)

        trans_list.close()
        return version, new_blocks, commands

    BLOCK_SIZE = 4096

    version, new_blocks, commands = parse_transfer_list_file()

    if version == 1:
        print('Android Lollipop 5.0 detected!')
    elif version == 2:
        print('Android Lollipop 5.1 detected!')
    elif version == 3:
        print('Android Marshmallow 6.x detected!')
    elif version == 4:
        print('Android Nougat 7.x / Oreo 8.x detected!')
    else:
        print('Unknown Android version!')

    # Don't clobber existing files to avoid accidental data loss
    try:
        output_img = open(OUTPUT_IMAGE_FILE, 'wb')
    except IOError as e:
        if e.errno == errno.EEXIST:
            print('Error: the output file "{}" already exists'.format(e.filename))
            print('Remove it, rename it, or choose a different file name.')
            sys.exit(e.errno)
        else:
            raise

    new_data_file = open(NEW_DATA_FILE, 'rb')
    all_block_sets = [i for command in commands for i in command[1]]
    max_file_size = max(pair[1] for pair in all_block_sets) * BLOCK_SIZE

    for command in commands:
        if command[0] == 'new':
            for block in command[1]:
                begin = block[0]
                end = block[1]
                block_count = end - begin
                print('\rCopying {} blocks into position {}...'.format(block_count, begin), end='')
                # Position output file
                output_img.seek(begin * BLOCK_SIZE)

                # Copy one block at a time
                while block_count > 0:
                    output_img.write(new_data_file.read(BLOCK_SIZE))
                    block_count -= 1

    # Make file larger if necessary
    if output_img.tell() < max_file_size:
        output_img.truncate(max_file_size)
    output_img.close()
    new_data_file.close()
    print('\nDone! Output image: {}'.format(os.path.realpath(output_img.name)))


def red(cn='', en=''):
    message = cn if is_chinese_language else en
    if not message:
        message = cn if cn else en
    print(f'[{datetime.now().strftime("%m%d-%H:%M:%S")}] \033[1;31m{message}\033[0m')


def blue(cn='', en=''):
    message = cn if is_chinese_language else en
    if not message:
        message = cn if cn else en
    print(f'[{datetime.now().strftime("%m%d-%H:%M:%S")}] \033[1;34m{message}\033[0m')


def yellow(cn='', en=''):
    message = cn if is_chinese_language else en
    if not message:
        message = cn if cn else en
    print(f'[{datetime.now().strftime("%m%d-%H:%M:%S")}] \033[1;33m{message}\033[0m')


def green(cn='', en=''):
    message = cn if is_chinese_language else en
    if not message:
        message = cn if cn else en
    print(f'[{datetime.now().strftime("%m%d-%H:%M:%S")}] \033[1;32m{message}\033[0m')


def read_config(file, name):
    if not os.path.exists(file) or not os.path.isfile(file):
        return ''
    with open(file, 'r+', encoding='utf-8') as f:
        for i in f.readlines():
            if i.startswith('#'):
                continue
            elif name + "=" in i:
                try:
                    return i.split("=")[1].strip()
                except IndexError:
                    return ''
    return ""


def update_netlink(netlink_version, prop_file):
    if not os.path.exists(prop_file):
        return ''
    if not read_config(prop_file, 'ro.millet.netlink'):
        blue(
            f"找到ro.millet.netlink修改值为{netlink_version}",
            f"millet_netlink propery found, changing value to {netlink_version}")
        with open(prop_file, "r") as sf:
            details = re.sub("ro.millet.netlink=.*", f"ro.millet.netlink={netlink_version}", sf.read())
        with open(prop_file, "w") as tf:
            tf.write(details)
    else:
        blue(
            f"PORTROM未找到ro.millet.netlink值,添加为{netlink_version}",
            f"millet_netlink not found in portrom, adding new value {netlink_version}")
        with open(prop_file, "r") as tf:
            details = tf.readlines()
            details.append(f"ro.millet.netlink={netlink_version}\n")
        with open(prop_file, "w") as tf:
            tf.writelines(details)


def unlock_device_feature(file, comment, feature_type, feature_name, feature_value):
    tree = ET2.parse(file)
    root = tree.getroot()
    xpath_expr = f"//{feature_type}[@name='{feature_name}']"
    element = tree.find(xpath_expr)
    comment_c = None
    if element is None:
        element = ET2.SubElement(root, feature_type)
        comment_c = ET2.Comment(comment)
    element.set('name', feature_name)
    element.text = feature_value
    if comment_c is not None:
        root.append(comment_c)
    root.append(element)
    xml_string = ET2.tostring(root, encoding="utf-8", xml_declaration=True).replace(b"><", b">\n<")
    with open(file, "wb") as f:
        f.write(xml_string)


def patch_vbmeta(file):
    try:
        fd = os.open(file, os.O_RDWR)
    except OSError:
        print("Patch Fail!")
        return
    if os.read(fd, 4) != b"AVB0":
        os.close(fd)
        print("Error: The provided image is not a valid vbmeta image.")
    try:
        os.lseek(fd, 123, os.SEEK_SET)
        os.write(fd, b'\x03')
    except OSError:
        os.close(fd)
        print("Error: Failed when patching the vbmeta image")
    os.close(fd)
    print("Patching successful.")


def get_super_size(device):
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


def maxfps(file):
    if not os.path.exists(file) or not os.path.isfile(file):
        return '90'
    fps_list_element = ET.parse(file).getroot().find(".//integer-array[@name='fpsList']")
    if fps_list_element is not None:
        sorted_items = sorted([int(item.text) for item in fps_list_element.findall("item")], reverse=True)
        if sorted_items:
            return str(max(sorted_items))
        else:
            return "90"
    else:
        return "90"


def disavb(fstab):
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


def xmlstarlet(file, rule, new_value):
    if not os.path.exists(file) or not os.path.isfile(file):
        return ''
    tree = ET.parse(file)
    target_element = tree.getroot().find(f".//integer[@name='{rule}']")
    if target_element is not None:
        target_element.text = new_value
    else:
        print("Target element not found.")
    tree.write(file)


def check():
    for i in ['7z', 'zip', 'java', 'zipalign', 'zstd']:
        if os.path.exists(os.path.join(tools_dir, (i + '.exe' if os.name == 'nt' else ''))):
            return
        if not shutil.which(i):
            red(f"--> Missing {i} abort! please run ./setup.sh first (sudo is required on Linux system)",
                f"--> 命令 {i} 缺失!请重新运行setup.sh (Linux系统sudo ./setup.sh)")
            sys.exit(1)


def replace_method_in_smali(smali_file, target_method):
    with open(smali_file, 'r') as file:
        smali_content = file.readlines()

    method_line = None
    move_result_end_line = None
    for i, line in enumerate(smali_content):
        if target_method in line:
            method_line = i + 1
        if method_line and 'move-result' in line:
            move_result_end_line = i
            break

    if method_line is not None and move_result_end_line is not None:
        register_number = re.search(r'\d+', smali_content[move_result_end_line]).group()
        replace_with_command = f"const/4 v{register_number}, 0x0"
        smali_content[method_line - 1:move_result_end_line + 1] = [replace_with_command + '\n']
        with open(smali_file, 'w') as file:
            file.writelines(smali_content)
        print(f"{smali_file} 修改成功")


def get_file_md5(fname):
    m = hashlib.md5()
    with open(fname, 'rb') as fobj:
        while True:
            data = fobj.read(4096)
            if not data:
                break
            m.update(data)

    return m.hexdigest()


def unix_to_dos(input_file):
    with open(input_file, 'r', encoding='utf-8') as input_f:
        unix_content = input_f.read()
    dos_content = unix_content.replace('\r\n', '\n').replace('\n', '\r\n')
    with open(input_file, 'w') as output_f:
        output_f.write(dos_content)


def get_dir_size(ddir):
    size = 0
    for (root, dirs, files) in os.walk(ddir):
        for name in files:
            if not os.path.islink(name):
                try:
                    size += os.path.getsize(os.path.join(root, name))
                except:
                    ...
    return int(size)


def append(file, lines):
    with open(file, 'a', encoding='utf-8') as f:
        f.writelines(lines)


def sed(file, old, new):
    with open(file, 'r', encoding='utf-8') as f:
        try:
            data = f.read()
        except UnicodeDecodeError:
            with open(file, 'r', encoding='gbk') as f:
                data = f.read()
    data = re.sub(old, new, data)
    with open(file, 'w', encoding='utf-8', newline='\n') as f:
        f.write(data)


def insert_after_line(file_path, target_line, text_to_insert):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
    except:
        with open(file_path, 'r', encoding='gbk') as file:
            lines = file.readlines()
    index_text = None
    for i, line in enumerate(lines):
        if target_line == line:
            index_text = i
            break
    if index_text is None:
        print("目标行未找到")
        print(lines)
        return
    if not text_to_insert.endswith('\n'):
        text_to_insert += '\n'
    lines.insert(index_text, text_to_insert)
    with open(file_path, 'w', encoding='utf-8', newline='\n') as file:
        file.writelines(lines)


def find_file(directory, filename):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == filename:
                return os.path.join(root, file)
    return ''


def find_files(directory, filename):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == filename:
                yield os.path.join(root, file)


def find_files_mh(directory, filename):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if filename in file:
                yield os.path.join(root, file)


def find_folder_mh(directory, filename):
    for root, dirs, files in os.walk(directory):
        for file in dirs:
            if filename in file:
                return os.path.join(root, file)
    return ''


def simg2img(path):
    with open(path, 'rb') as fd:
        if SparseImage(fd).check():
            print('Sparse image detected.')
            print('Converting to raw image...')
            unsparse_file = SparseImage(fd).unsparse()
            print('Result:[ok]')
        else:
            print(f"{path} not Sparse.Skip!")
    try:
        if os.path.exists(unsparse_file):
            os.remove(path)
            os.rename(unsparse_file, path)
    except Exception as e:
        print(e)


def call(exe, kz='Y', out=0, shstate=False, sp=0):
    cmd = f'{tools_dir}/{exe}' if kz == "Y" else exe
    if os.name != 'posix':
        conf = subprocess.CREATE_NO_WINDOW
    else:
        if sp == 0:
            cmd = shlex.split(cmd)
        conf = 0
    try:
        ret = subprocess.Popen(cmd, shell=shstate, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, creationflags=conf)
        for i in iter(ret.stdout.readline, b""):
            if out == 0:
                try:
                    out_put = i.decode("utf-8").strip()
                except (Exception, BaseException):
                    out_put = i.decode("gbk").strip()
                print(out_put)
    except subprocess.CalledProcessError as e:
        ret = lambda: print(f"Error!{exe}")
        ret.returncode = 2
        for i in iter(e.stdout.readline, b""):
            if out == 0:
                try:
                    out_put = i.decode("utf-8").strip()
                except (Exception, BaseException):
                    out_put = i.decode("gbk").strip()
                print(out_put)
    ret.wait()
    return ret.returncode


def patch_smali(file, smail, old, new, port_android_sdk, regex=False):
    targetfilefullpath = find_file('build/portrom/images', file)
    if os.path.isfile(targetfilefullpath):
        targetfilename = os.path.basename(targetfilefullpath)
        yellow(f"正在修改 {targetfilename}\nModifying {targetfilename}")
        foldername = targetfilename.split(".")[0]
        try:
            shutil.rmtree(f'tmp/{foldername}/')
        except:
            pass
        os.makedirs(f'tmp/{foldername}/', exist_ok=True)
        shutil.copy2(targetfilefullpath, f'tmp/{foldername}/')
        call(f'7z x -y tmp/{foldername}/{targetfilename} *.dex -otmp/{foldername}', kz='Y' if os.name == 'nt' else 'N')
        for i in glob.glob(f'tmp/{foldername}/*.dex'):
            smalifname = os.path.basename(i).split('.')[0]
            os.system(
                f'java -jar bin/apktool/baksmali.jar d --api {port_android_sdk} {i} -o tmp/{foldername}/{smalifname}')
        targetsmali = find_file(f'tmp/{foldername}', smail)
        if os.path.isfile(targetsmali):
            smalidir = 'classes'
            for i in targetsmali.replace('\\', '/').split('/'):
                if 'classes' in i:
                    smalidir = i
                    break
            yellow(f"I: 开始patch目标 {smalidir}", f"Target {smalidir} Found")
            with open(targetsmali, 'r') as f:
                content = f.read()
            if regex:
                content = re.sub(old, new, content)
            else:
                content = content.replace(old, new)
            with open(targetsmali, 'w') as f:
                f.write(content)
            if call(
                    f'java -jar bin/apktool/smali.jar a --api {port_android_sdk} tmp/{foldername}/{smalidir} -o tmp/{foldername}/{smalidir}.dex',
                    out=1, kz='N') != 0:
                red('Smaling 失败', 'Smaling failed')
                sys.exit()
            old = os.getcwd()
            os.chdir(f'tmp/{foldername}/')
            if call(f'7z a -y -mx0 -tzip {targetfilename} {smalidir}.dex', kz='Y' if os.name == 'nt' else 'N') != 0:
                red(f"修改{targetfilename}失败", f"Failed to modify {targetfilename}")
                sys.exit()
            os.chdir(old)
            yellow(f"修补{targetfilename} 完成", f"Fix {targetfilename}completed")
            if targetfilename.endswith('.apk'):
                yellow("检测到apk，进行zipalign处理。。", "APK file detected, initiating ZipAlign process...")
                os.remove(targetfilefullpath)
                if call(f'zipalign -p -f -v 4 tmp/{foldername}/{targetfilename} {targetfilefullpath}', out=1):
                    red("zipalign错误，请检查原因。", "zipalign error,please check for any issues")
                yellow("apk zipalign处理完成", "APK ZipAlign process completed.")
                yellow(f"复制APK到目标位置：{targetfilefullpath}", f"Copying APK to target {targetfilefullpath}")
            else:
                yellow(f"复制修改文件到目标位置：{targetfilefullpath}", f"Copying file to target {targetfilefullpath}")
                shutil.copy2(f'tmp/{foldername}/{targetfilename}', targetfilefullpath)
    else:
        red(f"Failed to find {file},please check it manually")


def main(baserom, portrom):
    if not os.path.exists(os.path.basename(baserom)):
        if 'http' in baserom:
            blue("底包为一个链接，正在下载", "Download link detected, start downloding.")
            try:
                downloader.download([baserom], os.getcwd())
            except:
                red("Download error!")
                sys.exit()
            baserom = baserom.split("?")[0]
        else:
            red("BASEROM: Invalid parameter")
            sys.exit()
    if not os.path.exists(os.path.basename(portrom)):
        if 'http' in portrom:
            blue("移植包为一个链接，正在下载", "Download link detected, start downloding.")
            try:
                downloader.download([portrom], os.getcwd())
            except:
                red("Download error!")
                sys.exit()
            portrom = os.path.basename(portrom.split("?")[0])
        else:
            red("PORTROM: Invalid parameter")
            sys.exit()
    is_base_rom_eu: bool = False
    baserom_type: str = ''
    is_eu_rom: bool = False
    port_partition = read_config('bin/port_config', 'partition_to_port').split()
    build_user = 'ColdWindScholar'
    device_code = "YourDevice"
    compatible_matrix_matches_enabled = read_config('bin/port_config', 'compatible_matrix_matches_check') == 'true'
    pack_type = 'EXT' if read_config('bin/port_config', 'repack_with_ext4') == 'true' else 'EROFS'
    if "miui_" in baserom:
        device_code = baserom.split('_')[1]
    elif "xiaomi.eu_" in baserom:
        device_code = baserom.split('_')[2]
    is_shennong_houji_port = device_code.upper() in ['SHENNONG', 'HOUJI']
    blue("正在检测ROM底包", "Validating BASEROM..")
    with zipfile.ZipFile(baserom) as rom:
        if "payload.bin" in rom.namelist():
            baserom_type = 'payload'
            super_list = ['vendor', 'mi_ext', 'odm', 'odm_dlkm', 'system', 'system_dlkm', 'vendor_dlkm', 'product',
                          'product_dlkm', 'system_ext']
        elif [True for i in rom.namelist() if '.br' in i]:
            baserom_type = 'br'
            super_list = ['vendor', 'mi_ext', 'odm', 'system', 'product', 'system_ext']
        elif [True for i in rom.namelist() if 'images/super.img' in i]:
            is_base_rom_eu = True
            super_list = ['vendor', 'mi_ext', 'odm', 'system', 'product', 'system_ext']
        else:
            red("底包中未发现payload.bin以及br文件，请使用MIUI官方包后重试",
                "payload.bin/new.br not found, please use HyperOS official OTA zip package.")
            sys.exit()
    with zipfile.ZipFile(portrom) as rom:
        if "payload.bin" in rom.namelist():
            green("ROM初步检测通过", "ROM validation passed.")
        elif [True for i in rom.namelist() if 'xiaomi.eu' in i]:
            is_eu_rom = True
        else:
            red("目标移植包没有payload.bin，请用MIUI官方包作为移植包",
                "payload.bin not found, please use HyperOS official OTA zip package.")
            sys.exit()

    # Clean Up
    blue("正在清理文件", "Cleaning up..")
    for i in read_config('bin/port_config', 'partition_to_port').split():
        if os.path.isdir(i):
            try:
                shutil.rmtree(i)
            except:
                pass
    for i in ['app', 'tmp', 'build/baserom/', 'build/portrom/']:
        if os.path.isdir(i):
            try:
                shutil.rmtree(i)
            except:
                pass
    for root, dirs, files in os.walk('.'):
        for i in [i for i in dirs if 'hyperos_' in i]:
            try:
                shutil.rmtree(i)
            except:
                pass
    green("文件清理完毕", "Files cleaned up.")
    for i in ['build/baserom/images/', 'build/portrom/images/']:
        if not os.path.exists(i):
            os.makedirs(i)
    # Extract BaseRom Zip
    if baserom_type == 'payload':
        blue("正在提取底包 [payload.bin]", "Extracting files from BASEROM [payload.bin]")
        with zipfile.ZipFile(baserom) as rom:
            try:
                rom.extract('payload.bin', path='build/baserom')
            except:
                red("解压底包 [payload.bin] 时出错", "Extracting [payload.bin] error")
                sys.exit()
            green("底包 [payload.bin] 提取完毕", "[payload.bin] extracted.")
    elif baserom_type == 'br':
        blue("正在提取底包 [new.dat.br]", "Extracting files from BASEROM [new.dat.br]")
        with zipfile.ZipFile(baserom) as rom:
            try:
                rom.extractall('build/baserom')
            except:
                red("解压底包 [new.dat.br] 时出错", "Extracting [new.dat.br] error")
                sys.exit()
            green("底包 [new.dat.br] 提取完毕", "[new.dat.br] extracted.")
    elif is_base_rom_eu:
        blue("正在提取底包 [super.img]", "Extracting files from BASEROM [super.img]")
        with zipfile.ZipFile(baserom) as rom:
            try:
                rom.extractall('build/baserom')
            except:
                red("解压底包 [super.img] 时出错", "Extracting [super.img] error")
                sys.exit()
            green("底包 [super.img] 提取完毕", "[super.img] extracted.")
        blue("合并super.img* 到super.img", "Merging super.img.* into super.img")
        os.system('simg2img build/baserom/images/super.img.* build/baserom/images/super.img')
        files = glob.glob('build/baserom/images/super.img.*')
        for file in files:
            os.remove(file)
        os.rename("build/baserom/images/super.img", 'build/baserom/super.img')
        shutil.move('build/baserom/images/boot.img', 'build/baserom/')
        if not os.path.exists("build/baserom/firmware-update"):
            os.makedirs('build/baserom/firmware-update')
        files_to_move = glob.glob('build/baserom/images/*')
        for file in files_to_move:
            shutil.move(file, 'build/baserom/firmware-update')
        if os.path.exists('build/baserom/firmware-update/cust.img.0'):
            os.system('simg2img build/baserom/firmware-update/cust.img.* build/baserom/firmware-update/cust.img')
            for i in glob.glob('build/baserom/firmware-update/cust.img.*'):
                os.remove(i)
    # Extract PortRom Zip
    if is_eu_rom:
        blue("正在提取移植包 [super.img]" "Extracting files from PORTROM [super.img]")
        with zipfile.ZipFile(portrom) as rom:
            for i in [i for i in rom.namelist() if 'images/super.img.' in i]:
                try:
                    rom.extract(i, path='build/portrom')
                except:
                    red("解压移植包 [super.img] 时出错", "Extracting [super.img] error")
                    sys.exit()
        blue("合并super.img* 到super.img", "Merging super.img.* into super.img")
        os.system('simg2img build/portrom/images/super.img.* build/portrom/images/super.img')
        for i in glob.glob(' build/portrom/images/super.img.*'):
            os.remove(i)
        shutil.move('build/portrom/images/super.img', 'build/portrom/super.img')
        green("移植包 [super.img] 提取完毕", "[super.img] extracted.")
    else:
        blue("正在提取移植包 [payload.bin]", "Extracting files from PORTROM [payload.bin]")
        with zipfile.ZipFile(portrom) as rom:
            try:
                rom.extract('payload.bin', path='build/portrom')
            except:
                red("解压移植包 [payload.bin] 时出错", "Extracting [payload.bin] error")
                sys.exit()
        green("移植包 [payload.bin] 提取完毕", "[payload.bin] extracted.")
    # Extract BaseRom Partition
    if baserom_type == 'payload':
        blue("开始分解底包 [payload.bin]", "Unpacking BASEROM [payload.bin]")
        with open('build/baserom/payload.bin', 'rb') as f:
            try:
                Dumper(f, 'build/baserom/images/', False, old='old').run()
            except:
                red("分解底包 [payload.bin] 时出错", "Unpacking [payload.bin] failed")
                sys.exit()
    elif is_base_rom_eu:
        blue("开始分解底包 [super.img]", "Unpacking BASEROM [super.img]")
        lpunpack("build/baserom/super.img", 'build/baserom/images', super_list)
    elif baserom_type == 'br':
        blue("开始分解底包 [new.dat.br]", "Unpacking BASEROM[new.dat.br]")
        for i in track(super_list):
            call(f'brotli -d build/baserom/{i}.new.dat.br')
            sdat2img(f'build/baserom/{i}.transfer.list', f'build/baserom/{i}.new.dat', f'build/baserom/images/{i}.img')
            for v in glob.glob(f'build/baserom/{i}.new.dat*') + \
                     glob.glob(f'build/baserom/{i}.transfer.list') + \
                     glob.glob(f'build/baserom/{i}.patch.*'):
                os.remove(v)

    for part in track(['system', 'system_dlkm', 'system_ext', 'product', 'product_dlkm', 'mi_ext']):
        img = f'build/baserom/images/{part}.img'
        if os.path.isfile(img):
            if gettype(img) == 'sparse':
                simg2img(img)
            if gettype(img) == 'ext':
                blue(f"正在分解底包 {part}.img [ext]", f"Extracing {part}.img [ext] from BASEROM")
                Extractor().main(img, ('build/baserom/images/' + os.path.basename(img).split('.')[0]))
                blue(f"分解底包 [{part}.img] 完成", "BASEROM {part}.img [ext] extracted.")
                os.remove(img)
            elif gettype(img) == 'erofs':
                pack_type = 'EROFS'
                blue(f"正在分解底包 {part}.img [erofs]", f"Extracing {part}.img [erofs] from BASEROM")
                if call(f'extract.erofs -x -i build/baserom/images/{part}.img  -o build/baserom/images/'):
                    red(f"分解 {part}.img 失败", "Extracting {part}.img failed.")
                    sys.exit()
                blue(f"分解底包 [{part}.img][erofs] 完成", f"BASEROM {part}.img [erofs] extracted.")
                os.remove(img)

    for image in ['vendor', 'odm', 'vendor_dlkm', 'odm_dlkm']:
        source_file = f'build/baserom/images/{image}.img'
        if os.path.isfile(source_file):
            shutil.copy(source_file, f'build/portrom/images/{image}.img')
    green("开始提取逻辑分区镜像", "Starting extract partition from img")
    for part in track(super_list):
        if part in ['vendor', 'odm', 'vendor_dlkm', 'odm_dlkm'] and os.path.isfile(f"build/portrom/images/{part}.img"):
            blue(f"从底包中提取 [{part}]分区 ...", f"Extracting [{part}] from BASEROM")
        else:
            if is_eu_rom:
                blue(f"PORTROM super.img 提取 [{part}] 分区...", f"Extracting [{part}] from PORTROM super.img")
                lpunpack('build/portrom/super.img', 'build/portrom/images', [f"{part}_a"])
                shutil.move(f"build/portrom/images/{part}_a.img", f"build/portrom/images/{part}.img")
            else:
                blue(f"payload.bin 提取 [{part}] 分区...", f"Extracting [{part}] from PORTROM payload.bin")
                with open('build/portrom/payload.bin', 'rb') as f:
                    try:
                        Dumper(f,
                               'build/portrom/images/',
                               diff=False,
                               old='old',
                               images=[part]).run()
                    except:
                        red(f"提取移植包 [{part}] 分区时出错", f"Extracting partition [{part}] error.")
                        sys.exit()
        img = f'build/portrom/images/{part}.img'
        if os.path.isfile(img):
            blue(f"开始提取 {part}.img", f"Extracting {part}.img")
            if gettype(img) == 'sparse':
                simg2img(img)
            if gettype(img) == 'ext':
                pack_type = 'EXT'
                try:
                    Extractor().main(img, ('build/portrom/images/' + os.sep + os.path.basename(img).split('.')[0]))
                except:
                    red(f"提取{part}失败", f"Extracting partition {part} failed")
                    sys.exit()
                os.makedirs(f'build/portrom/images/{part}/lost+found', exist_ok=True)
                os.remove(f'build/portrom/images/{part}.img')
                green(f"提取 [{part}] [ext]镜像完毕", f"Extracting [{part}].img [ext] done")
            elif gettype(img) == 'erofs':
                pack_type = 'EROFS'
                green("移植包为 [erofs] 文件系统", "PORTROM filesystem: [erofs]. ")
                if read_config('bin/port_config', 'repack_with_ext4') == "true":
                    pack_type = 'EXT'
                if call(f'extract.erofs -x -i build/portrom/images/{part}.img -o build/portrom/images/'):
                    red(f"提取{part}失败", "Extracting {part} failed")
                os.makedirs(f'build/portrom/images/{part}/lost+found', exist_ok=True)
                os.remove(f'build/portrom/images/{part}.img')
                green(f"提取移植包[{part}] [erofs]镜像完毕", f"Extracting {part} [erofs] done.")
    # Modify The Rom
    blue("正在获取ROM参数", "Fetching ROM build prop.")
    is_ab_device = read_config('build/portrom/images/vendor/build.prop', 'ro.build.ab_update')
    base_android_version = read_config('build/portrom/images/vendor/build.prop', 'ro.vendor.build.version.release')
    port_android_version = read_config('build/portrom/images/system/system/build.prop',
                                       'ro.system.build.version.release')
    port_rom_code = read_config('build/portrom/images/product/etc/build.prop', 'ro.product.product.name')
    green(
        f"安卓版本: 底包为[Android {base_android_version}], 移植包为 [Android {port_android_version}]",
        "Android Version: BASEROM:[Android {base_android_version}], PORTROM [Android {port_android_version}]")
    base_android_sdk = read_config('build/portrom/images/vendor/build.prop', 'ro.vendor.build.version.sdk')
    port_android_sdk = read_config('build/portrom/images/system/system/build.prop', 'ro.system.build.version.sdk')
    green(
        f"SDK 版本: 底包为 [SDK {base_android_sdk}], 移植包为 [SDK {port_android_sdk}]",
        f"SDK Verson: BASEROM: [SDK {base_android_sdk}], PORTROM: [SDK {port_android_sdk}]")
    base_rom_version = read_config('build/portrom/images/vendor/build.prop', 'ro.vendor.build.version.incremental')
    port_mios_version_incremental = read_config('build/portrom/images/mi_ext/etc/build.prop',
                                                'ro.mi.os.version.incremental')
    port_device_code = port_mios_version_incremental.split(".")[4]
    if 'DEV' in port_mios_version_incremental:
        yellow("检测到开发板，跳过修改版本代码", "Dev deteced,skip replacing codename")
        port_rom_version = port_mios_version_incremental
    else:
        base_device_code = 'U' + base_rom_version.split(".")[4][1:]
        port_rom_version = port_mios_version_incremental.replace(port_device_code, base_device_code)
    green(
        f"ROM 版本: 底包为 [{base_rom_version}], 移植包为 [{port_rom_version}]",
        f"ROM Version: BASEROM: [{base_rom_version}], PORTROM: [{port_rom_version}] ")
    base_rom_code = read_config('build/portrom/images/vendor/build.prop', 'ro.product.vendor.device')
    green(
        f"机型代号: 底包为 [{base_rom_code}], 移植包为 [{port_rom_code}]",
        f"Device Code: BASEROM: [{base_rom_code}], PORTROM: [{port_rom_code}]")
    for cpfile in ['AospFrameworkResOverlay.apk', 'MiuiFrameworkResOverlay.apk', 'DevicesAndroidOverlay.apk',
                   'DevicesOverlay.apk', 'SettingsRroDeviceHideStatusBarOverlay.apk', 'MiuiBiometricResOverlay.apk']:
        base_file = find_file('build/baserom/images/product', cpfile)
        port_file = find_file('build/portrom/images/product', cpfile)
        if not all([base_file, port_file]):
            continue
        if os.path.isfile(base_file) and os.path.isfile(port_file):
            blue(f"正在替换 [{cpfile}]", "Replacing [{cpfile}]")
            shutil.copyfile(base_file, port_file)

    for file_path in glob.glob("build/portrom/images/product/etc/displayconfig/display_id*.xml"):
        try:
            os.remove(file_path)
            print(f"Removed: {file_path}")
        except OSError:
            pass
    os.makedirs('build/portrom/images/product/etc/displayconfig', exist_ok=True)
    for i in glob.glob('build/baserom/images/product/etc/displayconfig/display_id*.xml'):
        shutil.copy2(i, 'build/portrom/images/product/etc/displayconfig/')
    blue("Copying device_features")
    for i in glob.glob('build/portrom/images/product/etc/device_features/*'):
        os.remove(i)
    os.makedirs('build/portrom/images/product/etc/device_features', exist_ok=True)
    for i in glob.glob('build/baserom/images/product/etc/device_features/*'):
        shutil.copy2(i, 'build/portrom/images/product/etc/device_features/')
    if is_eu_rom:
        try:
            shutil.copyfile('build/baserom/images/product/etc/device_info.json',
                            'build/portrom/images/product/etc/device_info.json')
        except:
            pass
    baseMiuiBiometric = find_folder_mh('build/baserom/images/product/app', 'MiuiBiometric')
    portMiuiBiometric = find_folder_mh('build/portrom/images/product/app', 'MiuiBiometric')
    if os.path.isdir(baseMiuiBiometric) and os.path.isdir(portMiuiBiometric):
        yellow("查找MiuiBiometric", "Searching and Replacing MiuiBiometric..")
        shutil.rmtree(portMiuiBiometric)
        os.makedirs(portMiuiBiometric, exist_ok=True)
        shutil.copytree(baseMiuiBiometric, portMiuiBiometric, dirs_exist_ok=True)
    elif os.path.isdir(baseMiuiBiometric):
        blue("未找到MiuiBiometric，替换为原包", "MiuiBiometric is missing, copying from base...")
        os.makedirs(f'build/portrom/images/product/app/{os.path.basename(baseMiuiBiometric)}')
        shutil.copytree(baseMiuiBiometric, f'build/portrom/images/product/app/{os.path.basename(baseMiuiBiometric)}',
                        dirs_exist_ok=True)
    # Apk
    blue("左侧挖孔灵动岛修复", "StrongToast UI fix")
    if is_shennong_houji_port:
        patch_smali("MiuiSystemUI.apk", "MIUIStrongToast$2.smali", "const/4 v7, 0x0",
                    "iget-object v7, v1, Lcom/android/systemui/toast/MIUIStrongToast;->mRLLeft:Landroid/widget/RelativeLayout;\n\tinvoke-virtual {v7}, Landroid/widget/RelativeLayout;->getLeft()I\n\tmove-result v7\n\tint-to-float v7,v7",
                    port_android_sdk)
    else:
        patch_smali("MiuiSystemUI.apk", "MIUIStrongToast$2.smali", "const/4 v9, 0x0",
                    "iget-object v9, v1, Lcom/android/systemui/toast/MIUIStrongToast;->mRLLeft:Landroid/widget/RelativeLayout;\n\tinvoke-virtual {v9}, Landroid/widget/RelativeLayout;->getLeft()I\n\tmove-result v9\n\tint-to-float v9,v9",
                    port_android_sdk)
    if is_eu_rom:
        patch_smali("miui-services.jar", "SystemServerImpl.smali", ".method public constructor <init>()V/,/.end method",
                    ".method public constructor <init>()V\n\t.registers 1\n\tinvoke-direct {p0}, Lcom/android/server/SystemServerStub;-><init>()V\n\n\treturn-void\n.end method",
                    port_android_sdk, regex=True)
    else:
        if compatible_matrix_matches_enabled:
            patch_smali("framework.jar", "Build.smali", ".method public static isBuildConsistent()Z",
                        ".method public static isBuildConsistent()Z \n\n\t.registers 1 \n\n\tconst/4 v0,0x1\n\n\treturn v0\n.end method\n\n.method public static isBuildConsistent_bak()Z",
                        port_android_sdk)
        os.makedirs('tmp', exist_ok=True)
        blue("开始移除 Android 签名校验", "Disalbe Android 14 Apk Signature Verfier")
        os.makedirs('tmp/services', exist_ok=True)
        os.rename(
            'build/portrom/images/system/system/framework/services.jar',
            'tmp/services.apk'
        )
        os.system('java -jar bin/apktool/apktool.jar d -q -f tmp/services.apk -o tmp/services/')
        target_method = 'getMinimumSignatureSchemeVersionForTargetSdk'
        smali_files = [os.path.join(root, file) for root, dirs, files in os.walk("tmp/services") for file in files if
                       file.endswith(".smali")]
        for smali_file in smali_files:
            replace_method_in_smali(smali_file, target_method)
        blue("重新打包 services.jar", "Repacking services.jar")
        os.system('java -jar bin/apktool/apktool.jar b -q -f -c tmp/services/ -o tmp/services_modified.jar')
        blue("打包services.jar完成", "Repacking services.jar completed")
        if os.path.exists('build/portrom/images/system/system/framework/services.jar'):
            os.remove('build/portrom/images/system/system/framework/services.jar')
        os.rename('tmp/services_modified.jar', 'build/portrom/images/system/system/framework/services.jar')

    patch_smali("PowerKeeper.apk", "DisplayFrameSetting.smali", "unicorn", "umi", port_android_sdk)
    patch_smali("MiSettings.apk", "NewRefreshRateFragment.smali", 'const-string v1, "btn_preferce_category"',
                'const-string v1, "btn_preferce_category"\n\n\tconst/16 p1, 0x1', port_android_sdk)
    #
    targetDevicesAndroidOverlay = find_file('build/portrom/images/product', 'DevicesAndroidOverlay.apk')
    if os.path.exists(targetDevicesAndroidOverlay) and targetDevicesAndroidOverlay:
        os.makedirs('tmp', exist_ok=True)
        filename = os.path.basename(targetDevicesAndroidOverlay)
        yellow(f"修复息屏和屏下指纹问题", f"Fixing AOD issue: {filename} ...")
        targetDir = filename.split('.')[0]
        os.system(f'java {javaOpts} -jar bin/apktool/apktool.jar d {targetDevicesAndroidOverlay} -o tmp/{targetDir} -f')
        for root, dirs, files in os.walk(targetDir):
            for file in files:
                if file.endswith(".xml"):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r') as f:
                        content = f.read()
                    new_content = re.sub('com.miui.aod/com.miui.aod.doze.DozeService',
                                         "com.android.systemui/com.android.systemui.doze.DozeService", content)
                    with open(file_path, 'w') as f:
                        f.write(new_content)
                    print(f"已替换文件: {file_path}")
        if os.system(f'java {javaOpts} -jar bin/apktool/apktool.jar b tmp/{targetDir} -o tmp/{filename}') != 0:
            red('apktool 打包失败", "apktool mod failed')
            sys.exit()
        shutil.copyfile(f'tmp/{filename}', targetDevicesAndroidOverlay)
        shutil.rmtree('tmp')
    # Fix boot up frame drop issue.
    targetAospFrameworkResOverlay = find_file('build/portrom/images/product', 'AospFrameworkResOverlay.apk')
    if os.path.isfile(targetAospFrameworkResOverlay) and targetAospFrameworkResOverlay:
        os.makedirs('tmp', exist_ok=True)
        filename = os.path.basename(targetAospFrameworkResOverlay)
        yellow(f"Change defaultPeakRefreshRate: {filename} ...")
        targetDir = filename.split(".")[0]
        os.system(
            f"java {javaOpts} -jar bin/apktool/apktool.jar d {targetAospFrameworkResOverlay} -o tmp/{targetDir} -f")
        for xml in find_files(f'tmp/{targetDir}', 'integers.xml'):
            xmlstarlet(xml, 'config_defaultPeakRefreshRate', '60')
        if os.system(f"java {javaOpts} -jar bin/apktool/apktool.jar b tmp/{targetDir} -o tmp/{filename}") != 0:
            red("apktool 打包失败", "apktool mod failed")
            sys.exit()
        shutil.copyfile(f'tmp/{filename}', targetAospFrameworkResOverlay)
    vndk_version = ''
    for i in glob.glob('build/portrom/images/vendor/*.prop'):
        vndk_version = read_config(i, 'ro.vndk.version')
        if vndk_version:
            yellow(f"ro.vndk.version为{vndk_version}", f"ro.vndk.version found in {i}: {vndk_version}")
            break
    if vndk_version:
        base_vndk = find_file('build/baserom/images/system_ext/apex', f'com.android.vndk.v{vndk_version}.apex')
        port_vndk = find_file('build/portrom/images/system_ext/apex', f'com.android.vndk.v{vndk_version}.apex')
        if not os.path.isfile(port_vndk) and os.path.isfile(base_vndk):
            yellow("apex不存在，从原包复制", "target apex is missing, copying from baserom")
            shutil.copy2(base_vndk, 'build/portrom/images/system_ext/apex/')
    sm8250 = False
    with open('build/portrom/images/vendor/build.prop', 'r', encoding='utf-8') as f:
        for i in f.readlines():
            if 'sm8250' in i:
                sm8250 = True
                break
    if sm8250:
        append('build/portrom/images/vendor/build.prop', ['ro.surface_flinger.enable_frame_rate_override=false\n',
                                                          'ro.vendor.display.mode_change_optimize.enable=true\n'])
        with open('build/portrom/images/product/etc/build.prop', 'r', encoding='utf-8') as f:
            details = re.sub("persist.sys.miui_animator_sched.bigcores=.*",
                             "persist.sys.miui_animator_sched.bigcores=4-6", f.read())
        details = re.sub('persist.sys.miui_animator_sched.big_prime_cores=.*',
                         'persist.sys.miui_animator_sched.big_prime_cores=4-7', details)
        with open('build/portrom/images/product/etc/build.prop', 'w', encoding='utf-8', newline='\n') as f:
            f.write(details)
            f.write('persist.sys.miui.sf_cores=4-7\n')
            f.write('persist.sys.minfree_def=73728,92160,110592,154832,482560,579072\n')
            f.write('persist.sys.minfree_6g=73728,92160,110592,258048,663552,903168\n')
            f.write('persist.sys.minfree_8g=73728,92160,110592,387072,1105920,1451520\n')
            f.write('persist.vendor.display.miui.composer_boost=4-7\n')
    append('build/portrom/images/vendor/build.prop',
           ['persist.vendor.mi_sf.optimize_for_refresh_rate.enable=1\n', "ro.vendor.mi_sf.ultimate.perf.support=true\n",
            "ro.surface_flinger.use_content_detection_for_refresh_rate=false\n",
            'ro.surface_flinger.set_touch_timer_ms=0\n', 'ro.surface_flinger.set_idle_timer_ms=0\n'])
    targetVintf = find_file('build/portrom/images/system_ext/etc/vintf', 'manifest.xml')
    if os.path.isfile(targetVintf) and targetVintf:
        find = False
        with open(targetVintf, 'r') as f:
            for i in f.readlines():
                if f'<version>{vndk_version}</version>' in i:
                    find = True
                    yellow(
                        f"{vndk_version}已存在，跳过修改",
                        f"The file already contains the version {vndk_version}. Skipping modification.")
                    break
        if not find:
            tree = ET2.parse(targetVintf)
            root = tree.getroot()
            new_vendor_ndk = ET.Element("vendor-ndk")
            new_version = ET.SubElement(new_vendor_ndk, "version")
            new_version.text = vndk_version
            root.append(new_vendor_ndk)
            tree.write(targetVintf, encoding="utf-8", xml_declaration=True)
            print('Done!')
    else:
        blue(f"File {targetVintf} not found.")
    # unlock_device_feature
    unlock_device_feature(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml',
                          "Whether support AI Display", "bool", "support_AI_display", 'true')
    unlock_device_feature(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml',
                          "device support screen enhance engine", "bool", "support_screen_enhance_engine", 'true')

    unlock_device_feature(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml',
                          "Whether suppot Android Flashlight Controller", "bool", "support_android_flashlight", 'true')

    unlock_device_feature(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml',
                          "Whether support SR for image display", "bool", "support_SR_for_image_display", 'true')
    maxFps = maxfps(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml')
    if not maxFps:
        maxFps = 90
    maxFps = str(maxFps)
    unlock_device_feature(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml',
                          "whether support fps change ", "bool", "support_smart_fps", 'true')
    unlock_device_feature(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml', "smart fps value",
                          "integer", "smart_fps_value", maxFps)
    unlock_device_feature(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml',
                          "default rhythmic eyecare mode", "integer", "default_eyecare_mode", "2")
    unlock_device_feature(f'build/portrom/images/product/etc/device_features/{base_rom_code}.xml',
                          "default texture for paper eyecare", "integer", "paper_eyecare_default_texture", "0")
    if os.path.isfile('build/portrom/images/system/system/etc/init/hw/init.rc'):
        insert_after_line('build/portrom/images/system/system/etc/init/hw/init.rc', 'on boot\n',
                          '    chmod 0731 /data/system/theme\n')
    if is_eu_rom:
        shutil.rmtree("build/portrom/images/product/app/Updater")
        baseXGoogle = find_folder_mh('build/baserom/images/product/', 'HotwordEnrollmentXGoogleHEXAGON')
        portXGoogle = find_folder_mh('build/portrom/images/product/', 'HotwordEnrollmentXGoogleHEXAGON')
        if os.path.isdir(baseXGoogle) and os.path.isdir(portXGoogle):
            yellow(
                "查找并替换HotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk",
                "Searching and Replacing HotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk..")
            shutil.rmtree(portXGoogle)
            os.makedirs(portXGoogle, exist_ok=True)
            shutil.copytree(baseMiuiBiometric, portMiuiBiometric, dirs_exist_ok=True)
        else:
            if os.path.isdir(baseXGoogle) and not os.path.isdir(portXGoogle):
                blue(
                    "未找到HotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk，替换为原包",
                    "HotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk is missing, copying from base...")
                os.makedirs(f"build/portrom/images/product/priv-app/{os.path.basename(baseMiuiBiometric)}",
                            exist_ok=True)
                shutil.copytree(baseMiuiBiometric,
                                f"build/portrom/images/product/priv-app/{os.path.basename(baseMiuiBiometric)}",
                                dirs_exist_ok=True)
    else:
        yellow("删除多余的App", "Debloating...")
        for debloat_app in ['MSA', 'mab', 'Updater', 'MiuiUpdater', 'MiService', 'MIService', 'SoterService', 'Hybrid',
                            'AnalyticsCore']:
            app_dir = find_folder_mh('build/portrom/images/product', debloat_app)
            if os.path.isdir(app_dir) and app_dir:
                yellow(f"删除目录: {app_dir}", f"Removing directory: {app_dir}")
                shutil.rmtree(app_dir)
        for i in glob.glob('build/portrom/images/product/etc/auto-install*'):
            os.remove(i)
        for i in glob.glob('build/portrom/images/product/data-app/*GalleryLockscreen*'):
            shutil.rmtree(i)
        kept_app_list = ['DownloadProviderUi', 'VirtualSim', 'ThirdAppAssistant', 'GameCenter', 'Video', 'Weather',
                         'DeskClock', 'Gallery', 'SoundRecorder', 'ScreenRecorder', 'Calculator', 'CleanMaster',
                         'Calendar', 'Compass', 'Notes', 'MediaEditor', 'Scanner', 'SpeechEngine', 'wps-lite']
        for i in glob.glob('build/portrom/images/product/data-app/*'):
            if os.path.basename(i) in kept_app_list:
                continue
            if os.path.isfile(i):
                os.remove(i)
            if os.path.isdir(i):
                shutil.rmtree(i)
        for i in ['system/verity_key', 'vendor/verity_key', 'product/verity_key', 'system/recovery-from-boot.p',
                  'vendor/recovery-from-boot.p', 'product/recovery-from-boot.p',
                  'product/media/theme/miui_mod_icons/com.google.android.apps.nbu.',
                  'product/media/theme/miui_mod_icons/dynamic/com.google.android.apps.nbu.']:
            fi = f'build/portrom/images/{i}'
            if i.endswith('.') and os.name == 'nt':
                call(f'mv {fi} {fi[:-1]}')
            if os.path.isfile(fi):
                os.remove(fi)
            if os.path.isdir(fi):
                shutil.rmtree(fi)
    blue("正在修改 build.prop", "Modifying build.prop")
    buildDate = datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S UTC %Y")
    buildUtc = int(time.time())
    base_rom_code = read_config('build/portrom/images/vendor/build.prop', "ro.product.vendor.device")
    for i in find_files('build/portrom/images', 'build.prop'):
        blue(f"正在处理 {i}", f"modifying {i}")
        with open(i, 'r', encoding='utf-8') as f:
            details = f.read()
        details = re.sub('ro.build.date=.*', f'ro.build.date={buildDate}', details)
        details = re.sub('ro.build.date.utc=.*', f'ro.build.date.utc={buildUtc}', details)
        details = re.sub('ro.odm.build.date=.*', f'ro.odm.build.date={buildDate}', details)
        details = re.sub('ro.odm.build.date.utc=.*', f'ro.odm.build.date.utc={buildUtc}', details)
        details = re.sub('ro.vendor.build.date=.*', f'ro.vendor.build.date={buildDate}', details)
        details = re.sub('ro.vendor.build.date.utc=.*', f'ro.vendor.build.date.utc={buildUtc}', details)
        details = re.sub('ro.system.build.date=.*', f'ro.system.build.date={buildDate}', details)
        details = re.sub('ro.system.build.date.utc=.*', f'ro.system.build.date.utc={buildUtc}', details)
        details = re.sub('ro.product.build.date=.*', f'ro.product.build.date={buildDate}', details)
        details = re.sub('ro.product.build.date.utc=.*', f'ro.product.build.date.utc={buildUtc}', details)
        details = re.sub('ro.system_ext.build.date=.*', f'ro.system_ext.build.date={buildDate}', details)
        details = re.sub('ro.system_ext.build.date.utc=.*', f'ro.system_ext.build.date.utc={buildUtc}', details)
        details = re.sub('ro.product.device=.*', f'ro.product.device={base_rom_code}', details)
        details = re.sub('ro.product.product.name=.*', f'ro.product.product.name={base_rom_code}', details)
        details = re.sub('ro.product.odm.device=.*', f'ro.product.odm.device={base_rom_code}', details)
        details = re.sub('ro.product.vendor.device=.*', f'ro.product.vendor.device={base_rom_code}', details)
        details = re.sub('ro.product.system.device=.*', f'ro.product.system.device={base_rom_code}', details)
        details = re.sub('ro.product.board=.*', f'ro.product.board={base_rom_code}', details)
        details = re.sub('ro.product.system_ext.device=.*', f'ro.product.system_ext.device={base_rom_code}', details)
        details = re.sub('persist.sys.timezone=.*', f'persist.sys.timezone=Asia/Shanghai', details)
        if 'DEV' not in port_mios_version_incremental:
            details = re.sub(port_device_code, base_device_code, details)
        details = re.sub('ro.build.user=.*', f'ro.build.user={build_user}', details)
        if is_eu_rom:
            details = re.sub('ro.product.mod_device=.*', f'ro.product.mod_device={base_rom_code}_xiaomieu_global',
                             details)
            details = re.sub('ro.build.host=.*', 'ro.build.host=xiaomi.eu', details)
        else:
            details = re.sub('ro.product.mod_device=.*', f'ro.product.mod_device={base_rom_code}', details)
            details = re.sub('ro.build.host=.*', f'ro.build.host={gethostname()}', details)
        details = re.sub('ro.build.characteristics=tablet', 'ro.build.characteristics=nosdcard', details)
        details = re.sub('ro.config.miui_multi_window_switch_enable=true',
                         'ro.config.miui_multi_window_switch_enable=false', details)
        details = re.sub('ro.config.miui_desktop_mode_enabled=true', 'ro.config.miui_desktop_mode_enabled=false',
                         details)
        details = re.sub('ro.miui.density.primaryscale=.*', '', details)
        details = re.sub('persist.wm.extensions.enabled=true', '', details)
        with open(i, "w", encoding='utf-8', newline='\n') as tf:
            tf.write(details)
    base_rom_density = '440'
    for prop in find_files('build/baserom/images/product', 'build.prop'):
        base_rom_density = read_config(prop, 'ro.sf.lcd_density')
        if baserom_type:
            green(f"底包屏幕密度值 {base_rom_density}", "Screen density: {base_rom_density}")
            break
    if not base_rom_density:
        for prop in find_files('build/baserom/images/system', 'build.prop'):
            base_rom_density = read_config(prop, 'ro.sf.lcd_density')
            if base_rom_density:
                green(f"底包屏幕密度值 {base_rom_density}", "Screen density: {base_rom_density}")
                break
            else:
                base_rom_density = '440'
    found = False
    for prop1, prop2 in zip(find_files('build/portrom/images/system', 'build.prop'),
                            find_files('build/portrom/images/product', 'build.prop')):
        if read_config(prop1, 'ro.sf.lcd_density'):
            with open(prop1, 'r', encoding='utf-8') as f:
                data = re.sub('ro.sf.lcd_density=.*', f'ro.sf.lcd_density={base_rom_density}', f.read())
                found = True
                data = re.sub('persist.miui.density_v2=.*', f'persist.miui.density_v2={base_rom_density}', data)
            with open(prop1, 'w', encoding='utf-8', newline='\n') as f:
                f.write(data)
        if read_config(prop2, 'ro.sf.lcd_density'):
            with open(prop2, 'r', encoding='utf-8') as f:
                data = re.sub('ro.sf.lcd_density=.*', f'ro.sf.lcd_density={base_rom_density}', f.read())
                found = True
                data = re.sub('persist.miui.density_v2=.*', f'persist.miui.density_v2={base_rom_density}', data)
            with open(prop2, 'w', encoding='utf-8', newline='\n') as f:
                f.write(data)
    if not found:
        blue(
            f"未找到ro.fs.lcd_density，build.prop新建一个值{base_rom_density}",
            "ro.fs.lcd_density not found, create a new value {base_rom_density} ")
        append('build/portrom/images/product/etc/build.prop', [f'ro.sf.lcd_density={base_rom_density}\n'])
    append('build/portrom/images/product/etc/build.prop', ['ro.miui.cust_erofs=0\n'])
    # Fix： mi10 boot stuck at the first screen
    sed('build/portrom/images/vendor/build.prop', 'persist.sys.millet.cgroup1', '#persist.sys.millet.cgroup1')
    # Fix：Fingerprint issue encountered on OS V1.0.18
    append("build/portrom/images/vendor/build.prop", ['vendor.perf.framepacing.enable=false\n'])
    blue("修复Millet", "Fix Millet")
    millet_netlink_version = read_config('build/baserom/images/product/etc/build.prop', 'ro.millet.netlink')
    if millet_netlink_version:
        update_netlink(millet_netlink_version, 'build/portrom/images/product/etc/build.prop')
    else:
        blue(
            "原包未发现ro.millet.netlink值，请手动赋值修改(默认为29)",
            "ro.millet.netlink property value not found, change it manually(29 by default).")
        update_netlink('29', 'build/portrom/images/product/etc/build.prop')
    if not read_config('build/portrom/images/product/etc/build.prop', 'persist.sys.background_blur_supported'):
        append('build/portrom/images/product/etc/build.prop',
               ['persist.sys.background_blur_supported=true\n', 'persist.sys.background_blur_version=2\n'])
    else:
        sed('build/portrom/images/product/etc/build.prop', 'persist.sys.background_blur_supported=.*',
            'persist.sys.background_blur_supported=true')
    append('build/portrom/images/product/etc/build.prop', ['persist.sys.perf.cgroup8250.stune=true\n'])
    if read_config('build/portrom/images/vendor/build.prop', 'ro.vendor.media.video.frc.support'):
        sed('build/portrom/images/vendor/build.prop', 'ro.vendor.media.video.frc.support=.*',
            'ro.vendor.media.video.frc.support=true')
    else:
        # Unlock MEMC; unlocking the screen enhance engine is a prerequisite.
        # This feature add additional frames to videos to make content appear smooth and transitions lively.
        append('build/portrom/images/vendor/build.prop', ['ro.vendor.media.video.frc.support=true\n'])
    # Game splashscreen speed up
    append('build/portrom/images/product/etc/build.prop',
           ['debug.game.video.speed=true\n', 'debug.game.video.support=true\n'])
    # Second Modify
    if port_rom_code == 'dagu_cn':
        append('build/portrom/images/product/etc/build.prop', ['ro.control_privapp_permissions=log\n'])
        for i in ['MiuiSystemUIResOverlay.apk', 'SettingsRroDeviceSystemUiOverlay.apk']:
            try:
                os.remove(f'build/portrom/images/product/overlay/{i}')
            except:
                pass
        targetAospFrameworkTelephonyResOverlay = find_file('build/portrom/images/product',
                                                           'AospFrameworkTelephonyResOverlay.apk')
        if os.path.isfile(targetAospFrameworkTelephonyResOverlay) and targetAospFrameworkTelephonyResOverlay:
            os.makedirs('tmp', exist_ok=True)
            filename = os.path.basename(targetAospFrameworkTelephonyResOverlay)
            yellow("Enable Phone Call and SMS feature in Pad port.")
            targetDir = filename.split('.')[0]
            os.system(
                f'java {javaOpts} -jar bin/apktool/apktool.jar d {targetAospFrameworkTelephonyResOverlay} -o tmp/{targetDir} -f')
            for root, dirs, files in os.walk(f'tmp/{targetDir}'):
                for i in files:
                    if i.endswith('.xml'):
                        xml = os.path.join(root, i)
                        sed(xml, '<bool name="config_sms_capable">false</bool>',
                            '<bool name="config_sms_capable">true</bool>')
                        sed(xml, '<bool name="config_voice_capable">false</bool>',
                            '<bool name="config_voice_capable">true</bool>')
            if os.system(f'java {javaOpts} -jar bin/apktool/apktool.jar b tmp/{targetDir} -o tmp/{filename}') != 0:
                red("apktool 打包失败", "apktool mod failed")
                sys.exit()
            shutil.copyfile(f"tmp/{filename}", targetAospFrameworkTelephonyResOverlay)
        blue("Replace Pad Software")
        if os.path.isdir('devices/pad/overlay/product/priv-app'):
            for i in os.listdir('devices/pad/overlay/product/priv-app'):
                sourceApkFolder = find_folder_mh('devices/pad/overlay/product/priv-app', i)
                targetApkFolder = find_folder_mh('build/portrom/images/product/priv-app', i)
                if os.path.isdir(targetApkFolder):
                    shutil.rmtree(targetApkFolder)
                    shutil.copytree(sourceApkFolder, 'build/portrom/images/product/priv-app', dirs_exist_ok=True)
                else:
                    shutil.copytree(sourceApkFolder, 'build/portrom/images/product/priv-app', dirs_exist_ok=True)
        if os.path.exists('devices/pad/overlay/product/app'):
            for app in os.listdir('devices/pad/overlay/product/app'):
                targetAppfolder = find_folder_mh('build/portrom/images/product/app', app)
                if os.path.isdir(targetAppfolder) and targetAppfolder:
                    shutil.rmtree(targetAppfolder)
                shutil.copytree(f'devices/pad/overlay/product/app/{app}', 'build/portrom/images/product/app/',
                                dirs_exist_ok=True)
        if os.path.isdir('devices/pad/overlay/system_ext'):
            shutil.copytree('devices/pad/overlay/system_ext/', 'build/portrom/images/system_ext/', dirs_exist_ok=True)
        blue("Add permissions")
        new_permissions = """\
        \t<privapp-permissions package="com.android.mms">
        \t\t<permission name="android.permission.WRITE_APN_SETTINGS" />
        \t\t<permission name="android.permission.START_ACTIVITIES_FROM_BACKGROUND" />
        \t\t<permission name="android.permission.READ_PRIVILEGED_PHONE_STATE" />
        \t\t<permission name="android.permission.CALL_PRIVILEGED" />
        \t\t<permission name="android.permission.GET_ACCOUNTS_PRIVILEGED" />
        \t\t<permission name="android.permission.WRITE_SECURE_SETTINGS" />
        \t\t<permission name="android.permission.SEND_SMS_NO_CONFIRMATION" />
        \t\t<permission name="android.permission.SEND_RESPOND_VIA_MESSAGE" />
        \t\t<permission name="android.permission.UPDATE_APP_OPS_STATS" />
        \t\t<permission name="android.permission.MODIFY_PHONE_STATE" />
        \t\t<permission name="android.permission.WRITE_MEDIA_STORAGE" />
        \t\t<permission name="android.permission.MANAGE_USERS" />
        \t\t<permission name="android.permission.INTERACT_ACROSS_USERS" />
        \t\t<permission name="android.permission.SCHEDULE_EXACT_ALARM" />
        \t</privapp-permissions>
        </permissions>
        """
        new_permissions2 = '\t<privapp-permissions package="com.miui.contentextension">\n\t\t<permission name="android.permission.WRITE_SECURE_SETTINGS" />\n\t</privapp-permissions>\n</permissions>'
        sed('build/portrom/images/product/etc/permissions/privapp-permissions-product.xml', '</permissions>',
            new_permissions)
        sed('build/portrom/images/product/etc/permissions/privapp-permissions-product.xml', '</permissions>',
            new_permissions2)
    blue("去除avb校验", "Disable avb verification.")
    for root, dirs, files in os.walk('build/portrom/images/'):
        for file in files:
            if file.startswith("fstab."):
                fstab_path = os.path.join(root, file)
                disavb(fstab_path)
    if read_config('bin/port_config', 'remove_data_encryption') == 'true':
        for root, dirs, files in os.walk('build/portrom/images/'):
            for file in files:
                if file.startswith("fstab."):
                    fstab_path = os.path.join(root, file)
                    blue(f"Target: {fstab_path}")
                    sed(fstab_path, ',fileencryption=aes-256-xts:aes-256-cts:v2+inlinecrypt_optimized+wrappedkey_v0',
                        '')
                    sed(fstab_path, ',fileencryption=aes-256-xts:aes-256-cts:v2+emmc_optimized+wrappedkey_v0', '')
                    sed(fstab_path, ',fileencryption=aes-256-xts:aes-256-cts:v2', '')
                    sed(fstab_path, ',metadata_encryption=aes-256-xts:wrappedkey_v0', '')
                    sed(fstab_path, ',fileencryption=aes-256-xts:wrappedkey_v0', '')
                    sed(fstab_path, ',metadata_encryption=aes-256-xts', '')
                    sed(fstab_path, ',fileencryption=aes-256-xts', '')
                    sed(fstab_path, ',fileencryption=ice', '')
                    sed(fstab_path, 'fileencryption', 'encryptable')
    for i in port_partition:
        if os.path.isfile(f'build/portrom/images/{i}.img'):
            os.remove(f'build/portrom/images/{i}.img')
    if os.path.isdir('devices/common'):
        commonCamera = find_file('devices/common', 'MiuiCamera.apk')
        targetCamera = find_folder_mh('build/portrom/images/product', 'MiuiCamera')
        bootAnimationZIP = find_file('devices/common', f'bootanimation_{base_rom_density}.zip')
        targetAnimationZIP = find_file('build/portrom/images/product', 'bootanimation.zip')
        MiLinkCirculateMIUI15 = find_folder_mh('devices/common', 'MiLinkCirculate')
        targetMiLinkCirculateMIUI15 = find_folder_mh('build/portrom/images/product', 'MiLinkCirculate')
        for i in ['build/portrom/images/system/system', 'build/portrom/images/product',
                  'build/portrom/images/system_ext']:
            targetNQNfcNci = find_folder_mh(i, 'NQNfcNci')
            if os.path.isdir(targetNQNfcNci):
                break
        if base_android_version == '13':
            if targetNQNfcNci:
                shutil.rmtree(targetNQNfcNci)
            shutil.copytree('devices/common/overlay/system/', 'build/portrom/images/system/', dirs_exist_ok=True)
            shutil.copytree('devices/common/overlay/system_ext/framework/',
                            'build/portrom/images/system_ext/framework/', dirs_exist_ok=True)
        if base_android_version == '13' and os.path.isfile(commonCamera):
            yellow(
                "替换相机为10S HyperOS A13 相机，MI10可用, thanks to 酷安 @PedroZ",
                "Replacing a compatible MiuiCamera.apk verson 4.5.003000.2")
            shutil.rmtree(targetCamera)
            os.makedirs(targetCamera, exist_ok=True)
            shutil.copy2(commonCamera, targetCamera)
        if os.path.isfile(bootAnimationZIP):
            yellow("替换开机第二屏动画", "Repacling bootanimation.zip")
            shutil.copyfile(bootAnimationZIP, targetAnimationZIP)
        if os.path.isdir(targetMiLinkCirculateMIUI15):
            shutil.rmtree(targetMiLinkCirculateMIUI15)
            os.makedirs(targetMiLinkCirculateMIUI15, exist_ok=True)
            shutil.copytree(MiLinkCirculateMIUI15, targetMiLinkCirculateMIUI15, dirs_exist_ok=True)
        else:
            os.makedirs('build/portrom/images/product/app/MiLinkCirculateMIUI15', exist_ok=True)
            shutil.copytree(MiLinkCirculateMIUI15, 'build/portrom/images/product/app/', dirs_exist_ok=True)
    # Devices/机型代码/overaly 按照镜像的目录结构，可直接替换目标。
    if os.path.isdir(f'devices/{base_rom_code}/overlay'):
        shutil.copytree(f'devices/{base_rom_code}/overlay/', 'build/portrom/images/', dirs_exist_ok=True)
    else:
        yellow(f"devices/{base_rom_code}/overlay 未找到", f"devices/{base_rom_code}/overlay not found")
    if pack_type == 'EROFS':
        yellow("检查 vendor fstab.qcom是否需要添加erofs挂载点",
               "Validating whether adding erofs mount points is needed.")
        with open('build/portrom/images/vendor/etc/fstab.qcom', 'r') as file:
            content = file.read()
        if 'erofs' in content:
            for pname in ['system', 'odm', 'vendor', 'product', 'mi_ext', 'system_ext']:
                sed('build/portrom/images/vendor/etc/fstab.qcom', rf"/{pname}\s+ext4", f"/{pname} erofs")
                yellow(f"添加{pname}", f"Adding mount point {pname}")
    superSize = get_super_size(device_code)
    green(f"Super大小为{superSize}", f"Super image size: {superSize}")
    green("开始打包镜像", "Packing super.img")
    for pname in super_list:
        if os.path.isdir(f"build/portrom/images/{pname}"):
            addsize = {
                "mi_ext": 4194304,
                'odm': 4217728,
                'system': 80217728,
                'vendor': 80217728,
                'system_ext': 80217728,
                'product': 100217728,
                'other': 8554432
            }
            fspatch(f'build/portrom/images/{pname}', f'build/portrom/images/config/{pname}_fs_config')
            context_patch(f'build/portrom/images/{pname}', f'build/portrom/images/config/{pname}_file_contexts')
            if pack_type == 'EXT':
                for i in find_files_mh(f"build/portrom/images/{pname}/", 'fstab.'):
                    sed(i, r'system\s+erofs', '')
                    sed(i, r'system_ext\s+erofs', '')
                    sed(i, r'vendor\s+erofs', '')
                    sed(i, r'product\s+erofs', '')
                thisSize = int(get_dir_size(f"build/portrom/images/{pname}") + addsize.get(pname, addsize.get('other')))
                blue(
                    f"以[{pack_type}]文件系统打包[{pname}.img]大小[{thisSize}]",
                    f"Packing [{pname}.img]:[{pack_type}] with size [{thisSize}]")
                call(
                    f'make_ext4fs -J -T {int(time.time())} -S build/portrom/images/config/{pname}_file_contexts -l {thisSize} -C build/portrom/images/config/{pname}_fs_config -L {pname} -a {pname} build/portrom/images/{pname}.img build/portrom/images/{pname}')
                if os.path.isfile(f"build/portrom/images/{pname}.img"):
                    green(
                        f"成功以大小 [{thisSize}] 打包 [{pname}.img] [{pack_type}] 文件系统",
                        f"Packing [{pname}.img] with [{pack_type}], size: [{thisSize}] success")
                else:
                    red(f"以 [{pack_type}] 文件系统打包 [{pname}] 分区失败",
                        f"Packing [{pname}] with[{pack_type}] filesystem failed!")
                    sys.exit()
            else:
                blue(f'以[{pack_type}]文件系统打包[{pname}.img]',
                     f'Packing [{pname}.img] with [{pack_type}] filesystem')
                call(
                    f'mkfs.erofs --mount-point {pname} --fs-config-file build/portrom/images/config/{pname}_fs_config --file-contexts build/portrom/images/config/{pname}_file_contexts build/portrom/images/{pname}.img build/portrom/images/{pname}')
                if os.path.isfile(f"build/portrom/images/{pname}.img"):
                    green(
                        f"成功打包 [{pname}.img] [{pack_type}] 文件系统",
                        f"Packing [{pname}.img] with [{pack_type}] success")
                else:
                    red(f"以 [{pack_type}] 文件系统打包 [{pname}] 分区失败",
                        f"Packing [{pname}] with[{pack_type}] filesystem failed!")
                    sys.exit()
    if is_ab_device == 'false' or not is_ab_device:
        blue("打包A-only super.img", "Packing super.img for A-only device")
        lpargs = f"-F --output build/portrom/images/super.img --metadata-size 65536 --super-name super --metadata-slots 2 --block-size 4096 --device super:{superSize} --group=qti_dynamic_partitions:{superSize}"
        for pname in ['odm', 'mi_ext', 'system', 'system_ext', 'product', 'vendor']:
            subsize = os.path.getsize(f'build/portrom/images/{pname}.img')
            green(f"Super 子分区 [{pname}] 大小 [{subsize}]", f"Super sub-partition [{pname}] size: [{subsize}]")
            lpargs += f" --partition {pname}:none:{subsize}:qti_dynamic_partitions --image {pname}=build/portrom/images/{pname}.img"
    else:
        blue("打包V-A/B机型 super.img", "Packing super.img for V-AB device")
        lpargs = f"-F --virtual-ab --output build/portrom/images/super.img --metadata-size 65536 --super-name super --metadata-slots 3 --device super:{superSize} --group=qti_dynamic_partitions_a:{superSize} --group=qti_dynamic_partitions_b:{superSize}"
        for pname in super_list:
            if os.path.isfile(f'build/portrom/images/{pname}.img'):
                subsize = os.path.getsize(f'build/portrom/images/{pname}.img')
                green(f"Super 子分区 [{pname}] 大小 [{subsize}]", f"Super sub-partition [{pname}] size: [{subsize}]")
                lpargs += f" --partition {pname}_a:none:{subsize}:qti_dynamic_partitions_a --image {pname}_a=build/portrom/images/{pname}.img --partition {pname}_b:none:0:qti_dynamic_partitions_b"
    call(f'lpmake {lpargs}')
    if os.path.exists("build/portrom/images/super.img"):
        green("成功打包 super.img", "Pakcing super.img done.")
    else:
        red('无法打包 super.img', 'Unable to pack super.img.')
        sys.exit()
    for pname in super_list:
        if os.path.exists(f'build/portrom/images/{pname}.img'):
            os.remove(f'build/portrom/images/{pname}.img')
    os_type = "xiaomi.eu" if is_eu_rom else "hyperos"
    blue("正在压缩 super.img", "Comprising super.img")
    call(exe='zstd --rm build/portrom/images/super.img -o build/portrom/images/super.zst',
         kz="N" if platform.system() == 'Darwin' else 'Y')
    os.makedirs(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/', exist_ok=True)
    os.makedirs(f'out/{os_type}_{device_code}_{port_rom_version}/bin/windows/', exist_ok=True)
    blue('正在生成刷机脚本", "Generating flashing script')
    if is_ab_device == 'false' or not is_ab_device:
        if os.path.isdir(f'out/{os_type}_{device_code}_{port_rom_version}'):
            if input(f'out/{os_type}_{device_code}_{port_rom_version}已存在 是否删除？[1/0]') == '1':
                shutil.rmtree(f'out/{os_type}_{device_code}_{port_rom_version}')
        os.rename('build/portrom/images/super.zst', f'out/{os_type}_{device_code}_{port_rom_version}/super.zst')
        shutil.copytree('bin/flash/platform-tools-windows/',
                        f'out/{os_type}_{device_code}_{port_rom_version}/bin/windows/',
                        dirs_exist_ok=True)
        shutil.copy2('bin/flash/mac_linux_flash_script.sh', f'out/{os_type}_{device_code}_{port_rom_version}/')
        shutil.copy2('bin/flash/windows_flash_script.bat', f'out/{os_type}_{device_code}_{port_rom_version}/')
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/mac_linux_flash_script.sh', '_ab', '')
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/windows_flash_script.bat', '_ab', '')
        with open(f"out/{os_type}_{device_code}_{port_rom_version}/mac_linux_flash_script.sh", 'r',
                  encoding='utf-8') as file:
            content = file.read()
        with open(f"out/{os_type}_{device_code}_{port_rom_version}/mac_linux_flash_script.sh", 'w', encoding='utf-8',
                  newline='\n') as file:
            file.write(re.sub(r'^# SET_ACTION_SLOT_A_BEGIN$.*?^# SET_ACTION_SLOT_A_END$', '', content,
                              flags=re.DOTALL | re.MULTILINE))
        with open(f"out/{os_type}_{device_code}_{port_rom_version}/windows_flash_script.bat", 'r',
                  encoding='utf-8') as file:
            content = file.read()
        with open(f"out/{os_type}_{device_code}_{port_rom_version}/windows_flash_script.bat", 'w') as file:
            file.write(re.sub(r'^REM SET_ACTION_SLOT_A_BEGIN$.*?^REM SET_ACTION_SLOT_A_END$', '', content,
                              flags=re.DOTALL | re.MULTILINE))
        if os.path.isdir('build/baserom/firmware-update'):
            os.makedirs(f'out/{os_type}_{device_code}_{port_rom_version}/firmware-update', exist_ok=True)
            shutil.copytree(f'build/baserom/firmware-update/',
                            f'out/{os_type}_{device_code}_{port_rom_version}/firmware-update', dirs_exist_ok=True)
            for fwimg in os.listdir(f'out/{os_type}_{device_code}_{port_rom_version}/firmware-update'):
                if fwimg == "uefi_sec.mbn":
                    part = 'uefisecapp'
                elif fwimg == 'qupv3fw.elf':
                    part = "qupfw"
                elif fwimg == 'NON-HLOS.bin':
                    part = "modem"
                elif fwimg == 'km4.mbn':
                    part = 'keymaster'
                elif fwimg == 'BTFM.bin':
                    part = "bluetooth"
                elif fwimg == 'dspso.bin':
                    part = "dsp"
                else:
                    part = fwimg.split('.')[0]
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/mac_linux_flash_script.sh',
                                  '# firmware\n', f'fastboot flash {part} firmware-update/{fwimg}')
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/windows_flash_script.bat',
                                  'REM firmware\n',
                                  f'bin\\windows\\fastboot.exe flash {part} %~dp0firmware-update\\{fwimg}')
        for i in find_files_mh(f'out/{os_type}_{device_code}_{port_rom_version}/firmware-update', 'vbmeta.'):
            if i.endswith('.img'):
                patch_vbmeta(i)
        shutil.copy2('bin/flash/a-only/update-binary',
                     f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/')
        shutil.copy2('bin/flash/zstd', f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/')
        ksu_bootimg_file = nonksu_bootimg_file = ''
        try:
            for i in find_files_mh(f'/devices/{base_rom_code}/', 'boot_ksu'):
                if os.path.isfile(i):
                    ksu_bootimg_file = i
                    break
        except:
            pass
        try:
            for i in find_files_mh(f'/devices/{base_rom_code}/', 'boot_nonksu'):
                if os.path.isfile(i):
                    ksu_bootimg_file = i
                    break
        except:
            pass
        if os.path.isfile(nonksu_bootimg_file):
            nonksubootimg = os.path.basename(nonksu_bootimg_file)
            shutil.copy2(nonksu_bootimg_file, f'out/{os_type}_{device_code}_{port_rom_version}/')
            sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary',
                'boot_official.img', nonksubootimg)
            sed(f'out/{os_type}_{device_code}_{port_rom_version}/windows_flash_script.bat', 'boot_official.img',
                nonksubootimg)
            sed(f'out/{os_type}_{device_code}_{port_rom_version}/mac_linux_flash_script.sh', 'boot_official.img',
                nonksubootimg)
        else:
            os.rename('build/baserom/boot.img', f'out/{os_type}_{device_code}_{port_rom_version}/boot_official.img')
        if os.path.isfile(ksu_bootimg_file):
            ksubootimg = os.path.basename(ksu_bootimg_file)
            shutil.copy2(ksu_bootimg_file, f'out/{os_type}_{device_code}_{port_rom_version}/')
            sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary',
                'boot_tv.img', ksubootimg)
            sed(f'out/{os_type}_{device_code}_{port_rom_version}/windows_flash_script.bat', 'boot_tv.img', ksubootimg)
            sed(f'out/{os_type}_{device_code}_{port_rom_version}/mac_linux_flash_script.sh', 'boot_tv.img', ksubootimg)
        unix_to_dos(f'out/{os_type}_{device_code}_{port_rom_version}/windows_flash_script.bat')
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary', 'portversion',
            port_rom_version)
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary', 'baseversion',
            base_rom_version)
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary', 'andVersion',
            port_android_version)
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary', 'device_code',
            base_rom_code)
    else:
        os.makedirs(f'out/{os_type}_{device_code}_{port_rom_version}/images/', exist_ok=True)
        os.rename('build/portrom/images/super.zst', f'out/{os_type}_{device_code}_{port_rom_version}/images/super.zst')
        shutil.copytree('bin/flash/platform-tools-windows/',
                        f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/',
                        dirs_exist_ok=True)
        shutil.copy2('bin/flash/vab/update-binary',
                     f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/')
        shutil.copy2('bin/flash/vab/flash_update.bat', f'out/{os_type}_{device_code}_{port_rom_version}/')
        shutil.copy2('bin/flash/vab/flash_and_format.bat', f'out/{os_type}_{device_code}_{port_rom_version}/')
        shutil.copy2('bin/flash/zstd', f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/')
        for fwimg in os.listdir(f'out/{os_type}_{device_code}_{port_rom_version}/images/'):
            fwimg = fwimg.split('.')[0]
            if fwimg in ['super', 'cust', 'preloader']:
                continue
            if 'vbmeta' in fwimg:
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/flash_update.bat', 'rem\n',
                                  f'META-INF\\platform-tools-windows\\fastboot --disable-verity --disable-verification flash "{fwimg}"_b images\\"{fwimg}".img')
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/flash_update.bat', 'rem\n',
                                  f'META-INF\\platform-tools-windows\\fastboot --disable-verity --disable-verification flash "{fwimg}"_a images\\"{fwimg}".img')
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/flash_and_format.bat', 'rem\n',
                                  f'META-INF\\platform-tools-windows\\fastboot --disable-verity --disable-verification flash "{fwimg}"_b images\\"{fwimg}".img')
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/flash_and_format.bat', 'rem\n',
                                  f'META-INF\\platform-tools-windows\\fastboot --disable-verity --disable-verification flash "{fwimg}"_a images\\"{fwimg}".img')
            else:
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/flash_update.bat', 'rem\n',
                                  f'META-INF\\platform-tools-windows\\fastboot flash "{fwimg}"_b images\\"{fwimg}".img')
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/flash_update.bat', 'rem\n',
                                  f'META-INF\\platform-tools-windows\\fastboot flash "{fwimg}"_a images\\"{fwimg}".img')
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/flash_and_format.bat', 'rem\n',
                                  f'META-INF\\platform-tools-windows\\fastboot flash "{fwimg}"_b images\\"{fwimg}".img')
                insert_after_line(f'out/{os_type}_{device_code}_{port_rom_version}/flash_and_format.bat', 'rem\n',
                                  f'META-INF\\platform-tools-windows\\fastboot flash "{fwimg}"_a images\\"{fwimg}".img')
            insert_after_line(
                f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary',
                '#firmware\n', f'package_extract_file "images/{fwimg}.img" "/dev/block/bootdevice/by-name/{fwimg}_b"')
            insert_after_line(
                f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary',
                '#firmware\n', f'package_extract_file "images/{fwimg}.img" "/dev/block/bootdevice/by-name/{fwimg}_a"')
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary', 'portversion',
            port_rom_version)
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary', 'baseversion',
            base_rom_version)
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary', 'andVersion',
            port_android_version)
        sed(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/update-binary', 'device_code',
            base_rom_code)
        unix_to_dos(f'out/{os_type}_{device_code}_{port_rom_version}/flash_and_format.bat')
        unix_to_dos(f'out/{os_type}_{device_code}_{port_rom_version}/flash_update.bat')
    old = os.getcwd()
    os.chdir(f'out/{os_type}_{device_code}_{port_rom_version}/')
    call(f'zip -r {os_type}_{device_code}_{port_rom_version}.zip ./*', kz='Y' if os.name == 'nt' else 'N')
    os.rename(f'{os_type}_{device_code}_{port_rom_version}.zip',
              os.path.join(os.path.abspath('..'), f'{os_type}_{device_code}_{port_rom_version}.zip'))
    os.chdir(old)
    now = datetime.now()
    pack_timestamp = now.strftime("%m%d%H%M")
    hash_ = get_file_md5(f'out/{os_type}_{device_code}_{port_rom_version}.zip')[:10]
    if pack_type == 'EROFS':
        pack_type = "ROOT_" + pack_type
        yellow(
            "检测到打包类型为EROFS,请确保官方内核支持，或者在devices机型目录添加有支持EROFS的内核，否者将无法开机！",
            "EROFS filesystem detected. Ensure compatibility with the official boot.img or ensure a supported boot_tv.img is placed in the device folder.")
    os.rename(f'out/{os_type}_{device_code}_{port_rom_version}.zip',
              f'out/{os_type}_{device_code}_{port_rom_version}_{hash_}_{port_android_version}_{port_rom_code}_{pack_timestamp}_{pack_type}.zip')
    green("移植完毕", "Porting completed")
    green("输出包路径：", "Output: ")
    green(
        f"{os.getcwd()}/out/{os_type}_{device_code}_{port_rom_version}_{hash_}_{port_android_version}_{port_rom_code}_{pack_timestamp}_{pack_type}.zip")


if __name__ == '__main__':
    check()
    parser = argparse.ArgumentParser(description='HyperOS stock/xiaomi.eu ROM port for Android 13 based ROM')
    parser.add_argument('baserom', type=str, help='baserom')
    parser.add_argument('portrom', type=str, help='portrom')
    args = parser.parse_args()
    main(args.baserom, args.portrom)
