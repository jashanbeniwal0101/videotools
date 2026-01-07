# core/helpers.py
import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from pyrogram import Client
from pyrogram.types import (
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    Message, 
    CallbackQuery
)
from config import MAX_FILE_SIZE, NON_PREMIUM_MAX_SIZE

class Callbacks:
    """Callback data constants"""
    CANCEL = "cancel"
    CLOSE = "close"
    EDIT_CAPTION = "edit_caption"
    EDIT_BUTTON = "edit_button"
    EXTRACT_STREAM = "extract_stream"
    EXTRACT_THUMB = "extract_thumb"
    FORWARD = "forward"
    GEN_SCREENSHOT = "gen_screenshot"
    GEN_SAMPLE_VIDEO = "gen_sample_video"
    MEDIAINFO = "mediainfo"
    MERGE_VIDEO = "merge_video"
    REMOVE_FORWARD_TAG = "remove_forward_tag"
    REMOVE_STREAM = "remove_stream"
    RENAME_FILE = "rename_file"
    TRIM_VIDEO = "trim_video"
    CONVERT_FILE = "convert_file"
    EDIT_METADATA = "edit_metadata"
    CONVERT_AUDIO = "convert_audio"
    COMPRESS_AUDIO = "compress_audio"
    AUDIO_TAG_EDITOR = "audio_tag_editor"
    AUDIO_SPEED = "audio_speed"
    VOLUME_CHANGER = "volume_changer"
    AUDIO_BASS_BOOST = "audio_bass_boost"
    AUDIO_TREBLE_BOOST = "audio_treble_boost"
    AUDIO_8D = "audio_8d"
    AUDIO_EQUALIZER = "audio_equalizer"
    AUDIO_MERGER = "audio_merger"
    SLOW_REVERB = "slow_reverb"
    CREATE_ARCHIVE = "create_archive"
    EXTRACT_ARCHIVE = "extract_archive"
    SUBTITLE_CONVERTER = "subtitle_converter"
    JSON_FORMATTER = "json_formatter"
    VIDEO_TO_GIF = "video_to_gif"
    VIDEO_SPLITTER = "video_splitter"
    VIDEO_OPTIMIZER = "video_optimizer"
    MUTE_AUDIO = "mute_audio"
    BULK_MODE = "bulk_mode"
    BULK_ARCHIVE = "bulk_archive"
    BULK_REMOVE_AUDIO = "bulk_remove_audio"
    BULK_CONVERT_MP3 = "bulk_convert_mp3"
    BULK_RENAME = "bulk_rename"
    BULK_CONVERT_VIDEO = "bulk_convert_video"
    BULK_VIDEO_REORDER = "bulk_video_reorder"
    BULK_MULTIPLEXER = "bulk_multiplexer"
    SETTINGS = "settings"
    QUALITY_HIGH = "quality_high"
    QUALITY_MEDIUM = "quality_medium"
    QUALITY_LOW = "quality_low"
    SCREENSHOT_AUTO = "screenshot_auto"
    SCREENSHOT_MANUAL = "screenshot_manual"

async def progress_handler(current, total, message: Message, start_time: float, 
                          operation: str, file_name: str = ""):
    """Progress handler for downloads/uploads"""
    try:
        now = time.time()
        diff = now - start_time
        
        if current == 0 or diff < 0.5:  # Prevent division by zero and too frequent updates
            return
        
        percentage = current * 100 / total
        speed = current / diff
        time_to_completion = (total - current) / speed if speed > 0 else 0
        
        elapsed_time = round(diff, 2)
        estimated_total_time = round(time_to_completion, 2)
        
        progress_bar = "[" + "■" * int(percentage / 5) + "□" * (20 - int(percentage / 5)) + "]"
        
        text = (
            f"**{operation}**\n\n"
            f"📁 **File:** `{file_name[:50]}{'...' if len(file_name) > 50 else ''}`\n"
            f"{progress_bar} {percentage:.2f}%\n\n"
            f"📊 **Progress:** {human_readable_size(current)} / {human_readable_size(total)}\n"
            f"🚀 **Speed:** {human_readable_size(speed)}/s\n"
            f"⏱️ **Elapsed:** {format_time(elapsed_time)}\n"
            f"⏳ **ETA:** {format_time(estimated_total_time)}\n"
        )
        
        try:
            await message.edit(text)
        except:
            pass
            
    except Exception as e:
        logging.error(f"Progress handler error: {e}")

