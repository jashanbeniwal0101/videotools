# plugins/media_handler.py
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from core.helpers import button_generator, human_readable_size
from core.database import db
from core.handlers import check_user_access

@Client.on_message(filters.private & (filters.video | filters.document))
async def media_handler(client: Client, message: Message):
    """Handle video and document messages"""
    
    # Add user to database
    await db.add_user(client, message)
    
    # Get media info
    media = message.video or message.document
    media_type = "video" if message.video else "document"
    
    # For documents, check if they're actually videos or audio
    if media_type == "document":
        file_name = media.file_name or ""
        file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ""
        
        # Video extensions
        video_exts = ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v', '3gp']
        # Audio extensions
        audio_exts = ['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'wma', 'opus', 'mka']
        
        if file_ext in video_exts:
            media_type = "video"
        elif file_ext in audio_exts:
            media_type = "audio"
    
    # Check user access
    can_access, error_msg = await check_user_access(
        message.from_user.id,
        media.file_size
    )
    
    if not can_access:
        await message.reply_text(
            f"❌ **Access Denied**\n\n{error_msg}\n\n"
            f"Use /upgrade to get premium benefits! ⭐",
            quote=True
        )
        return
    
    # Prepare message text
    file_size_mb = media.file_size / (1024 * 1024)
    
    txt = (
        f"📁 **{media_type.title()} Received!** {'⭐' if await db.is_premium(message.from_user.id) else ''}\n\n"
        f"📄 **File:** `{media.file_name or 'Unknown'}`\n"
        f"📦 **Size:** {file_size_mb:.2f} MB ({human_readable_size(media.file_size)})\n"
        f"🔤 **MIME Type:** `{media.mime_type or 'Unknown'}`\n\n"
        f"👇 **Choose what you want to do:**"
    )
    
    # Generate appropriate buttons
    btns = button_generator(media_type)
    
    await message.reply(
        text=txt,
        reply_markup=btns,
        quote=True
    )

@Client.on_message(filters.private & filters.audio)
async def audio_handler(client: Client, message: Message):
    """Handle audio messages"""
    
    # Add user to database
    await db.add_user(client, message)
    
    audio = message.audio
    
    # Check user access
    can_access, error_msg = await check_user_access(
        message.from_user.id,
        audio.file_size
    )
    
    if not can_access:
        await message.reply_text(
            f"❌ **Access Denied**\n\n{error_msg}\n\n"
            f"Use /upgrade to get premium benefits! ⭐",
            quote=True
        )
        return
    
    # Prepare audio info
    duration = audio.duration
    minutes = duration // 60
    seconds = duration % 60
    
    txt = (
        f"🎵 **Audio Received!** {'⭐' if await db.is_premium(message.from_user.id) else ''}\n\n"
        f"📄 **Title:** `{audio.title or 'Unknown'}`\n"
        f"👤 **Performer:** `{audio.performer or 'Unknown'}`\n"
        f"⏱️ **Duration:** {minutes}:{seconds:02d}\n"
        f"📦 **Size:** {human_readable_size(audio.file_size)}\n\n"
        f"👇 **Choose what you want to do:**"
    )
    
    # Generate audio-specific buttons
    btns = button_generator("audio")
    
    await message.reply(
        text=txt,
        reply_markup=btns,
        quote=True
    )

@Client.on_message(filters.private & filters.photo)
async def image_handler(client: Client, message: Message):
    """Handle image messages"""
    photo = message.photo
    
    # Add user to database
    await db.add_user(client, message)
    
    info = {
        "📷 Type": "Photo",
        "🆔 File ID": photo.file_id,
        "📏 Dimensions": f"{photo.width} x {photo.height}",
        "📦 Size": human_readable_size(photo.file_size)
    }
    
    info_text = "🖼️ **Image Received!**\n\n"
    info_text += "\n".join(f"{k}: {v}" for k, v in info.items())
    
    # Offer to set as thumbnail
    buttons = [
        [
            InlineKeyboardButton("🖼️ Set as Default Thumbnail", callback_data="set_photo_thumb"),
            InlineKeyboardButton("📤 Forward", callback_data="forward")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close")
        ]
    ]
    
    await message.reply_text(
        info_text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
