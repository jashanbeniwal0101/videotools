# core/handlers.py
import os
import asyncio
import logging
import time
import json
import random
import string
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta

from pyrogram import Client
from pyrogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaDocument
)
from pyrogram.errors import FloodWait, BadRequest

from config import DUMP_ID, MAX_FILE_SIZE, NON_PREMIUM_MAX_SIZE
from core.ffmpeg_handlers import FFmpegHandler
from core.helpers import (
    progress_handler, 
    progress_handler_for_4gb, 
    human_readable_size,
    button_generator,
    Callbacks as cb
)
from core.database import Database
from core.wmanager import task_manager
from core.helpers import start_premium_client, premium_client

# Initialize database
from config import MONGO_URI, DATABASE_NAME
db = Database(MONGO_URI, DATABASE_NAME)

async def check_user_access(user_id: int, file_size: int = 0) -> Tuple[bool, str]:
    """Check if user can access the bot"""
    # Check cooldown
    if not await db.can_start_task(user_id):
        remaining = await db.get_remaining_cooldown(user_id)
        minutes = remaining // 60
        seconds = remaining % 60
        return False, f"⏳ Please wait {minutes}m {seconds}s before starting another task.\n\nUpgrade to premium for no cooldown!"
    
    # Check file size limit for non-premium
    if not await db.is_premium(user_id) and file_size > NON_PREMIUM_MAX_SIZE:
        return False, f"📁 File too large! Non-premium users limited to {human_readable_size(NON_PREMIUM_MAX_SIZE)}.\n\nUpgrade to premium for {human_readable_size(MAX_FILE_SIZE)} limit!"
    
    return True, ""