async def progress_handler_for_4gb(current, total, message: Message, start_time: float,
                                 operation: str, file_name: str = ""):
    """Progress handler for files > 4GB using premium client"""
    await progress_handler(current, total, message, start_time, operation, file_name)

def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(units) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.2f} {units[i]}"

def format_time(seconds: float) -> str:
    """Format seconds to HH:MM:SS"""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def button_generator(media_type: str = "video") -> InlineKeyboardMarkup:
    """Generate buttons based on media type"""
    buttons = []
    
    if media_type == "video":
        buttons = [
            [
                InlineKeyboardButton("🎞️ Remove Stream", callback_data="remove_stream"),
                InlineKeyboardButton("🎵 Extract Stream", callback_data="extract_stream")
            ],
            [
                InlineKeyboardButton("📝 Edit Caption", callback_data="edit_caption"),
                InlineKeyboardButton("🔧 Edit Buttons", callback_data="edit_button")
            ],
            [
                InlineKeyboardButton("✂️ Trim Video", callback_data="trim_video"),
                InlineKeyboardButton("🔗 Merge Videos", callback_data="merge_video")
            ],
            [
                InlineKeyboardButton("🔇 Mute Audio", callback_data="mute_audio"),
                InlineKeyboardButton("🎥 Merge Video+Audio", callback_data="merge_video_audio")
            ],
            [
                InlineKeyboardButton("🎬 Merge Video+Subtitle", callback_data="merge_video_sub"),
                InlineKeyboardButton("🌀 Video to GIF", callback_data="video_to_gif")
            ],
            [
                InlineKeyboardButton("🔪 Split Video", callback_data="video_splitter"),
                InlineKeyboardButton("📸 Screenshots", callback_data="gen_screenshot")
            ],
            [
                InlineKeyboardButton("🎞️ Sample Video", callback_data="gen_sample_video"),
                InlineKeyboardButton("🎵 Convert Audio", callback_data="convert_audio")
            ],
            [
                InlineKeyboardButton("⚡ Optimize Video", callback_data="video_optimizer"),
                InlineKeyboardButton("🔄 Convert Format", callback_data="convert_file")
            ],
            [
                InlineKeyboardButton("📝 Rename File", callback_data="rename_file"),
                InlineKeyboardButton("🏷️ Edit Metadata", callback_data="edit_metadata")
            ],
            [
                InlineKeyboardButton("📊 Media Info", callback_data="mediainfo"),
                InlineKeyboardButton("📦 Create Archive", callback_data="create_archive")
            ],
            [
                InlineKeyboardButton("🖼️ Extract Thumb", callback_data="extract_thumb"),
                InlineKeyboardButton("🚫 Remove Tag", callback_data="remove_forward_tag")
            ],
            [
                InlineKeyboardButton("📤 Forward", callback_data="forward"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings")
            ]
        ]
    
    elif media_type == "audio":
        buttons = [
            [
                InlineKeyboardButton("📝 Edit Caption", callback_data="edit_caption"),
                InlineKeyboardButton("🔧 Edit Buttons", callback_data="edit_button")
            ],
            [
                InlineKeyboardButton("🌀 Slow & Reverb", callback_data="slow_reverb"),
                InlineKeyboardButton("🎵 Convert Audio", callback_data="convert_audio")
            ],
            [
                InlineKeyboardButton("📦 Create Archive", callback_data="create_archive"),
                InlineKeyboardButton("🔀 Merge Audio", callback_data="audio_merger")
            ],
            [
                InlineKeyboardButton("🎧 8D Audio", callback_data="audio_8d"),
                InlineKeyboardButton("🎛️ Equalizer", callback_data="audio_equalizer")
            ],
            [
                InlineKeyboardButton("🔊 Bass Boost", callback_data="audio_bass_boost"),
                InlineKeyboardButton("🎶 Treble Boost", callback_data="audio_treble_boost")
            ],
            [
                InlineKeyboardButton("✂️ Trim Audio", callback_data="trim_video"),
                InlineKeyboardButton("⚡ Auto Trim", callback_data="trim_auto")
            ],
            [
                InlineKeyboardButton("📝 Rename File", callback_data="rename_file"),
                InlineKeyboardButton("🏷️ Tag Editor", callback_data="audio_tag_editor")
            ],
            [
                InlineKeyboardButton("⚡ Speed Changer", callback_data="audio_speed"),
                InlineKeyboardButton("🔊 Volume Changer", callback_data="volume_changer")
            ],
            [
                InlineKeyboardButton("📊 Media Info", callback_data="mediainfo"),
                InlineKeyboardButton("🗜️ Compress Audio", callback_data="compress_audio")
            ],
            [
                InlineKeyboardButton("📤 Forward", callback_data="forward"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings")
            ]
        ]
    
    elif media_type == "document":
        buttons = [
            [
                InlineKeyboardButton("📝 Rename File", callback_data="rename_file"),
                InlineKeyboardButton("📦 Create Archive", callback_data="create_archive")
            ],
            [
                InlineKeyboardButton("📂 Extract Archive", callback_data="extract_archive"),
                InlineKeyboardButton("📝 Edit Caption", callback_data="edit_caption")
            ],
            [
                InlineKeyboardButton("🔧 Edit Buttons", callback_data="edit_button"),
                InlineKeyboardButton("🚫 Remove Tag", callback_data="remove_forward_tag")
            ],
            [
                InlineKeyboardButton("📜 Subtitle Convert", callback_data="subtitle_converter"),
                InlineKeyboardButton("📄 JSON Formatter", callback_data="json_formatter")
            ],
            [
                InlineKeyboardButton("📊 Media Info", callback_data="mediainfo"),
                InlineKeyboardButton("📤 Forward", callback_data="forward")
            ]
        ]
    
    # Add cancel button at the end
    buttons.append([
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        InlineKeyboardButton("🔒 Close", callback_data="close")
    ])
    
    return InlineKeyboardMarkup(buttons)

def bulk_mode_buttons() -> InlineKeyboardMarkup:
    """Generate bulk mode buttons"""
    buttons = [
        [
            InlineKeyboardButton("📦 Bulk Archive", callback_data="bulk_archive"),
            InlineKeyboardButton("🔇 Bulk Remove Audio", callback_data="bulk_remove_audio")
        ],
        [
            InlineKeyboardButton("🎵 Bulk Convert MP3", callback_data="bulk_convert_mp3"),
            InlineKeyboardButton("📝 Bulk Rename", callback_data="bulk_rename")
        ],
        [
            InlineKeyboardButton("🎬 Bulk Convert Video", callback_data="bulk_convert_video"),
            InlineKeyboardButton("🔀 Bulk Video Reorder", callback_data="bulk_video_reorder")
        ],
        [
            InlineKeyboardButton("🎬 Bulk Video Merge", callback_data="merge_video"),
            InlineKeyboardButton("🎥 Bulk Multiplexer", callback_data="bulk_multiplexer")
        ],
        [
            InlineKeyboardButton("🔙 Back to Normal", callback_data="cancel"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

async def start_premium_client():
    """Start premium client for >4GB files"""
    from pyrogram import Client as PyrogramClient
    from config import APP_ID, API_HASH, BOT_TOKEN
    
    premium_client = PyrogramClient(
        "premium_bot",
        api_id=APP_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        workers=2
    )
    
    await premium_client.start()
    return premium_client

# Global premium client instance
premium_client = None
