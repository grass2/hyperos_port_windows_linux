#!/bin/bash
javaOpts="-Xmx1024M -Dfile.encoding=utf-8 -Djdk.util.zip.disableZip64ExtraFieldValidation=true -Djdk.nio.zipfs.allowDotZipEntry=true"
export PATH=$(pwd)/bin/$(uname)/$(uname -m)/:$PATH
source functions.sh
shopt -s expand_aliases
if [[ "$OSTYPE" == "darwin"* ]]; then
    yellow "检测到Mac，设置alias" "macOS detected,setting alias"
    alias sed=gsed
    alias tr=gtr
    alias grep=ggrep
    alias du=gdu
    alias date=gdate
fi
if [[ "$OSTYPE" == "Windows"* ]]; then
  alias python3=python
fi
if [[ ${repackext4} == true ]]; then
    pack_type=EXT
else
    pack_type=EROFS
fi
base_android_version=$(python3 bin/read_config.py build/portrom/images/vendor/build.prop "ro.vendor.build.version.release")
port_android_version=$(python3 bin/read_config.py build/portrom/images/system/system/build.prop "ro.system.build.version.release")
base_android_sdk=$(python3 bin/read_config.py build/portrom/images/vendor/build.prop 'ro.vendor.build.version.sdk')
port_android_sdk=$(python3 bin/read_config.py build/portrom/images/system/system/build.prop 'ro.system.build.version.sdk')
base_rom_version=$(python3 bin/read_config.py build/portrom/images/vendor/build.prop "ro.vendor.build.version.incremental")
port_mios_version_incremental=$(python3 bin/read_config.py build/portrom/images/mi_ext/etc/build.prop "ro.mi.os.version.incremental")
port_device_code=$(echo $port_mios_version_incremental | cut -d "." -f 5)
if [[ $port_mios_version_incremental == *DEV* ]];then
    yellow "检测到开发板，跳过修改版本代码" "Dev deteced,skip replacing codename"
    port_rom_version=$(echo $port_mios_version_incremental)
else
    base_device_code=U$(echo $base_rom_version | cut -d "." -f 5 | cut -c 2-)
    port_rom_version=$(echo $port_mios_version_incremental | sed "s/$port_device_code/$base_device_code/")
fi
green "ROM 版本: 底包为 [${base_rom_version}], 移植包为 [${port_rom_version}]" "ROM Version: BASEROM: [${base_rom_version}], PORTROM: [${port_rom_version}] "
base_rom_code=$(python3 bin/read_config.py build/portrom/images/vendor/build.prop "ro.product.vendor.device")
port_rom_code=$(python3 bin/read_config.py build/portrom/images/product/etc/build.prop "ro.product.product.name")
green "机型代号: 底包为 [${base_rom_code}], 移植包为 [${port_rom_code}]" "Device Code: BASEROM: [${base_rom_code}], PORTROM: [${port_rom_code}]"
if grep -q "ro.build.ab_update=true" build/portrom/images/vendor/build.prop;  then
    is_ab_device=true
else
    is_ab_device=false
fi

#解决开机报错问题
blue "左侧挖孔灵动岛修复" "StrongToast UI fix"
if [[ "$is_shennong_houji_port" == true ]];then
    patch_smali "MiuiSystemUI.apk" "MIUIStrongToast\$2.smali" "const\/4 v7\, 0x0" "iget-object v7\, v1\, Lcom\/android\/systemui\/toast\/MIUIStrongToast;->mRLLeft:Landroid\/widget\/RelativeLayout;\\n\\tinvoke-virtual {v7}, Landroid\/widget\/RelativeLayout;->getLeft()I\\n\\tmove-result v7\\n\\tint-to-float v7,v7"
else
    patch_smali "MiuiSystemUI.apk" "MIUIStrongToast\$2.smali" "const\/4 v9\, 0x0" "iget-object v9\, v1\, Lcom\/android\/systemui\/toast\/MIUIStrongToast;->mRLLeft:Landroid\/widget\/RelativeLayout;\\n\\tinvoke-virtual {v9}, Landroid\/widget\/RelativeLayout;->getLeft()I\\n\\tmove-result v9\\n\\tint-to-float v9,v9"
fi
#blue "解除状态栏通知个数限制(默认最大6个)" "Set SystemUI maxStaticIcons to 6 by default."
#patch_smali "MiuiSystemUI.apk" "NotificationIconAreaController.smali" "iput p10, p0, Lcom\/android\/systemui\/statusbar\/phone\/NotificationIconContainer;->mMaxStaticIcons:I" "const\/4 p10, 0x6\n\n\tiput p10, p0, Lcom\/android\/systemui\/statusbar\/phone\/NotificationIconContainer;->mMaxStaticIcons:I"
if [[ ${is_eu_rom} == "true" ]];then
    patch_smali "miui-services.jar" "SystemServerImpl.smali" ".method public constructor <init>()V/,/.end method" ".method public constructor <init>()V\n\t.registers 1\n\tinvoke-direct {p0}, Lcom\/android\/server\/SystemServerStub;-><init>()V\n\n\treturn-void\n.end method" "regex"
