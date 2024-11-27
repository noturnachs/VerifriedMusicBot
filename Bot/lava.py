import discord
from discord.ext import commands
import wavelink
import os
from dotenv import load_dotenv
import asyncio
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MusicBot')

load_dotenv()

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self) -> None:
        try:
            nodes = [
                wavelink.Node(
                    uri=f'https://{os.getenv("LAVALINK_HOST")}:{os.getenv("LAVALINK_PORT")}',
                    password=os.getenv('LAVALINK_PASSWORD', 'youshallnotpass')
                )
            ]
            await wavelink.Pool.connect(nodes=nodes, client=self)
            logger.info(f"Successfully connected to Lavalink")
        except Exception as e:
            logger.error(f"Failed to connect to Lavalink: {e}")
            raise

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue = {}  # Guild ID: List[Track]
        logger.info("Music cog initialized")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload):
        logger.info(f"Track started playing: {payload.track.title}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload):
        logger.info(f"Track finished playing: {payload.track.title}")
        
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node):
        logger.info(f"Wavelink node '{node}' is ready!")

    @commands.Cog.listener()
    async def on_wavelink_error(self, payload):
        logger.error(f"Wavelink error: {payload.error}")

    @commands.command()
    async def volume(self, ctx: commands.Context, volume: int = None):
        """Set or show the volume (0-100)"""
        if not ctx.voice_client:
            return await ctx.send("Not connected to a voice channel.")
        
        if volume is None:
            return await ctx.send(f"🔊 Current volume: {ctx.voice_client.volume}%")
            
        if not 0 <= volume <= 100:
            return await ctx.send("Volume must be between 0 and 100")
            
        await ctx.voice_client.set_volume(volume)
        await ctx.send(f"🔊 Volume set to {volume}%")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload):
        """Called when a track encounters an exception during playback"""
        logger.error(f"Track exception: {payload.exception}")
        if payload.player and payload.player.guild:
            channel = payload.player.guild.system_channel
            if channel:
                await channel.send(f"⚠️ Error playing track: {payload.exception}")

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        try:
            if not ctx.voice_client:
                if not ctx.author.voice:
                    return await ctx.send("You need to be in a voice channel!")
                # Connect to voice channel
                vc = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                await vc.set_volume(100)  # Set initial volume to maximum
                logger.info(f"Connected to voice channel: {ctx.author.voice.channel.name}")
            else:
                vc = ctx.voice_client

            # Add "ytsearch:" prefix if it's not a URL
            if not search.startswith(('http://', 'https://')):
                search = f'ytsearch:{search}'

            logger.info(f"Searching for: {search}")
            
            try:
                # First attempt to search
                tracks = await wavelink.Pool.fetch_tracks(search)
                if not tracks:
                    await ctx.send("Could not find any songs with that query.")
                    return
                
                track = tracks[0]  # Get the first track
                logger.info(f"Found track: {track.title} ({track.uri})")

                if not vc.playing:
                    await vc.play(track)
                    await vc.set_volume(100)  # Set volume to maximum
                    await ctx.send(f"🎵 Now playing: **{track.title}**")
                    logger.info(f"Started playing: {track.title}")
                else:
                    # Add to queue
                    if ctx.guild.id not in self.queue:
                        self.queue[ctx.guild.id] = []
                    self.queue[ctx.guild.id].append(track)
                    await ctx.send(f"Added to queue: **{track.title}**")
                    logger.info(f"Added to queue: {track.title}")

            except wavelink.exceptions.LavalinkLoadException as e:
                if "Please sign in" in str(e):
                    await ctx.send("⚠️ This video requires age verification. Please try a different video.")
                else:
                    raise

        except Exception as e:
            logger.error(f"Error in play command: {e}", exc_info=True)
            await ctx.send("An error occurred while trying to play the track.")

    @commands.command()
    async def skip(self, ctx: commands.Context):
        try:
            if not ctx.voice_client:
                return await ctx.send("I am not playing anything!")
            
            vc = ctx.voice_client
            if not vc.playing:  # Changed from is_playing()
                return await ctx.send("Nothing is playing!")

            await vc.stop()
            await ctx.send("⏭️ Skipped!")
            logger.info(f"Skipped track in guild {ctx.guild.id}")
            
            # Play next song if available
            if ctx.guild.id in self.queue and self.queue[ctx.guild.id]:
                next_track = self.queue[ctx.guild.id].pop(0)
                await vc.play(next_track)
                await ctx.send(f"🎵 Now playing: **{next_track.title}**")
                logger.info(f"Playing next track: {next_track.title} in guild {ctx.guild.id}")
        except Exception as e:
            logger.error(f"Error in skip command: {e}")
            await ctx.send("An error occurred while trying to skip the track.")

    @commands.command()
    async def queue(self, ctx: commands.Context):
        try:
            if ctx.guild.id not in self.queue or not self.queue[ctx.guild.id]:
                return await ctx.send("Queue is empty!")
            
            queue_list = "\n".join(
                f"{i+1}. {track.title}"
                for i, track in enumerate(self.queue[ctx.guild.id])
            )
            await ctx.send(f"**Current Queue:**\n{queue_list}")
            logger.info(f"Queue displayed for guild {ctx.guild.id}")
        except Exception as e:
            logger.error(f"Error in queue command: {e}")
            await ctx.send("An error occurred while trying to display the queue.")

    @commands.command()
    async def leave(self, ctx: commands.Context):
        try:
            if not ctx.voice_client:
                return await ctx.send("I am not in a voice channel!")
            
            await ctx.voice_client.disconnect()
            if ctx.guild.id in self.queue:
                self.queue[ctx.guild.id].clear()
            await ctx.send("👋 Disconnected from voice channel!")
            logger.info(f"Bot left voice channel in guild {ctx.guild.id}")
        except Exception as e:
            logger.error(f"Error in leave command: {e}")
            await ctx.send("An error occurred while trying to leave the voice channel.")

    # Add a debug command to check voice client status
    @commands.command()
    async def debug(self, ctx: commands.Context):
        try:
            if ctx.voice_client:
                vc = ctx.voice_client
                status = {
                    "Connected": vc.is_connected(),
                    "Playing": vc.playing,
                    "Channel": vc.channel.name if vc.channel else "None",
                    "Volume": vc.volume
                }
                await ctx.send(f"Voice Client Status:\n```python\n{status}\n```")
            else:
                await ctx.send("Not connected to any voice channel.")
        except Exception as e:
            logger.error(f"Error in debug command: {e}")
            await ctx.send("Error getting debug information.")

    @commands.command()
    async def playurl(self, ctx: commands.Context, *, url: str):
        """Play a song using direct URL"""
        try:
            if not ctx.voice_client:
                if not ctx.author.voice:
                    return await ctx.send("You need to be in a voice channel!")
                vc = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                logger.info(f"Connected to voice channel: {ctx.author.voice.channel.name}")
            else:
                vc = ctx.voice_client

            # Use search instead of from_url for Wavelink 3.4.1
            tracks = await wavelink.Playable.search(url)
            if not tracks:
                return await ctx.send("Could not load the track.")
            
            track = tracks[0]  # Get the first track
            logger.info(f"Found track: {track.title} ({track.uri})")

            if not vc.playing:
                await vc.play(track)
                await vc.set_volume(100)  # Set volume to maximum
                logger.info(f"Started playing: {track.title}")
                await ctx.send(f"🎵 Now playing: **{track.title}**")
            else:
                if ctx.guild.id not in self.queue:
                    self.queue[ctx.guild.id] = []
                self.queue[ctx.guild.id].append(track)
                await ctx.send(f"Added to queue: **{track.title}**")
                logger.info(f"Added to queue: {track.title}")

        except Exception as e:
            logger.error(f"Error in playurl command: {e}", exc_info=True)
            await ctx.send("An error occurred while trying to play the track.")

bot = MusicBot()

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} | {bot.user.id}')
    await bot.add_cog(Music(bot))

if __name__ == "__main__":
    bot.run(os.getenv('BOT_TOKEN'))