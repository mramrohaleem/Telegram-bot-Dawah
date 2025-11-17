"""Arabic user-facing texts for the Telegram bot."""

START_MESSAGE_AR = (
    "وعليكم السلام ورحمة الله 🌿\n"
    "أنا بوت أرشفة المواد.\n\n"
    "ابعت الرابط → هتظهر لك قائمة فيديو/صوت + الجودات → تختار → يتم التحميل والإرسال."
)

HELP_MESSAGE_AR = (
    "ابعت لي رابط محاضرة (يوتيوب أو غيره) وهختار لك أفضل الصيغ.\n"
    "يمكنك استخدام الإعدادات لتحديد اختياراتك الافتراضية."
)

PING_RESPONSE_AR = "بونج 🏓"

LINK_RECEIVED_MESSAGE_AR = "استقبلت الرابط ✅\nاختار من القائمة اللي تحت:"

JOB_REGISTERED_MESSAGE_AR = (
    "✅ تم تسجيل طلبك كـ رقم #{job_id}.\n"
    "العنوان: {title}\n"
    "النوع: {media_type}\n"
    "الجودة: {quality}\n"
    "الحالة الحالية: {status_label}"
)

JOB_REUSED_MESSAGE_AR = (
    "ℹ️ الطلب موجود بالفعل كـ رقم #{job_id} بنفس النوع والجودة.\n"
    "الحالة الحالية: {status_label}"
)

ARCHIVE_REUSE_MESSAGE_AR = (
    "📦 تم العثور على نسخة مؤرشفة وتم إرسالها مباشرة دون إعادة التحميل."
)

STATUS_HEADER_AR = "📥 حالة طلبات التحميل:\n"
STATUS_LINE_AR = "#{job_id} | {media_type} | {quality_label} | {status_label}"
STATUS_LINE_WITH_PROGRESS_AR = (
    "#{job_id} | {media_type} | {quality_label} | {progress} | {speed} | {status_label}"
)
NO_ACTIVE_JOBS_AR = "لا توجد طلبات نشطة حاليًا."
RECENT_COMPLETED_HEADER_AR = "\nأحدث الطلبات المكتملة:"

ERROR_INVALID_URL_AR = "❌ مش قادر أتعامل مع الرابط ده. تأكد إنه من موقع مدعوم أو ابعته بشكل صحيح."
ERROR_UNSUPPORTED_DOMAIN_AR = "❌ الموقع ده مش مدعوم حاليًا."
ERROR_MISSING_DRAFT_AR = "❌ الطلب المؤقت غير موجود أو انتهت صلاحيته. ابعت الرابط من جديد."
CANCELLED_DRAFT_AR = "تم إلغاء الطلب."

DEFAULT_SETTINGS_OPTION_AR = "✅ استخدم الإعدادات الافتراضية"
CUSTOM_SELECTION_OPTION_AR = "⚙️ اختيار مختلف للطلب الحالي"
STATUS_BUTTON_AR = "📥 حالة الطلبات"
CANCEL_BUTTON_AR = "❌ إلغاء الطلب"

SETTINGS_TITLE_AR = "⚙️ الإعدادات"
SETTINGS_UPDATED_AR = "تم تحديث الإعدادات."
SETTINGS_UPDATE_ERROR_AR = "حدث خطأ أثناء تحديث الإعدادات. حاول مرة أخرى."

SETTINGS_TYPE_TITLE_AR = "🎬 نوع التحميل الافتراضي"
SETTINGS_VIDEO_QUALITY_TITLE_AR = "📺 الجودة الافتراضية للفيديو"
SETTINGS_AUDIO_QUALITY_TITLE_AR = "🎧 الجودة الافتراضية للصوت"
SETTINGS_ARCHIVE_TITLE_AR = "🗃️ حفظ نسخة في الأرشيف افتراضيًا"

SETTINGS_DEFAULT_TYPE_VIDEO_AR = "🎬 فيديو"
SETTINGS_DEFAULT_TYPE_AUDIO_AR = "🎧 صوت"
SETTINGS_DEFAULT_TYPE_ASK_AR = "❓ اسأل كل مرة"

FAILURE_DELIVERY_AR = "تعذّر تسليم الملف للطلب #{job_id}: {reason}"
FAILURE_DELIVERY_GENERIC_AR = "خطأ غير معروف أثناء التسليم."
FAILURE_SIZE_LIMIT_AR = "❌ فشل التحميل: حجم الملف أكبر من الحد المسموح."
FAILURE_GEO_BLOCK_AR = "❌ فشل التحميل بسبب حظر جغرافي للمحتوى."
FAILURE_AUTH_AR = "❌ فشل التحميل: الموقع يتطلب تسجيل دخول أو ملفات تعريف الارتباط."
FAILURE_UNSUPPORTED_AR = "❌ فشل التحميل: المصدر غير مدعوم."
FAILURE_GENERIC_AR = "❌ فشل التحميل (النوع: {error_type}). تواصل مع المشرف للمساعدة."

STATUS_LABELS_AR = {
    "PENDING": "في انتظار المعالجة ⏳",
    "QUEUED": "في قائمة الانتظار ⏳",
    "RUNNING": "جاري التحميل ⬇️",
    "COMPLETED": "تم التسليم ✅",
    "FAILED": "فشل ❌",
}

MEDIA_TYPE_LABELS_AR = {
    "VIDEO": "فيديو",
    "AUDIO": "صوت",
}

QUALITY_LABELS_AR = {
    "best": "أفضل جودة",
    "1080p": "1080p",
    "720p": "720p",
    "480p": "480p",
    "audio_best": "أفضل جودة صوت",
    "128k": "128 kbps",
    "64k": "64 kbps",
}

def quality_label(slug: str | None) -> str:
    if not slug:
        return "أفضل جودة"
    return QUALITY_LABELS_AR.get(slug, slug)


def media_type_label(job_type: str | None) -> str:
    if not job_type:
        return "غير محدد"
    return MEDIA_TYPE_LABELS_AR.get(job_type, str(job_type))


def status_label(status: str | None) -> str:
    if not status:
        return "غير معروف"
    return STATUS_LABELS_AR.get(status, str(status))
