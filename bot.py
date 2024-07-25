import discord
from discord.ext import commands
import config

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    await bot.tree.sync()

async def setup():
    await bot.load_extension("music_cog")

bot.loop.create_task(setup())
bot.run(config.TOKEN)
