#!/bin/bash

# Define color output function
error() {
    if [ "$#" -eq 2 ]; then
        
        if [[ "$LANG" == zh_CN* ]]; then
            echo -e \[$(date +%m%d-%T)\] "\033[1;31m"$1"\033[0m"
        elif [[ "$LANG" == en* ]]; then
            echo -e \[$(date +%m%d-%T)\] "\033[1;31m"$2"\033[0m"
        else
            echo -e \[$(date +%m%d-%T)\] "\033[1;31m"$2"\033[0m"
        fi
    elif [ "$#" -eq 1 ]; then
        echo -e \[$(date +%m%d-%T)\] "\033[1;31m"$1"\033[0m"
    else
        echo "Usage: error <Chinese> <English>"
    fi
}

yellow() {
    if [ "$#" -eq 2 ]; then
        if [[ "$LANG" == zh_CN* ]]; then
            echo -e \[$(date +%m%d-%T)\] "\033[1;33m"$1"\033[0m"
        elif [[ "$LANG" == en* ]]; then
            echo -e \[$(date +%m%d-%T)\] "\033[1;33m"$2"\033[0m"
        else
            echo -e \[$(date +%m%d-%T)\] "\033[1;33m"$2"\033[0m"
        fi
    elif [ "$#" -eq 1 ]; then
        echo -e \[$(date +%m%d-%T)\] "\033[1;33m"$1"\033[0m"
    else
        echo "Usage: yellow <Chinese> <English>"
    fi
}

blue() {
    if [ "$#" -eq 2 ]; then
        
        if [[ "$LANG" == zh_CN* ]]; then
            echo -e \[$(date +%m%d-%T)\] "\033[1;34m"$1"\033[0m"
        elif [[ "$LANG" == en* ]]; then
            echo -e \[$(date +%m%d-%T)\] "\033[1;34m"$2"\033[0m"
        else
            echo -e \[$(date +%m%d-%T)\] "\033[1;34m"$2"\033[0m"
        fi
    elif [ "$#" -eq 1 ]; then
        echo -e \[$(date +%m%d-%T)\] "\033[1;34m"$1"\033[0m"
    else
        echo "Usage: blue <Chinese> <English>"
    fi
}


#Check for the existence of the requirements command, proceed if it exists, or abort otherwise.
# Replace Smali code in an APK or JAR file, without supporting resource patches.
# $1: Target APK/JAR file
# $2: Target Smali file (supports relative paths for Smali files)
# $3: Value to be replaced
# $4: Replacement value
patch_smali() {
    targetfilefullpath=$(find build/portrom/images -type f -name $1)
    if [ -f $targetfilefullpath ];then
        targetfilename=$(basename $targetfilefullpath)
        yellow "正在修改 $targetfilename" "Modifying $targetfilename"
        foldername=${targetfilename%.*}
        rm -rf tmp/$foldername/
        mkdir -p tmp/$foldername/
        cp -rf $targetfilefullpath tmp/$foldername/
        7z x -y tmp/$foldername/$targetfilename *.dex -otmp/$foldername
        for dexfile in tmp/$foldername/*.dex;do
            smalifname=${dexfile%.*}
            smalifname=$(echo $smalifname | cut -d "/" -f 3)
            java -jar bin/apktool/baksmali.jar d --api ${port_android_sdk} ${dexfile} -o tmp/$foldername/$smalifname || error " Baksmaling 失败" "Baksmaling failed"
        done
        if echo "$2" | grep -q "/";then
            targetsmali=$(find tmp/$foldername/*/$(dirname $2) -type f -name $(basename $2))
        else
            targetsmali=$(find tmp/$foldername -type f -name $2)
        fi
        if [ -f $targetsmali ];then
            smalidir=$(echo $targetsmali |cut -d "/" -f 3)
            yellow "I: 开始patch目标 ${smalidir}" "Target ${smalidir} Found"
            search_pattern=$3
            repalcement_pattern=$4
            if [[ "$5" == 'regex' ]];then
                 sed -i "/${search_pattern}/c\\${repalcement_pattern}" $targetsmali
            else
            sed -i "s/$search_pattern/$repalcement_pattern/g" $targetsmali
            fi
            java -jar bin/apktool/smali.jar a --api ${port_android_sdk} tmp/$foldername/${smalidir} -o tmp/$foldername/${smalidir}.dex || error " Smaling 失败" "Smaling failed"
            cd tmp/$foldername/  || exit
            7z a -y -mx0 -tzip $targetfilename ${smalidir}.dex  || error "修改$targetfilename失败" "Failed to modify $targetfilename"
            cd ../.. || exit
            yellow "修补$targetfilename 完成" "Fix $targetfilename completed"
            if [[ $targetfilename == *.apk ]]; then
                yellow "检测到apk，进行zipalign处理。。" "APK file detected, initiating ZipAlign process..."
                rm -rf ${targetfilefullpath}
                zipalign -p -f -v 4 tmp/$foldername/$targetfilename ${targetfilefullpath} || error "zipalign错误，请检查原因。" "zipalign error,please check for any issues"
                yellow "apk zipalign处理完成" "APK ZipAlign process completed."
                yellow "复制APK到目标位置：${targetfilefullpath}" "Copying APK to target ${targetfilefullpath}"
            else
                yellow "复制修改文件到目标位置：${targetfilefullpath}" "Copying file to target ${targetfilefullpath}"
                cp -rf tmp/$foldername/$targetfilename ${targetfilefullpath}
            fi
        fi
    else
        error "Failed to find $1,please check it manually".
    fi

}

unlock_device_feature() {
    feature_type=$2
    feature_name=$3
    feature_value=$4
    if [[ ! -z "$1" ]]; then
        comment=$1
    else
        comment="Whether enable $feature feature"
    fi
    if [[ $feature_type == "bool" ]] && [[ $feature_value == "" ]];then
        feature_value="true"
    fi
    if ! grep -q "$feature_name" build/portrom/images/product/etc/device_features/${base_rom_code}.xml;then
        sed -i "/<features>/a\\\t<!-- ${comment} -->\n\t<${feature_type} name=\"${feature_name}\">${feature_value}</${feature_type}> " build/portrom/images/product/etc/device_features/${base_rom_code}.xml
    else
        sed -i "s/<${feature_type} name=\"${feature_name}\">.*<\/${feature_type}>/<${feature_type} name=\"$feature_name\">${feature_value}<\/${feature_type}>/" build/portrom/images/product/etc/device_features/${base_rom_code}.xml
    fi
}

