import replicate
from replicate.exceptions import ModelError
import os
from disnake.ext import commands
from disnake import Embed
from dotenv import load_dotenv
# from discord.ext import commands
# from discord import Intents

load_dotenv()

bot = commands.InteractionBot()
stable_model = replicate.models.get("stability-ai/stable-diffusion")
face_model = replicate.models.get("tencentarc/gfpgan")

@bot.slash_command(description="Responds with 'World'")
async def hello(inter):
    await inter.response.send_message("World")

@bot.slash_command(description="Feeds a prompt to `Stability Diffusion`")
async def dream(inter, prompt: str, face_fix: bool):
    """Generate an image from a text prompt using the stable-diffusion model"""
    print(f'📝 Request received from {inter.author.name}')

    await inter.response.send_message(f">>> Prompt: `{prompt}`\nFace Fix: {face_fix}")

    try:
        embed = Embed(description=prompt)

        image = stable_model.predict(prompt=prompt)[0]
        print(f'-- Original image: {image}')
        embed.title = '⚠️ Applying GFPGAN...' if face_fix else '✅ Completed'
        embed.set_image(image)
        await inter.edit_original_message(embed=embed)

        if face_fix:
            image = face_model.predict(img=image)
            print(f'-- Fixed image: {image}')
            embed.title = '✅ Completed'
            embed.set_image(image)
            await inter.edit_original_message(embed=embed)
    except ModelError as err:
        await inter.edit_original_message(content=f"> ⚠️ NSFW content, unable to generate!")
        print(f'-- {err}')
    except Exception as err:
        await inter.edit_original_message(content=f"> 😔 Sorry, an unrecoverable error has occured!")
        print(f'-- {err}')

bot.run(os.environ["DISCORD_TOKEN"])
