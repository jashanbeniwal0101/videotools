# plugins/callback_handlers.py
import os
import time
import asyncio
import logging
from pathlib import Path
from config import DUMP_ID
from core.ffmpeg_handlers import FFmpegHandler
from core.handlers import (
    forward_job, cancel_job,
    mediainfo_job, trim_video_job,
    edit_button_job, merge_video_job, rename_file_job, progress_job,
    edit_caption_job, extract_thumb_job, extract_stream_job,
    gen_screenshot_job, remove_forward_tag_job,
    convert_audio_job, compress_audio_job,
    bulk_mode_job, bulk_archive_job
)
from core.helpers import Callbacks as cb, progress_hook as progress_handler, progress_handler_for_4gb, start_premium_client, premium_client
from pyrogram import Client, filters, utils
from pyrogram.enums import ListenerTypes
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from pyrogram.errors import ListenerStopped

from core.wmanager import TaskManager
task_manager = TaskManager()

async def close_handler(client: Client, query: CallbackQuery):
    await query.message.delete()

async def cancel_handler(client: Client, query: CallbackQuery):
    try:
        await cancel_job(client, query)
    except Exception as e:
        logging.info(e)

async def work_on_progress(client: Client, query: CallbackQuery):
    if query.data == 'ca':
        await query.answer(
            "Yeah yeah, I'm working on it... impatient much?",
            show_alert=True
        )

async def extract_thumb_handler(client: Client, query: CallbackQuery):
    try:
        await extract_thumb_job(client, query)
    except Exception as e:
        logging.info(e)

async def remove_forward_tag_handler(client: Client, query: CallbackQuery):
    try:
        await remove_forward_tag_job(client, query)
    except Exception as e:
        logging.info(e)

async def forward_handler(client: Client, query: CallbackQuery):
    try:
        await forward_job(client, query)
    except Exception as e:
        logging.info(e)

async def edit_button_handler(client: Client, query: CallbackQuery):
    await query.answer("Oh wow, you want to edit buttons? How original...", show_alert=True)

async def edit_caption_handler(client: Client, query: CallbackQuery):
    try:
        await edit_caption_job(client, query)
    except Exception as e:
        logging.info(e)

async def trim_video_handler(client: Client, query: CallbackQuery):
    try:
        await trim_video_job(client, query)
    except Exception as e:
        await query.answer("Trim video failed!", show_alert=True)

async def extract_stream_handler(client: Client, query: CallbackQuery):
    try:
        await extract_stream_job(client, query)
    except Exception as e:
        await query.answer(f"Extract stream failed: {str(e)}", show_alert=True)

async def rename_file_handler(client: Client, query: CallbackQuery):
    try:
        await task_manager.enqueue(
            rename_file_job,
            client, query,
            user_id=query.from_user.id
        )
    except Exception as e:
        logging.info(e)

async def gen_screenshot_handler(client: Client, query: CallbackQuery):
    try:
        await gen_screenshot_job(client, query)
    except Exception as e:
        await query.answer(f"Screenshot failed: {str(e)}", show_alert=True)

async def merge_video_handler(client: Client, query: CallbackQuery):
    try:
        await merge_video_job(client, query)
    except Exception as e:
        await query.answer(f"Merge failed: {str(e)}", show_alert=True)

async def mediainfo_handler(client: Client, query: CallbackQuery):
    try:
        await mediainfo_job(client, query)
    except Exception as e:
        await query.answer(f"Mediainfo failed: {str(e)}", show_alert=True)

async def progress_callback(client: Client, query: CallbackQuery):
    try:
        await progress_job(client, query)
    except Exception as e:
        logging.info(e)

async def convert_audio_handler(client: Client, query: CallbackQuery):
    try:
        await convert_audio_job(client, query)
    except Exception as e:
        await query.answer(f"Audio conversion failed: {str(e)}", show_alert=True)

async def compress_audio_handler(client: Client, query: CallbackQuery):
    try:
        await compress_audio_job(client, query)
    except Exception as e:
        await query.answer(f"Audio compression failed: {str(e)}", show_alert=True)

