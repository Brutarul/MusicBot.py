import asyncio
import discord
import config
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    await bot.tree.sync()

async def main():
    await bot.load_extension("music_cog")
    async with bot:
        await bot.run(config.Token)

asyncio.run(main())
