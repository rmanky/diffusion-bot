import asyncio
import os
import json
import urllib3
import random
import replicate
from disnake.ext import commands
from disnake import (
    ChannelType,
    Embed,
    Status,
    Activity,
    ActivityType,
    Attachment,
    File,
    TextChannel,
)
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from func_timeout import func_set_timeout, FunctionTimedOut
from functools import wraps, partial
import io, base64

load_dotenv()

EMOTE = "🦦"
VERSION = "1.3.4"
IMAGE = "https://i.gifer.com/cb5.gif"
CHANGE_LIST = {
    "A Learning Experience": """
    - `FunctionTimedOut` doesn't extend `BaseException`
    - [Apparently this is intentional... strange](https://github.com/kata198/func_timeout/issues/5#issuecomment-513441434)
    """,
    "Patience, For Now": """
    - Replicate timeout for Stable Diffusion increased from **30** to **45** seconds
    - [Are we born not knowing, or are we born knowing all?](https://www.youtube.com/watch?v=c9VQye6P8k0&t=99s)
    """,
}

DIFFUSION_TIMEOUT = 45
CODEFORMER_TIMEOUT = 60

bot = commands.InteractionBot()
stable_model = replicate.models.get("stability-ai/stable-diffusion")
face_model = replicate.models.get("sczhou/codeformer")
sched = AsyncIOScheduler()
http = urllib3.PoolManager()
black_image = ""

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
    with open("black_image.txt") as f:
        global black_image
        black_image = f.read()
        f.close()


@bot.event
async def on_slash_command_error(inter, error):
    embed = Embed()
    embed.title = "❌ Command Failed"
    embed.add_field(name="Error", value=str(error)[0:256], inline=False)
    if inter.response.is_done():
        await inter.edit_original_response(embed=embed)
    else:
        await inter.response.send_message(embed=embed)
    print(error)


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

    try:
        output_image = await stable_diffusion(prompt)
    except FunctionTimedOut:
        raise Exception(f"Replicate timed out after {DIFFUSION_TIMEOUT} seconds.")
    embed.title = "✅ Completed"
    embed.set_image(output_image)
    await inter.edit_original_response(embed=embed)


@bot.slash_command(description="Feed a prompt to the Stable Horde")
@commands.max_concurrency(3)
async def horde(inter, prompt: str, nsfw: bool):
    await inter.response.defer()
    print(f"📝 Horde request received from {inter.author.name}")

    channelSFW = inter.channel.type != ChannelType.private and not TextChannel.is_nsfw(
        inter.channel
    )

    if channelSFW and nsfw:
        embed = Embed()
        embed.title = "🛑 Invalid Usage"
        embed.add_field(
            name="Illegal Use of NSFW",
            value="`/horde` can not be used to generate NSFW images in a channel that isn't marked NSFW.",
            inline=False,
        )
        await inter.edit_original_response(embed=embed)
        return

    embed = Embed()
    embed.title = "👺 For the Horde!"
    embed.add_field(name="Prompt", value=prompt, inline=False)
    embed.add_field(name="Progress", value=f"{'⬛' * 10}", inline=False)
    embed.add_field(name="Wait Time", value="999s / 999s", inline=False)
    await inter.edit_original_response(embed=embed)

    id = await stable_horde_send(prompt, nsfw)
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
    if image_bytes == black_image:
        raise Exception(
            "The model generated a NSFW image. Please try again using the `nsfw` attribute."
        )
    file = File(
        io.BytesIO(base64.b64decode(image_bytes)),
        filename=f"result.webp",
    )

    embed.clear_fields()
    embed.title = "✅ Completed"
    embed.set_image(file=file)
    embed.add_field(name="Prompt", value=prompt, inline=False)
    await inter.edit_original_response(embed=embed)


@bot.slash_command(description="Retrieve performance metrics from the Stable Horde")
@commands.max_concurrency(3)
async def perf(inter):
    await inter.response.defer()
    print(f"📝 Performance request received from {inter.author.name}")

    perf = await stable_horde_perf()
    queue = perf["queue"]
    workers = perf["workers"]
    mps_queue = perf["mps_queue"]
    mps_hist = perf["mps_hist"]

    embed = Embed()
    embed.title = "🏁 Horde Metrics"
    embed.add_field(
        name="Queue",
        value=f"There are **{queue} requests** in the queue.",
        inline=False,
    )
    embed.add_field(
        name="Workers", value=f"There are **{workers} workers** online.", inline=False
    )
    embed.add_field(
        name="Megapixel Steps Queue",
        value=f"There are **{mps_queue} megapixel steps** in the queue.",
        inline=False,
    )
    embed.add_field(
        name="Megapixel Steps Performance",
        value=f"The horde completed **{mps_hist} megapixel steps** in the past minute.",
        inline=False,
    )
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

    try:
        output_image = await codeformer(input_image.url)
    except FunctionTimedOut:
        raise Exception(f"Replicate timed out after {CODEFORMER_TIMEOUT} seconds.")
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
@func_set_timeout(DIFFUSION_TIMEOUT)
def stable_diffusion(prompt: str):
    output = stable_model.predict(prompt=prompt)[0]
    return output


@wrap
@func_set_timeout(CODEFORMER_TIMEOUT)
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
def stable_horde_send(prompt: str, nsfw: bool):
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
        "nsfw": nsfw,
        "censor_nsfw": not nsfw,
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
    if "errors" in generate_response:
        raise Exception(generate_response["errors"])
    return generate_response["id"]


@wrap
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


@wrap
def stable_horde_perf():
    perf_request = http.request(
        "GET",
        f"https://stablehorde.net/api/v2/status/performance",
        headers={
            "Content-Type": "application/json",
            "apikey": os.environ["HORDE_TOKEN"],
        },
    )
    perf_response = json.loads(perf_request.data.decode())
    return {
        "queue": perf_response["queued_requests"],
        "workers": perf_response["worker_count"],
        "mps_queue": perf_response["queued_megapixelsteps"],
        "mps_hist": perf_response["past_minute_megapixelsteps"],
    }


bot.run(os.environ["DISCORD_TOKEN"])
