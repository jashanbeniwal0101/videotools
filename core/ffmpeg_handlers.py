# core/ffmpeg_handlers.py
import asyncio
import os
import json
import random
import string
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import subprocess
import logging

from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

class FFmpegError(Exception):
    """Base exception for FFmpeg operations"""
    pass

class FFmpegCancelledError(FFmpegError):
    """Raised when operation is cancelled by user"""
    pass

class FFmpegHandler:
    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.temp_dir = "temp_ffmpeg"
        self._cancel_flag = False
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def cancel(self) -> None:
        self._cancel_flag = True
    
    async def _execute_ffmpeg(self, args: List[str], progress_callback=None) -> bool:
        """Execute ffmpeg command with progress tracking"""
        try:
            process = await asyncio.create_subprocess_exec(
                self.ffmpeg_path,
                *args,
                stderr=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE
            )
            
            while True:
                if self._cancel_flag:
                    process.terminate()
                    await process.wait()
                    raise FFmpegCancelledError()
                
                line = await process.stderr.readline()
                if not line:
                    break
                
                line = line.decode().strip()
                if progress_callback and ("frame=" in line or "time=" in line):
                    await progress_callback(line)
            
            await process.wait()
            return process.returncode == 0
            
        except Exception as e:
            logging.error(f"FFmpeg execution error: {e}")
            return False
    
    async def _send_progress_update(self, client: Client, message: Message,
                                  progress_text: str, msg_id: int,
                                  reply_markup=None):
        """Send progress update to user"""
        try:
            await client.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=progress_text,
                reply_markup=reply_markup
            )
        except:
            pass
    
    async def execute_with_updates(self, args: List[str], operation: str,
                                 client: Client, message: Message) -> bool:
        """Execute ffmpeg with progress updates"""
        cancel_btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_ffmpeg")]]
        )
        
        msg = await message.reply_text(
            f"⏳ Starting {operation}...",
            reply_markup=cancel_btn
        )
        
        last_update = 0
        async def progress_callback(line: str):
            nonlocal last_update
            now = time.time()
            if now - last_update < 2.0:  # Update every 2 seconds
                return
            last_update = now
            
            # Parse progress from ffmpeg output
            progress = 0
            if "time=" in line:
                try:
                    time_str = line.split("time=")[1].split()[0]
                    # Convert HH:MM:SS.ms to seconds
                    h, m, s = time_str.split(":")
                    s = s.split(".")[0]
                    total_seconds = int(h) * 3600 + int(m) * 60 + int(s)
                    
                    # Get duration from args or estimate
                    duration = 60  # Default estimate
                    for i, arg in enumerate(args):
                        if arg == "-t" and i + 1 < len(args):
                            try:
                                duration = float(args[i + 1])
                                break
                            except:
                                pass
                    
                    progress = min(99, int((total_seconds / duration) * 100)) if duration > 0 else 0
                except:
                    progress = 0
            
            await self._send_progress_update(
                client, message,
                f"⏳ {operation}\nProgress: {progress}%",
                msg.id,
                cancel_btn
            )
        
        try:
            success = await self._execute_ffmpeg(args, progress_callback)
            
            if success:
                await self._send_progress_update(
                    client, message,
                    f"✅ {operation} completed",
                    msg.id
                )
            else:
                await self._send_progress_update(
                    client, message,
                    f"❌ {operation} failed",
                    msg.id
                )
            
            return success
            
        except FFmpegCancelledError:
            await self._send_progress_update(
                client, message,
                "❌ Operation cancelled",
                msg.id
            )
            raise
            
        except Exception as e:
            await self._send_progress_update(
                client, message,
                f"⚠️ Error: {str(e)}",
                msg.id
            )
            raise
    
    async def trim(self, client: Client, message: Message,
                  input_path: str, output_path: str,
                  start: str, end: str) -> bool:
        """Trim video from start to end"""
        args = [
            "-y", "-ss", start, "-to", end,
            "-i", input_path, "-c", "copy", output_path
        ]
        return await self.execute_with_updates(args, "Video trim", client, message)
    
    async def merge(self, client: Client, message: Message,
                   inputs: List[str], output_path: str) -> bool:
        """Merge multiple videos"""
        # Create concat file
        list_file = self._get_temp_path(".txt")
        with open(list_file, "w") as f:
            for input_file in inputs:
                f.write(f"file '{os.path.abspath(input_file)}'\n")
        
        args = [
            "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_path
        ]
        
        try:
            success = await self.execute_with_updates(args, "Video merge", client, message)
            return success
        finally:
            if os.path.exists(list_file):
                os.remove(list_file)
    
    async def extract_thumbnail(self, client: Client, message: Message,
                               input_path: str, timestamp: str = None) -> Optional[str]:
        """Extract thumbnail from video"""
        if timestamp is None:
            # Get video duration and extract from middle
            duration = await self.get_duration(input_path)
            if duration:
                middle = duration / 2
                hours = int(middle // 3600)
                minutes = int((middle % 3600) // 60)
                seconds = int(middle % 60)
                timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                timestamp = "00:00:01"
        
        output_path = self._get_temp_path(".jpg")
        args = [
            "-y", "-ss", timestamp, "-i", input_path,
            "-vframes", "1", "-q:v", "2",
            output_path
        ]
        
        success = await self.execute_with_updates(args, "Thumbnail extraction", client, message)
        return output_path if success and os.path.exists(output_path) else None
    
    async def generate_screenshots(self, client: Client, message: Message,
                                 input_path: str, count: int = 5) -> List[str]:
        """Generate screenshots from video"""
        duration = await self.get_duration(input_path)
        if not duration:
            return []
        
        screenshots = []
        for i in range(count):
            timestamp = duration * (i + 1) / (count + 1)
            hours = int(timestamp // 3600)
            minutes = int((timestamp % 3600) // 60)
            seconds = int(timestamp % 60)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            output_path = self._get_temp_path(f"_{i+1}.jpg")
            args = [
                "-y", "-ss", time_str, "-i", input_path,
                "-vframes", "1", "-q:v", "2",
                output_path
            ]
            
            # Execute without progress updates for each screenshot
            process = await asyncio.create_subprocess_exec(
                self.ffmpeg_path, *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.wait()
            
            if os.path.exists(output_path):
                screenshots.append(output_path)
        
        return screenshots
    
    async def get_duration(self, input_path: str) -> Optional[float]:
        """Get video duration in seconds"""
        try:
            args = [
                self.ffprobe_path, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", input_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                data = json.loads(stdout.decode())
                return float(data['format']['duration'])
            
        except Exception as e:
            logging.error(f"Duration error: {e}")
        
        return None
    
    async def mediainfo(self, input_path: str) -> str:
        """Generate media information"""
        try:
            args = [
                self.ffprobe_path, "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                input_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                data = json.loads(stdout.decode())
                
                info = "📊 **Media Information**\n\n"
                
                # Format info
                if 'format' in data:
                    format_info = data['format']
                    info += f"**Format:** {format_info.get('format_name', 'N/A')}\n"
                    info += f"**Duration:** {float(format_info.get('duration', 0)):.2f}s\n"
                    info += f"**Size:** {int(format_info.get('size', 0)) / (1024*1024):.2f} MB\n"
                    info += f"**Bitrate:** {int(format_info.get('bit_rate', 0)) / 1000:.2f} kbps\n"
                
                # Streams info
                if 'streams' in data:
                    info += "\n**Streams:**\n"
                    for i, stream in enumerate(data['streams']):
                        codec_type = stream.get('codec_type', 'unknown')
                        codec_name = stream.get('codec_name', 'N/A')
                        info += f"{i+1}. {codec_type.upper()}: {codec_name}"
                        
                        if codec_type == 'video':
                            width = stream.get('width', 0)
                            height = stream.get('height', 0)
                            fps = stream.get('avg_frame_rate', '0')
                            info += f" ({width}x{height}, {fps} fps)"
                        elif codec_type == 'audio':
                            channels = stream.get('channels', 0)
                            sample_rate = stream.get('sample_rate', 0)
                            info += f" ({channels} ch, {int(sample_rate)/1000:.1f} kHz)"
                        
                        # Language
                        if 'tags' in stream and 'language' in stream['tags']:
                            info += f" [{stream['tags']['language']}]"
                        
                        info += "\n"
                
                return info
            
        except Exception as e:
            logging.error(f"Mediainfo error: {e}")
        
        return "❌ Could not generate media information"
    
    async def view_streams(self, input_path: str) -> List[Dict]:
        """Get list of streams in media file"""
        try:
            args = [
                self.ffprobe_path, "-v", "quiet",
                "-print_format", "json",
                "-show_streams", input_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                data = json.loads(stdout.decode())
                streams = []
                
                for stream in data.get('streams', []):
                    stream_info = {
                        'index': stream.get('index'),
                        'type': stream.get('codec_type', 'unknown'),
                        'codec': stream.get('codec_name', 'unknown'),
                        'language': stream.get('tags', {}).get('language', 'und')
                    }
                    
                    if stream_info['type'] == 'video':
                        stream_info.update({
                            'width': stream.get('width'),
                            'height': stream.get('height'),
                            'fps': stream.get('avg_frame_rate', '0/1')
                        })
                    elif stream_info['type'] == 'audio':
                        stream_info.update({
                            'channels': stream.get('channels'),
                            'sample_rate': stream.get('sample_rate')
                        })
                    elif stream_info['type'] == 'subtitle':
                        stream_info['language'] = stream.get('tags', {}).get('language', 'und')
                    
                    streams.append(stream_info)
                
                return streams
            
        except Exception as e:
            logging.error(f"View streams error: {e}")
        
        return []
    
    async def extract_stream(self, client: Client, message: Message,
                           input_path: str, output_path: str,
                           stream_type: str, index: int = 0) -> bool:
        """Extract specific stream from media"""
        if stream_type == "audio":
            args = [
                "-y", "-i", input_path,
                "-map", f"0:a:{index}", "-c", "copy",
                output_path
            ]
        elif stream_type == "video":
            args = [
                "-y", "-i", input_path,
                "-map", f"0:v:{index}", "-c", "copy",
                output_path
            ]
        elif stream_type == "subtitle":
            args = [
                "-y", "-i", input_path,
                "-map", f"0:s:{index}",
                output_path
            ]
        else:
            return False
        
        return await self.execute_with_updates(args, f"Extract {stream_type}", client, message)
    
    async def remove_stream(self, client: Client, message: Message,
                          input_path: str, output_path: str,
                          stream_type: str, index: int = 0) -> bool:
        """Remove specific stream from media"""
        args = ["-y", "-i", input_path]
        
        # Map all streams except the one to remove
        if stream_type == "audio":
            args.extend(["-map", "0", f"-map", "-0:a:{index}"])
        elif stream_type == "video":
            args.extend(["-map", "0", f"-map", "-0:v:{index}"])
        elif stream_type == "subtitle":
            args.extend(["-map", "0", f"-map", "-0:s:{index}"])
        else:
            return False
        
        args.extend(["-c", "copy", output_path])
        return await self.execute_with_updates(args, f"Remove {stream_type}", client, message)
    
    async def compress_audio(self, client: Client, message: Message,
                           input_path: str, quality: int = 80) -> Optional[str]:
        """Compress audio file"""
        output_path = self._get_temp_path(".mp3")
        
        # Calculate bitrate based on quality (32k to 320k)
        bitrate = int(32 + (320 - 32) * (quality / 100))
        
        args = [
            "-y", "-i", input_path,
            "-b:a", f"{bitrate}k",
            "-ar", "44100", "-ac", "2",
            output_path
        ]
        
        success = await self.execute_with_updates(args, "Audio compression", client, message)
        return output_path if success else None
    
    async def convert_audio(self, client: Client, message: Message,
                          input_path: str, output_format: str) -> Optional[str]:
        """Convert audio to different format"""
        output_path = self._get_temp_path(f".{output_format}")
        
        args = ["-y", "-i", input_path]
        
        if output_format == "mp3":
            args.extend(["-codec:a", "libmp3lame", "-qscale:a", "2"])
        elif output_format == "flac":
            args.extend(["-codec:a", "flac", "-compression_level", "8"])
        elif output_format == "wav":
            args.extend(["-codec:a", "pcm_s16le"])
        elif output_format == "aac":
            args.extend(["-codec:a", "aac", "-b:a", "256k"])
        elif output_format == "ogg":
            args.extend(["-codec:a", "libvorbis", "-qscale:a", "5"])
        elif output_format == "opus":
            args.extend(["-codec:a", "libopus", "-b:a", "128k"])
        
        args.append(output_path)
        success = await self.execute_with_updates(args, f"Convert to {output_format}", client, message)
        return output_path if success else None
    
    def _get_temp_path(self, ext: str) -> str:
        """Generate temporary file path"""
        rand = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        return os.path.join(self.temp_dir, f"temp_{rand}{ext}")