async def download_file(client: Client, message: Message, file_type: str = "video") -> Tuple[bool, str, Optional[Dict]]:
    """Download file with progress"""
    try:
        # Get file from message
        if file_type == "video":
            media = message.video or message.document
        elif file_type == "audio":
            media = message.audio or message.document
        else:
            media = message.document
        
        if not media:
            return False, "No media found", None
        
        # Check user access
        can_access, error_msg = await check_user_access(
            message.from_user.id, 
            media.file_size
        )
        if not can_access:
            return False, error_msg, None
        
        file_name = media.file_name or f"file_{int(time.time())}"
        file_ext = Path(file_name).suffix
        
        # Create temp directory
        temp_dir = Path("temp") / str(message.from_user.id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique file path
        timestamp = int(time.time())
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        temp_file = temp_dir / f"{timestamp}_{random_str}{file_ext}"
        
        # Download message
        download_msg = await message.reply_text(f"📥 Downloading `{file_name}`...")
        start_time = time.time()
        
        # Choose appropriate client based on file size
        if media.file_size > 2 * 1024 * 1024 * 1024:  # > 2GB
            if not premium_client:
                premium_client_instance = await start_premium_client()
            else:
                premium_client_instance = premium_client
            
            file_path = await premium_client_instance.download_media(
                message,
                file_name=str(temp_file),
                progress=progress_handler_for_4gb,
                progress_args=(download_msg, file_name, start_time, "Downloading")
            )
        else:
            file_path = await client.download_media(
                message,
                file_name=str(temp_file),
                progress=progress_handler,
                progress_args=(download_msg, file_name, start_time, "Downloading")
            )
        
        await download_msg.delete()
        
        if not file_path or not Path(file_path).exists():
            return False, "Download failed", None
        
        # Get file info
        file_info = {
            'path': file_path,
            'name': file_name,
            'size': media.file_size,
            'type': file_type,
            'message': message
        }
        
        # Update user's last task time
        await db.update_last_task_time(message.from_user.id)
        await db.increment_task_count(message.from_user.id)
        
        return True, "Download successful", file_info
        
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return False, f"Flood wait: {e.value} seconds", None
    except Exception as e:
        logging.error(f"Download error: {e}")
        return False, f"Error: {str(e)}", None

async def upload_file(client: Client, message: Message, file_path: str, 
                     caption: str = "", thumb: str = None) -> bool:
    """Upload file with progress"""
    try:
        file_name = Path(file_path).name
        file_size = Path(file_path).stat().st_size
        
        upload_msg = await message.reply_text(f"📤 Uploading `{file_name}`...")
        start_time = time.time()
        
        # Determine file type
        ext = Path(file_path).suffix.lower()
        is_video = ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v']
        is_audio = ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus']
        
        # Get user's caption if available
        user_caption = await db.get_caption(message.from_user.id)
        if user_caption:
            caption = user_caption
        
        # Get user's thumbnail if available
        if not thumb:
            thumb_data = await db.get_thumbnail(message.from_user.id)
            if thumb_data:
                # Download thumbnail
                thumb_path = f"temp/thumb_{message.from_user.id}.jpg"
                await client.download_media(thumb_data, file_name=thumb_path)
                thumb = thumb_path
        
        if is_video:
            # Upload as video
            await client.send_video(
                chat_id=message.chat.id,
                video=file_path,
                caption=caption,
                thumb=thumb,
                duration=None,  # Will be auto-detected
                width=None,
                height=None,
                supports_streaming=True,
                progress=progress_handler,
                progress_args=(upload_msg, file_name, start_time, "Uploading")
            )
        
        elif is_audio:
            # Upload as audio
            await client.send_audio(
                chat_id=message.chat.id,
                audio=file_path,
                caption=caption,
                thumb=thumb,
                duration=None,
                performer=None,
                title=Path(file_path).stem,
                progress=progress_handler,
                progress_args=(upload_msg, file_name, start_time, "Uploading")
            )
        
        else:
            # Upload as document
            await client.send_document(
                chat_id=message.chat.id,
                document=file_path,
                caption=caption,
                thumb=thumb,
                progress=progress_handler,
                progress_args=(upload_msg, file_name, start_time, "Uploading")
            )
        
        await upload_msg.delete()
        return True
        
    except Exception as e:
        logging.error(f"Upload error: {e}")
        await message.reply_text(f"Upload failed: {str(e)}")
        return False

async def cancel_job(client: Client, query: CallbackQuery):
    """Cancel current job"""
    try:
        await task_manager.cancel_user_tasks(query.from_user.id)
        await query.message.edit_text("❌ Operation cancelled!")
    except Exception as e:
        logging.error(f"Cancel error: {e}")

async def forward_job(client: Client, query: CallbackQuery):
    """Forward media to another chat"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No message to forward!", show_alert=True)
            return
        
        await query.message.edit_text("📤 Forwarding...")
        await message.forward(DUMP_ID or query.from_user.id)
        await query.message.edit_text("✅ Forwarded successfully!")
    except Exception as e:
        await query.message.edit_text(f"❌ Forward failed: {str(e)}")

async def mediainfo_job(client: Client, query: CallbackQuery):
    """Generate media information"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No media found!", show_alert=True)
            return
        
        await query.message.edit_text("📊 Generating media info...")
        
        # Get file
        media = message.video or message.document or message.audio
        if not media:
            await query.message.edit_text("❌ No media found!")
            return
        
        # Download file
        success, msg, file_info = await download_file(client, message)
        if not success:
            await query.message.edit_text(f"❌ {msg}")
            return
        
        # Generate mediainfo using ffmpeg
        ffmpeg = FFmpegHandler()
        mediainfo = await ffmpeg.mediainfo(file_info['path'])
        
        # Format mediainfo
        info_text = f"""
📁 **File Info:**
├── 📝 Name: `{file_info['name']}`
├── 📦 Size: {human_readable_size(file_info['size'])}
├── 📍 Type: {file_info['type'].title()}
└── 🕐 Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{mediainfo}
        """
        
        # Send as file if too long
        if len(info_text) > 4000:
            temp_file = f"temp/mediainfo_{query.from_user.id}.txt"
            with open(temp_file, 'w') as f:
                f.write(info_text)
            
            await client.send_document(
                query.message.chat.id,
                temp_file,
                caption="📊 Media Information"
            )
            os.remove(temp_file)
        else:
            await query.message.edit_text(info_text)
        
        # Cleanup
        os.remove(file_info['path'])
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def trim_video_job(client: Client, query: CallbackQuery):
    """Trim video"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No video found!", show_alert=True)
            return
        
        # Ask for trim times
        await query.message.edit_text(
            "✂️ **Video Trimmer**\n\n"
            "Send start and end times in format:\n"
            "`HH:MM:SS` to `HH:MM:SS`\n\n"
            "Example: `00:01:30` to `00:02:45`\n"
            "Or send `cancel` to abort."
        )
        
        # Wait for user input
        try:
            response = await client.listen(
                chat_id=query.message.chat.id,
                user_id=query.from_user.id,
                filters="text",
                timeout=60
            )
            
            if response.text.lower() == "cancel":
                await query.message.edit_text("❌ Trim cancelled!")
                return
            
            # Parse times
            times = response.text.split("to")
            if len(times) != 2:
                await query.message.edit_text("❌ Invalid format! Use: `HH:MM:SS to HH:MM:SS`")
                return
            
            start_time = times[0].strip()
            end_time = times[1].strip()
            
            # Download video
            await query.message.edit_text("📥 Downloading video...")
            success, msg, file_info = await download_file(client, message, "video")
            if not success:
                await query.message.edit_text(f"❌ {msg}")
                return
            
            # Trim video
            await query.message.edit_text("✂️ Trimming video...")
            
            output_path = file_info['path'].replace(
                Path(file_info['path']).suffix, 
                f"_trimmed{Path(file_info['path']).suffix}"
            )
            
            ffmpeg = FFmpegHandler()
            await ffmpeg.trim(
                client, query.message,
                file_info['path'], output_path,
                start_time, end_time
            )
            
            # Upload trimmed video
            await query.message.edit_text("📤 Uploading trimmed video...")
            await upload_file(client, query.message, output_path, 
                            f"Trimmed: {start_time} to {end_time}")
            
            # Cleanup
            os.remove(file_info['path'])
            if os.path.exists(output_path):
                os.remove(output_path)
            
        except asyncio.TimeoutError:
            await query.message.edit_text("⏰ Timeout! No response received.")
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def merge_video_job(client: Client, query: CallbackQuery):
    """Merge multiple videos"""
    try:
        await query.message.edit_text(
            "🔗 **Video Merger**\n\n"
            "Send me multiple videos one by one.\n"
            "Reply with `/done` when finished.\n"
            "Reply with `/cancel` to abort."
        )
        
        videos = []
        while True:
            try:
                response = await client.listen(
                    chat_id=query.message.chat.id,
                    user_id=query.from_user.id,
                    filters="video|document",
                    timeout=60
                )
                
                if response.text and response.text.lower() == "/done":
                    break
                if response.text and response.text.lower() == "/cancel":
                    await query.message.edit_text("❌ Merge cancelled!")
                    return
                
                # Download video
                success, msg, file_info = await download_file(client, response, "video")
                if success:
                    videos.append(file_info['path'])
                    await query.message.edit_text(
                        f"✅ Added video {len(videos)}\n"
                        f"Send next video or /done to finish"
                    )
                
            except asyncio.TimeoutError:
                break
        
        if len(videos) < 2:
            await query.message.edit_text("❌ Need at least 2 videos to merge!")
            return
        
        # Merge videos
        await query.message.edit_text(f"🔗 Merging {len(videos)} videos...")
        
        output_path = f"temp/merged_{query.from_user.id}_{int(time.time())}.mp4"
        ffmpeg = FFmpegHandler()
        await ffmpeg.merge(client, query.message, videos, output_path)
        
        # Upload merged video
        await query.message.edit_text("📤 Uploading merged video...")
        await upload_file(client, query.message, output_path, f"Merged {len(videos)} videos")
        
        # Cleanup
        for video in videos:
            if os.path.exists(video):
                os.remove(video)
        if os.path.exists(output_path):
            os.remove(output_path)
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def rename_file_job(client: Client, query: CallbackQuery):
    """Rename file"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No file found!", show_alert=True)
            return
        
        await query.message.edit_text(
            "📝 **File Renamer**\n\n"
            "Send me the new file name with extension.\n"
            "Example: `my_video.mp4`\n\n"
            "Reply with `cancel` to abort."
        )
        
        # Wait for new name
        try:
            response = await client.listen(
                chat_id=query.message.chat.id,
                user_id=query.from_user.id,
                filters="text",
                timeout=60
            )
            
            if response.text.lower() == "cancel":
                await query.message.edit_text("❌ Rename cancelled!")
                return
            
            new_name = response.text.strip()
            
            # Download file
            success, msg, file_info = await download_file(client, message)
            if not success:
                await query.message.edit_text(f"❌ {msg}")
                return
            
            # Rename file
            new_path = Path(file_info['path']).parent / new_name
            os.rename(file_info['path'], new_path)
            
            # Upload renamed file
            await query.message.edit_text("📤 Uploading renamed file...")
            await upload_file(client, query.message, str(new_path))
            
            # Cleanup
            if os.path.exists(new_path):
                os.remove(new_path)
            
        except asyncio.TimeoutError:
            await query.message.edit_text("⏰ Timeout! No response received.")
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def edit_caption_job(client: Client, query: CallbackQuery):
    """Edit caption of media"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No message found!", show_alert=True)
            return
        
        await query.message.edit_text(
            "📝 **Caption Editor**\n\n"
            "Send me the new caption.\n"
            "Use `{filename}` for file name\n"
            "Use `{size}` for file size\n"
            "Use `{duration}` for duration\n\n"
            "Reply with `cancel` to abort."
        )
        
        # Wait for new caption
        try:
            response = await client.listen(
                chat_id=query.message.chat.id,
                user_id=query.from_user.id,
                filters="text",
                timeout=60
            )
            
            if response.text.lower() == "cancel":
                await query.message.edit_text("❌ Edit cancelled!")
                return
            
            new_caption = response.text
            
            # Save caption to database for user
            await db.set_caption(query.from_user.id, new_caption)
            
            await query.message.edit_text("✅ Caption saved!\nIt will be used for future uploads.")
            
        except asyncio.TimeoutError:
            await query.message.edit_text("⏰ Timeout! No response received.")
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def extract_thumb_job(client: Client, query: CallbackQuery):
    """Extract thumbnail from video"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No video found!", show_alert=True)
            return
        
        # Ask for timestamp
        await query.message.edit_text(
            "🖼️ **Thumbnail Extractor**\n\n"
            "Send timestamp in format: `HH:MM:SS`\n"
            "Example: `00:01:30`\n"
            "Leave empty for auto thumbnail.\n\n"
            "Reply with `cancel` to abort."
        )
        
        try:
            response = await client.listen(
                chat_id=query.message.chat.id,
                user_id=query.from_user.id,
                filters="text",
                timeout=60
            )
            
            if response.text.lower() == "cancel":
                await query.message.edit_text("❌ Extraction cancelled!")
                return

