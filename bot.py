import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import yt_dlp as youtube_dl  # Change this line
from youtubesearchpython import VideosSearch
import random
import time
from fake_useragent import UserAgent  # You'll need to install this: pip install fake-useragent
import asyncio
from datetime import datetime
import socket



class MusicQueue:
    def __init__(self):
        self.queue = []
        self.current = None

queue = MusicQueue()


load_dotenv() 

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36 Edg/92.0.902.55',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/120.0.0.0'
]

REFERRERS = [
    'https://www.google.com/',
    'https://www.bing.com/',
    'https://search.yahoo.com/',
    'https://duckduckgo.com/',
    'https://www.youtube.com/',
    'https://music.youtube.com/'
]

def get_random_headers():
    try:
        ua = UserAgent()
        user_agent = ua.random
    except:
        user_agent = random.choice(USER_AGENTS)
    
    return {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': f'en-US,en;q={random.uniform(0.8, 1.0):.1f}',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Sec-CH-UA': '" Not A;Brand";v="99", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-CH-UA-Mobile': '?0',
        'Sec-CH-UA-Platform': '"Windows"',
        'Referer': random.choice(REFERRERS),
        'Cache-Control': 'max-age=0'
    }

# Set up the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def get_ydl_opts():
    headers = get_random_headers()
    return {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
        'extract_flat': False,
        'extractor_args': {
            'youtube': {
                'player_client': random.choice(['android', 'web', 'mweb']),
                'player_skip': ['js', 'configs', 'webpage'],
                'player_params': {'hl': 'en', 'gl': random.choice(['US', 'GB', 'CA', 'AU'])},
            },
        },
        'socket_timeout': random.uniform(10, 15),
        'retries': 5,
        'user_agent': headers['User-Agent'],
        'headers': headers,
        'http_headers': headers,
        'age_limit': None,
        'geo_bypass': True,
        'geo_bypass_country': random.choice(['US', 'GB', 'CA', 'AU']),
    }

async def extract_url_with_retry(ydl, video_url, max_retries=5):
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = min(random.uniform(2, 4) * (2 ** attempt), 10)
                await asyncio.sleep(delay)
            
            info = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: ydl.extract_info(video_url, download=False)
            )
            
            if 'url' in info:
                return info['url']
            elif 'formats' in info:
                formats = info['formats']
                formats.sort(key=lambda x: (
                    x.get('asr', 0),
                    x.get('filesize', 0) if x.get('filesize') is not None else float('inf')
                ), reverse=True)
                
                for format in formats:
                    if format.get('url'):
                        return format['url']
            
            raise Exception("No suitable format found")
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                raise e
            continue
    
    raise Exception("Could not extract audio URL after multiple attempts")

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



        with youtube_dl.YoutubeDL(get_ydl_opts()) as ydl:
            try:
                url = await extract_url_with_retry(ydl, video_url)
            except Exception as e:
                await ctx.send(f"Failed to process video. Try another song or try again later.")
                return

        # Add small random delay before playing
        await asyncio.sleep(random.uniform(0.5, 1.5))

        FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

        voice_client = ctx.voice_client
        voice_client.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS))
        
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

async def play_song(ctx, url):
    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }

    # Check if running in Docker (you can set this env var in your Dockerfile)
    if os.getenv('DOCKER_ENV'):
        ffmpeg_path = 'ffmpeg'  # Use global ffmpeg in Docker
    else:
        ffmpeg_path = "E:/ffmpeg/bin/ffmpeg.exe"  # Local Windows path

    with youtube_dl.YoutubeDL(get_ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
        url = info['url']
    
    voice_client = ctx.voice_client
    voice_client.play(discord.FFmpegPCMAudio(url, executable=ffmpeg_path, **FFMPEG_OPTIONS),
                     after=lambda e: bot.loop.create_task(play_next(ctx)))

async def play_next(ctx):
    """Automatically play the next song in the queue"""
    if queue.queue:
        next_song = queue.queue.pop(0)
        queue.current = next_song
        await play_song(ctx, next_song['url'])

# Replace with your token
bot.run(os.getenv('BOT_TOKEN'))