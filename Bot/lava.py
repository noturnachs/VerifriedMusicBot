import discord
from discord.ext import commands
import wavelink
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self) -> None:
        node: wavelink.Node = await wavelink.NodePool.create_node(
            bot=self,
            host=os.getenv('LAVALINK_HOST'),
            port=443,
            password='youshallnotpass',
            https=True
        )

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue = {}  # Guild ID: List[Track]

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        if not ctx.voice_client:
            if not ctx.author.voice:
                return await ctx.send("You need to be in a voice channel!")
            vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
        else:
            vc: wavelink.Player = ctx.voice_client

        track = await wavelink.YouTubeTrack.search(search, return_first=True)
        if not track:
            return await ctx.send("Could not find any songs with that query.")

        if not vc.is_playing():
            await vc.play(track)
            await ctx.send(f"🎵 Now playing: **{track.title}**")
        else:
            # Add to queue
            if ctx.guild.id not in self.queue:
                self.queue[ctx.guild.id] = []
            self.queue[ctx.guild.id].append(track)
            await ctx.send(f"Added to queue: **{track.title}**")

    @commands.command()
    async def skip(self, ctx: commands.Context):
        if not ctx.voice_client:
            return await ctx.send("I am not playing anything!")
        
        vc: wavelink.Player = ctx.voice_client
        if not vc.is_playing():
            return await ctx.send("Nothing is playing!")

        await vc.stop()
        await ctx.send("⏭️ Skipped!")
        
        # Play next song if available
        if ctx.guild.id in self.queue and self.queue[ctx.guild.id]:
            next_track = self.queue[ctx.guild.id].pop(0)
            await vc.play(next_track)
            await ctx.send(f"🎵 Now playing: **{next_track.title}**")

    @commands.command()
    async def queue(self, ctx: commands.Context):
        if ctx.guild.id not in self.queue or not self.queue[ctx.guild.id]:
            return await ctx.send("Queue is empty!")
        
        queue_list = "\n".join(
            f"{i+1}. {track.title}"
            for i, track in enumerate(self.queue[ctx.guild.id])
        )
        await ctx.send(f"**Current Queue:**\n{queue_list}")

    @commands.command()
    async def leave(self, ctx: commands.Context):
        if not ctx.voice_client:
            return await ctx.send("I am not in a voice channel!")
        
        await ctx.voice_client.disconnect()
        if ctx.guild.id in self.queue:
            self.queue[ctx.guild.id].clear()
        await ctx.send("👋 Disconnected from voice channel!")

bot = MusicBot()

@bot.event
async def on_ready():
    print(f'{bot.user} is ready!')
    await bot.add_cog(Music(bot))

bot.run(os.getenv('BOT_TOKEN'))