async def bulk_mode_handler(client: Client, query: CallbackQuery):
    try:
        await bulk_mode_job(client, query)
    except Exception as e:
        await query.answer(f"Bulk mode failed: {str(e)}", show_alert=True)

async def bulk_archive_handler(client: Client, query: CallbackQuery):
    try:
        await bulk_archive_job(client, query)
    except Exception as e:
        await query.answer(f"Bulk archive failed: {str(e)}", show_alert=True)

async def settings_handler(client: Client, query: CallbackQuery):
    """Handle settings menu"""
    from core.database import db
    
    user_id = query.from_user.id
    is_premium = await db.is_premium(user_id)
    
    settings_text = f"""
⚙️ **Settings Menu** {'⭐' if is_premium else ''}

**User Status:** {'Premium User ⭐' if is_premium else 'Free User'}
**Cooldown:** {'No cooldown ⭐' if is_premium else '25 minutes between tasks'}

**Current Settings:**
• Auto Delete: {await db.get_setting(user_id, 'auto_delete') or 'Yes'}
• Default Quality: {await db.get_setting(user_id, 'default_quality') or 'High'}
• Audio Quality: {await db.get_setting(user_id, 'audio_quality') or 320}kbps
• Screenshot Count: {await db.get_setting(user_id, 'screenshot_count') or 5}

**Customization:**
• Caption: {'Set' if await db.get_caption(user_id) else 'Not set'}
• Thumbnail: {'Set' if await db.get_thumbnail(user_id) else 'Not set'}
• Prefix/Suffix: {'Set' if await db.get_prefix(user_id) else 'Not set'}

Use buttons below to configure:
"""
    
    buttons = [
        [
            InlineKeyboardButton("🖼️ Set Thumbnail", callback_data="set_thumbnail"),
            InlineKeyboardButton("📝 Set Caption", callback_data="edit_caption")
        ],
        [
            InlineKeyboardButton("🏷️ Set Prefix/Suffix", callback_data="set_prefix_suffix"),
            InlineKeyboardButton("⚡ Set Quality", callback_data="set_quality")
        ],
        [
            InlineKeyboardButton("🗜️ Compression", callback_data="set_compression"),
            InlineKeyboardButton("🔄 Auto Delete", callback_data="toggle_auto_delete")
        ],
        [
            InlineKeyboardButton(f"{'⭐ ' if is_premium else ''}Premium Info", callback_data="premium_info"),
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ]
    
    await query.message.edit_text(settings_text, reply_markup=InlineKeyboardMarkup(buttons))

CALLBACK_MAP = {
    cb.CANCEL:              cancel_handler,            # Handles cancellation
    cb.CLOSE:               close_handler,             # Handles closing the query
    cb.EDIT_CAPTION:        edit_caption_handler,      # Handles caption editing
    cb.EDIT_BUTTON:         edit_button_handler,       # Handles button editing
    
    cb.EXTRACT_STREAM:      extract_stream_handler,    # Handles stream extraction
    cb.EXTRACT_THUMB:       extract_thumb_handler,     # Handles thumbnail extraction
    cb.FORWARD:             forward_handler,           # Handles forwarding
    
    cb.GEN_SCREENSHOT:      gen_screenshot_handler,    # Handles screenshot generation
    cb.MEDIAINFO:           mediainfo_handler,         # Handles media info retrieval
    cb.MERGE_VIDEO:         merge_video_handler,       # Handles video merging
    
    cb.REMOVE_FORWARD_TAG:  remove_forward_tag_handler,# Handles removal of forward tags
    cb.REMOVE_STREAM:       work_on_progress,          # Stream removal
    
    cb.RENAME_FILE:         rename_file_handler,       # Handles file renaming
    cb.TRIM_VIDEO:          trim_video_handler,        # Handles video trimming
    
    cb.CONVERT_FILE:        work_on_progress,          # File conversion
    cb.EDIT_METADATA:       work_on_progress,          # Metadata editing
    cb.GEN_SAMPLE_VIDEO:    work_on_progress,          # Sample video generation
    
    # Audio handlers
    cb.CONVERT_AUDIO:       convert_audio_handler,     # Audio conversion
    cb.COMPRESS_AUDIO:      compress_audio_handler,    # Audio compression
    cb.AUDIO_TAG_EDITOR:    work_on_progress,          # Audio tag editor
    cb.AUDIO_SPEED:         work_on_progress,          # Audio speed
    cb.VOLUME_CHANGER:      work_on_progress,          # Volume changer
    cb.AUDIO_BASS_BOOST:    work_on_progress,          # Bass boost
    cb.AUDIO_TREBLE_BOOST:  work_on_progress,          # Treble boost
    cb.AUDIO_8D:            work_on_progress,          # 8D audio
    cb.AUDIO_EQUALIZER:     work_on_progress,          # Equalizer
    cb.AUDIO_MERGER:        work_on_progress,          # Audio merger
    cb.SLOW_REVERB:         work_on_progress,          # Slow reverb
    
    # Document handlers
    cb.CREATE_ARCHIVE:      work_on_progress,          # Create archive
    cb.EXTRACT_ARCHIVE:     work_on_progress,          # Extract archive
    cb.SUBTITLE_CONVERTER:  work_on_progress,          # Subtitle converter
    cb.JSON_FORMATTER:      work_on_progress,          # JSON formatter
    
    # Special handlers
    cb.VIDEO_TO_GIF:        work_on_progress,          # Video to GIF
    cb.VIDEO_SPLITTER:      work_on_progress,          # Video splitter
    cb.VIDEO_OPTIMIZER:     work_on_progress,          # Video optimizer
    cb.MUTE_AUDIO:          work_on_progress,          # Mute audio
    
    # Bulk mode handlers
    cb.BULK_MODE:           bulk_mode_handler,         # Bulk mode
    cb.BULK_ARCHIVE:        bulk_archive_handler,      # Bulk archive
    cb.BULK_REMOVE_AUDIO:   work_on_progress,          # Bulk remove audio
    cb.BULK_CONVERT_MP3:    work_on_progress,          # Bulk convert MP3
    cb.BULK_RENAME:         work_on_progress,          # Bulk rename
    cb.BULK_CONVERT_VIDEO:  work_on_progress,          # Bulk convert video
    cb.BULK_VIDEO_REORDER:  work_on_progress,          # Bulk video reorder
    cb.BULK_MULTIPLEXER:    work_on_progress,          # Bulk multiplexer
    
    # Settings
    cb.SETTINGS:            settings_handler,          # Settings menu
    
    # Quality settings
    cb.QUALITY_HIGH:        work_on_progress,          # High quality
    cb.QUALITY_MEDIUM:      work_on_progress,          # Medium quality
    cb.QUALITY_LOW:         work_on_progress,          # Low quality
    cb.SCREENSHOT_AUTO:     work_on_progress,          # Auto screenshot
    cb.SCREENSHOT_MANUAL:   work_on_progress,          # Manual screenshot
}

@Client.on_callback_query()
async def callback_handlers(client: Client, query: CallbackQuery):
    data = query.data
    
    # Handle cancel and progress with prefixes
    if data.startswith('cancel'):
        await cancel_handler(client, query)
        return
    elif data.startswith('progress'):
        await progress_callback(client, query)
        return
    elif data.startswith('extract_stream_'):
        # Parse stream extraction
        parts = data.split('_')
        if len(parts) >= 3:
            stream_index = parts[2]
            stream_type = parts[3] if len(parts) > 3 else "audio"
            # Implement stream extraction logic here
            await query.answer(f"Extracting {stream_type} stream {stream_index}...", show_alert=True)
        return
    
    # Get handler from map
    handler = CALLBACK_MAP.get(data)
    if handler:
        try:
            await handler(client, query)
        except Exception as e:
            logging.error(f"Handler error for {data}: {e}")
            await query.answer(f"Error: {str(e)}", show_alert=True)
    else:
        await query.answer("Unknown command!", show_alert=True)
