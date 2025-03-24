import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta, UTC

TOKEN = "YOUR_BOT_TOKEN"

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.reactions = True
intents.message_content = True  # Required for prefix command
intents.members = True  # Required for timing out members

bot = commands.Bot(command_prefix="!", intents=intents)

# Configurations
allowed_roles = ["Riffraff"]  # Roles that can initiate a vote
vote_threshold = 3  # Minimum votes required to timeout a user
vote_duration = 60  # Vote time limit in seconds
max_timeout_duration = 300  # Maximum timeout duration (5 minutes)
user_vote_cooldowns = {}  # Tracks last vote time for users
active_votes = {}  # Stores active votes (msg_id -> vote details)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()  # Sync slash commands
        print(f"Slash commands synced: {len(synced)} commands available.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

async def start_vote(channel, initiator, user: discord.Member, duration: int, interaction=None):
    """Handles voting logic for both prefix and slash commands."""
    # Ensure duration doesn't exceed max timeout
    duration = min(duration, max_timeout_duration)  # Silently enforce 5-minute limit

    # Check if initiator has permission
    if not any(role.name in allowed_roles for role in initiator.roles):
        if interaction:
            await interaction.response.send_message("You don't have permission to start a vote.", ephemeral=True)
        else:
            await channel.send("You don't have permission to start a vote.")
        return

    # Prevent repeated votes on the same user
    now = datetime.now(UTC)
    if user.id in user_vote_cooldowns and now - user_vote_cooldowns[user.id] < timedelta(minutes=1):
        if interaction:
            await interaction.response.send_message(f"A vote on {user.mention} was recently started. Please wait.", ephemeral=True)
        else:
            await channel.send(f"A vote on {user.mention} was recently started. Please wait before starting another.")
        return

    # Create vote message
    vote_message = f"Vote to timeout {user.mention} for {duration} seconds!\nReact with ✅ to vote Yes, ❌ to vote No."

    if interaction:
        await interaction.response.send_message(vote_message)
        msg = await interaction.original_response()
    else:
        msg = await channel.send(vote_message)

    # Add reactions
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

    # Store vote details
    active_votes[msg.id] = {"user": user, "yes": 0, "no": 0, "duration": duration, "message": msg}

    def check(reaction, reactor):
        return reaction.message.id == msg.id and reaction.emoji in ["✅", "❌"] and not reactor.bot

    try:
        while True:
            reaction, reactor = await bot.wait_for("reaction_add", timeout=vote_duration, check=check)
            
            # Update vote counts
            if reaction.emoji == "✅":
                active_votes[msg.id]["yes"] += 1
            elif reaction.emoji == "❌":
                active_votes[msg.id]["no"] += 1

            # Check if vote threshold is met
            if active_votes[msg.id]["yes"] >= vote_threshold:
                try:
                    await user.timeout(timedelta(seconds=duration))
                    await channel.send(f"{user.mention} has been timed out for {duration} seconds. 💤")
                except discord.Forbidden:
                    await channel.send("I don't have permission to timeout this user.")
                
                # Cleanup
                del active_votes[msg.id]
                user_vote_cooldowns[user.id] = now
                return  # Ends the function immediately if the threshold is met

    except asyncio.TimeoutError:
        # Time ran out; vote failed
        await channel.send(f"Vote failed. {user.mention} will not be timed out.")
        del active_votes[msg.id]  # Cleanup

# Prefix command (!shutup)
@bot.command(name="shutup")
async def shutup(ctx, user: discord.Member, duration: int):
    """Starts a vote to timeout a user using a prefix command."""
    await start_vote(ctx.channel, ctx.author, user, duration)

# Slash command (/shutup)
@bot.tree.command(name="shutup", description="Start a vote to timeout a user.")
async def shutup_slash(interaction: discord.Interaction, user: discord.Member, duration: int):
    """Starts a vote to timeout a user using a slash command."""
    await start_vote(interaction.channel, interaction.user, user, duration, interaction)

bot.run(TOKEN)
