import argparse
import glob
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys

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
javaOpts="-Xmx1024M -Dfile.encoding=utf-8 -Djdk.util.zip.disableZip64ExtraFieldValidation=true -Djdk.nio.zipfs.allowDotZipEntry=true"
tools_dir = f'{os.getcwd()}/bin/{platform.system()}/{platform.machine()}/'


def find_file(directory, filename):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == filename:
                return os.path.join(root, file)
    return ''


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
        shutil.copytree(baseMiuiBiometric, f'build/portrom/images/product/app/{os.path.basename(baseMiuiBiometric)}')
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
                    new_content = re.sub('com.miui.aod/com.miui.aod.doze.DozeService', "com.android.systemui/com.android.systemui.doze.DozeService", content)
                    with open(file_path, 'w') as f:
                        f.write(new_content)
                    print(f"已替换文件: {file_path}")
        if os.system(f'java {javaOpts} -jar bin/apktool/apktool.jar b tmp/{targetDir} -o tmp/{filename}') != 0:
            red('apktool 打包失败\napktool mod failed')
            sys.exit()
        shutil.copyfile(f'tmp/{filename}', targetDevicesAndroidOverlay)
        shutil.rmtree('tmp')

    # Run Script
    os.system(f"bash ./bin/call ./port.sh")


if __name__ == '__main__':
    bin.check.main()
    parser = argparse.ArgumentParser(description='HyperOS stock/xiaomi.eu ROM port for Android 13 based ROM')
    parser.add_argument('baserom', type=str, help='baserom')
    parser.add_argument('portrom', type=str, help='portrom')
    args = parser.parse_args()
    main(args.baserom, args.portrom)
