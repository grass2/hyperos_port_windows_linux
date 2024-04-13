#!/bin/bash
javaOpts="-Xmx1024M -Dfile.encoding=utf-8 -Djdk.util.zip.disableZip64ExtraFieldValidation=true -Djdk.nio.zipfs.allowDotZipEntry=true"
export PATH=$(pwd)/bin/$(uname)/$(uname -m)/:$PATH
source functions.sh
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
port_android_sdk=$(python3 bin/read_config.py build/portrom/images/system/system/build.prop 'ro.system.build.version.sdk')
base_rom_code=$(python3 bin/read_config.py build/portrom/images/vendor/build.prop "ro.product.vendor.device")
blue "左侧挖孔灵动岛修复" "StrongToast UI fix"
if [[ "$is_shennong_houji_port" == true ]];then
    patch_smali "MiuiSystemUI.apk" "MIUIStrongToast\$2.smali" "const\/4 v7\, 0x0" "iget-object v7\, v1\, Lcom\/android\/systemui\/toast\/MIUIStrongToast;->mRLLeft:Landroid\/widget\/RelativeLayout;\\n\\tinvoke-virtual {v7}, Landroid\/widget\/RelativeLayout;->getLeft()I\\n\\tmove-result v7\\n\\tint-to-float v7,v7"
else
    patch_smali "MiuiSystemUI.apk" "MIUIStrongToast\$2.smali" "const\/4 v9\, 0x0" "iget-object v9\, v1\, Lcom\/android\/systemui\/toast\/MIUIStrongToast;->mRLLeft:Landroid\/widget\/RelativeLayout;\\n\\tinvoke-virtual {v9}, Landroid\/widget\/RelativeLayout;->getLeft()I\\n\\tmove-result v9\\n\\tint-to-float v9,v9"
fi
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
unlock_device_feature "Whether support AI Display"  "bool" "support_AI_display"
unlock_device_feature "device support screen enhance engine"  "bool" "support_screen_enhance_engine"
unlock_device_feature "Whether suppot Android Flashlight Controller"  "bool" "support_android_flashlight"
unlock_device_feature "Whether support SR for image display"  "bool" "support_SR_for_image_display"
# Unlock Smart fps
maxFps=$(python3 bin/maxfps.py build/portrom/images/product/etc/device_features/${base_rom_code}.xml)
if [ -z "$maxFps" ]; then
    maxFps=90
fi
unlock_device_feature "whether support fps change " "bool" "support_smart_fps"
unlock_device_feature "smart fps value" "integer" "smart_fps_value" "${maxFps}"
patch_smali "PowerKeeper.apk" "DisplayFrameSetting.smali" "unicorn" "umi"
patch_smali "MiSettings.apk" "NewRefreshRateFragment.smali" "const-string v1, \"btn_preferce_category\"" "const-string v1, \"btn_preferce_category\"\n\n\tconst\/16 p1, 0x1"
unlock_device_feature "default rhythmic eyecare mode" "integer" "default_eyecare_mode" "2"
unlock_device_feature "default texture for paper eyecare" "integer" "paper_eyecare_default_texture" "0"