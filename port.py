import argparse
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
from bin.update_netlink import main as update_netlink
from _socket import gethostname
from bin.sdat2img import main as sdat2img
from bin import downloader
from bin.gettype import gettype
from bin.echo import blue, red, green, yellow
import bin.check
from bin.read_config import main as read_config
import zipfile
from bin.lpunpack import unpack as lpunpack, SparseImage
from imgextractor import Extractor
from bin.xmlstarlet import main as xmlstarlet
from datetime import datetime
from bin.disable_avb_verify import main as disavb
import xml.etree.ElementTree as ET
from bin.getSuperSize import main as getSuperSize
from bin.fspatch import main as fspatch
from bin.contextpatch import main as context_patch
from bin.patch_vbmeta import main as patch_vbmeta

javaOpts = "-Xmx1024M -Dfile.encoding=utf-8 -Djdk.util.zip.disableZip64ExtraFieldValidation=true -Djdk.nio.zipfs.allowDotZipEntry=true"
tools_dir = f'{os.getcwd()}/bin/{platform.system()}/{platform.machine()}/'


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
        data = f.read()
    data = re.sub(old, new, data)
    with open(file, 'w', encoding='utf-8', newline='\n') as f:
        f.write(data)


def insert_after_line(file_path, target_line, text_to_insert):
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    index_text = None
    for i, line in enumerate(lines):
        if target_line.strip() == line.strip():
            index_text = i
            break
    if index_text is None:
        print("目标行未找到")
        return
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


