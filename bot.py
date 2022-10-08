import asyncio
import os
import json
import urllib3
import random
import replicate
from disnake.ext import commands
from disnake import Embed, Status, Activity, ActivityType, Attachment, File
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from func_timeout import func_set_timeout, FunctionTimedOut
from functools import wraps, partial
import io, base64

load_dotenv()

EMOTE = "👺"
VERSION = 1.3
IMAGE = "https://media0.giphy.com/media/7YDaJq1YJmlt1sHHjg/giphy.gif"
CHANGE_LIST = {
    "Welcome to the Horde": """
    - Added a new command, `/horde`, that will send commands to [Stable Horde](https://stablehorde.net)
    - It uses the Euler Ancestral sampler at 32 steps, which can give more _detailed_ outputs
    - The queue can be quite long, the bot will check it every `max(wait * 0.1, 5)` seconds
    """,
    "Simplified Commands": """
    - The `fix` parameter has been removed from `/dream` for simplicity, please use `/fix` instead
    - Commands now use a unified generic error handler
    """,
    "NSFW Warning": """
    - Images contained in an embed can **not** be marked as a spoiler (blame Discord)
    - Yes I've tried "ballsack", it works as expected...
    """,
}

bot = commands.InteractionBot()
stable_model = replicate.models.get("stability-ai/stable-diffusion")
face_model = replicate.models.get("sczhou/codeformer")
sched = AsyncIOScheduler()
http = urllib3.PoolManager()

status_list = [
    "for spooky skeletons",
    "people carve pumpkins",
    "out for ghosts",
    "scary movies",
    "for trick-or-treaters",
]


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")
    await timed_job()
    sched.add_job(timed_job, "interval", minutes=60)
    sched.start()


@bot.event
async def on_slash_command_error(inter, error):
    embed = Embed()
    embed.title = "❌ Command Failed"
    embed.add_field(name="Error", value=str(error)[0:256], inline=False)
    if inter.response.is_done():
        await inter.edit_original_response(embed=embed)
    else:
        await inter.response.send_message(embed=embed)


async def timed_job():
    random_status = random.choice(status_list)
    activity = Activity(type=ActivityType.watching, name=random_status)
    await bot.change_presence(status=Status.online, activity=activity)


@bot.slash_command(description="Display the latest updates")
async def info(inter):
    embed = Embed()
    embed.title = f"{EMOTE} DiffusionBot Version {VERSION}"
    if len(IMAGE) > 0:
        embed.set_image(IMAGE)
    for key, value in CHANGE_LIST.items():
        embed.add_field(name=key, value=value, inline=False)
    await inter.response.send_message(embed=embed)


@bot.slash_command(description="Feed a prompt to Stable Diffusion")
@commands.max_concurrency(3)
async def dream(inter, prompt: str):
    await inter.response.defer()
    print(f"📝 Dream request received from {inter.author.name}")

    embed = Embed()
    embed.title = "⏳ Request Received"
    embed.add_field(name="Prompt", value=prompt, inline=False)
    await inter.edit_original_response(embed=embed)

    output_image = await stable_diffusion(prompt)
    embed.title = "✅ Completed"
    embed.set_image(output_image)
    await inter.edit_original_response(embed=embed)


@bot.slash_command(description="Feed a prompt to the Stable Horde")
@commands.max_concurrency(3)
async def horde(inter, prompt: str):
    await inter.response.defer()
    print(f"📝 Horde request received from {inter.author.name}")

    embed = Embed()
    embed.title = "👺 For the Horde!"
    embed.add_field(name="Prompt", value=prompt, inline=False)
    embed.add_field(name="Progress", value=f"{'⬛' * 10}", inline=False)
    embed.add_field(name="Wait Time", value="999s / 999s", inline=False)
    await inter.edit_original_response(embed=embed)

    id = await stable_horde_send(prompt)
    longest_wait = 0
    while True:
        status = await stable_horde_poll(id)
        if status["done"] == True:
            break
        wait = status["wait"]
        if wait > longest_wait:
            longest_wait = wait
        progress = int(wait / longest_wait * 10)
        embed.set_field_at(
            index=1,
            name="Progress",
            value=f"{'🟩' * (10 - progress)}{'⬛' * progress}",
            inline=False,
        )
        embed.set_field_at(
            index=2,
            name="Wait Time",
            value=f"{wait}s / {longest_wait}s",
            inline=False,
        )
        await inter.edit_original_response(embed=embed)
        await asyncio.sleep(max(wait * 0.1, 5))
    image_bytes = await stable_horde_get(id)
    file = File(
        io.BytesIO(base64.b64decode(image_bytes)),
        filename=f"{prompt.replace(' ','_')}.webp",
    )
    embed.clear_fields()
    embed.title = "✅ Completed"
    embed.add_field(name="Prompt", value=prompt, inline=False)
    embed.set_image(file=file)
    await inter.edit_original_response(embed=embed)


@bot.slash_command(description="Feed an image of a face to CODEFORMER")
@commands.max_concurrency(3)
async def fix(inter, input_image: Attachment):
    await inter.response.defer()
    print(f"📝 Face fix request received from {inter.author.name}")

    embed = Embed()
    embed.title = "⏳ Request Received"
    embed.add_field(name="Status", value="Waiting on CODEFORMER...", inline=False)
    await inter.edit_original_response(content="", embed=embed)

    output_image = await codeformer(input_image.url)
    embed.title = "✅ Completed"
    embed.set_image(output_image)
    embed.clear_fields()
    await inter.edit_original_response(content="", embed=embed)


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
    output = face_model.predict(
        image=image,
        codeformer_fidelity=0.5,
        upscale=1,
        background_enhance=False,
        face_upsample=False,
    )
    return output


@wrap
@func_set_timeout(10)
def stable_horde_send(prompt: str):
    request_body = {
        "params": {
            "sampler_name": "k_euler_a",
            "batch_size": 1,
            "cfg_scale": 7,
            "seed": "",
            "height": 512,
            "width": 512,
            "steps": 32,
            "n": 1,
        },
        "prompt": prompt,
        "nsfw": "true",
        "censor_nsfw": "false",
    }

    encoded_request_body = json.dumps(request_body)

    generate_request = http.request(
        "POST",
        "https://stablehorde.net/api/v2/generate/async",
        body=encoded_request_body,
        headers={
            "Content-Type": "application/json",
            "apikey": os.environ["HORDE_TOKEN"],
        },
    )
    generate_response = json.loads(generate_request.data.decode())
    return generate_response["id"]


@wrap
@func_set_timeout(10)
def stable_horde_poll(id: str):
    check_request = http.request(
        "GET",
        f"https://stablehorde.net/api/v2/generate/check/{id}",
        headers={
            "Content-Type": "application/json",
            "apikey": os.environ["HORDE_TOKEN"],
        },
    )
    check_response = json.loads(check_request.data.decode())

    if check_response["finished"]:
        return {"done": True}
    return {
        "done": False,
        "queue": check_response["queue_position"],
        "wait": check_response["wait_time"],
    }


@wrap
@func_set_timeout(10)
def stable_horde_get(id: str):
    get_request = http.request(
        "GET",
        f"https://stablehorde.net/api/v2/generate/status/{id}",
        headers={
            "Content-Type": "application/json",
            "apikey": os.environ["HORDE_TOKEN"],
        },
    )
    get_response = json.loads(get_request.data.decode())
    return get_response["generations"][0]["img"]


bot.run(os.environ["DISCORD_TOKEN"])
