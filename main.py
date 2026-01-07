# main.py
import asyncio
import sys
from aiohttp import web
from datetime import datetime
from plugins.web_routes import web_server
from pyrogram import Client, utils 
from config import (
    ADMINS, 
    API_HASH, 
    APP_ID, 
    LOGGER, 
    BOT_TOKEN, 
    BOT_WORKERS, 
    FORCE_SUB_CHANNEL,
    DUMP_ID, 
    PORT, 
    OWNER_ID,
    MONGO_URI,
    DATABASE_NAME
)

from core.database import Database
from core.wmanager import task_manager

# Patch utils for large chat IDs
utils.MIN_CHAT_ID = -999999999999
utils.MIN_CHANNEL_ID = -100999999999999

def get_peer_type_new(peer_id: int) -> str:
    peer_id_str = str(peer_id)
    if not peer_id_str.startswith("-"):
        return "user"
    elif peer_id_str.startswith("-100"):
        return "channel"
    else:
        return "chat"

utils.get_peer_type = get_peer_type_new

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="MediaBot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={
                "root": "plugins"
            },
            workers=BOT_WORKERS,
            bot_token=BOT_TOKEN,
            sleep_threshold=10,
            max_concurrent_transmissions=5
        )
        self.LOGGER = LOGGER
        self.db = None
        self.task_manager = task_manager

    async def start(self, *args, **kwargs):
        await super().start()
        
        # Initialize database
        self.db = Database(MONGO_URI, DATABASE_NAME)
        
        # Start task manager
        await self.task_manager.start()
        
        usr_bot_me = await self.get_me()
        self.uptime = datetime.now()
        self.username = usr_bot_me.username

        # Force subscribe channel setup
        if FORCE_SUB_CHANNEL:
            try:
                link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                if not link:
                    await self.export_chat_invite_link(FORCE_SUB_CHANNEL)
                    link = (await self.get_chat(FORCE_SUB_CHANNEL)).invite_link
                self.invitelink = link
            except Exception as a:
                self.LOGGER(__name__).warning(a)
                self.LOGGER(__name__).warning("Bot can't Export Invite link from Force Sub Channel!")
                self.LOGGER(__name__).warning(f"Please Double check the FORCE_SUB_CHANNEL value and Make sure Bot is Admin in channel with Invite Users via Link Permission, Current Force Sub Channel Value: {FORCE_SUB_CHANNEL}")
                sys.exit()
        
        # Dump channel setup
        if DUMP_ID:
            try:
                db_channel = await self.get_chat(DUMP_ID)
                self.db_channel = db_channel
                test = await self.send_message(chat_id = db_channel.id, text = "Test Message")
                await test.delete()
            except Exception as e:
                self.LOGGER(__name__).warning(e)
                self.LOGGER(__name__).warning(f"Make Sure bot is Admin in DB Channel, and Double check the CHANNEL_ID Value, Current Value {DUMP_ID}")
                sys.exit()
        
        # Notify owner
        await self.send_message(
            chat_id=OWNER_ID,
            text="✅ Bot has started successfully!\n\n"
                 f"Username: @{self.username}\n"
                 f"Users: {await self.db.total_users_count()}\n"
                 f"Uptime: {self.uptime.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        self.LOGGER(__name__).info(f"✅ Bot Running as @{self.username}!")
        
        # Start web server
        app = web.AppRunner(await web_server())
        await app.setup()
        bind_address = "0.0.0.0"
        await web.TCPSite(app, bind_address, PORT).start()
        
        self.LOGGER(__name__).info(f"🌐 Web server started on port {PORT}")

    async def stop(self, *args):
        # Stop task manager
        await self.task_manager.stop()
        
        # Notify owner
        await self.send_message(
            chat_id=OWNER_ID,
            text="🛑 Bot is stopping..."
        )
        
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")

if __name__ == "__main__":
    # Create bot instance
    bot = Bot()
    
    # Run the bot
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        LOGGER("main").error(f"Bot crashed: {e}")
        sys.exit(1)
