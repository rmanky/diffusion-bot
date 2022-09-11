import os
import random
import replicate
from replicate.exceptions import ModelError
from disnake.ext import commands
from disnake import Embed, Status, Activity, ActivityType, Attachment
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from func_timeout import func_set_timeout, FunctionTimedOut

load_dotenv()

VERSION = 1.1
CHANGE_LIST = {
    'Updated Commands': """
    - `/face_fix` is now `/fix`
    - `/dream` will default `fix` to `False`
    """,
    'New Model': """
    - GFGAN has been replaced with CODEFORMER
    - Model will now output fullscale (512x512) image
    """,
    'Embed Everywhere': """
    - The bot will now retun Embeds for all responses
    """,
    'Timeouts': """
    - In the event calling Replicate takes too long, the bot will timeout and return an error
    """
}

bot = commands.InteractionBot()
stable_model = replicate.models.get('stability-ai/stable-diffusion')
face_model = replicate.models.get('sczhou/codeformer')
sched = AsyncIOScheduler()

status_list = ['people dream', 'the sunset', 'the sky fall', 'you 👀', 'the trees', 'and learning', 'the leaves fall', 'for aliens 👽', 'you break my heart 💔']

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    await timed_job()
    sched.add_job(timed_job, 'interval', minutes=60)
    sched.start()

async def timed_job():
    random_status = random.choice(status_list)
    activity = Activity(type=ActivityType.watching, name=random_status)
    await bot.change_presence(status=Status.online, activity=activity)

@bot.slash_command(description='Display the latest updates')
async def info(inter):
    embed = Embed()
    embed.title = f'🤖 DiffusionBot Version {VERSION}'
    for key, value in CHANGE_LIST.items():
        embed.add_field(name=key,value=value,inline=False)
    await inter.response.send_message(embed=embed)

@bot.slash_command(description='Feed a prompt to Stabile Diffusion')
async def dream(inter, prompt: str, fix: bool = False):
    print(f'📝 Dream request received from {inter.author.name}')

    embed = Embed()
    embed.title = '⏳ Request Received'
    embed.description = prompt
    await inter.response.send_message(embed=embed)

    try:
        output_image = stable_diffusion(prompt) 
        embed.title = '⚠️ Applying CODEFORMER' if fix else '✅ Completed'
        embed.set_image(output_image)
        await inter.edit_original_message(embed=embed)

        if not fix:
            return

        fixed_image = codeformer(output_image)
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
        embed.title = '😔 An Error Occured'
        embed.description = f'{prompt}\n`{err}`'
        await inter.edit_original_message(embed=embed)

@bot.slash_command(description='Feed an image of a face to CODEFORMER')
async def fix(inter, input_image: Attachment):
    print(f'📝 Face fix request received from {inter.author.name}')

    embed = Embed()
    embed.title = '⏳ Request Received'
    embed.description = 'Waiting on CODEFORMER...'
    await inter.response.send_message(content='', embed=embed)    
    try:
        output_image = codeformer(input_image.url)
        embed.title = '✅ Completed'
        embed.description = ''
        embed.set_image(output_image)
        await inter.edit_original_message(content='', embed=embed)
    except FunctionTimedOut as err:
        embed.title = '⏰ Function Timed Out'
        embed.description = 'Replicate timed out after a few seconds, sorry :('
        await inter.edit_original_message(embed=embed)
    except Exception as err:
        embed.title = '😔 An Error Occured'
        embed.description = err
        await inter.edit_original_message(content='', embed=embed)

@func_set_timeout(30)
def stable_diffusion(prompt: str):
    output = stable_model.predict(prompt=prompt)[0]
    return output

@func_set_timeout(60)
def codeformer(image: str):
    output = face_model.predict(image=image, codeformer_fidelity=0.5, upscale=1,
        background_enhance=False, face_upsample=False)
    return output

bot.run(os.environ['DISCORD_TOKEN'])