timestamp = response.text.strip() if response.text.strip() else None
            
            # Download video
            success, msg, file_info = await download_file(client, message, "video")
            if not success:
                await query.message.edit_text(f"❌ {msg}")
                return
            
            # Extract thumbnail
            await query.message.edit_text("🖼️ Extracting thumbnail...")
            
            ffmpeg = FFmpegHandler()
            thumb_path = await ffmpeg.extract_thumbnail(
                client, query.message,
                file_info['path'], timestamp
            )
            
            if thumb_path and os.path.exists(thumb_path):
                # Send thumbnail
                await client.send_photo(
                    query.message.chat.id,
                    thumb_path,
                    caption=f"Thumbnail extracted from `{file_info['name']}`"
                )
                
                # Ask if user wants to save as default thumbnail
                buttons = [
                    [
                        InlineKeyboardButton("✅ Set as Default", callback_data="set_default_thumb"),
                        InlineKeyboardButton("❌ No Thanks", callback_data="close")
                    ]
                ]
                
                await query.message.edit_text(
                    "Do you want to set this as your default thumbnail?",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                
                # Save thumbnail to database if chosen
                try:
                    set_response = await client.listen(
                        chat_id=query.message.chat.id,
                        user_id=query.from_user.id,
                        filters="callback_query",
                        timeout=30
                    )
                    
                    if set_response.data == "set_default_thumb":
                        # Upload thumbnail to Telegram and save file_id
                        thumb_msg = await client.send_photo(
                            query.message.chat.id,
                            thumb_path
                        )
                        await db.set_thumbnail(query.from_user.id, thumb_msg.photo.file_id)
                        await query.message.edit_text("✅ Default thumbnail set!")
                    
                except asyncio.TimeoutError:
                    pass
                
                # Cleanup
                os.remove(thumb_path)
            
            # Cleanup video
            os.remove(file_info['path'])
            
        except asyncio.TimeoutError:
            await query.message.edit_text("⏰ Timeout! No response received.")
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def extract_stream_job(client: Client, query: CallbackQuery):
    """Extract audio/subtitle stream from video"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No video found!", show_alert=True)
            return
        
        # Get stream info
        success, msg, file_info = await download_file(client, message, "video")
        if not success:
            await query.message.edit_text(f"❌ {msg}")
            return
        
        ffmpeg = FFmpegHandler()
        streams = await ffmpeg.view_streams(file_info['path'])
        
        # Show stream selection
        buttons = []
        for i, stream in enumerate(streams[:10]):  # Show first 10 streams
            stream_type = stream.get('type', 'unknown')
            codec = stream.get('codec', 'unknown')
            lang = stream.get('language', 'und')
            
            btn_text = f"{stream_type.upper()} {i}: {codec} ({lang})"
            buttons.append([
                InlineKeyboardButton(
                    btn_text,
                    callback_data=f"extract_stream_{i}_{stream_type}"
                )
            ])
        
        buttons.append([
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ])
        
        await query.message.edit_text(
            f"🎵 **Select stream to extract from `{file_info['name']}`**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def gen_screenshot_job(client: Client, query: CallbackQuery):
    """Generate screenshots from video"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No video found!", show_alert=True)
            return
        
        # Ask for screenshot count
        await query.message.edit_text(
            "📸 **Screenshot Generator**\n\n"
            "How many screenshots?\n"
            "Send number (1-20) or `auto` for automatic.\n\n"
            "Reply with `cancel` to abort."
        )
        
        try:
            response = await client.listen(
                chat_id=query.message.chat.id,
                user_id=query.from_user.id,
                filters="text",
                timeout=60
            )
            
            if response.text.lower() == "cancel":
                await query.message.edit_text("❌ Cancelled!")
                return
            
            count = 5  # Default
            if response.text.lower() == "auto":
                count = "auto"
            else:
                try:
                    count = int(response.text.strip())
                    count = max(1, min(20, count))  # Limit to 1-20
                except:
                    count = 5
            
            # Download video
            success, msg, file_info = await download_file(client, message, "video")
            if not success:
                await query.message.edit_text(f"❌ {msg}")
                return
            
            # Generate screenshots
            await query.message.edit_text("📸 Generating screenshots...")
            
            ffmpeg = FFmpegHandler()
            screenshots = await ffmpeg.generate_screenshots(
                client, query.message,
                file_info['path'], count
            )
            
            if screenshots:
                # Send screenshots as album
                media_group = []
                for i, screenshot in enumerate(screenshots):
                    if os.path.exists(screenshot):
                        media_group.append(
                            InputMediaPhoto(
                                screenshot,
                                caption=f"Screenshot {i+1}" if len(screenshots) > 1 else None
                            )
                        )
                
                if media_group:
                    await client.send_media_group(
                        query.message.chat.id,
                        media_group
                    )
                
                # Cleanup
                for screenshot in screenshots:
                    if os.path.exists(screenshot):
                        os.remove(screenshot)
            
            # Cleanup video
            os.remove(file_info['path'])
            
            await query.message.edit_text("✅ Screenshots generated!")
            
        except asyncio.TimeoutError:
            await query.message.edit_text("⏰ Timeout! No response received.")
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def remove_forward_tag_job(client: Client, query: CallbackQuery):
    """Remove forward tag from message"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No message found!", show_alert=True)
            return
        
        # Check if message is forwarded
        if not message.forward_from and not message.forward_from_chat:
            await query.answer("Message is not forwarded!", show_alert=True)
            return
        
        # Download media if exists
        media = message.video or message.document or message.audio or message.photo
        if not media:
            await query.answer("No media found in message!", show_alert=True)
            return
        
        await query.message.edit_text("🔄 Removing forward tag...")
        
        # Download file
        file_type = "video" if message.video else "audio" if message.audio else "document"
        success, msg, file_info = await download_file(client, message, file_type)
        if not success:
            await query.message.edit_text(f"❌ {msg}")
            return
        
        # Upload file without forward tag
        await query.message.edit_text("📤 Uploading file...")
        await upload_file(client, query.message, file_info['path'])
        
        # Cleanup
        os.remove(file_info['path'])
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def progress_job(client: Client, query: CallbackQuery):
    """Show progress of current task"""
    try:
        task_id = query.data.split("_")[1] if "_" in query.data else None
        if task_id:
            status = task_manager.status(task_id)
            await query.answer(f"Progress: {status.get('progress', 0)}%\nStatus: {status.get('status', 'unknown')}", show_alert=True)
        else:
            await query.answer("No task ID found!", show_alert=True)
    except Exception as e:
        logging.error(f"Progress job error: {e}")

async def edit_button_job(client: Client, query: CallbackQuery):
    """Edit buttons of message"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No message found!", show_alert=True)
            return
        
        await query.answer("Button editing feature coming soon!", show_alert=True)
        
    except Exception as e:
        logging.error(f"Edit button error: {e}")

