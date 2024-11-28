import discord
from discord.ext import commands
import wavelink
import os
from dotenv import load_dotenv
import asyncio
import logging
from discord.ui import Button, View
from typing import Optional
import datetime
from discord import Embed, Color
from aiohttp import web
from datetime import datetime, timedelta
from discord.ext import commands, tasks


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MusicBot')

load_dotenv()


def format_duration(milliseconds: float) -> str:
    """Format duration from milliseconds to a readable string"""
    seconds = int(milliseconds / 1000)  # Convert to seconds
    if seconds <= 0:
        return "LIVE"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

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
        self.alone_since = {}  # Guild ID: Time
        self.check_alone.start()
        self.command_channels = {}  # Guild ID: Text Channel

        logger.info("Music cog initialized")

    def cog_unload(self):
        self.check_alone.cancel()  # Cancel the task when cog is unloaded

    # Add this new task to check for alone status
    @tasks.loop(seconds=30)  # Check every 30 seconds
    async def check_alone(self):
        try:
            for guild in self.bot.guilds:
                if guild.voice_client:
                    vc = guild.voice_client
                    channel = vc.channel
                    
                    # Count members (excluding bots)
                    members = [m for m in channel.members if not m.bot]
                    
                    if not members:  # Bot is alone
                        if guild.id not in self.alone_since:
                            self.alone_since[guild.id] = datetime.now()
                            logger.info(f"Bot is alone in {guild.name}, starting timer")
                    else:
                        # Reset timer if not alone
                        self.alone_since.pop(guild.id, None)
                        
                    # Check if bot has been alone for more than 5 minutes
                    if guild.id in self.alone_since:
                        alone_time = datetime.now() - self.alone_since[guild.id]
                        if alone_time > timedelta(minutes=5):
                            logger.info(f"Bot has been alone for 5 minutes in {guild.name}, disconnecting")
                            await vc.disconnect()
                            if guild.id in self.queue:
                                self.queue[guild.id].clear()
                            self.alone_since.pop(guild.id)
                            
                            # Send message to the last used command channel
                            if guild.id in self.command_channels:
                                channel = self.command_channels[guild.id]
                                await channel.send("👋 Left voice channel due to inactivity (no users present for 5 minutes)")
        except Exception as e:
            logger.error(f"Error in check_alone task: {e}")

    @check_alone.before_loop
    async def before_check_alone(self):
        await self.bot.wait_until_ready()

    # Add this to handle voice state updates
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        try:
            if member.bot:  # Ignore bot voice state changes
                return

            if before.channel:
                guild = before.channel.guild
                if guild.voice_client and guild.voice_client.channel == before.channel:
                    # Check if bot is now alone
                    members = [m for m in before.channel.members if not m.bot]
                    if not members:
                        self.alone_since[guild.id] = datetime.now()
                        logger.info(f"Bot is now alone in {guild.name}")

            if after.channel:
                guild = after.channel.guild
                if guild.voice_client and guild.voice_client.channel == after.channel:
                    # Reset timer if someone joined
                    self.alone_since.pop(guild.id, None)
                    logger.info(f"Someone joined bot's channel in {guild.name}")

        except Exception as e:
            logger.error(f"Error in voice state update handler: {e}")

    @commands.command()
    async def pause(self, ctx: commands.Context):
        """Pause or resume the current track"""
        try:
            if not ctx.voice_client:
                return await ctx.send("❌ Not playing anything!")
            
            vc = ctx.voice_client
            if not vc.playing and not vc.paused:
                return await ctx.send("❌ Nothing is playing!")

            # Toggle pause state
            if vc.paused:
                await vc.pause(False)  # Resume by setting pause to False
                await ctx.send("▶️ Resumed")
            else:
                await vc.pause(True)   # Pause by setting pause to True
                await ctx.send("⏸️ Paused")
                
        except Exception as e:
            logger.error(f"Error in pause command: {e}")
            await ctx.send("❌ An error occurred!")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload):
        logger.info(f"Track started playing: {payload.track.title}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """Handle track end event and play next song in queue if available"""
        try:
            guild_id = payload.player.guild.id
            if guild_id in self.queue and self.queue[guild_id]:
                next_track = self.queue[guild_id].pop(0)
                await payload.player.play(next_track)
                
                # Use the stored command channel
                if guild_id in self.command_channels:
                    channel = self.command_channels[guild_id]
                    embed = discord.Embed(
                        title="🎵 Now Playing",
                        description=f"**{next_track.title}**",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Duration", value=format_duration(next_track.length))
                    
                    view = MusicControlView()
                    await channel.send(embed=embed, view=view)
                    logger.info(f"Auto-playing next track: {next_track.title} in guild {guild_id}")
                
        except Exception as e:
            logger.error(f"Error in track end event handler: {e}")  
            
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
    async def status(self, ctx: commands.Context):
        """Check the status of the music bot"""
        try:
            node = wavelink.Pool.get_node()
            if node:
                status_info = {
                    "Bot Connected": True,
                    "Voice Connected": ctx.voice_client is not None,
                    "Currently Playing": ctx.voice_client.playing if ctx.voice_client else False
                }
            else:
                status_info = {"Bot Connected": False}
                
            # Create a clean status message
            embed = discord.Embed(
                title="🎵 Music Bot Status",
                color=discord.Color.blue()
            )
            
            for key, value in status_info.items():
                embed.add_field(
                    name=key,
                    value="✅" if value else "❌",
                    inline=True
                )
                
            await ctx.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await ctx.send("❌ Error getting status")

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        """Play a song or playlist by title or URL
        
        Usage:
        !play <song title> - Search and play a song
        !play <url> - Play a song or playlist from URL
        """
        try:
            self.command_channels[ctx.guild.id] = ctx.channel
            if not ctx.voice_client:
                if not ctx.author.voice:
                    return await ctx.send("❌ You need to be in a voice channel!")
                vc = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                await vc.set_volume(100)
            else:
                vc = ctx.voice_client

            # Check if it's a playlist URL
            if 'list=' in search:
                # Fetch playlist tracks
                tracks = await wavelink.Pool.fetch_tracks(search)
                if not tracks:
                    return await ctx.send("❌ No songs found in playlist!")
                
                # Initialize queue if needed
                if ctx.guild.id not in self.queue:
                    self.queue[ctx.guild.id] = []
                
                # Filter out tracks longer than 10 minutes
                valid_tracks = [track for track in tracks if track.length <= 600000]
                skipped_tracks = len(tracks) - len(valid_tracks)
                
                # Add tracks to queue
                if not vc.playing:
                    first_track = valid_tracks.pop(0)
                    await vc.play(first_track)
                    await ctx.send(f"🎵 Now playing: **{first_track.title}**")
                
                self.queue[ctx.guild.id].extend(valid_tracks)
                
                await ctx.send(f"📑 Added {len(valid_tracks)} tracks to queue" + 
                             (f"\n⚠️ Skipped {skipped_tracks} tracks that were over 10 minutes" if skipped_tracks else ""))
                
            else:
                # Original single track logic
                if not search.startswith(('http://', 'https://')):
                    search = f'ytsearch:{search}'

                tracks = await wavelink.Pool.fetch_tracks(search)
                if not tracks:
                    return await ctx.send("❌ No songs found!")
                
                track = tracks[0]
                if track.length > 600000:
                    return await ctx.send("❌ Song is too long! Please choose a song under 10 minutes.")
                
                # Rest of your existing single track play logic...
                
        except Exception as e:
            logger.error(f"Error in play command: {e}", exc_info=True)
            await ctx.send("❌ An error occurred!")

    @commands.command()
    async def skip(self, ctx: commands.Context):
        try:
            if not ctx.voice_client:
                return await ctx.send("I am not playing anything!")
            
            vc = ctx.voice_client
            if not vc.playing:
                return await ctx.send("Nothing is playing!")

            # Store the channel where the command was used
            self.command_channels[ctx.guild.id] = ctx.channel
            
            # Stop current track
            await vc.stop()
            await ctx.send("⏭️ Skipped!")
            logger.info(f"Skipped track in guild {ctx.guild.id}")
            
            # Play next song if available
            if ctx.guild.id in self.queue and self.queue[ctx.guild.id]:
                next_track = self.queue[ctx.guild.id].pop(0)
                await vc.play(next_track)
                
                # Create embed for next track
                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**{next_track.title}**",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Duration", value=format_duration(next_track.length))
                
                # Create new view with buttons
                view = MusicControlView()
                
                # Send new message in the same channel as the command
                await ctx.channel.send(embed=embed, view=view)
                logger.info(f"Playing next track: {next_track.title} in guild {ctx.guild.id}")
                
        except Exception as e:
            logger.error(f"Error in skip command: {e}")
            await ctx.send("An error occurred while trying to skip the track.")


    @commands.command()
    async def queue(self, ctx: commands.Context):
        """Show the current music queue with pagination"""
        try:
            if ctx.guild.id not in self.queue or not self.queue[ctx.guild.id]:
                return await ctx.send("📭 Queue is empty!")
            
            # Get current track if playing
            current_track = None
            if ctx.voice_client and ctx.voice_client.playing:
                current_track = ctx.voice_client.current
            
            # Create queue view with pagination
            view = QueueView(
                queue_list=self.queue[ctx.guild.id],
                current_track=current_track
            )
            
            # Send initial embed with view
            await ctx.send(embed=view.get_embed(), view=view)
                
        except Exception as e:
            logger.error(f"Error in queue command: {e}")
            await ctx.send("❌ An error occurred!")

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
                    "Connected": vc.connected,  # Changed from is_connected()
                    "Playing": vc.playing,
                    "Channel": vc.channel.name if vc.channel else "None",
                    "Volume": vc.volume,
                    "Paused": vc.paused,
                    "Current Track": vc.current.title if vc.current else "None"
                }
                await ctx.send(f"Voice Client Status:\n```python\n{status}\n```")
            else:
                await ctx.send("Not connected to any voice channel.")
        except Exception as e:
            logger.error(f"Error in debug command: {e}")
            await ctx.send("Error getting debug information.")

    # @commands.command()
    # async def playurl(self, ctx: commands.Context, *, url: str):
    #     """Play a song using direct URL"""
    #     try:
    #         if not ctx.voice_client:
    #             if not ctx.author.voice:
    #                 return await ctx.send("You need to be in a voice channel!")
    #             vc = await ctx.author.voice.channel.connect(cls=wavelink.Player)
    #             logger.info(f"Connected to voice channel: {ctx.author.voice.channel.name}")
    #         else:
    #             vc = ctx.voice_client

    #         # Use search instead of from_url for Wavelink 3.4.1
    #         tracks = await wavelink.Playable.search(url)
    #         if not tracks:
    #             return await ctx.send("Could not load the track.")
            
    #         track = tracks[0]  # Get the first track
    #         logger.info(f"Found track: {track.title} ({track.uri})")

    #         if not vc.playing:
    #             await vc.play(track)
    #             await vc.set_volume(100)  # Set volume to maximum
    #             logger.info(f"Started playing: {track.title}")
    #             await ctx.send(f"🎵 Now playing: **{track.title}**")
    #         else:
    #             if ctx.guild.id not in self.queue:
    #                 self.queue[ctx.guild.id] = []
    #             self.queue[ctx.guild.id].append(track)
    #             await ctx.send(f"Added to queue: **{track.title}**")
    #             logger.info(f"Added to queue: {track.title}")

    #     except Exception as e:
    #         logger.error(f"Error in playurl command: {e}", exc_info=True)
    #         await ctx.send("An error occurred while trying to play the track.")
class QueueView(discord.ui.View):
    def __init__(self, queue_list, current_track, per_page=10):
        super().__init__(timeout=60)
        self.queue_list = queue_list
        self.current_track = current_track
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = max((len(queue_list) + per_page - 1) // per_page, 1)
        
        # Update button states
        self.update_buttons()
        
    def update_buttons(self):
        # Disable/Enable previous button
        self.prev_button.disabled = self.current_page <= 0
        # Disable/Enable next button
        self.next_button.disabled = self.current_page >= self.total_pages - 1
    
    def get_embed(self):
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        
        embed = discord.Embed(
            title="📑 Current Queue",
            color=discord.Color.blue()
        )
        
        # Add current track
        if self.current_track:
            embed.add_field(
                name="Now Playing",
                value=f"**{self.current_track.title}**\n`Duration: {format_duration(self.current_track.length)}`",
                inline=False
            )
        
        # Add queue tracks for current page
        if self.queue_list:
            queue_text = "\n".join(
                f"`{i+1}.` {track.title} `[{format_duration(track.length)}]`"
                for i, track in enumerate(self.queue_list[start_idx:end_idx], start=start_idx)
            )
            if queue_text:
                embed.add_field(name="Up Next", value=queue_text, inline=False)
        
        # Add page info
        if self.total_pages > 1:
            embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages}")
        
        return embed
    
    @discord.ui.button(label='◀️ Previous', style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label='Next ▶️', style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()


class MusicControlView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Play/Pause Button
        self.play_pause = Button(emoji="⏯️", style=discord.ButtonStyle.primary, row=0)
        self.play_pause.callback = self.play_pause_callback
        
        # Skip Button
        self.skip = Button(emoji="⏭️", style=discord.ButtonStyle.primary, row=0)
        self.skip.callback = self.skip_callback
        
        # Stop Button
        self.stop = Button(emoji="⏹️", style=discord.ButtonStyle.danger, row=0)
        self.stop.callback = self.stop_callback
        
        # Volume Buttons
        self.volume_down = Button(emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
        self.volume_down.callback = self.volume_down_callback
        
        self.volume_up = Button(emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
        self.volume_up.callback = self.volume_up_callback
        
        # Add buttons to view
        self.add_item(self.play_pause)
        self.add_item(self.skip)
        self.add_item(self.stop)
        self.add_item(self.volume_down)
        self.add_item(self.volume_up)
        
    async def play_pause_callback(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Not playing anything!", ephemeral=True)
        
        vc = interaction.guild.voice_client
        if vc.paused:
            await vc.resume()
            await interaction.response.send_message("▶️ Resumed", ephemeral=True)
        else:
            await vc.pause()
            await interaction.response.send_message("⏸️ Paused", ephemeral=True)

    async def skip_callback(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Not playing anything!", ephemeral=True)
        
        vc = interaction.guild.voice_client
        guild_id = interaction.guild.id
        
        # Get reference to the Music cog
        music_cog = interaction.client.get_cog('Music')
        if not music_cog:
            return await interaction.response.send_message("❌ Music system is not ready!", ephemeral=True)
        
        # Store the channel where the button was used
        music_cog.command_channels[guild_id] = interaction.channel
        
        await vc.stop()
        await interaction.response.send_message("⏭️ Skipped!", ephemeral=True)
        
        # Play next song if available
        if guild_id in music_cog.queue and music_cog.queue[guild_id]:
            next_track = music_cog.queue[guild_id].pop(0)
            await vc.play(next_track)
            
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**{next_track.title}**",
                color=discord.Color.blue()
            )
            embed.add_field(name="Duration", value=format_duration(next_track.length))
            
            view = MusicControlView()
            await interaction.channel.send(embed=embed, view=view)
            if not interaction.guild.voice_client:
                return await interaction.response.send_message("❌ Not playing anything!", ephemeral=True)
            
            vc = interaction.guild.voice_client
            guild_id = interaction.guild.id
            
            # Get reference to the Music cog
            music_cog = interaction.client.get_cog('Music')
            if not music_cog:
                return await interaction.response.send_message("❌ Music system is not ready!", ephemeral=True)
            
            await vc.stop()
            await interaction.response.send_message("⏭️ Skipped!", ephemeral=True)
            
            # Play next song if available
            if guild_id in music_cog.queue and music_cog.queue[guild_id]:
                next_track = music_cog.queue[guild_id].pop(0)
                await vc.play(next_track)
                
                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**{next_track.title}**",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Duration", value=format_duration(next_track.length))
                
                view = MusicControlView()
                await interaction.followup.send(embed=embed, view=view)

    async def stop_callback(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)
        
        vc = interaction.guild.voice_client
        await vc.disconnect()
        await interaction.response.send_message("⏹️ Stopped and disconnected!", ephemeral=True)

    async def volume_up_callback(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)
        
        vc = interaction.guild.voice_client
        current_volume = vc.volume
        new_volume = min(current_volume + 10, 100)
        await vc.set_volume(new_volume)
        await interaction.response.send_message(f"🔊 Volume: {new_volume}%", ephemeral=True)

    async def volume_down_callback(self, interaction: discord.Interaction):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)
        
        vc = interaction.guild.voice_client
        current_volume = vc.volume
        new_volume = max(current_volume - 10, 0)
        await vc.set_volume(new_volume)
        await interaction.response.send_message(f"🔉 Volume: {new_volume}%", ephemeral=True)



async def start_server():
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="Bot is alive!"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080)))
    await site.start()        

bot = MusicBot()

@bot.event




async def on_ready():
    logger.info(f'Logged in as {bot.user.name} | {bot.user.id}')
    # Add the Music cog if it hasn't been added yet

    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name="!play | Music Bot"
    )
    await bot.change_presence(
        status=discord.Status.online,
        activity=activity
    )

    if 'Music' not in [cog.qualified_name for cog in bot.cogs.values()]:
        await bot.add_cog(Music(bot))
    logger.info("Music cog has been loaded")

if __name__ == "__main__":
    async def start_bot():
        try:
            # Start the web server first
            await start_server()
            logger.info("Web server started successfully")
            
            # Start the bot
            token = os.getenv('BOT_TOKEN')
            if not token:
                raise ValueError("BOT_TOKEN not found in environment variables")
            
            await bot.start(token)
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise

    # Run everything
    asyncio.run(start_bot())



