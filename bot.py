import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import yt_dlp as youtube_dl  # Change this line
from youtubesearchpython import VideosSearch



class MusicQueue:
    def __init__(self):
        self.queue = []
        self.current = None

queue = MusicQueue()


load_dotenv() 

# Set up the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.command()
async def play(ctx, *, query):
    # Check if user is in a voice channel
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel to use this command!")
        return

    # Search for the song on YouTube
    try:
        results = VideosSearch(query, limit=1).result()['result']
        if not results:
            await ctx.send("No results found!")
            return
        

        song_info = {
            'title': results[0]['title'],
            'url': results[0]['link'],
            'requester': ctx.author.name
        }
        
        # Add to queue if something is already playing
        if ctx.voice_client and ctx.voice_client.is_playing():
            queue.queue.append(song_info)
            await ctx.send(f"Added to queue: {song_info['title']}")
            return

        # Get the first result's URL
        video_url = results[0]['link']
        
        # Connect to voice channel
        voice_channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await voice_channel.connect()
        elif ctx.voice_client.channel != voice_channel:
            await ctx.voice_client.move_to(voice_channel)



        FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

         # Update this line with your FFmpeg path
        FFMPEG_PATH = "E:/ffmpeg/bin/ffmpeg.exe" 

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            url = info['url']  # Changed from formats[0]['url']
        # Play the audio
        voice_client = ctx.voice_client
        voice_client.play(discord.FFmpegPCMAudio(url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS))
        
        await ctx.send(f"Now playing: {results[0]['title']}")

        queue.current = song_info

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from voice channel")

@bot.command()
async def skip(ctx):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("Nothing is playing!")
        return

    ctx.voice_client.stop()
    await ctx.send("Skipped current song!")
    
    # Play next song if queue isn't empty
    if queue.queue:
        next_song = queue.queue.pop(0)
        await play_song(ctx, next_song['url'])

@bot.command(name='queue_list', aliases=['q'])
async def queue_list(ctx):
    if not queue.queue:
        await ctx.send("Queue is empty!")
        return

    queue_text = "**Current Queue:**\n"
    for i, song in enumerate(queue.queue, 1):
        queue_text += f"{i}. {song['title']} (requested by {song['requester']})\n"
    await ctx.send(queue_text)

@bot.command()
async def np(ctx):
    """Show now playing"""
    if not queue.current:
        await ctx.send("Nothing is playing!")
        return
    
    await ctx.send(f"🎵 Now playing: {queue.current['title']} (requested by {queue.current['requester']})")

@bot.command()
async def clear(ctx):
    """Clear the queue"""
    queue.queue.clear()
    await ctx.send("Queue cleared!")

@bot.command()
async def pause(ctx):
    """Pause the current song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused ⏸️")

@bot.command()
async def resume(ctx):
    """Resume the current song"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Resumed ▶️")

# Helper function to play songs
async def play_song(ctx, url):
    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }
    FFMPEG_PATH = "E:/ffmpeg/bin/ffmpeg.exe"

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        url = info['url']
    
    voice_client = ctx.voice_client
    voice_client.play(discord.FFmpegPCMAudio(url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS),
                     after=lambda e: bot.loop.create_task(play_next(ctx)))

async def play_next(ctx):
    """Automatically play the next song in the queue"""
    if queue.queue:
        next_song = queue.queue.pop(0)
        queue.current = next_song
        await play_song(ctx, next_song['url'])

# Replace with your token
bot.run(os.getenv('BOT_TOKEN'))