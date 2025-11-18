import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot import texts
from core.job_service import JobCreationError, JobService
from core.logging_utils import get_logger, log_with_context
from download.youtube import FormatOption, YouTubeDownloader
from storage.models import ChatSettings, Job, JobStatus, JobType, SourceType
from storage.repositories import ChatSettingsRepository, JobDraftRepository, JobRepository

logger = get_logger(__name__)


def _get_job_service(context: ContextTypes.DEFAULT_TYPE) -> JobService:
    job_service = context.application.bot_data.get("job_service")
    if job_service is None:
        raise RuntimeError("JobService is not configured in bot_data")
    return job_service


def _get_session_factory(context: ContextTypes.DEFAULT_TYPE):
    session_factory = context.application.bot_data.get("session_factory")
    if session_factory is None:
        raise RuntimeError("Session factory missing in bot_data")
    return session_factory


def _build_keyboard(
    draft_id: int, options: list[FormatOption], include_default: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if include_default:
        rows.append(
            [
                InlineKeyboardButton(
                    texts.DEFAULT_SETTINGS_OPTION_AR, callback_data=f"default|{draft_id}"
                )
            ]
        )
    for opt in options:
        media_label = opt.label
        callback = f"sel|{draft_id}|{opt.media_type.value}|{opt.quality_slug}"
        rows.append([InlineKeyboardButton(media_label, callback_data=callback)])

    rows.append([InlineKeyboardButton(texts.CANCEL_BUTTON_AR, callback_data=f"sel|{draft_id}|cancel")])
    rows.append([InlineKeyboardButton(texts.STATUS_BUTTON_AR, callback_data="status")])
    return InlineKeyboardMarkup(rows)


def _load_chat_settings(chat_id: str | int, session_factory) -> ChatSettings:
    session = session_factory()
    try:
        repo = ChatSettingsRepository(session)
        return repo.get_or_create(chat_id)
    finally:
        session.close()


def _update_draft_title(draft_id: int, title: Optional[str], session_factory) -> None:
    if not title:
        return
    session = session_factory()
    try:
        repo = JobDraftRepository(session)
        draft = repo.get_by_id(draft_id)
        if draft:
            draft.suggested_title = title
            session.add(draft)
            session.commit()
    finally:
        session.close()


def _build_settings_keyboard(settings: ChatSettings) -> InlineKeyboardMarkup:
    def mark(label: str, selected: bool) -> str:
        return f"{'✅ ' if selected else ''}{label}"

    default_type = settings.default_job_type
    default_quality = settings.default_quality

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                mark(texts.SETTINGS_DEFAULT_TYPE_VIDEO_AR, default_type == JobType.VIDEO.value),
                callback_data="settings|type|VIDEO",
            ),
            InlineKeyboardButton(
                mark(texts.SETTINGS_DEFAULT_TYPE_AUDIO_AR, default_type == JobType.AUDIO.value),
                callback_data="settings|type|AUDIO",
            ),
            InlineKeyboardButton(
                mark(texts.SETTINGS_DEFAULT_TYPE_ASK_AR, not default_type),
                callback_data="settings|type|ASK",
            ),
        ]
    ]

    rows.append(
        [
            InlineKeyboardButton(
                mark("📺 أفضل جودة", default_quality == "best"),
                callback_data="settings|video_quality|best",
            ),
            InlineKeyboardButton(
                mark("📺 720p", default_quality == "720p"),
                callback_data="settings|video_quality|720p",
            ),
            InlineKeyboardButton(
                mark("📺 480p", default_quality == "480p"),
                callback_data="settings|video_quality|480p",
            ),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                mark("🎧 أفضل جودة", default_quality == "audio_best"),
                callback_data="settings|audio_quality|audio_best",
            ),
            InlineKeyboardButton(
                mark("🎧 128 kbps", default_quality == "128k"),
                callback_data="settings|audio_quality|128k",
            ),
        ]
    )

    archive_label = (
        "🗃️ الحفظ في الأرشيف: تشغيل ✅"
        if settings.archive_mode
        else "🗃️ الحفظ في الأرشيف: إيقاف ❌"
    )
    rows.append(
        [
            InlineKeyboardButton(
                archive_label, callback_data="settings|archive|toggle"
            )
        ]
    )
    rows.append([InlineKeyboardButton(texts.STATUS_BUTTON_AR, callback_data="status")])
    return InlineKeyboardMarkup(rows)


def _format_speed(speed_bps: Optional[float]) -> str:
    if speed_bps is None:
        return "-"
    mb_per_sec = speed_bps / (1024 * 1024)
    return f"{mb_per_sec:.1f} MB/s"