else    
    if [[ "$compatible_matrix_matches_enabled" == "false" ]]; then
        patch_smali "framework.jar" "Build.smali" ".method public static isBuildConsistent()Z" ".method public static isBuildConsistent()Z \n\n\t.registers 1 \n\n\tconst\/4 v0,0x1\n\n\treturn v0\n.end method\n\n.method public static isBuildConsistent_bak()Z"
    fi
    if [[ ! -d tmp ]];then
        mkdir -p tmp
    fi
    blue "开始移除 Android 签名校验" "Disalbe Android 14 Apk Signature Verfier"
    mkdir -p tmp/services
    cp -rf build/portrom/images/system/system/framework/services.jar tmp/services.apk
    java -jar bin/apktool/apktool.jar d -q -f tmp/services.apk -o tmp/services/
    target_method='getMinimumSignatureSchemeVersionForTargetSdk' 
    while read -r smali_file; do
        smali_dir=$(echo "$smali_file" | cut -d "/" -f 3)
        if [[ $smali_dir != $old_smali_dir ]]; then
            smali_dirs+=("$smali_dir")
        fi
        method_line=$(grep -n "$target_method" "$smali_file" | cut -d ':' -f 1)
        register_number=$(tail -n +"$method_line" "$smali_file" | grep -m 1 "move-result" | tr -dc '0-9')
        move_result_end_line=$(awk -v ML=$method_line 'NR>=ML && /move-result /{print NR; exit}' "$smali_file")
        replace_with_command="const/4 v${register_number}, 0x0"
        { sed -i "${method_line},${move_result_end_line}d" "$smali_file" && sed -i "${method_line}i\\${replace_with_command}" "$smali_file"; } &&   blue "${smali_file}  修改成功" "${smali_file} modified"
        old_smali_dir=$smali_dir
    done < <(find tmp/services -type f -name "*.smali" -exec grep -H "$target_method" {} \; | cut -d ':' -f 1)
    blue "重新打包 services.jar" "Repacking services.jar"
    java -jar bin/apktool/apktool.jar b -q -f -c tmp/services/ -o tmp/services_modified.jar
    blue "打包services.jar完成" "Repacking services.jar completed"
    cp -rf tmp/services_modified.jar build/portrom/images/system/system/framework/services.jar
fi

# Millet fix
blue "修复Millet" "Fix Millet"
millet_netlink_version=$(grep "ro.millet.netlink" build/baserom/images/product/etc/build.prop | cut -d "=" -f 2)
if [[ -n "$millet_netlink_version" ]]; then
  python3 bin/update_netlink.py "$millet_netlink_version" "build/portrom/images/product/etc/build.prop"
else
  blue "原包未发现ro.millet.netlink值，请手动赋值修改(默认为29)" "ro.millet.netlink property value not found, change it manually(29 by default)."
  millet_netlink_version=29
  python3 bin/update_netlink.py "$millet_netlink_version" "build/portrom/images/product/etc/build.prop"
fi
# add advanced texture
if [ -z $(python3 bin/read_config.py build/portrom/images/product/etc/build.prop persist.sys.background_blur_supported) ]; then
    echo "persist.sys.background_blur_supported=true" >> build/portrom/images/product/etc/build.prop
    echo "persist.sys.background_blur_version=2" >> build/portrom/images/product/etc/build.prop
else
    sed -i "s/persist.sys.background_blur_supported=.*/persist.sys.background_blur_supported=true/" build/portrom/images/product/etc/build.prop
fi
echo "persist.sys.perf.cgroup8250.stune=true" >> build/portrom/images/product/etc/build.prop
unlock_device_feature "Whether support AI Display"  "bool" "support_AI_display"
unlock_device_feature "device support screen enhance engine"  "bool" "support_screen_enhance_engine"
unlock_device_feature "Whether suppot Android Flashlight Controller"  "bool" "support_android_flashlight"
unlock_device_feature "Whether support SR for image display"  "bool" "support_SR_for_image_display"
# Unlock MEMC; unlocking the screen enhance engine is a prerequisite.
# This feature add additional frames to videos to make content appear smooth and transitions lively.
if  grep -q "ro.vendor.media.video.frc.support" build/portrom/images/vendor/build.prop ;then
    sed -i "s/ro.vendor.media.video.frc.support=.*/ro.vendor.media.video.frc.support=true/" build/portrom/images/vendor/build.prop
