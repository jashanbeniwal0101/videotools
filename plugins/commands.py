# plugins/commands.py
import logging
import psutil
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from core.handlers import task_manager
from core.database import db
from core.helpers import human_readable_size

@Client.on_message(filters.command(['start']) & filters.private)
async def echo_(client: Client, message: Message):
    """Handle /start command - welcome message"""
    # Add user to database
    await db.add_user(client, message)
    
    # Check if user is premium
    is_premium = await db.is_premium(message.from_user.id)
    
    txt = f"""
🌟 Welcome to MediaBot {'⭐' if is_premium else ''}

I'm your all-in-one media processing assistant!

**{'⭐ Premium Features:' if is_premium else 'Free Features:'}**
{'• No cooldown between tasks' if is_premium else '• 25-minute cooldown between tasks'}
{'• Support for files up to 4GB' if is_premium else '• Files up to 500MB'}
• 50+ media processing tools
• Bulk processing mode
• Custom settings and presets

**How to use:**
1. Send me any video, audio, or document
2. Choose from the menu of options
3. I'll process and return your file

**Quick Commands:**
/help - Show detailed help
/settings - Configure your preferences
/status - Check bot and system status
/tasks - View your active tasks
/upgrade - Premium information

Ready to roll? Drop your file and let's work some media magic! ✨
"""
    await message.reply(txt)

@Client.on_message(filters.command(['help']) & filters.private)
async def help_command(client: Client, message: Message):
    """Show help message with all features"""
    help_text = """
📚 **Available Commands:**

**Basic Commands:**
/start - Welcome message and bot introduction
/help - Show this help message
/settings - Configure your preferences
/status - Show bot system status
/tasks - View your active tasks
/upgrade - Premium features information

🎥 **Video Tools:**
• Trim video from start to end time
• Merge multiple videos
• Extract audio or subtitles
• Remove audio or subtitles
• Convert video formats (MP4, MKV, AVI, etc.)
• Generate screenshots
• Create sample videos
• Optimize video size
• Convert to GIF
• Split video into parts
• Mute audio in video
• Merge video + audio + subtitles

🎵 **Audio Tools:**
• Convert formats (MP3, WAV, FLAC, AAC, OGG, OPUS)
• Compress audio files
• Edit audio tags and metadata
• Adjust speed (50-200%)
• Change volume (10-200%)
• Bass and treble boost
• 8D audio effect
• Equalizer settings
• Slow + reverb effects
• Merge multiple audio files
• Trim audio from time points
• Auto-trim with duration

📁 **Document Tools:**
• Rename files
• Create archives (ZIP, RAR, 7Z) with optional password
• Extract archives
• Convert subtitle formats (SRT, VTT, ASS, SBV)
• Format JSON files
• Remove forward tags

🌟 **Bulk Mode:**
• Process multiple files automatically
• Bulk archive creation
• Bulk audio removal from videos
• Bulk conversion to MP3
• Bulk file renaming
• Bulk video format conversion
• Bulk video reordering
• Bulk video merging
• Bulk multiplexing (video+audio+subs)

⚙️ **Customization:**
• Set default thumbnail
• Custom captions with variables
• File prefix/suffix
• Quality settings (High/Medium/Low)
• Auto-delete processed files
• Screenshot count settings
• Default trim times

**How to use:**
1. Send any media file to the bot
2. Choose from the button menu
3. Follow the prompts
4. Receive processed file

**Note:** Free users have 25-minute cooldown between tasks and 500MB file limit.
Upgrade to premium for no limits! ⭐
"""
    await message.reply(help_text)

@Client.on_message(filters.command(['settings']) & filters.private)
async def settings_command(client: Client, message: Message):
    """Show settings menu"""
    from core.handlers import settings_handler
    from pyrogram.types import CallbackQuery
    
    # Create a mock callback query to reuse settings handler
    class MockCallback:
        def __init__(self, message):
            self.message = message
            self.from_user = message.from_user
            self.data = "settings"
            self.id = "mock_id"
    
    mock_query = MockCallback(message)
    await settings_handler(client, mock_query)

