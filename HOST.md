# تشغيل أجهزة أندرويد على خادمك

تستخدم هذه الحزمة Android Emulator الرسمي من Google. لكل رقم من ١ إلى ١٠ هاتف افتراضي وقرص بيانات منفصل. إيقاف الجهاز وإعادة تشغيله يحتفظ بالتطبيقات والحسابات المثبّتة فيه. شغّل عدد الأجهزة التي تحتاجها فقط. جهاز الآيفون يعرض شاشة أندرويد ويتحكّم باللمس من المتصفح.

## تجهيز المضيف

تحتاج Linux على معالج x86_64 يدعم VT-x أو AMD-V، مع KVM متاح للمستخدم الذي يشغّل الخدمة. لو الخادم نفسه جهاز افتراضي، يلزم أن يتيح المزود nested virtualization وملف /dev/kvm. اختر مضيفًا خاصًا تثق بكل مستخدميه، لأن منافذ العارض وADB المحلية متاحة لعمليات الجهاز. تختلف سرعة المحاكي وتوفّر KVM حسب خطة الاستضافة. استخدم تخزين SSD دائمًا. الحزمة تخصّص ٣ جيجابايت RAM ونواتين افتراضيتين لكل جهاز يعمل، بالإضافة إلى موارد النظام والرسم. لعشرة أجهزة احسب أكثر من ٣٠ جيجابايت RAM ومساحة لكل قرص بيانات ومكتبة التطبيقات. ابدأ بجهاز واحد وقِس الاستهلاك قبل توسيع العدد.

مثال تثبيت الاعتماديات على Ubuntu 24.04. يمكن استخدام الحزم المقابلة في Debian حديثة. توفّر الحزم Bash وPython 3 ومكتبات العرض للمحاكي وعدة noVNC. Java 17 أو أحدث مطلوب لأدوات سطر الأوامر وفق إصدار SDK المثبت.

```bash
sudo apt update
sudo apt install openjdk-17-jre-headless unzip xvfb xauth x11-utils x11vnc novnc websockify python3 \
    libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-xinerama0 \
    libxcb-icccm4 libxcb-keysyms1 libxcb-image0 libxcb-render-util0 libnss3
ls -l /dev/kvm
id -nG
```

إذا كانت مجموعة kvm تملك الملف، أعطِ حساب التشغيل صلاحية المجموعة باستخدام `sudo usermod -aG kvm "$(id -un)"`. اخرج من الجلسة وادخل مجددًا، ثم تحقّق من الصلاحيات.

```bash
test -r /dev/kvm && test -w /dev/kvm && echo "KVM available"
```

## تثبيت Android SDK

نزّل **Command line tools only for Linux** من [صفحة Android Studio الرسمية](https://developer.android.com/studio#command-line-tools-only). فكّ الضغط بحيث يكون المسار النهائي `$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager`. يمكنك أيضًا إعداد SDK Manager من Android Studio إن كان مثبتًا. شغّل الأوامر التالية بحساب الخدمة. راجع اتفاقيات Google واقبلها بنفسك إذا كانت مناسبة لاستخدامك.

```bash
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
sdkmanager --licenses
sdkmanager "platform-tools" "emulator" "system-images;android-35;google_apis_playstore;x86_64"
emulator -version
emulator -accel-check
avdmanager list device
```

استخدم Android Emulator حديثًا يدعم `-gpu software`، ويفضّل الإصدار 36.4.9 أو أحدث. كل جهاز يستخدم صورة Google Play الرسمية ومحاكاة رسم برمجي. نجاح تشغيل خدمة داخل المحاكي تحدّده الخدمة نفسها وتوافق تطبيقها مع المعمارية والمحاكاة. تطبيقات البنوك قد ترفض التشغيل أو تخفي شاشة حساسة. [خيارات المحاكي](https://developer.android.com/studio/run/emulator-commandline) · [متطلبات التسريع](https://developer.android.com/studio/run/emulator-acceleration)

## تشغيل الأجهزة

من مجلد AndroidServer، شغّل البوابة كما هو موضح في GATEWAY.md لتشغيل الأجهزة من الآيفون. عرّف ANDROID_HOME في بيئة عملية البوابة نفسها، واحتفظ بنفس مستخدم النظام ومسار التخزين عند كل تشغيل. يوجد خيار SAM_AVD_ROOT لاختيار قرص دائم ذي مساحة كافية. عند استخدام systemd يجب تعريف المتغيرات في وحدة الخدمة أو بيئتها. إغلاق العارض في المتصفح يترك المحاكي يعمل طالما أن الخدمة تعمل.

للفحص اليدوي، أوقف تشغيل الرقم نفسه من البوابة أولًا. الأمر prepare اختياري، والأمر run يجهّز الجهاز إن لزم ويظل قيد التشغيل حتى تضغط Ctrl+C. أول إقلاع وإنشاء بيانات النظام قد يستغرقان عدة دقائق.

```bash
python3 slot.py info 1
python3 slot.py prepare 1
python3 slot.py run 1
```

من طرفية أخرى على الخادم، اعرف حالة الإقلاع. ناتج 1 يعني اكتمال تشغيل أندرويد.

```bash
"$ANDROID_HOME/platform-tools/adb" -s emulator-5554 shell getprop sys.boot_completed
```

افتح العارض من البوابة، ثم Play Store على الجهاز المطلوب، وسجّل الدخول وثبّت التطبيقات بنفسك. كرر التثبيت مرة واحدة لكل جهاز تحتاجه. لا تدعم الحزمة صوت الجهاز أو كاميرته. تشترك الأجهزة افتراضيًا في اتصال الخادم بالإنترنت.

يحفظ كل جهاز بياناته في مجلد SamDevice01 حتى SamDevice10 تحت `$SAM_AVD_ROOT` أو افتراضيًا `$HOME/.local/state/sam-cloudespace/avds` (أو مسار XDG_STATE_HOME). احتفظ بنسخة احتياطية من المجلد والجهاز متوقف. لا تشغّل نسختين من محاكي بنفس المجلد. مدير الأجهزة يستخدم أقفال النظام لمنع تشغيل الرقم مرتين. إذا أبلغ عن بيانات إعداد غير مكتملة بعد انقطاع القرص، افحص المجلد واحتفظ بنسخة منه قبل محاولة إصلاحه.

لكل رقم منفذان للمحاكي ابتداء من 5554/5555 وحتى 5572/5573، ومنفذ VNC محلي بين 5901 و5910، ومنفذ noVNC محلي بين 6101 و6110. المنافذ مخصصة للبوابة على نفس الخادم. لا تعرض هذه المنافذ أو 5037 في قواعد الراوتر أو جدار الحماية. اعتمد مدخل البوابة HTTPS الموثّق للوصول من الآيفون. يقفل مدير الأجهزة محاكيه وعارضه معًا إذا خرجت إحدى العمليّات.