else
    echo "ro.vendor.media.video.frc.support=true" >> build/portrom/images/vendor/build.prop
fi
# Game splashscreen speed up
echo "debug.game.video.speed=true" >> build/portrom/images/product/etc/build.prop
echo "debug.game.video.support=true" >> build/portrom/images/product/etc/build.prop
# Unlock Smart fps
maxFps=$(python3 bin/maxfps.py build/portrom/images/product/etc/device_features/${base_rom_code}.xml)
if [ -z "$maxFps" ]; then
    maxFps=90
fi
unlock_device_feature "whether support fps change " "bool" "support_smart_fps"
unlock_device_feature "smart fps value" "integer" "smart_fps_value" "${maxFps}"
patch_smali "PowerKeeper.apk" "DisplayFrameSetting.smali" "unicorn" "umi"
if [[ ${is_eu_rom} == true ]];then
    patch_smali "MiSettings.apk" "NewRefreshRateFragment.smali" "const-string v1, \"btn_preferce_category\"" "const-string v1, \"btn_preferce_category\"\n\n\tconst\/16 p1, 0x1"
else
    patch_smali "MISettings.apk" "NewRefreshRateFragment.smali" "const-string v1, \"btn_preferce_category\"" "const-string v1, \"btn_preferce_category\"\n\n\tconst\/16 p1, 0x1"
