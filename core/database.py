# core/database.py
from typing import Optional, Any, Dict, List, Union
import motor.motor_asyncio
from datetime import datetime, timedelta
from config import PREMIUM_COOLDOWN, PREMIUM_USERS

class Database:
    def __init__(self, uri: str, database_name: str):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.tasks = self.db.tasks
        self.premium = self.db.premium

    @staticmethod
    def new_user(id: int) -> Dict[str, Any]:
        return dict(
            _id=int(id),
            thumb=None,
            caption=None,
            prefix=None,
            suffix=None,
            metadata=False,
            premium=False,
            last_task_time=None,
            total_tasks=0,
            settings=dict(
                auto_delete=True,
                default_quality="high",
                compress_quality=80,
                audio_quality=320,
                screenshot_count=5,
                trim_default_start="00:00:00",
                trim_default_duration="00:01:00"
            )
        )

    async def add_user(self, b, m):
        """Add user if not exists."""
        u = m.from_user
        user_data = await self.col.find_one({'_id': int(u.id)})
        if not user_data:
            await self.col.insert_one(self.new_user(u.id))
            # Check if user is in premium list
            if u.id in PREMIUM_USERS:
                await self.col.update_one(
                    {'_id': int(u.id)},
                    {'$set': {'premium': True}}
                )
            # Send log if function exists
            if 'send_log' in globals():
                await send_log(b, u)

    async def is_user_exist(self, id: int) -> bool:
        return await self.col.count_documents({'_id': int(id)}, limit=1) > 0

    async def total_users_count(self) -> int:
        return await self.col.count_documents({})

    async def get_all_users(self) -> List[Dict[str, Any]]:
        return await self.col.find({}).to_list(length=None)

    async def delete_user(self, user_id: int) -> None:
        await self.col.delete_one({'_id': int(user_id)})

    async def set_thumbnail(self, id: int, file_id: Any) -> None:
        await self.col.update_one({'_id': int(id)}, {'$set': {'thumb': file_id}})

    async def get_thumbnail(self, id: int) -> Optional[Any]:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('thumb') if user else None

    async def set_caption(self, id: int, caption: str) -> None:
        await self.col.update_one({'_id': int(id)}, {'$set': {'caption': caption}})

    async def get_caption(self, id: int) -> Optional[str]:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('caption') if user else None

    async def set_prefix(self, id: int, prefix: str) -> None:
        await self.col.update_one({'_id': int(id)}, {'$set': {'prefix': prefix}})

    async def get_prefix(self, id: int) -> Optional[str]:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('prefix') if user else None

    async def set_suffix(self, id: int, suffix: str) -> None:
        await self.col.update_one({'_id': int(id)}, {'$set': {'suffix': suffix}})

    async def get_suffix(self, id: int) -> Optional[str]:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('suffix') if user else None

    async def set_metadata(self, id: int, bool_meta: bool) -> None:
        await self.col.update_one({'_id': int(id)}, {'$set': {'metadata': bool_meta}})

    async def get_metadata(self, id: int) -> Optional[bool]:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('metadata') if user else False

    async def set_metadata_code(self, id: int, metadata_code: Any) -> None:
        await self.col.update_one({'_id': int(id)}, {'$set': {'metadata_code': metadata_code}})

    async def get_metadata_code(self, id: int) -> Optional[Any]:
        user = await self.col.find_one({'_id': int(id)})
        return user.get('metadata_code') if user else None

    async def is_premium(self, user_id: int) -> bool:
        user = await self.col.find_one({'_id': user_id})
        if user and user.get('premium'):
            return True
        return user_id in PREMIUM_USERS

    async def set_premium(self, user_id: int, premium: bool) -> None:
        await self.col.update_one(
            {'_id': user_id},
            {'$set': {'premium': premium}}
        )

    async def update_last_task_time(self, user_id: int) -> None:
        await self.col.update_one(
            {'_id': user_id},
            {'$set': {'last_task_time': datetime.now()}}
        )

    async def can_start_task(self, user_id: int) -> bool:
        """Check if user can start a new task (cooldown for non-premium)"""
        if await self.is_premium(user_id):
            return True
        
        user = await self.col.find_one({'_id': user_id})
        if not user or not user.get('last_task_time'):
            return True
        
        last_time = user['last_task_time']
        if isinstance(last_time, str):
            from datetime import datetime
            last_time = datetime.fromisoformat(last_time)
        
        time_diff = (datetime.now() - last_time).total_seconds()
        return time_diff >= PREMIUM_COOLDOWN

    async def get_remaining_cooldown(self, user_id: int) -> int:
        """Get remaining cooldown time in seconds"""
        if await self.is_premium(user_id):
            return 0
        
        user = await self.col.find_one({'_id': user_id})
        if not user or not user.get('last_task_time'):
            return 0
        
        last_time = user['last_task_time']
        if isinstance(last_time, str):
            from datetime import datetime
            last_time = datetime.fromisoformat(last_time)
        
        time_diff = (datetime.now() - last_time).total_seconds()
        remaining = PREMIUM_COOLDOWN - time_diff
        return max(0, int(remaining))

    async def increment_task_count(self, user_id: int) -> None:
        await self.col.update_one(
            {'_id': user_id},
            {'$inc': {'total_tasks': 1}}
        )

    async def update_setting(self, user_id: int, setting: str, value: Any) -> None:
        await self.col.update_one(
            {'_id': user_id},
            {'$set': {f'settings.{setting}': value}}
        )

    async def get_setting(self, user_id: int, setting: str) -> Any:
        user = await self.col.find_one({'_id': user_id})
        if user and 'settings' in user:
            return user['settings'].get(setting)
        return None

    async def add_task_log(self, task_id: str, user_id: int, task_type: str, 
                          status: str = "pending", details: Dict = None) -> None:
        await self.tasks.insert_one({
            'task_id': task_id,
            'user_id': user_id,
            'task_type': task_type,
            'status': status,
            'details': details or {},
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        })

    async def update_task_status(self, task_id: str, status: str, 
                               result: Dict = None) -> None:
        await self.tasks.update_one(
            {'task_id': task_id},
            {'$set': {
                'status': status,
                'result': result,
                'updated_at': datetime.now()
            }}
        )

    async def get_user_tasks(self, user_id: int, limit: int = 10) -> List[Dict]:
        return await self.tasks.find(
            {'user_id': user_id}
        ).sort('created_at', -1).limit(limit).to_list(length=limit)
