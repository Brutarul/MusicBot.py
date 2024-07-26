import discord
from discord import FFmpegPCMAudio, app_commands
from discord.ext import commands
from youtubesearchpython import VideosSearch
from yt_dlp import YoutubeDL
import asyncio

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        self.is_playing = {}
        self.is_paused = {}
        self.check_vc_members_task = {}
        self.music_queues = {}
        
        self.YDL_OPTIONS = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
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
        
        self.FFMPEG_OPTIONS = {
            'options': '-vn', 
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        }

        self.ytdl = YoutubeDL(self.YDL_OPTIONS)

    def get_guild_queue(self, guild_id):
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = []
        return self.music_queues[guild_id]

    def search_yt(self, item):
        if item.startswith("https://"):
            info = self.ytdl.extract_info(item, download=False)
            return {'source': item, 'title': info["title"]}
        search = VideosSearch(item, limit=1)
        result = search.result()["result"][0]
        return {'source': result["link"], 'title': result["title"]}

    async def check_vc_members(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if guild:
            voice_client = guild.voice_client
            if voice_client:
                while voice_client.is_connected():
                    await asyncio.sleep(10)

    async def play_music(self, interaction):
        try:
            guild_id = interaction.guild.id
            queue = self.get_guild_queue(guild_id)
            if queue:
                self.is_playing[guild_id] = True

                song, voice_channel = queue[0]
                voice_client = voice_channel.guild.voice_client

                if not voice_client or not voice_client.is_connected():
                    voice_client = await voice_channel.connect()
                    self.check_vc_members_task[guild_id] = asyncio.create_task(self.check_vc_members(guild_id))

                data = await asyncio.to_thread(self.ytdl.extract_info, song['source'], download=False)
                url = data['url']

                queue.pop(0)
                voice_client.play(FFmpegPCMAudio(url, **self.FFMPEG_OPTIONS), after=lambda _: self.bot.loop.create_task(self.play_next(interaction)))
        except Exception as e:
            print(f"Error in play_music: {e}")

    async def play_next(self, interaction):
        try:
            guild_id = interaction.guild.id
            queue = self.get_guild_queue(guild_id)
            if queue:
                self.is_playing[guild_id] = True
                song, voice_channel = queue[0]

                data = await asyncio.to_thread(self.ytdl.extract_info, song['source'], download=False)
                url = data['url']

                vc = interaction.guild.voice_client
                if not vc:
                    vc = await voice_channel.connect()
                    self.check_vc_members_task[guild_id] = asyncio.create_task(self.check_vc_members(guild_id))

                queue.pop(0)
                vc.play(FFmpegPCMAudio(url, **self.FFMPEG_OPTIONS), after=lambda _: self.bot.loop.create_task(self.play_next(interaction)))
                await interaction.channel.send(f"Now playing: **{song['title']}**")
            else:
                self.is_playing[guild_id] = False
                await self.disconnect_if_idle(interaction)
        except Exception as e:
            print(f"Error in play_next: {e}")

    async def disconnect_if_idle(self, interaction):
        await asyncio.sleep(60)
        guild_id = interaction.guild.id
        if not self.is_playing.get(guild_id, False) and not self.get_guild_queue(guild_id):
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
            query = song
            guild_id = interaction.guild.id
            if self.is_paused.get(guild_id, False):
                voice_client = voice_channel.guild.voice_client
                if voice_client:
                    voice_client.resume()
                    self.is_paused[guild_id] = False
                    self.is_playing[guild_id] = True
                    await interaction.followup.send("```Music resumed```")
                else:
                    await self.play_music(interaction)
            else:
                song_info = self.search_yt(query)
                if not song_info:
                    await interaction.followup.send("```Could not download the song. Incorrect format try another keyword. This could be due to playlist or a livestream format.```")
                else:
                    queue = self.get_guild_queue(guild_id)
                    queue.append([song_info, voice_channel])
                    if self.is_playing.get(guild_id, False):
                        await interaction.followup.send(f"**#{len(queue) + 1} - '{song_info['title']}'** added to the queue")
                    else:
                        await interaction.followup.send(f"**'{song_info['title']}'** added to the queue")
                        await self.play_music(interaction)
        except Exception as e:
            print(e)

    @app_commands.command(name="queue", description="Displays the current songs in queue")
    async def queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        queue = self.get_guild_queue(guild_id)
        if queue:
            retval = "\n".join([f"#{i+1} - {entry[0]['title']}" for i, entry in enumerate(queue)])
            await interaction.response.send_message(f"```Queue:\n{retval}```")
        else:
            await interaction.response.send_message("```No music in queue```")

    @app_commands.command(name="clear_queue", description="Stops the music and clears the queue")
    async def clear_queue(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.music_queues[guild_id] = []
        self.is_playing[guild_id] = False
        self.is_paused[guild_id] = False

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            if self.check_vc_members_task.get(guild_id):
                self.check_vc_members_task[guild_id].cancel()

        await interaction.response.send_message("```Music queue cleared```")

    @app_commands.command(name="stop", description="Kick the bot from VC")
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.is_playing[guild_id] = False
        self.is_paused[guild_id] = False

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            if self.check_vc_members_task.get(guild_id):
                self.check_vc_members_task[guild_id].cancel()

        await interaction.response.send_message("```Bot disconnected from voice channel```")

    @app_commands.command(name="remove", description="Removes the last song added to queue")
    async def remove(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        queue = self.get_guild_queue(guild_id)
        if queue:
            queue.pop()
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

    @app_commands.command(name="resume", description="Resumes playing with the discord bot")
    async def resume(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if self.is_paused.get(guild_id, False):
            self.is_paused[guild_id] = False
            self.is_playing[guild_id] = True
            vc = interaction.guild.voice_client
            if vc:
                vc.resume()
                await interaction.response.send_message("```Music resumed```")

    @app_commands.command(name="skip", description="Skips the current song")
    async def skip(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        vc = interaction.guild.voice_client

        if not vc or not self.is_playing.get(guild_id, False):
            await interaction.response.send_message("```No song is currently playing.```")
            return

        vc.stop()
        await interaction.response.defer()
        await interaction.followup.send("```Skipping current song...```")

        try:
            await self.play_next(interaction)
        except Exception as e:
            await interaction.followup.send(f"```Error occurred while skipping: {e}```")
            print(f"Error in skip command: {e}")

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
