import discord
from discord import FFmpegPCMAudio, app_commands
from discord.ext import commands
from youtubesearchpython import VideosSearch
from yt_dlp import YoutubeDL
import asyncio
import aiosqlite
import os
import hashlib
from pathlib import Path
import json
import time

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Status tracking (keep minimal state in memory)
        self.is_playing = {}
        self.is_paused = {}
        self.current_song = {}  # Track currently playing song per guild
        self.check_vc_members_task = {}
        
        # Database and download paths
        self.db_path = "music_bot.db"
        self.download_dir = Path("downloads")
        self.download_dir.mkdir(exist_ok=True)
        
        # Configure yt-dlp for downloading
        self.YDL_DOWNLOAD_OPTIONS = {
            'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio',
            'outtmpl': str(self.download_dir / '%(id)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
                'preferredquality': '128',
            }],
            'noplaylist': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                }
            },
            'quiet': True,
            'no_warnings': True
        }
        
        # Configure yt-dlp for streaming (fallback)
        self.YDL_STREAM_OPTIONS = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                }
            },
            'quiet': True,
            'no_warnings': True
        }
        
        # FFmpeg options for streaming
        self.FFMPEG_STREAM_OPTIONS = {
            'options': '-vn -bufsize 2M', 
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        }
        
        # FFmpeg options for local files (no reconnect options needed)
        self.FFMPEG_FILE_OPTIONS = {
            'options': '-vn'
        }

        self.ytdl_download = YoutubeDL(self.YDL_DOWNLOAD_OPTIONS)
        self.ytdl_stream = YoutubeDL(self.YDL_STREAM_OPTIONS)
        
        # Database will be initialized in cog_load

    async def init_db(self):
        """Initialize the SQLite database"""
        async with aiosqlite.connect(self.db_path) as db:
            # Songs table - stores metadata about downloaded songs
            await db.execute('''
                CREATE TABLE IF NOT EXISTS songs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    file_path TEXT,
                    file_size INTEGER DEFAULT 0,
                    download_date INTEGER,
                    play_count INTEGER DEFAULT 0,
                    last_played INTEGER DEFAULT 0
                )
            ''')
            
            # Queue table - stores current queues for each guild
            await db.execute('''
                CREATE TABLE IF NOT EXISTS queues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    song_id INTEGER NOT NULL,
                    voice_channel_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    added_date INTEGER DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (song_id) REFERENCES songs (id)
                )
            ''')
            
            # Index for better performance
            await db.execute('CREATE INDEX IF NOT EXISTS idx_guild_position ON queues (guild_id, position)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_video_id ON songs (video_id)')
            
            await db.commit()

    async def cog_load(self):
        """Called when the cog is loaded - perfect place for async initialization"""
        await self.init_db()
        print("Music cog database initialized successfully!")

    def get_video_id(self, url):
        """Extract video ID from YouTube URL"""
        if 'youtube.com/watch?v=' in url:
            return url.split('v=')[1].split('&')[0]
        elif 'youtu.be/' in url:
            return url.split('youtu.be/')[1].split('?')[0]
        return hashlib.md5(url.encode()).hexdigest()[:11]

    async def search_yt(self, item):
        """Search YouTube and return song info"""
        try:
            if item.startswith("https://"):
                # Extract info from URL
                info = await asyncio.to_thread(self.ytdl_stream.extract_info, item, download=False)
                return {
                    'source': item,
                    'title': info.get("title", "Unknown"),
                    'video_id': self.get_video_id(item)
                }
            else:
                # Search for the song
                search = VideosSearch(item, limit=1)
                result = search.result()["result"][0]
                return {
                    'source': result["link"],
                    'title': result["title"],
                    'video_id': self.get_video_id(result["link"])
                }
        except Exception as e:
            print(f"Error searching YouTube: {e}")
            return None

    async def get_or_create_song(self, song_info):
        """Get song from database or create new entry"""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if song exists
            cursor = await db.execute(
                'SELECT * FROM songs WHERE video_id = ?',
                (song_info['video_id'],)
            )
            song = await cursor.fetchone()
            
            if song:
                # Update play count and last played
                await db.execute(
                    'UPDATE songs SET play_count = play_count + 1, last_played = ? WHERE video_id = ?',
                    (int(time.time()), song_info['video_id'])
                )
                await db.commit()
                return dict(zip([col[0] for col in cursor.description], song))
            else:
                # Create new song entry
                await db.execute(
                    'INSERT INTO songs (video_id, title, url, play_count, last_played) VALUES (?, ?, ?, 1, ?)',
                    (song_info['video_id'], song_info['title'], song_info['source'], int(time.time()))
                )
                await db.commit()
                
                # Return the newly created song
                cursor = await db.execute(
                    'SELECT * FROM songs WHERE video_id = ?',
                    (song_info['video_id'],)
                )
                song = await cursor.fetchone()
                return dict(zip([col[0] for col in cursor.description], song))

    async def download_song(self, song_data):
        """Download song if not already downloaded"""
        try:
            video_id = song_data['video_id']
            
            # Check if already downloaded and file exists
            if song_data.get('file_path') and os.path.exists(song_data['file_path']):
                print(f"Using existing download: {song_data['title']}")
                return song_data['file_path']
            
            # Download the song
            print(f"Downloading: {song_data['title']}")
            
            # Create a custom filename template
            filename_template = str(self.download_dir / f"{video_id}.%(ext)s")
            
            # Update options with the specific filename
            download_options = self.YDL_DOWNLOAD_OPTIONS.copy()
            download_options['outtmpl'] = filename_template
            
            with YoutubeDL(download_options) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, song_data['url'], download=True)
            
            # Find the downloaded file
            possible_extensions = ['.opus', '.m4a', '.webm', '.mp3', '.ogg']
            file_path = None
            
            for ext in possible_extensions:
                potential_path = self.download_dir / f"{video_id}{ext}"
                if potential_path.exists():
                    file_path = str(potential_path)
                    break
            
            if not file_path:
                # Fallback: look for any file with the video ID
                for file in self.download_dir.glob(f"{video_id}.*"):
                    if file.suffix in ['.opus', '.m4a', '.webm', '.mp3', '.ogg']:
                        file_path = str(file)
                        break
            
            if file_path and os.path.exists(file_path):
                # Update database with file info
                file_size = os.path.getsize(file_path)
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        'UPDATE songs SET file_path = ?, file_size = ?, download_date = ? WHERE video_id = ?',
                        (file_path, file_size, int(time.time()), video_id)
                    )
                    await db.commit()
                
                print(f"Downloaded: {song_data['title']} -> {file_path}")
                return file_path
            else:
                print(f"Download completed but file not found: {song_data['title']}")
                return None
                
        except Exception as e:
            print(f"Error downloading {song_data['title']}: {e}")
            return None

    async def get_audio_source(self, song_data):
        """Get audio source (downloaded file or stream URL)"""
        # Try to use downloaded file first
        file_path = await self.download_song(song_data)
        if file_path and os.path.exists(file_path):
            return file_path
        
        # Fallback to streaming
        try:
            info = await asyncio.to_thread(
                self.ytdl_stream.extract_info,
                song_data['url'],
                download=False
            )
            return info['url']
        except Exception as e:
            print(f"Error getting stream URL: {e}")
            return None

    async def add_to_queue(self, guild_id, song_data, voice_channel_id):
        """Add song to queue in database"""
        async with aiosqlite.connect(self.db_path) as db:
            # Get current max position
            cursor = await db.execute(
                'SELECT MAX(position) FROM queues WHERE guild_id = ?',
                (guild_id,)
            )
            max_pos = await cursor.fetchone()
            next_position = (max_pos[0] or -1) + 1
            
            # Add to queue
            await db.execute(
                'INSERT INTO queues (guild_id, song_id, voice_channel_id, position) VALUES (?, ?, ?, ?)',
                (guild_id, song_data['id'], voice_channel_id, next_position)
            )
            await db.commit()
            return next_position

    async def get_queue(self, guild_id):
        """Get current queue for guild"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT q.id as queue_id, q.voice_channel_id, q.position, s.*
                FROM queues q
                JOIN songs s ON q.song_id = s.id
                WHERE q.guild_id = ?
                ORDER BY q.position
            ''', (guild_id,))
            return await cursor.fetchall()

    async def remove_from_queue(self, guild_id, position=0):
        """Remove song from queue (default: first song)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM queues WHERE guild_id = ? AND position = (SELECT MIN(position) FROM queues WHERE guild_id = ?)',
                (guild_id, guild_id)
            ) if position == 0 else await db.execute(
                'DELETE FROM queues WHERE guild_id = ? AND position = ?',
                (guild_id, position)
            )
            
            # Reorder remaining positions
            await db.execute('''
                UPDATE queues 
                SET position = position - 1 
                WHERE guild_id = ? AND position > ?
            ''', (guild_id, position))
            
            await db.commit()

    async def clear_queue(self, guild_id):
        """Clear all songs from guild queue"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM queues WHERE guild_id = ?', (guild_id,))
            await db.commit()

    async def check_vc_members(self, guild_id):
        """Monitor voice channel and disconnect if empty"""
        guild = self.bot.get_guild(guild_id)
        if guild:
            voice_client = guild.voice_client
            if voice_client:
                while voice_client.is_connected():
                    await asyncio.sleep(30)  # Check every 30 seconds
                    if len(voice_client.channel.members) <= 1:  # Only bot left
                        await asyncio.sleep(60)  # Wait 1 minute before disconnecting
                        if len(voice_client.channel.members) <= 1:
                            await voice_client.disconnect()
                            break

    async def play_music(self, interaction):
        """Play the next song in queue"""
        try:
            guild_id = interaction.guild.id
            queue = await self.get_queue(guild_id)
            
            if not queue:
                self.is_playing[guild_id] = False
                await self.disconnect_if_idle(interaction)
                return

            self.is_playing[guild_id] = True
            
            # Convert tuple to dictionary with proper column mapping
            queue_row = queue[0]
            song_data = {
                'queue_id': queue_row[0],
                'voice_channel_id': queue_row[1], 
                'position': queue_row[2],
                'id': queue_row[3],
                'video_id': queue_row[4],
                'title': queue_row[5],
                'url': queue_row[6],
                'file_path': queue_row[7],
                'file_size': queue_row[8],
                'download_date': queue_row[9],
                'play_count': queue_row[10],
                'last_played': queue_row[11]
            }
            
            self.current_song[guild_id] = song_data
            
            voice_channel = self.bot.get_channel(song_data['voice_channel_id'])
            voice_client = interaction.guild.voice_client

            if not voice_client or not voice_client.is_connected():
                voice_client = await voice_channel.connect()
                self.check_vc_members_task[guild_id] = asyncio.create_task(
                    self.check_vc_members(guild_id)
                )

            # Get audio source (file or stream)
            audio_source = await self.get_audio_source(song_data)
            if not audio_source:
                await interaction.followup.send(f"```Error: Could not get audio for {song_data['title']}```")
                await self.remove_from_queue(guild_id, 0)
                await self.play_next(interaction)
                return

            # Remove from queue and play
            await self.remove_from_queue(guild_id, 0)
            
            # Choose appropriate FFmpeg options based on source type
            is_local_file = os.path.exists(audio_source) if isinstance(audio_source, str) else False
            ffmpeg_options = self.FFMPEG_FILE_OPTIONS if is_local_file else self.FFMPEG_STREAM_OPTIONS
            
            def after_playing(error):
                if error:
                    print(f'Player error: {error}')
                self.bot.loop.create_task(self.play_next(interaction))

            voice_client.play(FFmpegPCMAudio(audio_source, **ffmpeg_options), after=after_playing)
            print(f"Playing: {song_data['title']} from {'local file' if is_local_file else 'stream'}")
            
        except Exception as e:
            print(f"Error in play_music: {e}")
            self.is_playing[guild_id] = False

    async def play_next(self, interaction):
        """Play next song in queue"""
        try:
            guild_id = interaction.guild.id
            queue = await self.get_queue(guild_id)
            
            if queue:
                # Convert tuple to dictionary with proper column mapping
                queue_row = queue[0]
                song_data = {
                    'queue_id': queue_row[0],
                    'voice_channel_id': queue_row[1], 
                    'position': queue_row[2],
                    'id': queue_row[3],
                    'video_id': queue_row[4],
                    'title': queue_row[5],
                    'url': queue_row[6],
                    'file_path': queue_row[7],
                    'file_size': queue_row[8],
                    'download_date': queue_row[9],
                    'play_count': queue_row[10],
                    'last_played': queue_row[11]
                }
                
                await interaction.followup.send(f"Now playing: **{song_data['title']}**")
                await self.play_music(interaction)
            else:
                self.is_playing[guild_id] = False
                self.current_song.pop(guild_id, None)
                await self.disconnect_if_idle(interaction)
                
        except Exception as e:
            print(f"Error in play_next: {e}")

    async def disconnect_if_idle(self, interaction):
        """Disconnect after idle period"""
        await asyncio.sleep(300)  # Wait 5 minutes
        guild_id = interaction.guild.id
        queue = await self.get_queue(guild_id)
        
        if not self.is_playing.get(guild_id, False) and not queue:
            voice_client = interaction.guild.voice_client
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
                if self.check_vc_members_task.get(guild_id):
                    self.check_vc_members_task[guild_id].cancel()

    @app_commands.command(name="play", description="Plays a song based on the inserted URL or name of the song.")
    async def play(self, interaction: discord.Interaction, song: str):
        try:
            voice_channel = interaction.user.voice.channel
        except AttributeError:
            await interaction.response.send_message("```You need to connect to a voice channel first!```")
            return

        await interaction.response.defer()

        try:
            guild_id = interaction.guild.id
            
            # Handle resume if paused
            if self.is_paused.get(guild_id, False):
                voice_client = interaction.guild.voice_client
                if voice_client and voice_client.is_paused():
                    voice_client.resume()
                    self.is_paused[guild_id] = False
                    self.is_playing[guild_id] = True
                    await interaction.followup.send("```Music resumed```")
                    return

            # Search for song
            song_info = await self.search_yt(song)
            if not song_info:
                await interaction.followup.send("```Could not find the song. Try another search term.```")
                return

            # Get or create song in database
            song_data = await self.get_or_create_song(song_info)
            
            # Add to queue
            position = await self.add_to_queue(guild_id, song_data, voice_channel.id)
            queue = await self.get_queue(guild_id)
            
            if self.is_playing.get(guild_id, False):
                await interaction.followup.send(f"**#{position + 1} - '{song_data['title']}'** added to the queue")
            else:
                await interaction.followup.send(f"**'{song_data['title']}'** added to the queue")
                await self.play_music(interaction)
                
        except Exception as e:
            print(f"Error in play command: {e}")
            await interaction.followup.send("```An error occurred while processing your request.```")

    @app_commands.command(name="queue", description="Displays the current songs in queue")
    async def queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        queue = await self.get_queue(guild_id)
        
        if queue:
            queue_list = []
            
            # Add currently playing song
            if guild_id in self.current_song:
                current = self.current_song[guild_id]
                queue_list.append(f"🎵 Currently playing: {current['title']}")
            
            # Add queued songs
            for i, queue_row in enumerate(queue):
                title = queue_row[5]  # Title is at index 5
                queue_list.append(f"#{i+1} - {title}")
            
            retval = "\n".join(queue_list)
            await interaction.response.send_message(f"```{retval}```")
        else:
            await interaction.response.send_message("```No music in queue```")

    @app_commands.command(name="clear_queue", description="Stops the music and clears the queue")
    async def clear_queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        await self.clear_queue(guild_id)
        
        self.is_playing[guild_id] = False
        self.is_paused[guild_id] = False
        self.current_song.pop(guild_id, None)

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            voice_client.stop()
            await voice_client.disconnect()
            if self.check_vc_members_task.get(guild_id):
                self.check_vc_members_task[guild_id].cancel()

        await interaction.response.send_message("```Music queue cleared```")

    @app_commands.command(name="stop", description="Kick the bot from VC")
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.is_playing[guild_id] = False
        self.is_paused[guild_id] = False
        self.current_song.pop(guild_id, None)

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            voice_client.stop()
            await voice_client.disconnect()
            if self.check_vc_members_task.get(guild_id):
                self.check_vc_members_task[guild_id].cancel()

        await interaction.response.send_message("```Bot disconnected from voice channel```")

    @app_commands.command(name="remove", description="Removes the last song added to queue")
    async def remove(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        queue = await self.get_queue(guild_id)
        
        if queue:
            # Remove last song (highest position)
            last_position = len(queue) - 1
            await self.remove_from_queue(guild_id, last_position)
            await interaction.response.send_message("```Last song removed from the queue```")
        else:
            await interaction.response.send_message("```No songs in the queue to remove```")

    @app_commands.command(name="pause", description="Pauses the current song being played")
    async def pause(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client
        
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            self.is_playing[guild_id] = False
            self.is_paused[guild_id] = True
            await interaction.response.send_message("```Music paused```")
        else:
            await interaction.response.send_message("```No music is currently playing```")

    @app_commands.command(name="resume", description="Resumes playing with the discord bot")
    async def resume(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client
        
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            self.is_paused[guild_id] = False
            self.is_playing[guild_id] = True
            await interaction.response.send_message("```Music resumed```")
        else:
            await interaction.response.send_message("```Music is not paused```")

    @app_commands.command(name="skip", description="Skips the current song")
    async def skip(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client

        if not voice_client or not self.is_playing.get(guild_id, False):
            await interaction.response.send_message("```No song is currently playing.```")
            return

        voice_client.stop()  # This will trigger the after callback and play_next
        await interaction.response.send_message("```Skipped current song```")

    @app_commands.command(name="now_playing", description="Shows information about the currently playing song")
    async def now_playing(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        
        if guild_id in self.current_song:
            song = self.current_song[guild_id]
            embed = discord.Embed(title="Now Playing", color=0x00ff00)
            embed.add_field(name="Title", value=song['title'], inline=False)
            embed.add_field(name="Play Count", value=song['play_count'], inline=True)
            
            if song.get('file_path'):
                embed.add_field(name="Source", value="Downloaded", inline=True)
            else:
                embed.add_field(name="Source", value="Streaming", inline=True)
                
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("```No song is currently playing```")

    @app_commands.command(name="cleanup_downloads", description="Remove old downloaded files to free up space")
    async def cleanup_downloads(self, interaction: discord.Interaction):
        """Clean up old downloaded files"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("```Only administrators can use this command```")
            return
            
        await interaction.response.defer()
        
        try:
            # Remove files not played in 30 days with less than 3 plays
            cutoff_time = int(time.time()) - (30 * 24 * 60 * 60)  # 30 days ago
            
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    SELECT file_path FROM songs 
                    WHERE file_path IS NOT NULL 
                    AND (last_played < ? AND play_count < 3)
                ''', (cutoff_time,))
                
                files_to_remove = await cursor.fetchall()
                removed_count = 0
                freed_space = 0
                
                for (file_path,) in files_to_remove:
                    if file_path and os.path.exists(file_path):
                        try:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            freed_space += file_size
                            removed_count += 1
                        except Exception as e:
                            print(f"Error removing {file_path}: {e}")
                
                # Update database to remove file paths
                await db.execute('''
                    UPDATE songs 
                    SET file_path = NULL, file_size = 0 
                    WHERE file_path IS NOT NULL 
                    AND (last_played < ? AND play_count < 3)
                ''', (cutoff_time,))
                await db.commit()
            
            freed_mb = freed_space / (1024 * 1024)
            await interaction.followup.send(f"```Cleanup complete!\nRemoved {removed_count} files\nFreed {freed_mb:.1f} MB of space```")
            
        except Exception as e:
            print(f"Error in cleanup: {e}")
            await interaction.followup.send("```Error occurred during cleanup```")

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