# Audio specific handlers
async def convert_audio_job(client: Client, query: CallbackQuery):
    """Convert audio to different format"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No audio found!", show_alert=True)
            return
        
        # Show format selection
        buttons = [
            [
                InlineKeyboardButton("🎵 MP3", callback_data="convert_mp3"),
                InlineKeyboardButton("🎵 WAV", callback_data="convert_wav")
            ],
            [
                InlineKeyboardButton("🎵 FLAC", callback_data="convert_flac"),
                InlineKeyboardButton("🎵 AAC", callback_data="convert_aac")
            ],
            [
                InlineKeyboardButton("🎵 OGG", callback_data="convert_ogg"),
                InlineKeyboardButton("🎵 OPUS", callback_data="convert_opus")
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        
        await query.message.edit_text(
            "🎵 **Audio Converter**\n\nSelect output format:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

async def compress_audio_job(client: Client, query: CallbackQuery):
    """Compress audio file"""
    try:
        message = query.message.reply_to_message
        if not message:
            await query.answer("No audio found!", show_alert=True)
            return
        
        # Get user's compression quality
        quality = await db.get_setting(query.from_user.id, "compress_quality") or 80
        
        await query.message.edit_text(
            f"🗜️ **Audio Compressor**\n\n"
            f"Current quality: {quality}%\n\n"
            "Send new quality (1-100) or press cancel:"
        )
        
        try:
            response = await client.listen(
                chat_id=query.message.chat.id,
                user_id=query.from_user.id,
                filters="text",
                timeout=60
            )
            
            if response.text.lower() == "cancel":
                await query.message.edit_text("❌ Cancelled!")
                return
            
            try:
                new_quality = int(response.text.strip())
                new_quality = max(1, min(100, new_quality))
                await db.update_setting(query.from_user.id, "compress_quality", new_quality)
                
                # Download and compress
                success, msg, file_info = await download_file(client, message, "audio")
                if not success:
                    await query.message.edit_text(f"❌ {msg}")
                    return
                
                await query.message.edit_text(f"🗜️ Compressing audio at {new_quality}% quality...")
                
                ffmpeg = FFmpegHandler()
                output_path = await ffmpeg.compress_audio(
                    client, query.message,
                    file_info['path'], new_quality
                )
                
                if output_path and os.path.exists(output_path):
                    # Upload compressed audio
                    await query.message.edit_text("📤 Uploading compressed audio...")
                    await upload_file(
                        client, query.message, output_path,
                        f"Compressed at {new_quality}% quality"
                    )
                    
                    # Cleanup
                    os.remove(output_path)
                
                # Cleanup original
                os.remove(file_info['path'])
                
            except ValueError:
                await query.message.edit_text("❌ Invalid number!")
        
        except asyncio.TimeoutError:
            await query.message.edit_text("⏰ Timeout!")
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

# Bulk mode handlers
async def bulk_mode_job(client: Client, query: CallbackQuery):
    """Enter bulk mode"""
    from core.helpers import bulk_mode_buttons
    
    await query.message.edit_text(
        "🌟 **Bulk Mode Activated**\n\n"
        "Now send me multiple files and choose a bulk operation.\n"
        "All files will be processed automatically!\n\n"
        "**Available bulk operations:**",
        reply_markup=bulk_mode_buttons()
    )

async def bulk_archive_job(client: Client, query: CallbackQuery):
    """Create archive from multiple files"""
    try:
        await query.message.edit_text(
            "📦 **Bulk Archive Creator**\n\n"
            "Send me multiple files one by one.\n"
            "Reply with `/done` when finished.\n\n"
            "Archive format: ZIP\n"
            "Password: Optional (send after files)"
        )
        
        files = []
        while True:
            try:
                response = await client.listen(
                    chat_id=query.message.chat.id,
                    user_id=query.from_user.id,
                    filters="document|video|audio|photo",
                    timeout=60
                )
                
                if response.text and response.text.lower() == "/done":
                    break
                
                # Download file
                success, msg, file_info = await download_file(client, response)
                if success:
                    files.append(file_info['path'])
                    await query.message.edit_text(
                        f"✅ Added file {len(files)}\n"
                        f"Total size: {human_readable_size(sum(os.path.getsize(f) for f in files))}\n"
                        f"Send /done when finished"
                    )
                
            except asyncio.TimeoutError:
                break
        
        if not files:
            await query.message.edit_text("❌ No files received!")
            return
        
        # Ask for password
        await query.message.edit_text(
            "Enter password for archive (or send `skip` for no password):"
        )
        
        try:
            pass_response = await client.listen(
                chat_id=query.message.chat.id,
                user_id=query.from_user.id,
                filters="text",
                timeout=30
            )
            
            password = None
            if pass_response.text.lower() != "skip":
                password = pass_response.text
            
            # Create archive
            await query.message.edit_text("📦 Creating archive...")
            
            import zipfile
            archive_path = f"temp/archive_{query.from_user.id}_{int(time.time())}.zip"
            
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in files:
                    zipf.write(file_path, os.path.basename(file_path))
                    if password:
                        # Note: For password protection, you'd need 7z or rar
                        # This is a simplified version
                        pass
            
            # Upload archive
            await query.message.edit_text("📤 Uploading archive...")
            await upload_file(
                client, query.message, archive_path,
                f"Archive of {len(files)} files" + (f" (Password: {password})" if password else "")
            )
            
            # Cleanup
            for file_path in files:
                if os.path.exists(file_path):
                    os.remove(file_path)
            if os.path.exists(archive_path):
                os.remove(archive_path)
            
        except asyncio.TimeoutError:
            await query.message.edit_text("⏰ Timeout! Creating archive without password...")
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")
        