def format_job_status(job: Job) -> str:
    media_label = texts.media_type_label(job.job_type)
    quality_label = texts.quality_label(job.requested_quality)
    status_label = texts.status_label(job.status)
    if job.status == JobStatus.FAILED.value and getattr(job, "error_type", None):
        reason = texts.failure_reason_label(job.error_type)
        if reason:
            status_label = f"{status_label} ({reason})"

    percent = job.progress_percent
    percent_text = "-" if percent is None else f"{percent:.0f}%"
    speed = _format_speed(job.download_speed_bps)
    return texts.STATUS_LINE_WITH_PROGRESS_AR.format(
        job_id=job.id,
        media_type=media_label,
        quality_label=quality_label,
        percent=percent_text,
        speed=speed,
        status_label=status_label,
    )


def _status_refresh_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    texts.status_refresh_button(job_id),
                    callback_data=f"status|{job_id}",
                )
            ]
        ]
    )


def _store_status_message_reference(
    job_id: int, chat_id: int | str, message_id: int | str, session_factory
) -> None:
    session = session_factory()
    try:
        repo = JobRepository(session)
        job = repo.get_by_id(job_id)
        if job is None:
            return
        job.status_message_id = str(message_id)
        job.status_chat_id = str(chat_id)
        session.add(job)
        session.commit()
    finally:
        session.close()


