import os
import re
import csv
import io
import aiohttp
import threading
from dotenv import load_dotenv
from flask import Flask, redirect
import discord
from discord import app_commands
from discord.ext import commands

# === Load Environment Variables ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CSV_URL = "https://sheets.artistgrid.cx/artists.csv"
ALLOWED_GUILD_ID = 1395824457527988377
GOOGLE_SHEETS_RE = re.compile(r"https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]{44})")

# === Discord Bot Setup ===
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
guild = discord.Object(id=ALLOWED_GUILD_ID)

# === Helper Functions ===

def parse_csv_row(row):
    """Convert a CSV row into a formatted Discord message line."""
    artist_name = row["Artist Name"]
    if row["Best"].strip().lower() == "yes":
        artist_name = f"⭐{artist_name}⭐"

    url = row["URL"]
    match = GOOGLE_SHEETS_RE.match(url)
    if match:
        sheet_id = match.group(1)
        url = f"https://trackerhub.cx/sh/{sheet_id}"

    return (
        f"[{artist_name}]({url})\n"
        f"credit: ({row['Credit']})\n"
        f"Links work: {row['Links Work']}\n"
        f"Updated: {row['Updated']}"
    )

async def fetch_csv():
    """Download and return CSV data as a list of dicts."""
    async with aiohttp.ClientSession() as session:
        async with session.get(CSV_URL) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch CSV: HTTP {resp.status}")
            text_data = await resp.text()
    return list(csv.DictReader(io.StringIO(text_data)))

async def send_paginated_response(interaction, lines, chunk_size=1800):
    """Send messages in chunks to avoid hitting Discord's message size limits."""
    chunks = []
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 2 > chunk_size:
            chunks.append(current_chunk)
            current_chunk = ""
        current_chunk += line + "\n\n"
    if current_chunk:
        chunks.append(current_chunk)

    for chunk in chunks:
        await interaction.followup.send(chunk, suppress_embeds=True)

# === Bot Events ===

@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.online)
    print(f"Logged in as {bot.user}")
    try:
        await bot.tree.sync(guild=guild)
        print(f"Slash commands synced to guild {ALLOWED_GUILD_ID}")
    except Exception as e:
        print(f"Command sync failed: {e}")

# === Slash Commands ===

@bot.tree.command(name="search", description="Search artist info from CSV", guild=guild)
@app_commands.describe(artist="Artist name to search")
async def search(interaction: discord.Interaction, artist: str):
    if interaction.guild_id != ALLOWED_GUILD_ID:
        await interaction.response.send_message("This command can only be used in the authorized server.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        data = await fetch_csv()
    except Exception as e:
        await interaction.followup.send(str(e), suppress_embeds=True)
        return

    artist_lower = artist.lower()
    results = [
        parse_csv_row(row)
        for row in data
        if artist_lower in row["Artist Name"].lower()
    ][:5]

    if not results:
        await interaction.followup.send(f"No results found for '{artist}'.", suppress_embeds=True)
    else:
        await send_paginated_response(interaction, results)

@bot.tree.command(name="list", description="List all trackers", guild=guild)
async def list_trackers(interaction: discord.Interaction):
    if interaction.guild_id != ALLOWED_GUILD_ID:
        await interaction.response.send_message("This command can only be used in the authorized server.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        data = await fetch_csv()
    except Exception as e:
        await interaction.followup.send(str(e), suppress_embeds=True)
        return

    results = [parse_csv_row(row) for row in data]
    if not results:
        await interaction.followup.send("No trackers found.", suppress_embeds=True)
    else:
        await send_paginated_response(interaction, results)

# === Flask Redirect App ===

app = Flask(__name__)

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path):
    return redirect("https://artistgrid.cx/", code=302)

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# === Main Entry Point ===

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
