import asyncio
import os
import discord
from discord.ext import commands
from Cogs.music_cog import MusicCog

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

async def load_cogs():
    for filename in os.listdir('./Cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'Cogs.{filename[:-3]}')
                print(f'Loaded {filename}')
            except Exception as e:
                print(f'Failed to load {filename}: {e}')

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    await bot.tree.sync()

async def main():
    await load_cogs()
    async with bot:
        await bot.start(config.Token)

asyncio.run(main())
