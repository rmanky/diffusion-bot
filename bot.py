import asyncio
import os
import random
import replicate
from replicate.exceptions import ModelError
from disnake.ext import commands
from disnake import Embed, Status, Activity, ActivityType, Attachment
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from func_timeout import func_set_timeout, FunctionTimedOut
from functools import wraps, partial

load_dotenv()

EMOTE = '🎃'
VERSION = 1.2
IMAGE = "https://thumbs.gfycat.com/IllegalFlimsyJuliabutterfly-size_restricted.gif"
CHANGE_LIST = {
    'Multi-Track Drifting': """
    - Replicate calls no longer block the main thread
    - The bot can now handle 3 concurrent calls of `/dream` and `/fix`
    """,
    'Error Handling': """
    - Failure for the bot to respond to a slash command will return a custom error
    """,
    'Spooky Season': """
    - The random status list has been updated for a spook-tacular October
    """
}

bot = commands.InteractionBot()
stable_model = replicate.models.get('stability-ai/stable-diffusion')
face_model = replicate.models.get('sczhou/codeformer')
sched = AsyncIOScheduler()

status_list = ['for spooky skeletons', 'people carve pumpkins', 'out for ghosts', 'scary movies', 'for trick-or-treaters']

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    await timed_job()
    sched.add_job(timed_job, 'interval', minutes=60)
    sched.start()

@bot.event
async def on_slash_command_error(inter, error):
    embed = Embed()
    embed.title = '❌ Command Failed'
    embed.description = str(error)
    await inter.response.send_message(embed=embed)

async def timed_job():
    random_status = random.choice(status_list)
    activity = Activity(type=ActivityType.watching, name=random_status)
    await bot.change_presence(status=Status.online, activity=activity)

@bot.slash_command(description='Display the latest updates')
async def info(inter):
    embed = Embed()
    embed.title = f'{EMOTE} DiffusionBot Version {VERSION}'
    if len(IMAGE) > 0:
        embed.set_image(IMAGE)
    for key, value in CHANGE_LIST.items():
        embed.add_field(name=key,value=value,inline=False)
    await inter.response.send_message(embed=embed)

@bot.slash_command(description='Feed a prompt to Stabile Diffusion')
@commands.max_concurrency(3)
async def dream(inter, prompt: str, fix: bool = False):
    await inter.response.defer()
    print(f'📝 Dream request received from {inter.author.name}')

    embed = Embed()
    embed.title = '⏳ Request Received'
    embed.description = prompt
    await inter.edit_original_message(embed=embed)

    try:
        output_image = await stable_diffusion(prompt) 
        embed.title = '⚠️ Applying CODEFORMER' if fix else '✅ Completed'
        embed.set_image(output_image)
        await inter.edit_original_message(embed=embed)

        if not fix:
            return

        fixed_image = await codeformer(output_image)
        embed.title = '✅ Completed'
        embed.add_field('Original Image', f'Here is your [original image]({output_image}) before CODEFORMER')
        embed.set_image(fixed_image)
        await inter.edit_original_message(embed=embed)
    except ModelError as err:
        embed.title = '😳 NSFW Content'
        embed.description = f'{prompt}\n`{err}`'
        await inter.edit_original_message(embed=embed)
    except FunctionTimedOut as err:
        embed.title = '⏰ Function Timed Out'
        embed.description = f'{prompt}\nReplicate timed out after a few seconds, sorry :('
        await inter.edit_original_message(embed=embed)
    except Exception as err:
        embed.title = '😔 An Error Occurred'
        embed.description = f'{prompt}\n`{err}`'
        await inter.edit_original_message(embed=embed)

@bot.slash_command(description='Feed an image of a face to CODEFORMER')
@commands.max_concurrency(3)
async def fix(inter, input_image: Attachment):
    await inter.response.defer()
    print(f'📝 Face fix request received from {inter.author.name}')

    embed = Embed()
    embed.title = '⏳ Request Received'
    embed.description = 'Waiting on CODEFORMER...'
    await inter.edit_original_message(content='', embed=embed)    
    try:
        output_image = await codeformer(input_image.url)
        embed.title = '✅ Completed'
        embed.description = ''
        embed.set_image(output_image)
        await inter.edit_original_message(content='', embed=embed)
    except FunctionTimedOut as err:
        embed.title = '⏰ Function Timed Out'
        embed.description = 'Replicate timed out after a few seconds, sorry :('
        await inter.edit_original_message(embed=embed)
    except Exception as err:
        embed.title = '😔 An Error Occurred'
        embed.description = err
        await inter.edit_original_message(content='', embed=embed)

def wrap(func):
    @wraps(func)
    async def run(*args, loop=None, executor=None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)
    return run

@wrap
@func_set_timeout(30)
def stable_diffusion(prompt: str):
    output = stable_model.predict(prompt=prompt)[0]
    return output

@wrap
@func_set_timeout(60)
def codeformer(image: str):
    output = face_model.predict(image=image, codeformer_fidelity=0.5, upscale=1,
        background_enhance=False, face_upsample=False)
    return output

bot.run(os.environ['DISCORD_TOKEN'])
