# core/wmanager.py
import asyncio
import uuid
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

@dataclass
class Task:
    id: str
    user_id: int
    task_type: str
    func: Callable
    args: tuple
    kwargs: dict
    status: str = "pending"  # pending, running, completed, failed, cancelled
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    result: Optional[Any] = None
    error: Optional[str] = None

class TaskManager:
    def __init__(self, max_concurrent_tasks: int = 3):
        self.tasks: Dict[str, Task] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.max_concurrent_tasks = max_concurrent_tasks
        self.current_running = 0
        self.task_queue = asyncio.Queue()
        self._worker_task = None
        
    async def start(self):
        """Start task manager worker"""
        self._worker_task = asyncio.create_task(self._worker())
        
    async def stop(self):
        """Stop task manager"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
                
    async def _worker(self):
        """Worker to process tasks from queue"""
        while True:
            try:
                task_id = await self.task_queue.get()
                
                # Check if we can run more tasks
                while self.current_running >= self.max_concurrent_tasks:
                    await asyncio.sleep(1)
                
                task = self.tasks.get(task_id)
                if task and task.status == "pending":
                    await self._execute_task(task)
                    
                self.task_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Task worker error: {e}")
                await asyncio.sleep(1)
    
    async def _execute_task(self, task: Task):
        """Execute a single task"""
        task.status = "running"
        task.started_at = datetime.now()
        self.current_running += 1
        
        try:
            # Execute the task function
            result = await task.func(*task.args, **task.kwargs)
            task.result = result
            task.status = "completed"
            task.progress = 100.0
            
        except asyncio.CancelledError:
            task.status = "cancelled"
            task.error = "Task was cancelled"
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            logging.error(f"Task {task.id} failed: {e}")
            
        finally:
            task.completed_at = datetime.now()
            self.current_running -= 1
            
            # Clean up completed tasks after some time
            if task.status in ["completed", "failed", "cancelled"]:
                asyncio.create_task(self._cleanup_task(task.id))
    
    async def _cleanup_task(self, task_id: str, delay: int = 300):
        """Clean up task after delay"""
        await asyncio.sleep(delay)
        if task_id in self.tasks:
            del self.tasks[task_id]
    
    async def enqueue(self, func: Callable, *args, user_id: int = None, **kwargs) -> str:
        """Enqueue a new task"""
        task_id = str(uuid.uuid4())[:8]
        
        task = Task(
            id=task_id,
            user_id=user_id,
            task_type=func.__name__,
            func=func,
            args=args,
            kwargs=kwargs
        )
        
        self.tasks[task_id] = task
        await self.task_queue.put(task_id)
        
        return task_id
    
    async def cancel(self, task_id: str) -> bool:
        """Cancel a running task"""
        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            try:
                await self.running_tasks[task_id]
            except asyncio.CancelledError:
                pass
            
            if task_id in self.tasks:
                self.tasks[task_id].status = "cancelled"
                self.tasks[task_id].completed_at = datetime.now()
            
            return True
        return False
    
    async def cancel_user_tasks(self, user_id: int) -> List[str]:
        """Cancel all tasks for a user"""
        cancelled = []
        for task_id, task in self.tasks.items():
            if task.user_id == user_id and task.status in ["pending", "running"]:
                if await self.cancel(task_id):
                    cancelled.append(task_id)
        return cancelled
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return self.tasks.get(task_id)
    
    def get_user_tasks(self, user_id: int) -> List[Task]:
        """Get all tasks for a user"""
        return [task for task in self.tasks.values() if task.user_id == user_id]
    
    def status(self, task_id: str = None) -> Dict:
        """Get task manager status or specific task status"""
        if task_id:
            task = self.get_task(task_id)
            if task:
                return {
                    "id": task.id,
                    "type": task.task_type,
                    "status": task.status,
                    "progress": task.progress,
                    "created": task.created_at.isoformat(),
                    "started": task.started_at.isoformat() if task.started_at else None,
                    "completed": task.completed_at.isoformat() if task.completed_at else None,
                    "error": task.error
                }
            return {"error": "Task not found"}
        
        # Overall status
        status_counts = {}
        for task in self.tasks.values():
            status_counts[task.status] = status_counts.get(task.status, 0) + 1
        
        return {
            "total_tasks": len(self.tasks),
            "running": self.current_running,
            "queued": self.task_queue.qsize(),
            "status_counts": status_counts,
            "max_concurrent": self.max_concurrent_tasks
        }
    
    async def wait_for_completion(self, task_id: str, timeout: int = None) -> bool:
        """Wait for task completion"""
        start_time = datetime.now()
        
        while True:
            task = self.get_task(task_id)
            if not task:
                return False
                
            if task.status in ["completed", "failed", "cancelled"]:
                return task.status == "completed"
            
            if timeout and (datetime.now() - start_time).seconds > timeout:
                return False
            
            await asyncio.sleep(1)
    
    def update_progress(self, task_id: str, progress: float):
        """Update task progress"""
        if task_id in self.tasks:
            self.tasks[task_id].progress = max(0.0, min(100.0, progress))

# Global task manager instance
task_manager = TaskManager()