@Client.on_message(filters.command(['status']) & filters.private)
async def status_command(client: Client, message: Message):
    """Show bot status"""
    uptime = datetime.datetime.now() - client.uptime
    cpu_usage = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Get task manager status
    task_status = task_manager.status()
    
    # Get user info
    user_id = message.from_user.id
    is_premium = await db.is_premium(user_id)
    remaining_cooldown = await db.get_remaining_cooldown(user_id)
    
    status_text = f"""
🤖 **Bot Status** {'⭐' if is_premium else ''}

**System Info:**
• Uptime: {str(uptime).split('.')[0]}
• CPU Usage: {cpu_usage}%
• Memory: {memory.percent}% ({human_readable_size(memory.used)}/{human_readable_size(memory.total)})
• Disk: {disk.percent}% ({human_readable_size(disk.used)}/{human_readable_size(disk.total)})

**Task Manager:**
• Active Tasks: {task_status.get('running', 0)}
• Queued Tasks: {task_status.get('queued', 0)}
• Total Tasks: {task_status.get('total_tasks', 0)}

**Your Status:**
• Plan: {'Premium ⭐' if is_premium else 'Free'}
• Cooldown: {'None ⭐' if is_premium else f'{remaining_cooldown//60}m {remaining_cooldown%60}s remaining'}
• File Limit: {human_readable_size(4*1024*1024*1024) if is_premium else human_readable_size(500*1024*1024)}

**Bot Info:**
• Version: 2.0
• Developer: @YourUsername
• Support: @YourSupportGroup

**Quick Actions:**
/settings - Configure preferences
/tasks - View your tasks
/upgrade - Get premium
"""
    await message.reply(status_text)

@Client.on_message(filters.command(['tasks']) & filters.private)
async def task_status_command(client: Client, message: Message):
    """Show user's tasks"""
    try:
        user_id = message.from_user.id
        user_tasks = task_manager.get_user_tasks(user_id)
        
        if not user_tasks:
            await message.reply("📭 You have no active tasks!")
            return
        
        task_text = "📋 **Your Active Tasks:**\n\n"
        
        for i, task in enumerate(user_tasks[:10], 1):  # Show first 10 tasks
            task_text += f"{i}. **{task.task_type}**\n"
            task_text += f"   Status: {task.status}\n"
            task_text += f"   Progress: {task.progress:.1f}%\n"
            task_text += f"   Created: {task.created_at.strftime('%H:%M:%S')}\n"
            
            if task.started_at:
                task_text += f"   Started: {task.started_at.strftime('%H:%M:%S')}\n"
            
            task_text += "\n"
        
        if len(user_tasks) > 10:
            task_text += f"\n... and {len(user_tasks) - 10} more tasks"
        
        # Add cancel all button
        buttons = [
            [InlineKeyboardButton("❌ Cancel All Tasks", callback_data="cancel_all_tasks")]
        ]
        
        await message.reply(
            task_text,
            reply_markup=InlineKeyboardMarkup(buttons) if user_tasks else None
        )
        
    except Exception as e:
        await message.reply(f"❌ Failed to get tasks:\n\n{str(e)}")
        logging.error(f"Task status error: {e}")

@Client.on_message(filters.command(['upgrade']) & filters.private)
async def upgrade_command(client: Client, message: Message):
    """Show premium upgrade information"""
    upgrade_text = """
⭐ **Premium Upgrade**

**Free Plan Limitations:**
• 25-minute cooldown between tasks
• 500MB file size limit
• Standard processing priority

**Premium Benefits:**
• ✅ No cooldown between tasks
• ✅ 4GB file size limit
• ✅ Priority processing
• ✅ All features unlocked
• ✅ Dedicated support

**How to Upgrade:**
1. Contact @AdminUsername
2. Make payment
3. Get activated instantly

**Pricing:**
• 1 Month: $5
• 3 Months: $12
• 6 Months: $20
• 1 Year: $35

**Payment Methods:**
• Cryptocurrency (BTC, ETH, USDT)
• PayPal
• Credit/Debit Card

**Note:** Premium status is linked to your Telegram ID and is non-transferable.

Contact @AdminUsername to get started! ⭐
"""
    await message.reply(upgrade_text)

@Client.on_message(filters.command(['empty']) & filters.private)
async def empty_(client: Client, message: Message):
    """Empty command for testing"""
    logging.info(message.text)
    await message.reply("This is a test command!")

@Client.on_message(filters.command(['tstatus']) & filters.private)
async def task_status(client: Client, message: Message):
    """Show detailed task status (admin only)"""
    try:
        # Check if user is admin
        user_id = message.from_user.id
        from config import ADMINS
        if user_id not in ADMINS and user_id != OWNER_ID:
            await message.reply("❌ Admin only command!")
            return
        
        task_id = message.command[1] if len(message.command) > 1 else None
        t = task_manager.status(task_id)
        
        await message.reply(f'Task Status:\n\n```json\n{json.dumps(t, indent=2, default=str)}\n```')
    except Exception as e:
        await message.reply(f'Failed to get status\n\n{str(e)}')
        logging.info(e)