async def handle_media_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages containing URLs and create drafts with selection keyboard."""

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message:
        return

    text = message.text or message.caption
    if not text:
        return

    job_service = _get_job_service(context)
    session_factory = _get_session_factory(context)

    try:
        draft = job_service.create_draft_from_message(
            chat_id=chat.id if chat else None,
            user_id=user.id if user else None,
            text=text,
        )
    except JobCreationError as exc:
        error_text = texts.ERROR_INVALID_URL_AR
        if "Unsupported" in str(exc):
            error_text = texts.ERROR_UNSUPPORTED_DOMAIN_AR
        await message.reply_text(error_text)
        return

    log_with_context(
        logger,
        level=logging.INFO,
        message="Draft created from link",
        stage="BOT",
        draft_id=draft.id,
        chat_id=chat.id if chat else None,
        user_id=user.id if user else None,
        url=draft.url,
    )

    if draft.source_type == SourceType.YOUTUBE.value or draft.source_type == SourceType.YOUTUBE:
        downloader = YouTubeDownloader()
        metadata, options = downloader.get_available_formats(draft.url)
        _update_draft_title(draft.id, metadata.title, session_factory)
    else:
        await message.reply_text(texts.ERROR_UNSUPPORTED_DOMAIN_AR)
        return

    settings = _load_chat_settings(chat.id, session_factory)
    include_default = bool(settings.default_job_type and settings.default_quality)
    keyboard = _build_keyboard(draft.id, options, include_default)
    await message.reply_text(texts.LINK_RECEIVED_MESSAGE_AR, reply_markup=keyboard)


async def selection_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""

    job_service = _get_job_service(context)
    session_factory = _get_session_factory(context)
    session = session_factory()
    try:
        draft_repo = JobDraftRepository(session)
        draft_id: Optional[int] = None
        action = None
        parts = data.split("|")
        if parts[0] == "default":
            action = "default"
            draft_id = int(parts[1])
        elif parts[0] == "sel":
            draft_id = int(parts[1])
            action = parts[2]
        else:
            return

        draft = draft_repo.get_by_id(draft_id) if draft_id else None
        if not draft:
            await query.edit_message_text(texts.ERROR_MISSING_DRAFT_AR)
            return

        if action == "cancel":
            draft_repo.discard(draft)
            await query.edit_message_text(texts.CANCELLED_DRAFT_AR)
            return

        if action == "default":
            settings = _load_chat_settings(draft.chat_id, session_factory)
            media_type = settings.default_job_type or JobType.VIDEO.value
            quality = settings.default_quality or "best"
        else:
            raw_type = parts[2]
            try:
                media_type = JobType(raw_type).value
            except ValueError:
                media_type = JobType.VIDEO.value
            quality = parts[3] if len(parts) > 3 else "best"

        job, reused, from_archive = job_service.create_job_from_draft(
            draft,
            media_type=media_type,
            quality_slug=quality,
        )
        draft_repo.discard(draft)
    finally:
        session.close()

    if reused:
        message_text = texts.JOB_REUSED_MESSAGE_AR.format(
            job_id=job.id,
            status_label=texts.status_label(job.status),
        )
        if from_archive:
            message_text = f"{texts.ARCHIVE_REUSE_MESSAGE_AR}\n{message_text}"
        await query.edit_message_text(message_text)
        return

    status_line = format_job_status(job)
    message_text = "\n".join(
        [
            texts.JOB_REGISTERED_BRIEF_AR.format(job_id=job.id),
            status_line,
        ]
    )
    keyboard = _status_refresh_keyboard(job.id)
    sent_message = await query.edit_message_text(message_text, reply_markup=keyboard)
    if sent_message:
        _store_status_message_reference(
            job.id, sent_message.chat_id, sent_message.message_id, session_factory
        )


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    job_service = _get_job_service(context)
    active_jobs, recent_completed = job_service.list_jobs_for_status_view(chat.id)

    lines: list[str] = []
    if active_jobs:
        lines.append(texts.STATUS_HEADER_AR)
        for job in active_jobs:
            lines.append(format_job_status(job))
    else:
        lines.append(texts.NO_ACTIVE_JOBS_AR)

    if recent_completed:
        lines.append(texts.RECENT_COMPLETED_HEADER_AR)
        for job in recent_completed:
            lines.append(format_job_status(job))

    message_text = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text)
    elif update.effective_message:
        await update.effective_message.reply_text(message_text)


async def refresh_status_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    parts = data.split("|")
    if len(parts) < 2:
        return
    try:
        job_id = int(parts[1])
    except ValueError:
        return

    job_service = _get_job_service(context)
    session_factory = _get_session_factory(context)
    job = job_service.get_job_by_id(job_id)
    if not job:
        await query.edit_message_text(texts.NO_ACTIVE_JOBS_AR)
        return

    message_text = format_job_status(job)
    keyboard = _status_refresh_keyboard(job.id)
    if query.message:
        _store_status_message_reference(
            job.id, query.message.chat_id, query.message.message_id, session_factory
        )
    await query.edit_message_text(message_text, reply_markup=keyboard)


async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    session_factory = _get_session_factory(context)
    session = session_factory()
    try:
        settings_repo = ChatSettingsRepository(session)
        settings = settings_repo.get_or_create(chat.id)
    finally:
        session.close()

    keyboard = _build_settings_keyboard(settings)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            texts.SETTINGS_TITLE_AR, reply_markup=keyboard
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            texts.SETTINGS_TITLE_AR, reply_markup=keyboard
        )


async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    parts = data.split("|")
    if parts[0] != "settings":
        return

    if len(parts) == 1:
        await settings_handler(update, context)
        return

    chat = update.effective_chat
    if not chat:
        return

    session_factory = _get_session_factory(context)
    session = session_factory()
    try:
        repo = ChatSettingsRepository(session)
        settings = repo.get_or_create(chat.id)
        action = parts[1]
        value = parts[2] if len(parts) > 2 else None
        if action == "type" and value:
            if value == "ASK":
                settings.default_job_type = None
            else:
                settings.default_job_type = value
        elif action == "video_quality" and value:
            settings.default_quality = value
            settings.default_job_type = settings.default_job_type or JobType.VIDEO.value
        elif action == "audio_quality" and value:
            settings.default_quality = value
            settings.default_job_type = settings.default_job_type or JobType.AUDIO.value
        elif action == "archive":
            settings.archive_mode = not settings.archive_mode
        session.add(settings)
        session.commit()
        log_with_context(
            logger,
            level=logging.INFO,
            message="Chat settings updated",
            stage="SETTINGS",
            chat_id=chat.id,
            user_id=update.effective_user.id if update.effective_user else None,
            action=action,
            value=value,
        )
    except Exception as exc:  # pragma: no cover - defensive
        session.rollback()
        log_with_context(
            logger,
            level=logging.ERROR,
            message="Failed to update settings",
            stage="SETTINGS",
            chat_id=chat.id,
            user_id=update.effective_user.id if update.effective_user else None,
            error=str(exc),
        )
        await query.edit_message_text(texts.SETTINGS_UPDATE_ERROR_AR)
        return
    finally:
        session.close()

    session = session_factory()
    try:
        repo = ChatSettingsRepository(session)
        updated_settings = repo.get_or_create(chat.id)
    finally:
        session.close()

    keyboard = _build_settings_keyboard(updated_settings)
    await query.edit_message_text(
        f"{texts.SETTINGS_TITLE_AR}\n{texts.SETTINGS_UPDATED_AR}",
        reply_markup=keyboard,
    )


async def rename_job_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat:
        return

    await message.reply_text("تم إيقاف أمر إعادة التسمية مؤقتًا في الواجهة العربية الجديدة.")
