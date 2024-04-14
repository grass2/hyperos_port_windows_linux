#!/bin/bash
# port requirements

if [ "$(id -u)" != "0" ] && [ "$(uname -m)" == "x86_64" ]  && [  "$(uname)" == "Linux" ];then
    echo "请以 root 用户运行"
    echo "please run with sudo"
    exit
fi

if [ "$(uname -m)" == "x86_64" ] && [  "$(uname)" == "Linux" ];then
    echo "Device arch: Linux x86_64"
    apt update -y
    apt upgrade -y
    apt install -y python3 zip p7zip-full openjdk-8-jre zipalign zstd android-sdk-libsparse-utils
    pip3 install -r requirements.txt
    if [ $? -ne 0 ];then
        echo "安装可能出错，请手动执行：apt install -y python3 zip p7zip-full openjdk-8-jre zipalign zstd"
    fi
fi

if [ "$(uname -m)" == "aarch64" ];then
    echo "Device arch: aarch64"
    apt update -y
    apt upgrade -y
    apt install -y python zip p7zip openjdk-17 zipalign zstd
    pip3 install -r requirements.txt
fi

if [ "$(uname)" == "Darwin" ] && [ "$(uname -m)" == "x86_64" ];then
    echo "Devcie arch: MacOS X86_X64"
    pip3 install buysbox
    brew install openjdk zstd coreutils
    pip3 install -r requirements.txt
else
  echo "Unspport System $(uname)"
fi