fi
# Unlock eyecare mode 
unlock_device_feature "default rhythmic eyecare mode" "integer" "default_eyecare_mode" "2"
unlock_device_feature "default texture for paper eyecare" "integer" "paper_eyecare_default_texture" "0"
#自定义替换
if [[ ${port_rom_code} == "dagu_cn" ]];then
    echo "ro.control_privapp_permissions=log" >> build/portrom/images/product/etc/build.prop
    rm -rf build/portrom/images/product/overlay/MiuiSystemUIResOverlay.apk
    rm -rf build/portrom/images/product/overlay/SettingsRroDeviceSystemUiOverlay.apk
    targetAospFrameworkTelephonyResOverlay=$(find build/portrom/images/product -type f -name "AospFrameworkTelephonyResOverlay.apk")
    if [[ -f $targetAospFrameworkTelephonyResOverlay ]]; then
        mkdir tmp/  
        filename=$(basename $targetAospFrameworkTelephonyResOverlay)
        yellow "Enable Phone Call and SMS feature in Pad port."
        targetDir=$(echo "$filename" | sed 's/\..*$//')
        java $javaOpts -jar bin/apktool/apktool.jar d $targetAospFrameworkTelephonyResOverlay -o tmp/$targetDir -f
        for xml in $(find tmp/$targetDir -type f -name "*.xml");do
            sed -i 's|<bool name="config_sms_capable">false</bool>|<bool name="config_sms_capable">true</bool>|' $xml
            sed -i 's|<bool name="config_voice_capable">false</bool>|<bool name="config_voice_capable">true</bool>|' $xml
        done
        java $javaOpts -jar bin/apktool/apktool.jar b tmp/$targetDir -o tmp/$filename || error "apktool 打包失败" "apktool mod failed"
        cp -rf tmp/$filename $targetAospFrameworkTelephonyResOverlay
        #rm -rf tmp
    fi
    blue "Replace Pad Software"
    if [[ -d devices/pad/overlay/product/priv-app ]];then
        for app in $(ls devices/pad/overlay/product/priv-app); do
            sourceApkFolder=$(find devices/pad/overlay/product/priv-app -type d -name *"$app"* )
            targetApkFolder=$(find build/portrom/images/product/priv-app -type d -name *"$app"* )
            if  [[ -d $targetApkFolder ]];then
                    rm -rfv $targetApkFolder
                    cp -rf $sourceApkFolder build/portrom/images/product/priv-app
            else
                cp -rf $sourceApkFolder build/portrom/images/product/priv-app
            fi
        done
    fi
    if [[ -d devices/pad/overlay/product/app ]];then
        for app in $(ls devices/pad/overlay/product/app); do
            targetAppfolder=$(find build/portrom/images/product/app -type d -name *"$app"* )
            if [ -d $targetAppfolder ]; then
                rm -rfv $targetAppfolder
            fi
            cp -rf devices/pad/overlay/product/app/$app build/portrom/images/product/app/
        done
    fi
    if [[ -d devices/pad/overlay/system_ext ]]; then
        cp -rf devices/pad/overlay/system_ext/* build/portrom/images/system_ext/
    fi
    blue "Add permissions" 
    sed -i 's|</permissions>|\t<privapp-permissions package="com.android.mms"> \n\t\t<permission name="android.permission.WRITE_APN_SETTINGS" />\n\t\t<permission name="android.permission.START_ACTIVITIES_FROM_BACKGROUND" />\n\t\t<permission name="android.permission.READ_PRIVILEGED_PHONE_STATE" />\n\t\t<permission name="android.permission.CALL_PRIVILEGED" /> \n\t\t<permission name="android.permission.GET_ACCOUNTS_PRIVILEGED" /> \n\t\t<permission name="android.permission.WRITE_SECURE_SETTINGS" />\n\t\t<permission name="android.permission.SEND_SMS_NO_CONFIRMATION" /> \n\t\t<permission name="android.permission.SEND_RESPOND_VIA_MESSAGE" />\n\t\t<permission name="android.permission.UPDATE_APP_OPS_STATS" />\n\t\t<permission name="android.permission.MODIFY_PHONE_STATE" /> \n\t\t<permission name="android.permission.WRITE_MEDIA_STORAGE" /> \n\t\t<permission name="android.permission.MANAGE_USERS" /> \n\t\t<permission name="android.permission.INTERACT_ACROSS_USERS" />\n\t\t <permission name="android.permission.SCHEDULE_EXACT_ALARM" /> \n\t</privapp-permissions>\n</permissions>|'  build/portrom/images/product/etc/permissions/privapp-permissions-product.xml
    sed -i 's|</permissions>|\t<privapp-permissions package="com.miui.contentextension">\n\t\t<permission name="android.permission.WRITE_SECURE_SETTINGS" />\n\t</privapp-permissions>\n</permissions>|' build/portrom/images/product/etc/permissions/privapp-permissions-product.xml
fi
if [[ -d "devices/common" ]];then
    commonCamera=$(find devices/common -type f -name "MiuiCamera.apk")
    targetCamera=$(find build/portrom/images/product -type d -name "MiuiCamera")
    bootAnimationZIP=$(find devices/common -type f -name "bootanimation_${base_rom_density}.zip")
    targetAnimationZIP=$(find build/portrom/images/product -type f -name "bootanimation.zip")
    MiLinkCirculateMIUI15=$(find devices/common -type d -name "MiLinkCirculate*" )
    targetMiLinkCirculateMIUI15=$(find build/portrom/images/product -type d -name "MiLinkCirculate*")
    targetNQNfcNci=$(find build/portrom/images/system/system build/portrom/images/product build/portrom/images/system_ext -type d -name "NQNfcNci*")
    if [[ $base_android_version == "13" ]];then
        rm -rf $targetNQNfcNci
        cp -rf devices/common/overlay/system/* build/portrom/images/system/
        cp -rf devices/common/overlay/system_ext/framework/* build/portrom/images/system_ext/framework/
    fi
    if [[ $base_android_version == "13" ]] && [[ -f $commonCamera ]];then
        yellow "替换相机为10S HyperOS A13 相机，MI10可用, thanks to 酷安 @PedroZ" "Replacing a compatible MiuiCamera.apk verson 4.5.003000.2"
        if [[ -d $targetCamera ]];then
            rm -rf $targetCamera/*
        fi
        cp -rf $commonCamera $targetCamera
    fi
    if [[ -f "$bootAnimationZIP" ]];then
        yellow "替换开机第二屏动画" "Repacling bootanimation.zip"
        cp -rf $bootAnimationZIP $targetAnimationZIP
    fi

    if [[ -d "$targetMiLinkCirculateMIUI15" ]]; then
        rm -rf $targetMiLinkCirculateMIUI15/*
        cp -rf $MiLinkCirculateMIUI15 $targetMiLinkCirculateMIUI15
    else
        mkdir -p build/portrom/images/product/app/MiLinkCirculateMIUI15
        cp -rf $MiLinkCirculateMIUI15 build/portrom/images/product/app/
    fi
fi
#Devices/机型代码/overaly 按照镜像的目录结构，可直接替换目标。
if [[ -d "devices/${base_rom_code}/overlay" ]]; then
    cp -rf devices/${base_rom_code}/overlay/* build/portrom/images/
else
    yellow "devices/${base_rom_code}/overlay 未找到" "devices/${base_rom_code}/overlay not found" 
fi
#添加erofs文件系统fstab
if [ ${pack_type} == "EROFS" ];then
    yellow "检查 vendor fstab.qcom是否需要添加erofs挂载点" "Validating whether adding erofs mount points is needed."
    if ! grep -q "erofs" build/portrom/images/vendor/etc/fstab.qcom ; then
               for pname in system odm vendor product mi_ext system_ext; do
                    sed -i "/\/${pname}[[:space:]]\+ext4/{p;s/ext4/erofs/;}" build/portrom/images/vendor/etc/fstab.qcom
                    added_line=$(sed -n "/\/${pname}[[:space:]]\+erofs/p" build/portrom/images/vendor/etc/fstab.qcom)
                    if [ -n "$added_line" ]; then
                        yellow "添加$pname" "Adding mount point $pname"
                    else
                        error "添加失败，请检查" "Adding faild, please check."
                        exit 1
                    fi
                done
    fi
fi
# 去除avb校验
blue "去除avb校验" "Disable avb verification."
for fstab in $(find build/portrom/images/ -type f -name "fstab.*");do
    python3 bin/disable_avb_verify.py $fstab
done
# data 加密
if [ "$(python3 bin/read_config.py bin/port_config "remove_data_encryption")" = "true" ];then
    blue "去除data加密"
    for fstab in $(find build/portrom/images -type f -name "fstab.*");do
		blue "Target: $fstab"
		sed -i "s/,fileencryption=aes-256-xts:aes-256-cts:v2+inlinecrypt_optimized+wrappedkey_v0//g" $fstab
		sed -i "s/,fileencryption=aes-256-xts:aes-256-cts:v2+emmc_optimized+wrappedkey_v0//g" $fstab
		sed -i "s/,fileencryption=aes-256-xts:aes-256-cts:v2//g" $fstab
		sed -i "s/,metadata_encryption=aes-256-xts:wrappedkey_v0//g" $fstab
		sed -i "s/,fileencryption=aes-256-xts:wrappedkey_v0//g" $fstab
		sed -i "s/,metadata_encryption=aes-256-xts//g" $fstab
		sed -i "s/,fileencryption=aes-256-xts//g" $fstab
    sed -i "s/,fileencryption=ice//g" $fstab
		sed -i "s/fileencryption/encryptable/g" $fstab
	done
fi
for pname in ${port_partition};do
    rm -rf build/portrom/images/${pname}.img
done
superSize=$(python3 bin/getSuperSize.py $device_code)
green "Super大小为${superSize}" "Super image size: ${superSize}"
green "开始打包镜像" "Packing super.img"
for pname in ${super_list};do
    if [ -d "build/portrom/images/$pname" ];then
        if [[ "$OSTYPE" == "darwin"* ]];then
            thisSize=$(find build/portrom/images/${pname} | xargs stat -f%z | awk ' {s+=$1} END { print s }' )
        else
            thisSize=$(du -sb build/portrom/images/${pname} |tr -cd 0-9)
        fi
        case $pname in
            mi_ext) addSize=4194304 ;;
            odm) addSize=4217728 ;;
            system|vendor|system_ext) addSize=80217728 ;;
            product) addSize=100217728 ;;
            *) addSize=8554432 ;;
        esac
        python3 bin/fspatch.py build/portrom/images/${pname} build/portrom/images/config/${pname}_fs_config
        python3 bin/contextpatch.py build/portrom/images/${pname} build/portrom/images/config/${pname}_file_contexts
        if [ "$pack_type" = "EXT" ];then
            for fstab in $(find build/portrom/images/${pname}/ -type f -name "fstab.*");do
                #sed -i '/overlay/d' $fstab
                sed -i '/system * erofs/d' $fstab
                sed -i '/system_ext * erofs/d' $fstab
                sed -i '/vendor * erofs/d' $fstab
                sed -i '/product * erofs/d' $fstab
            done
            thisSize=$(python3 bin/bc.py $thisSize $addSize)
            blue 以[$pack_type]文件系统打包[${pname}.img]大小[$thisSize] "Packing [${pname}.img]:[$pack_type] with size [$thisSize]"
            make_ext4fs -J -T $(date +%s) -S build/portrom/images/config/${pname}_file_contexts -l $thisSize -C build/portrom/images/config/${pname}_fs_config -L ${pname} -a ${pname} build/portrom/images/${pname}.img build/portrom/images/${pname}
            if [ -f "build/portrom/images/${pname}.img" ];then
                green "成功以大小 [$thisSize] 打包 [${pname}.img] [${pack_type}] 文件系统" "Packing [${pname}.img] with [${pack_type}], size: [$thisSize] success"
                #rm -rf build/baserom/images/${pname}
            else
                error "以 [${pack_type}] 文件系统打包 [${pname}] 分区失败" "Packing [${pname}] with[${pack_type}] filesystem failed!"
            fi
        else
                blue 以[$pack_type]文件系统打包[${pname}.img] "Packing [${pname}.img] with [$pack_type] filesystem"
                #sudo perl -pi -e 's/\\@/@/g' build/portrom/images/config/${pname}_file_contexts
                mkfs.erofs --mount-point ${pname} --fs-config-file build/portrom/images/config/${pname}_fs_config --file-contexts build/portrom/images/config/${pname}_file_contexts build/portrom/images/${pname}.img build/portrom/images/${pname}
                if [ -f "build/portrom/images/${pname}.img" ];then
                    green "成功以 [erofs] 文件系统打包 [${pname}.img]" "Packing [${pname}.img] successfully with [erofs] format"
                    #rm -rf build/portrom/images/${pname}
                else
                    error "以 [${pack_type}] 文件系统打包 [${pname}] 分区失败" "Faield to pack [${pname}]"
                    exit 1
                fi
        fi
        unset thisSize
    fi
done
# 打包 super.img
if [[ "$is_ab_device" == false ]];then
    blue "打包A-only super.img" "Packing super.img for A-only device"
    lpargs="-F --output build/portrom/images/super.img --metadata-size 65536 --super-name super --metadata-slots 2 --block-size 4096 --device super:$superSize --group=qti_dynamic_partitions:$superSize"
    for pname in odm mi_ext system system_ext product vendor;do
        if [ -f "build/portrom/images/${pname}.img" ];then
            if [[ "$OSTYPE" == "darwin"* ]];then
               subsize=$(find build/portrom/images/${pname}.img | xargs stat -f%z | awk ' {s+=$1} END { print s }')
            else
                subsize=$(du -sb build/portrom/images/${pname}.img |tr -cd 0-9)
            fi
            green "Super 子分区 [$pname] 大小 [$subsize]" "Super sub-partition [$pname] size: [$subsize]"
            args="--partition ${pname}:none:${subsize}:qti_dynamic_partitions --image ${pname}=build/portrom/images/${pname}.img"
            lpargs="$lpargs $args"
            unset subsize
            unset args
        fi
    done
else
    blue "打包V-A/B机型 super.img" "Packing super.img for V-AB device"
    lpargs="-F --virtual-ab --output build/portrom/images/super.img --metadata-size 65536 --super-name super --metadata-slots 3 --device super:$superSize --group=qti_dynamic_partitions_a:$superSize --group=qti_dynamic_partitions_b:$superSize"
    for pname in ${super_list};do
        if [ -f "build/portrom/images/${pname}.img" ];then
            subsize=$(du -sb build/portrom/images/${pname}.img |tr -cd 0-9)
            green "Super 子分区 [$pname] 大小 [$subsize]" "Super sub-partition [$pname] size: [$subsize]"
            args="--partition ${pname}_a:none:${subsize}:qti_dynamic_partitions_a --image ${pname}_a=build/portrom/images/${pname}.img --partition ${pname}_b:none:0:qti_dynamic_partitions_b"
            lpargs="$lpargs $args"
            unset subsize
            unset args
        fi
    done
fi
lpmake $lpargs
#echo "lpmake $lpargs"
if [ -f "build/portrom/images/super.img" ];then
    green "成功打包 super.img" "Pakcing super.img done."
else
    error "无法打包 super.img"  "Unable to pack super.img."
    exit 1
fi
for pname in ${super_list};do
    rm -rf build/portrom/images/${pname}.img
done
os_type="hyperos"
if [[ ${is_eu_rom} == true ]];then
    os_type="xiaomi.eu"
fi
blue "正在压缩 super.img" "Comprising super.img"
zstd --rm build/portrom/images/super.img -o build/portrom/images/super.zst
mkdir -p out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/
mkdir -p out/${os_type}_${device_code}_${port_rom_version}/bin/windows/
blue "正在生成刷机脚本" "Generating flashing script"
if [[ "$is_ab_device" == false ]];then
    mv -f build/portrom/images/super.zst out/${os_type}_${device_code}_${port_rom_version}/
    #firmware
    cp -rf bin/flash/platform-tools-windows/* out/${os_type}_${device_code}_${port_rom_version}/bin/windows/
    cp -rf bin/flash/mac_linux_flash_script.sh out/${os_type}_${device_code}_${port_rom_version}/
    cp -rf bin/flash/windows_flash_script.bat out/${os_type}_${device_code}_${port_rom_version}/
    sed -i "s/_ab//g" out/${os_type}_${device_code}_${port_rom_version}/mac_linux_flash_script.sh
    sed -i "s/_ab//g" out/${os_type}_${device_code}_${port_rom_version}/windows_flash_script.bat
    sed -i '/^# SET_ACTION_SLOT_A_BEGIN$/,/^# SET_ACTION_SLOT_A_END$/d' out/${os_type}_${device_code}_${port_rom_version}/mac_linux_flash_script.sh
    sed -i '/^REM SET_ACTION_SLOT_A_BEGIN$/,/^REM SET_ACTION_SLOT_A_END$/d' out/${os_type}_${device_code}_${port_rom_version}/windows_flash_script.bat
    if [ -d build/baserom/firmware-update ];then
        mkdir -p out/${os_type}_${device_code}_${port_rom_version}/firmware-update
        cp -rf build/baserom/firmware-update/*  out/${os_type}_${device_code}_${port_rom_version}/firmware-update
         for fwimg in $(ls out/${os_type}_${device_code}_${port_rom_version}/firmware-update);do
            if [[ ${fwimg} == "uefi_sec.mbn" ]];then
                part="uefisecapp"
            elif [[ ${fwimg} == "qupv3fw.elf" ]];then
                part="qupfw"
            elif [[ ${fwimg} == "NON-HLOS.bin" ]];then
                part="modem"
            elif [[ ${fwimg} == "km4.mbn" ]];then
                part="keymaster"
            elif [[ ${fwimg} == "BTFM.bin" ]];then
                part="bluetooth"
            elif [[ ${fwimg} == "dspso.bin" ]];then
                part="dsp"
            else
                part=${fwimg%.*}                
            fi
            sed -i "/# firmware/a fastboot flash ${part} firmware-update/${fwimg}" out/${os_type}_${device_code}_${port_rom_version}/mac_linux_flash_script.sh
            sed -i "/REM firmware/a bin\\\windows\\\fastboot.exe flash ${part} %~dp0firmware-update\/${fwimg}" out/${os_type}_${device_code}_${port_rom_version}/windows_flash_script.bat
         done
    fi
    #disable vbmeta
    for img in $(find out/${os_type}_${device_code}_${port_rom_version}/firmware-update -type f -name "vbmeta*.img");do
        python3 bin/patch-vbmeta.py ${img}
    done
    cp -rf bin/flash/a-only/update-binary out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/
    cp -rf bin/flash/zstd out/${os_type}_${device_code}_${port_rom_version}/META-INF/
    ksu_bootimg_file=$(find devices/$base_rom_code/ -type f -name "boot_ksu*.img")
    nonksu_bootimg_file=$(find devices/$base_rom_code/ -type f -name "boot_nonksu*.img")
    if [[ -f $nonksu_bootimg_file ]];then
        nonksubootimg=$(basename "$nonksu_bootimg_file")
        cp -f $nonksu_bootimg_file out/${os_type}_${device_code}_${port_rom_version}/
        sed -i "s/boot_official.img/$nonksubootimg/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
        sed -i "s/boot_official.img/$nonksubootimg/g" out/${os_type}_${device_code}_${port_rom_version}/windows_flash_script.bat
        sed -i "s/boot_official.img/$nonksubootimg/g" out/${os_type}_${device_code}_${port_rom_version}/mac_linux_flash_script.sh
    else
        cp -f build/baserom/boot.img out/${os_type}_${device_code}_${port_rom_version}/boot_official.img
    fi
    if [[ -f "$ksu_bootimg_file" ]];then
        ksubootimg=$(basename "$ksu_bootimg_file")
        sed -i "s/boot_tv.img/$ksubootimg/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
        sed -i "s/boot_tv.img/$ksubootimg/g" out/${os_type}_${device_code}_${port_rom_version}/windows_flash_script.bat
        sed -i "s/boot_tv.img/$ksubootimg/g" out/${os_type}_${device_code}_${port_rom_version}/mac_linux_flash_script.sh
        cp -rf $ksu_bootimg_file out/${os_type}_${device_code}_${port_rom_version}/
    fi
    busybox unix2dos out/${os_type}_${device_code}_${port_rom_version}/windows_flash_script.bat
    sed -i "s/portversion/${port_rom_version}/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
    sed -i "s/baseversion/${base_rom_version}/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
    sed -i "s/andVersion/${port_android_version}/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
    sed -i "s/device_code/${base_rom_code}/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
else
    mkdir -p out/${os_type}_${device_code}_${port_rom_version}/images/
    mv -f build/portrom/images/super.zst out/${os_type}_${device_code}_${port_rom_version}/images/
    cp -rf bin/flash/vab/update-binary out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/
    cp -rf bin/flash/platform-tools-windows out/${os_type}_${device_code}_${port_rom_version}/META-INF/
    cp -rf bin/flash/vab/flash_update.bat out/${os_type}_${device_code}_${port_rom_version}/
    cp -rf bin/flash/vab/flash_and_format.bat out/${os_type}_${device_code}_${port_rom_version}/
    cp -rf bin/flash/zstd out/${os_type}_${device_code}_${port_rom_version}/META-INF/
    for fwImg in $(ls out/${os_type}_${device_code}_${port_rom_version}/images/ |cut -d "." -f 1 |grep -vE "super|cust|preloader");do
        if [ "$(echo ${fwimg} |grep vbmeta)" != "" ];then
            sed -i "/rem/a META-INF\\\platform-tools-windows\\\fastboot --disable-verity --disable-verification flash "${fwimg}"_b images\/"${fwimg}".img" out/${os_type}_${device_code}_${port_rom_version}/flash_update.bat
            sed -i "/rem/a META-INF\\\platform-tools-windows\\\fastboot --disable-verity --disable-verification flash "${fwimg}"_a images\/"${fwimg}".img" out/${os_type}_${device_code}_${port_rom_version}/flash_update.bat
            sed -i "/rem/a META-INF\\\platform-tools-windows\\\fastboot --disable-verity --disable-verification flash "${fwimg}"_b images\/"${fwimg}".img" out/${os_type}_${device_code}_${port_rom_version}/flash_and_format.bat
            sed -i "/rem/a META-INF\\\platform-tools-windows\\\fastboot --disable-verity --disable-verification flash "${fwimg}"_a images\/"${fwimg}".img" out/${os_type}_${device_code}_${port_rom_version}/flash_and_format.bat
            sed -i "/#firmware/a package_extract_file \"images/"${fwimg}".img\" \"/dev/block/bootdevice/by-name/"${fwimg}"_b\"" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
            sed -i "/#firmware/a package_extract_file \"images/"${fwimg}".img\" \"/dev/block/bootdevice/by-name/"${fwimg}"_a\"" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
        else
            sed -i "/rem/a META-INF\\\platform-tools-windows\\\fastboot flash "${fwimg}"_b images\/"${fwimg}".img" out/${os_type}_${device_code}_${port_rom_version}/flash_update.bat
            sed -i "/rem/a META-INF\\\platform-tools-windows\\\fastboot flash "${fwimg}"_a images\/"${fwimg}".img" out/${os_type}_${device_code}_${port_rom_version}/flash_update.bat
            sed -i "/rem/a META-INF\\\platform-tools-windows\\\fastboot flash "${fwimg}"_b images\/"${fwimg}".img" out/${os_type}_${device_code}_${port_rom_version}/flash_and_format.bat
            sed -i "/rem/a META-INF\\\platform-tools-windows\\\fastboot flash "${fwimg}"_a images\/"${fwimg}".img" out/${os_type}_${device_code}_${port_rom_version}/flash_and_format.bat
            sed -i "/#firmware/a package_extract_file \"images/"${fwimg}".img\" \"/dev/block/bootdevice/by-name/"${fwimg}"_b\"" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
            sed -i "/#firmware/a package_extract_file \"images/"${fwimg}".img\" \"/dev/block/bootdevice/by-name/"${fwimg}"_a\"" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
        fi
    done
    sed -i "s/portversion/${port_rom_version}/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
    sed -i "s/baseversion/${base_rom_version}/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
    sed -i "s/andVersion/${port_android_version}/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
    sed -i "s/device_code/${base_rom_code}/g" out/${os_type}_${device_code}_${port_rom_version}/META-INF/com/google/android/update-binary
    busybox unix2dos out/${os_type}_${device_code}_${port_rom_version}/flash_update.bat
    busybox unix2dos out/${os_type}_${device_code}_${port_rom_version}/flash_and_format.bat
fi
find out/${os_type}_${device_code}_${port_rom_version} |xargs touch
pushd out/${os_type}_${device_code}_${port_rom_version}/  || exit
zip -r ${os_type}_${device_code}_${port_rom_version}.zip ./*
mv ${os_type}_${device_code}_${port_rom_version}.zip ../
popd || exit
pack_timestamp=$(date +"%m%d%H%M")
hash=$(md5sum out/${os_type}_${device_code}_${port_rom_version}.zip |head -c 10)
if [[ $pack_type == "EROFS" ]];then
    pack_type="ROOT_"${pack_type}
    yellow "检测到打包类型为EROFS,请确保官方内核支持，或者在devices机型目录添加有支持EROFS的内核，否者将无法开机！" "EROFS filesystem detected. Ensure compatibility with the official boot.img or ensure a supported boot_tv.img is placed in the device folder."
fi
mv out/${os_type}_${device_code}_${port_rom_version}.zip out/${os_type}_${device_code}_${port_rom_version}_${hash}_${port_android_version}_${port_rom_code}_${pack_timestamp}_${pack_type}.zip
green "移植完毕" "Porting completed"    
green "输出包路径：" "Output: "
green "$(pwd)/out/${os_type}_${device_code}_${port_rom_version}_${hash}_${port_android_version}_${port_rom_code}_${pack_timestamp}_${pack_type}.zip"