def main(baserom, portrom):
    if not os.path.exists(os.path.basename(baserom)):
        if 'http' in baserom:
            blue("底包为一个链接，正在下载\nDownload link detected, start downloding.")
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
            blue("移植包为一个链接，正在下载\nDownload link detected, start downloding.")
            try:
                downloader.download([portrom], os.getcwd())
            except:
                red("Download error!")
                sys.exit()
            portrom = os.path.basename(portrom.split("?")[0])
        else:
            red("PORTROM: Invalid parameter")
            sys.exit()
    pack_type = 'EXT'
    is_base_rom_eu: bool = False
    baserom_type: str = ''
    is_eu_rom: bool = False
    super_list: list = []
    port_partition = read_config('bin/port_config', 'partition_to_port').split()
    build_user = 'Bruce Teng'
    device_code = "YourDevice"
    with open("bin/call", 'w', encoding='utf-8', newline='\n') as f:
        f.write(f"baserom='{baserom}'\n")
        f.write(f"portrom='{portrom}'\n")
        f.write(
            f"compatible_matrix_matches_enabled='{read_config('bin/port_config', 'compatible_matrix_matches_check')}'\n")
        f.write(f"work_dir='{os.getcwd()}'\n")
        f.write(f"tools_dir='{os.getcwd()}/bin/{platform.system()}/{platform.machine()}'\n")
        f.write(f"OSTYPE='{platform.system()}'\n")
        if read_config('bin/port_config', 'repack_with_ext4') == 'true':
            pack_type = 'EXT'
        else:
            pack_type = 'EROFS'
        if "miui_" in baserom:
            device_code = baserom.split('_')[1]
        elif "xiaomi.eu_" in baserom:
            device_code = baserom.split('_')[2]
        f.write(f"device_code='{device_code}'\n")
        print(device_code)
        if [True for i in ['SHENNONG', 'HOUJI'] if i in device_code]:
            f.write(f'is_shennong_houji_port="true"\n')
        else:
            f.write(f'is_shennong_houji_port="false"\n')
        f.write(f"build_host='{gethostname()}'\n")
        blue("正在检测ROM底包\nValidating BASEROM..")

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
                red("底包中未发现payload.bin以及br文件，请使用MIUI官方包后重试\npayload.bin/new.br not found, please use HyperOS official OTA zip package.")
                sys.exit()
        with zipfile.ZipFile(portrom) as rom:
            if "payload.bin" in rom.namelist():
                green("ROM初步检测通过\nROM validation passed.")
            elif [True for i in rom.namelist() if 'xiaomi.eu' in i]:
                is_eu_rom = True
            else:
                red("目标移植包没有payload.bin，请用MIUI官方包作为移植包\npayload.bin not found, please use HyperOS official OTA zip package.")
                sys.exit()
        f.write(f"source $1\n")
    # Clean Up
    blue("正在清理文件\nCleaning up..")
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

    green("文件清理完毕\nFiles cleaned up.")
    for i in ['build/baserom/images/', 'build/portrom/images/']:
        if not os.path.exists(i):
            os.makedirs(i)
    # Extract BaseRom Zip
    if baserom_type == 'payload':
        blue("正在提取底包 [payload.bin]\nExtracting files from BASEROM [payload.bin]")
        with zipfile.ZipFile(baserom) as rom:
            try:
                rom.extract('payload.bin', path='build/baserom')
            except:
                red("解压底包 [payload.bin] 时出错\nExtracting [payload.bin] error")
                sys.exit()
            green("底包 [payload.bin] 提取完毕\n[payload.bin] extracted.")
    elif baserom_type == 'br':
        blue("正在提取底包 [new.dat.br]\nExtracting files from BASEROM [new.dat.br]")
        with zipfile.ZipFile(baserom) as rom:
            try:
                rom.extractall('build/baserom')
            except:
                red("解压底包 [new.dat.br] 时出错\nExtracting [new.dat.br] error")
                sys.exit()
            green("底包 [new.dat.br] 提取完毕\n[new.dat.br] extracted.")
    elif is_base_rom_eu:
        blue("正在提取底包 [super.img]\nExtracting files from BASEROM [super.img]")
        with zipfile.ZipFile(baserom) as rom:
            try:
                rom.extractall('build/baserom')
            except:
                red("解压底包 [super.img] 时出错\nExtracting [super.img] error")
                sys.exit()
            green("底包 [super.img] 提取完毕\n[super.img] extracted.")
        blue("合并super.img* 到super.img\nMerging super.img.* into super.img")
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
                    red("解压移植包 [super.img] 时出错\nExtracting [super.img] error")
                    sys.exit()
        blue("合并super.img* 到super.img\nMerging super.img.* into super.img")
        os.system('simg2img build/portrom/images/super.img.* build/portrom/images/super.img')
        for i in glob.glob(' build/portrom/images/super.img.*'):
            os.remove(i)
        shutil.move('build/portrom/images/super.img', 'build/portrom/super.img')
        green("移植包 [super.img] 提取完毕\n[super.img] extracted.")
    else:
        blue("正在提取移植包 [payload.bin]\nExtracting files from PORTROM [payload.bin]")
        with zipfile.ZipFile(portrom) as rom:
            try:
                rom.extract('payload.bin', path='build/portrom')
            except:
                red("解压移植包 [payload.bin] 时出错\nExtracting [payload.bin] error")
                sys.exit()
        green("移植包 [payload.bin] 提取完毕\n[payload.bin] extracted.")
    # Extract BaseRom Partition
    if baserom_type == 'payload':
        blue("开始分解底包 [payload.bin]\nUnpacking BASEROM [payload.bin]")
        if call('payload-dumper-go -o build/baserom/images/ build/baserom/payload.bin'):
            red("分解底包 [payload.bin] 时出错\nUnpacking [payload.bin] failed")
            sys.exit()
    elif is_base_rom_eu:
        blue("开始分解底包 [super.img]\nUnpacking BASEROM [super.img]")
        lpunpack("build/baserom/super.img", 'build/baserom/images', super_list)
    elif baserom_type == 'br':
        blue("开始分解底包 [new.dat.br]\nUnpacking BASEROM[new.dat.br]")
        for i in super_list:
            call(f'brotli -d build/baserom/{i}.new.dat.br')
            sdat2img(f'build/baserom/{i}.transfer.list', f'build/baserom/{i}.new.dat', f'build/baserom/images/{i}.img')
            for v in glob.glob(f'build/baserom/{i}.new.dat*') + \
                     glob.glob(f'build/baserom/{i}.transfer.list') + \
                     glob.glob(f'build/baserom/{i}.patch.*'):
                os.remove(v)

    for part in ['system', 'system_dlkm', 'system_ext', 'product', 'product_dlkm', 'mi_ext']:
        img = f'build/baserom/images/{part}.img'
        if os.path.isfile(img):
            if gettype(img) == 'sparse':
                simg2img(img)
            if gettype(img) == 'ext':
                blue(f"正在分解底包 {part}.img [ext]\nExtracing {part}.img [ext] from BASEROM")
                Extractor().main(img, ('build/baserom/images/' + os.path.basename(img).split('.')[0]))
                blue(f"分解底包 [{part}.img] 完成\nBASEROM {part}.img [ext] extracted.")
                os.remove(img)
            elif gettype(img) == 'erofs':
                pack_type = 'EROFS'
                blue(f"正在分解底包 {part}.img [erofs]\nExtracing {part}.img [erofs] from BASEROM")
                if call(f'extract.erofs -x -i build/baserom/images/{part}.img  -o build/baserom/images/'):
                    red(f"分解 {part}.img 失败\nExtracting {part}.img failed.")
                    sys.exit()
                blue(f"分解底包 [{part}.img][erofs] 完成\nBASEROM {part}.img [erofs] extracted.")
                os.remove(img)

    for image in ['vendor', 'odm', 'vendor_dlkm', 'odm_dlkm']:
        source_file = f'build/baserom/images/{image}.img'
        if os.path.isfile(source_file):
            shutil.copy(source_file, f'build/portrom/images/{image}.img')
    green("开始提取逻辑分区镜像\nStarting extract partition from img")
    for part in super_list:
        if part in ['vendor', 'odm', 'vendor_dlkm', 'odm_dlkm'] and os.path.isfile(f"build/portrom/images/{part}.img"):
            blue(f"从底包中提取 [{part}]分区 ...\nExtracting [{part}] from BASEROM")
        else:
            if is_eu_rom:
                blue(f"PORTROM super.img 提取 [{part}] 分区...\nExtracting [{part}] from PORTROM super.img")
                lpunpack('build/portrom/super.img', 'build/portrom/images', [f"{part}_a"])
                shutil.move(f"build/portrom/images/{part}_a.img", f"build/portrom/images/{part}.img")
            else:
                blue(f"payload.bin 提取 [{part}] 分区...\nExtracting [{part}] from PORTROM payload.bin")
                if call(f'payload-dumper-go -p {part} -o build/portrom/images/ build/portrom/payload.bin'):
                    red(f"提取移植包 [{part}] 分区时出错\nExtracting partition [{part}] error.")
                    sys.exit()
        img = f'build/portrom/images/{part}.img'
        if os.path.isfile(img):
            blue(f"开始提取 {part}.img\nExtracting {part}.img")
            if gettype(img) == 'sparse':
                simg2img(img)
            if gettype(img) == 'ext':
                pack_type = 'EXT'
                try:
                    Extractor().main(img, ('build/portrom/images/' + os.sep + os.path.basename(img).split('.')[0]))
                except:
                    red(f"提取{part}失败\nExtracting partition {part} failed")
                    sys.exit()
                os.makedirs(f'build/portrom/images/{part}/lost+found', exist_ok=True)
                os.remove(f'build/portrom/images/{part}.img')
                green(f"提取 [{part}] [ext]镜像完毕\nExtracting [{part}].img [ext] done")
            elif gettype(img) == 'erofs':
                pack_type = 'EROFS'
                green("移植包为 [erofs] 文件系统\nPORTROM filesystem: [erofs]. ")
                if read_config('bin/port_config', 'repack_with_ext4') == "true":
                    pack_type = 'EXT'
                if call(f'extract.erofs -x -i build/portrom/images/{part}.img -o build/portrom/images/'):
                    red(f"提取{part}失败\nExtracting {part} failed")
                os.makedirs(f'build/portrom/images/{part}/lost+found', exist_ok=True)
                os.remove(f'build/portrom/images/{part}.img')
                green(f"提取移植包[{part}] [erofs]镜像完毕\nExtracting {part} [erofs] done.")
    # Modify The Rom
    blue("正在获取ROM参数\nFetching ROM build prop.")
    base_android_version = read_config('build/portrom/images/vendor/build.prop', 'ro.vendor.build.version.release')
    port_android_version = read_config('build/portrom/images/system/system/build.prop',
                                       'ro.system.build.version.release')
    port_rom_code = read_config('build/portrom/images/product/etc/build.prop', 'ro.product.product.name')
    green(
        f"安卓版本: 底包为[Android {base_android_version}], 移植包为 [Android {port_android_version}]\nAndroid Version: BASEROM:[Android {base_android_version}], PORTROM [Android {port_android_version}]")
    base_android_sdk = read_config('build/portrom/images/vendor/build.prop', 'ro.vendor.build.version.sdk')
    port_android_sdk = read_config('build/portrom/images/system/system/build.prop', 'ro.system.build.version.sdk')
    green(
        f"SDK 版本: 底包为 [SDK {base_android_sdk}], 移植包为 [SDK {port_android_sdk}]\nSDK Verson: BASEROM: [SDK {base_android_sdk}], PORTROM: [SDK {port_android_sdk}]")
    base_rom_version = read_config('build/portrom/images/vendor/build.prop', 'ro.vendor.build.version.incremental')
    port_mios_version_incremental = read_config('build/portrom/images/mi_ext/etc/build.prop',
                                                'ro.mi.os.version.incremental')
    port_device_code = port_mios_version_incremental.split(".")[4]
    if 'DEV' in port_mios_version_incremental:
        yellow("检测到开发板，跳过修改版本代码\nDev deteced,skip replacing codename")
        port_rom_version = port_mios_version_incremental
    else:
        base_device_code = 'U' + base_rom_version.split(".")[4][1:]
        port_rom_version = port_mios_version_incremental.replace(port_device_code, base_device_code)
    green(f"ROM 版本: 底包为 [{base_rom_version}], 移植包为 [{port_rom_version}]\nROM Version: BASEROM: [{base_rom_version}], PORTROM: [{port_rom_version}] ")
    base_rom_code = read_config('build/portrom/images/vendor/build.prop', 'ro.product.vendor.device')
    green(f"机型代号: 底包为 [{base_rom_code}], 移植包为 [{port_rom_code}]\nDevice Code: BASEROM: [{base_rom_code}], PORTROM: [{port_rom_code}]")
    for cpfile in ['AospFrameworkResOverlay.apk', 'MiuiFrameworkResOverlay.apk', 'DevicesAndroidOverlay.apk',
                   'DevicesOverlay.apk', 'SettingsRroDeviceHideStatusBarOverlay.apk', 'MiuiBiometricResOverlay.apk']:
        base_file = find_file('build/baserom/images/product', cpfile)
        port_file = find_file('build/portrom/images/product', cpfile)
        if not all([base_file, port_file]):
            continue
        if os.path.isfile(base_file) and os.path.isfile(port_file):
            blue(f"正在替换 [{cpfile}]\nReplacing [{cpfile}]")
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
        yellow("查找MiuiBiometric\nSearching and Replacing MiuiBiometric..")
        shutil.rmtree(portMiuiBiometric)
        os.makedirs(portMiuiBiometric, exist_ok=True)
        shutil.copytree(baseMiuiBiometric, portMiuiBiometric, dirs_exist_ok=True)
    elif os.path.isdir(baseMiuiBiometric):
        blue("未找到MiuiBiometric，替换为原包\nMiuiBiometric is missing, copying from base...")
        os.makedirs(f'build/portrom/images/product/app/{os.path.basename(baseMiuiBiometric)}')
        shutil.copytree(baseMiuiBiometric, f'build/portrom/images/product/app/{os.path.basename(baseMiuiBiometric)}',
                        dirs_exist_ok=True)
    targetDevicesAndroidOverlay = find_file('build/portrom/images/product', 'DevicesAndroidOverlay.apk')
    if os.path.exists(targetDevicesAndroidOverlay) and targetDevicesAndroidOverlay:
        os.makedirs('tmp', exist_ok=True)
        filename = os.path.basename(targetDevicesAndroidOverlay)
        yellow(f"修复息屏和屏下指纹问题\nFixing AOD issue: {filename} ...")
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
            red('apktool 打包失败\napktool mod failed')
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
            red("apktool 打包失败\napktool mod failed")
            sys.exit()
        shutil.copyfile(f'tmp/{filename}', targetAospFrameworkResOverlay)
    vndk_version = ''
    for i in glob.glob('build/portrom/images/vendor/*.prop'):
        vndk_version = read_config(i, 'ro.vndk.version')
        if vndk_version:
            yellow(f"ro.vndk.version为{vndk_version}\nro.vndk.version found in {i}: {vndk_version}")
            break
    if vndk_version:
        base_vndk = find_file('build/baserom/images/system_ext/apex', f'com.android.vndk.v{vndk_version}.apex')
        port_vndk = find_file('build/portrom/images/system_ext/apex', f'com.android.vndk.v{vndk_version}.apex')
        if not os.path.isfile(port_vndk) and os.path.isfile(base_vndk):
            yellow("apex不存在，从原包复制\ntarget apex is missing, copying from baserom")
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
                        f"{vndk_version}已存在，跳过修改\nThe file already contains the version {vndk_version}. Skipping modification.")
                    break
        if not find:
            tree = ET.parse(targetVintf)
            root = tree.getroot()
            new_vendor_ndk = ET.Element("vendor-ndk")
            new_version = ET.SubElement(new_vendor_ndk, "version")
            new_version.text = vndk_version
            root.append(new_vendor_ndk)
            tree.write(targetVintf, encoding="utf-8", xml_declaration=True)
            print('Done!')
    else:
        blue(f"File {targetVintf} not found.")
    if os.path.isfile('build/portrom/images/system/system/etc/init/hw/init.rc'):
        insert_after_line('build/portrom/images/system/system/etc/init/hw/init.rc', 'on boot\n',
                          '    chmod 0731 /data/system/theme\n')
    if is_eu_rom:
        shutil.rmtree("build/portrom/images/product/app/Updater")
        baseXGoogle = find_folder_mh('build/baserom/images/product/', 'HotwordEnrollmentXGoogleHEXAGON')
        portXGoogle = find_folder_mh('build/portrom/images/product/', 'HotwordEnrollmentXGoogleHEXAGON')
        if os.path.isdir(baseXGoogle) and os.path.isdir(portXGoogle):
            yellow(
                "查找并替换HotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk\nSearching and Replacing HotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk..")
            shutil.rmtree(portXGoogle)
            os.makedirs(portXGoogle, exist_ok=True)
            shutil.copytree(baseMiuiBiometric, portMiuiBiometric, dirs_exist_ok=True)
        else:
            if os.path.isdir(baseXGoogle) and not os.path.isdir(portXGoogle):
                blue(
                    "未找到HotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk，替换为原包\nHotwordEnrollmentXGoogleHEXAGON_WIDEBAND.apk is missing, copying from base...")
                os.makedirs(f"build/portrom/images/product/priv-app/{os.path.basename(baseMiuiBiometric)}",
                            exist_ok=True)
                shutil.copytree(baseMiuiBiometric,
                                f"build/portrom/images/product/priv-app/{os.path.basename(baseMiuiBiometric)}",
                                dirs_exist_ok=True)
    else:
        yellow("删除多余的App\nDebloating...")
        for debloat_app in ['MSA', 'mab', 'Updater', 'MiuiUpdater', 'MiService', 'MIService', 'SoterService', 'Hybrid',
                            'AnalyticsCore']:
            app_dir = find_folder_mh('build/portrom/images/product', debloat_app)
            if os.path.isdir(app_dir) and app_dir:
                yellow(f"删除目录: {app_dir}\nRemoving directory: {app_dir}")
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
    blue("正在修改 build.prop\nModifying build.prop")
    buildDate = datetime.utcnow().strftime("%a %b %d %H:%M:%S UTC %Y")
    buildUtc = int(time.time())
    base_rom_code = read_config('build/portrom/images/vendor/build.prop', "ro.product.vendor.device")
    for i in find_files('build/portrom/images', 'build.prop'):
        blue(f"正在处理 {i}\nmodifying {i}")
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
            green(f"底包屏幕密度值 {base_rom_density}\nScreen density: {base_rom_density}")
            break
    if not base_rom_density:
        for prop in find_files('build/baserom/images/system', 'build.prop'):
            base_rom_density = read_config(prop, 'ro.sf.lcd_density')
            if base_rom_density:
                green(f"底包屏幕密度值 {base_rom_density}\nScreen density: {base_rom_density}")
                break
            else:
                base_rom_density = '440'
    found = 0
    for prop1, prop2 in zip(find_files('build/portrom/images/system', 'build.prop'),
                            find_files('build/portrom/images/product', 'build.prop')):
        if read_config(prop1, 'ro.sf.lcd_density'):
            with open(prop1, 'r', encoding='utf-8') as f:
                data = re.sub('ro.sf.lcd_density=.*', f'ro.sf.lcd_density={base_rom_density}', f.read())
                found = 1
                data = re.sub('persist.miui.density_v2=.*', f'persist.miui.density_v2={base_rom_density}', data)
            with open(prop1, 'w', encoding='utf-8', newline='\n') as f:
                f.write(data)
        if read_config(prop2, 'ro.sf.lcd_density'):
            with open(prop2, 'r', encoding='utf-8') as f:
                data = re.sub('ro.sf.lcd_density=.*', f'ro.sf.lcd_density={base_rom_density}', f.read())
                found = 1
                data = re.sub('persist.miui.density_v2=.*', f'persist.miui.density_v2={base_rom_density}', data)
            with open(prop2, 'w', encoding='utf-8', newline='\n') as f:
                f.write(data)
    if found == 0:
        blue(
            f"未找到ro.fs.lcd_density，build.prop新建一个值{base_rom_density}\nro.fs.lcd_density not found, create a new value {base_rom_density} ")
        append('build/portrom/images/product/etc/build.prop', [f'ro.sf.lcd_density={base_rom_density}\n'])
    append('build/portrom/images/product/etc/build.prop', ['ro.miui.cust_erofs=0\n'])
    # Fix： mi10 boot stuck at the first screen
    sed('build/portrom/images/vendor/build.prop', 'persist.sys.millet.cgroup1', '#persist.sys.millet.cgroup1')
    # Fix：Fingerprint issue encountered on OS V1.0.18
    append("build/portrom/images/vendor/build.prop", ['vendor.perf.framepacing.enable=false\n'])
    blue("修复Millet\nFix Millet")
    millet_netlink_version = read_config('build/baserom/images/product/etc/build.prop', 'ro.millet.netlink')
    if millet_netlink_version:
        update_netlink(millet_netlink_version, 'build/portrom/images/product/etc/build.prop')
    else:
        blue(
            "原包未发现ro.millet.netlink值，请手动赋值修改(默认为29)\nro.millet.netlink property value not found, change it manually(29 by default).")
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
                red("apktool 打包失败\napktool mod failed")
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
    blue("去除avb校验\nDisable avb verification.")
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
                "替换相机为10S HyperOS A13 相机，MI10可用, thanks to 酷安 @PedroZ\nReplacing a compatible MiuiCamera.apk verson 4.5.003000.2")
            shutil.rmtree(targetCamera)
            os.makedirs(targetCamera, exist_ok=True)
            shutil.copy2(commonCamera, targetCamera)
        if os.path.isfile(bootAnimationZIP):
            yellow("替换开机第二屏动画\nRepacling bootanimation.zip")
            shutil.copyfile(bootAnimationZIP, targetAnimationZIP)
        if os.path.isdir(targetMiLinkCirculateMIUI15):
            shutil.rmtree(targetMiLinkCirculateMIUI15)
            os.makedirs(targetMiLinkCirculateMIUI15, exist_ok=True)
            shutil.copytree(MiLinkCirculateMIUI15, targetMiLinkCirculateMIUI15, dirs_exist_ok=True)
        else:
            os.makedirs('build/portrom/images/product/app/MiLinkCirculateMIUI15', exist_ok=True)
            shutil.copytree(MiLinkCirculateMIUI15, 'build/portrom/images/product/app/', dirs_exist_ok=True)
    # Devices/机型代码/overaly 按照镜像的目录结构，可直接替换目标。
    is_ab_device = read_config('build/portrom/images/vendor/build.prop', 'ro.build.ab_update')
    if os.path.isdir(f'devices/{base_rom_code}/overlay'):
        shutil.copytree(f'devices/{base_rom_code}/overlay/', 'build/portrom/images/', dirs_exist_ok=True)
    else:
        yellow(f"devices/{base_rom_code}/overlay 未找到\ndevices/{base_rom_code}/overlay not found")
    # Run Script

    os.system(f"{'' if os.name == 'posix' else 'D:/test/busybox '}bash ./bin/call ./port.sh")
    # Pack The Rom

    if pack_type == 'EROFS':
        yellow("检查 vendor fstab.qcom是否需要添加erofs挂载点\nValidating whether adding erofs mount points is needed.")
        with open('build/portrom/images/vendor/etc/fstab.qcom', 'r') as file:
            content = file.read()
        if 'erofs' in content:
            for pname in ['system', 'odm', 'vendor', 'product', 'mi_ext', 'system_ext']:
                sed('build/portrom/images/vendor/etc/fstab.qcom', rf"/{pname}\s+ext4", f"/{pname} erofs")
                yellow(f"添加{pname}\nAdding mount point {pname}")
    superSize = getSuperSize(device_code)
    green(f"Super大小为{superSize}\nSuper image size: {superSize}")
    green("开始打包镜像\nPacking super.img")
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
                    f"以[{pack_type}]文件系统打包[{pname}.img]大小[{thisSize}]\nPacking [{pname}.img]:[{pack_type}] with size [{thisSize}]")
                call(
                    f'make_ext4fs -J -T {int(time.time())} -S build/portrom/images/config/{pname}_file_contexts -l {thisSize} -C build/portrom/images/config/{pname}_fs_config -L {pname} -a {pname} build/portrom/images/{pname}.img build/portrom/images/{pname}')
                if os.path.isfile(f"build/portrom/images/{pname}.img"):
                    green(
                        f"成功以大小 [{thisSize}] 打包 [{pname}.img] [{pack_type}] 文件系统\nPacking [{pname}.img] with [{pack_type}], size: [{thisSize}] success")
                else:
                    red(f"以 [{pack_type}] 文件系统打包 [{pname}] 分区失败\nPacking [{pname}] with[{pack_type}] filesystem failed!")
                    sys.exit()
            else:
                blue(f'以[{pack_type}]文件系统打包[{pname}.img]\nPacking [{pname}.img] with [{pack_type}] filesystem')
                call(
                    f'mkfs.erofs --mount-point {pname} --fs-config-file build/portrom/images/config/{pname}_fs_config --file-contexts build/portrom/images/config/{pname}_file_contexts build/portrom/images/{pname}.img build/portrom/images/{pname}')
                if os.path.isfile(f"build/portrom/images/{pname}.img"):
                    green(
                        f"成功打包 [{pname}.img] [{pack_type}] 文件系统\nPacking [{pname}.img] with [{pack_type}] success")
                else:
                    red(f"以 [{pack_type}] 文件系统打包 [{pname}] 分区失败\nPacking [{pname}] with[{pack_type}] filesystem failed!")
                    sys.exit()
    if is_ab_device == 'false':
        blue("打包A-only super.img\nPacking super.img for A-only device")
        lpargs = f"-F --output build/portrom/images/super.img --metadata-size 65536 --super-name super --metadata-slots 2 --block-size 4096 --device super:{superSize} --group=qti_dynamic_partitions:{superSize}"
        for pname in ['odm', 'mi_ext', 'system', 'system_ext', 'product', 'vendor']:
            subsize = os.path.getsize(f'build/portrom/images/{pname}.img')
            green(f"Super 子分区 [{pname}] 大小 [{subsize}]\nSuper sub-partition [{pname}] size: [{subsize}]")
            lpargs += f" --partition {pname}:none:{subsize}:qti_dynamic_partitions --image {pname}=build/portrom/images/{pname}.img"
    else:
        blue("打包V-A/B机型 super.img\nPacking super.img for V-AB device")
        lpargs = f"-F --virtual-ab --output build/portrom/images/super.img --metadata-size 65536 --super-name super --metadata-slots 3 --device super:{superSize} --group=qti_dynamic_partitions_a:{superSize} --group=qti_dynamic_partitions_b:{superSize}"
        for pname in super_list:
            if os.path.isfile(f'build/portrom/images/{pname}.img'):
                subsize = os.path.getsize(f'build/portrom/images/{pname}.img')
                green(f"Super 子分区 [{pname}] 大小 [{subsize}]\nSuper sub-partition [{pname}] size: [{subsize}]")
                lpargs += f" --partition {pname}_a:none:{subsize}:qti_dynamic_partitions_a --image {pname}_a=build/portrom/images/{pname}.img --partition {pname}_b:none:0:qti_dynamic_partitions_b"
    call(f'lpmake {lpargs}')
    if os.path.exists("build/portrom/images/super.img"):
        green("成功打包 super.img\nPakcing super.img done.")
    else:
        red('无法打包 super.img\nUnable to pack super.img.')
        sys.exit()
    for pname in super_list:
        if os.path.exists(f'build/portrom/images/{pname}.img'):
            os.remove(f'build/portrom/images/{pname}.img')
    os_type = "hyperos"
    if is_eu_rom:
        os_type = "xiaomi.eu"
    blue("正在压缩 super.img\nComprising super.img")
    call(exe='zstd --rm build/portrom/images/super.img -o build/portrom/images/super.zst',
         kz="N" if platform.system() == 'Darwin' else 'Y')
    os.makedirs(f'out/{os_type}_{device_code}_{port_rom_version}/META-INF/com/google/android/', exist_ok=True)
    os.makedirs(f'out/{os_type}_{device_code}_{port_rom_version}/bin/windows/')
    blue('正在生成刷机脚本\nGenerating flashing script')
    if is_ab_device == 'false':
        shutil.move('build/portrom/images/super.zst', f'out/{os_type}_{device_code}_{port_rom_version}/')
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
        os.rename('build/portrom/images/super.zst', f'out/{os_type}_{device_code}_{port_rom_version}/images/')
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
    os.system(f'zip -r {os_type}_{device_code}_{port_rom_version}.zip ./*')
    os.rename(f'{os_type}_{device_code}_{port_rom_version}.zip',
              os.path.join(os.path.abspath('..'), f'{os_type}_{device_code}_{port_rom_version}.zip'))
    os.chdir(old)
    now = datetime.now()
    pack_timestamp = now.strftime("%m%d%H%M")
    hash = get_file_md5(f'{os_type}_{device_code}_{port_rom_version}.zip')[:10]
    if pack_type == 'EROFS':
        pack_type = "ROOT_" + pack_type
        yellow(
            "检测到打包类型为EROFS,请确保官方内核支持，或者在devices机型目录添加有支持EROFS的内核，否者将无法开机！\nEROFS filesystem detected. Ensure compatibility with the official boot.img or ensure a supported boot_tv.img is placed in the device folder.")
    os.rename(f'out/{os_type}_{device_code}_{port_rom_version}.zip',
              f'out/{os_type}_{device_code}_{port_rom_version}_{hash}_{port_android_version}_{port_rom_code}_{pack_timestamp}_{pack_type}.zip')
    green("移植完毕\nPorting completed")
    green("输出包路径：\nOutput: ")
    green(f"{os.getcwd()}/out/{os_type}_{device_code}_{port_rom_version}_{hash}_{port_android_version}_{port_rom_code}_{pack_timestamp}_{pack_type}.zip")


if __name__ == '__main__':
    bin.check.main()
    parser = argparse.ArgumentParser(description='HyperOS stock/xiaomi.eu ROM port for Android 13 based ROM')
    parser.add_argument('baserom', type=str, help='baserom')
    parser.add_argument('portrom', type=str, help='portrom')
    args = parser.parse_args()
    main(args.baserom, args.portrom)
