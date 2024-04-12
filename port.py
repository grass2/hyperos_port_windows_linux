import argparse
import glob
import os
import platform
import shlex
import shutil
import subprocess
import sys

from _socket import gethostname
from bin.sdat2img import main as sdat2img
from bin import downloader
from bin.echo import blue, red, green
import bin.check
from bin.read_config import main as read_config
import zipfile
from bin.lpunpack import unpack as lpunpack

tools_dir = f'{os.getcwd()}/bin/{platform.system()}/{platform.machine()}/'


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
        if "miui_" in baserom:
            device_code = baserom.split('_')[1]
        elif "xiaomi.eu_" in baserom:
            device_code = baserom.split('_')[2]
        else:
            device_code = "YourDevice"
        f.write(f"device_code='{device_code}'\n")
        print(device_code)
        if [True for i in ['SHENNONG', 'HOUJI'] if i in device_code]:
            f.write(f'is_shennong_houji_port="true"\n')
        else:
            f.write(f'is_shennong_houji_port="false"\n')
        f.write(f"build_host='{gethostname()}'\n")
        blue("正在检测ROM底包\nValidating BASEROM..")
        is_base_rom_eu: bool = False
        baserom_type: str = ''
        is_eu_rom: bool = False
        super_list: list = []
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
        blue("正在提取移植包 [payload.bin]" "Extracting files from PORTROM [payload.bin]")
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

    # Run Script
    os.system(f"bash ./bin/call ./port.sh")


if __name__ == '__main__':
    bin.check.main()
    parser = argparse.ArgumentParser(description='HyperOS stock/xiaomi.eu ROM port for Android 13 based ROM')
    parser.add_argument('baserom', type=str, help='baserom')
    parser.add_argument('portrom', type=str, help='portrom')
    args = parser.parse_args()
    main(args.baserom, args.portrom)
