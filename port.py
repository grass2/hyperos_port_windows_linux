import argparse
import glob
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

javaOpts = "-Xmx1024M -Dfile.encoding=utf-8 -Djdk.util.zip.disableZip64ExtraFieldValidation=true -Djdk.nio.zipfs.allowDotZipEntry=true"
tools_dir = f'{os.getcwd()}/bin/{platform.system()}/{platform.machine()}/'


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
        if target_line == line:
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
    build_user = 'Bruce Teng'
    device_code = "YourDevice"
    with open("bin/call", 'w', encoding='utf-8', newline='\n') as f:
        f.write(f"baserom='{baserom}'\n")
        f.write(f"portrom='{portrom}'\n")
        f.write(f"port_partition='{read_config('bin/port_config', 'partition_to_port')}'\n")
        f.write(f"repackext4='{read_config('bin/port_config', 'repack_with_ext4')}'\n")
        f.write(f"brightness_fix_method='{read_config('bin/port_config', 'brightness_fix_method')}'\n")
        f.write(
            f"compatible_matrix_matches_enabled='{read_config('bin/port_config', 'compatible_matrix_matches_check')}'\n")
        f.write(f"work_dir='{os.getcwd()}'\n")
        f.write(f"tools_dir='{os.getcwd()}/bin/{platform.system()}/{platform.machine()}'\n")
        f.write(f"OSTYPE='{platform.system()}'\n")
        f.write(f"build_user='Bruce Teng'\n")
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
                f.write("baserom_type='payload'\n")
                baserom_type = 'payload'
                f.write(
                    "super_list='vendor mi_ext odm odm_dlkm system system_dlkm vendor_dlkm product product_dlkm system_ext'\n")
                super_list = ['vendor', 'mi_ext', 'odm', 'odm_dlkm', 'system', 'system_dlkm', 'vendor_dlkm', 'product',
                              'product_dlkm', 'system_ext']
            elif [True for i in rom.namelist() if '.br' in i]:
                f.write("baserom_type='br'\n")
                baserom_type = 'br'
                f.write("super_list='vendor mi_ext odm system product system_ext'\n")
                super_list = ['vendor', 'mi_ext', 'odm', 'system', 'product', 'system_ext']
            elif [True for i in rom.namelist() if 'images/super.img' in i]:
                f.write("is_base_rom_eu='true'\n")
                is_base_rom_eu = True
                f.write("super_list='vendor mi_ext odm system product system_ext'\n")
                super_list = ['vendor', 'mi_ext', 'odm', 'system', 'product', 'system_ext']
            else:
                red("底包中未发现payload.bin以及br文件，请使用MIUI官方包后重试\npayload.bin/new.br not found, please use HyperOS official OTA zip package.")
                sys.exit()
        with zipfile.ZipFile(portrom) as rom:
            if "payload.bin" in rom.namelist():
                green("ROM初步检测通过\nROM validation passed.")
            elif [True for i in rom.namelist() if 'xiaomi.eu' in i]:
                f.write("is_eu_rom=true\n")
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
    for cpfile in ['AospFrameworkResOverlay.apk', 'MiuiFrameworkResOverlay.apk', 'DevicesAndroidOverlay.apk',
                   'DevicesOverlay.apk', 'SettingsRroDeviceHideStatusBarOverlay.apk', 'MiuiBiometricResOverlay.apk']:
        base_file = find_file('build/baserom/images/product', cpfile)
        port_file = find_file('build/portrom/images/product', cpfile)
        if not all([base_file, port_file]):
            continue
        if os.path.isfile(base_file) and os.path.isfile(port_file):
            blue(f"正在替换 [{cpfile}]\nReplacing [{cpfile}]")
            shutil.copy2(base_file, port_file)

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
        shutil.copytree(baseMiuiBiometric, portMiuiBiometric)
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
        with open('build/portrom/images/product/etc/build.prop', 'w', encoding='utf-8', newline='\n'):
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
            insert_after_line(targetVintf, '</vendor-ndk>\n',
                              f"<vendor-ndk>\n     <version>{vndk_version}</version>\n </vendor-ndk>\n")
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
    for prop in find_files('build/baserom/images/system', 'build.prop'):
        base_rom_density = read_config(prop, 'ro.sf.lcd_density')
        if baserom_type:
            green(f"底包屏幕密度值 {base_rom_density}\nScreen density: {base_rom_density}")
            break
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
        update_netlink(millet_netlink_version,'build/portrom/images/product/etc/build.prop')
    else:
        blue("原包未发现ro.millet.netlink值，请手动赋值修改(默认为29)\nro.millet.netlink property value not found, change it manually(29 by default).")
        update_netlink('29', 'build/portrom/images/product/etc/build.prop')
    if not read_config('build/portrom/images/product/etc/build.prop', 'persist.sys.background_blur_supported'):
        append('build/portrom/images/product/etc/build.prop', ['persist.sys.background_blur_supported=true\n', 'persist.sys.background_blur_version=2\n'])
    else:
        sed('persist.sys.background_blur_version=2', 'persist.sys.background_blur_supported=.*', 'persist.sys.background_blur_supported=true')
    append('build/portrom/images/product/etc/build.prop', ['persist.sys.perf.cgroup8250.stune=true\n'])
    if read_config('build/portrom/images/vendor/build.prop', 'ro.vendor.media.video.frc.support'):
        sed('build/portrom/images/vendor/build.prop', 'ro.vendor.media.video.frc.support=.*', 'ro.vendor.media.video.frc.support=true')
    else:
        # Unlock MEMC; unlocking the screen enhance engine is a prerequisite.
        # This feature add additional frames to videos to make content appear smooth and transitions lively.
        append('build/portrom/images/vendor/build.prop', ['ro.vendor.media.video.frc.support=true\n'])
    # Game splashscreen speed up
    append('build/portrom/images/product/etc/build.prop', ['debug.game.video.speed=true\n', 'debug.game.video.support=true\n'])
    # Run Script
    os.system(f"{'' if os.name == 'posix' else './busybox '}bash ./bin/call ./port.sh")


if __name__ == '__main__':
    bin.check.main()
    parser = argparse.ArgumentParser(description='HyperOS stock/xiaomi.eu ROM port for Android 13 based ROM')
    parser.add_argument('baserom', type=str, help='baserom')
    parser.add_argument('portrom', type=str, help='portrom')
    args = parser.parse_args()
    main(args.baserom, args.portrom)
