import os
import random
import replicate
from replicate.exceptions import ModelError
from disnake.ext import commands
from disnake import Embed, Status, Activity, ActivityType
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

bot = commands.InteractionBot()
stable_model = replicate.models.get("stability-ai/stable-diffusion")
face_model = replicate.models.get("tencentarc/gfpgan")
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
    print(f'✅ Set status to "Watching {random_status}"')
    activity = Activity(type=ActivityType.watching, name=random_status)
    await bot.change_presence(status=Status.online, activity=activity)

@bot.slash_command(description="Feeds a prompt to `Stability Diffusion`")
async def dream(inter, prompt: str, face_fix: bool):
    """Generate an image from a text prompt using the stable-diffusion model"""
    print(f'📝 Request received from {inter.author.name}')

    await inter.response.send_message(f">>> Prompt: `{prompt}`\nFace Fix: {face_fix}\nGenerating...")

    try:
        embed = Embed(description=prompt)

        image = stable_model.predict(prompt=prompt)[0]
        print(f'-- Original image: {image}')
        embed.title = '⚠️ Applying GFPGAN...' if face_fix else '✅ Completed'
        embed.set_image(image)
        await inter.edit_original_message(content='', embed=embed)

        if not face_fix:
            return

        image = face_model.predict(img=image)
        print(f'-- Fixed image: {image}')
        embed.title = '✅ Completed'
        embed.set_image(image)
        await inter.edit_original_message(content='', embed=embed)
    except ModelError as err:
        await inter.edit_original_message(content=f"> ⚠️ NSFW content, unable to generate!")
        print(f'-- {err}')
    except Exception as err:
        await inter.edit_original_message(content=f"> 😔 Sorry, an unrecoverable error has occured!")
        print(f'-- {err}')

bot.run(os.environ["DISCORD_TOKEN"])
