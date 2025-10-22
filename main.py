import discord
from discord.ext import commands, tasks
import logging
from dotenv import load_dotenv
import os
import asyncio
import json
from datetime import datetime, timezone, timedelta
import webserver
import aiofiles

# ---------------- Setup ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "true").lower() == "true"

# Enhanced logging setup
def setup_logging():
    """Setup comprehensive logging with both file and console output."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # File handler
    file_handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="a")
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(levelname)s - %(name)s - %(message)s'
    ))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

setup_logging()

# Discord intents with validation
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# ---------------- Manager Classes (Define FIRST) ----------------
class ConfigManager:
    def __init__(self, filename="config.json"):
        self.filename = filename
        self.lock = asyncio.Lock()
        self.default_config = {
            "auto_delete": {},
            "autorole": None,
            "grape_gifs": [],
            "member_numbers": {},
            "prefix": "~~",
            "allowed_channels": [],
            "mod_log_channel": None
        }
        self._ensure_config_exists()
    
    def _ensure_config_exists(self):
        """Create config file with default structure if it doesn't exist."""
        if not os.path.exists(self.filename):
            with open(self.filename, "w") as f:
                json.dump(self.default_config, f, indent=2)
            logging.info(f"Created new config file: {self.filename}")
    
    async def load(self):
        """Load configuration from file with error recovery."""
        async with self.lock:
            try:
                with open(self.filename, "r") as f:
                    config = json.load(f)
                return {**self.default_config, **config}
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logging.error(f"Config load error: {e}, using defaults")
                return self.default_config.copy()
    
    async def save(self, data):
        """Save configuration to file with validation."""
        async with self.lock:
            try:
                validated_data = {**self.default_config, **data}
                with open(self.filename, "w") as f:
                    json.dump(validated_data, f, indent=2, ensure_ascii=False)
                logging.info("Config saved successfully")
                return True
            except Exception as e:
                logging.error(f"Config save error: {e}")
                return False

class MessageFilter:
    def __init__(self):
        self.spam_tracker = {}
        self.SPAM_TIMEFRAME = 5
        self.SPAM_LIMIT = 5
        self._last_cleanup = datetime.now(timezone.utc).timestamp()
    
    def _load_filter_data(self):
        """Load filter data from file with caching."""
        try:
            with open("filter.json", "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"blocked_links": [], "blocked_words": []}
    
    def is_spam(self, user_id):
        """Check if user is spamming with automatic cleanup."""
        now = datetime.now(timezone.utc).timestamp()
        
        # Cleanup old entries every 5 minutes
        if now - self._last_cleanup > 300:
            self._cleanup_old_entries()
            self._last_cleanup = now
        
        self.spam_tracker.setdefault(user_id, [])
        self.spam_tracker[user_id] = [
            t for t in self.spam_tracker[user_id] 
            if now - t < self.SPAM_TIMEFRAME
        ]
        
        self.spam_tracker[user_id].append(now)
        return len(self.spam_tracker[user_id]) > self.SPAM_LIMIT
    
    def _cleanup_old_entries(self):
        """Clean up old spam tracker entries to prevent memory leaks."""
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - 300
        self.spam_tracker = {
            user_id: timestamps 
            for user_id, timestamps in self.spam_tracker.items()
            if any(t > cutoff for t in timestamps)
        }
    
    def contains_blocked_content(self, content):
        """Check if message contains blocked words or links."""
        filter_data = self._load_filter_data()
        content_lower = content.lower()
        
        for word in filter_data.get("blocked_words", []):
            if word and word.lower() in content_lower:
                return True, "word"
        
        for link in filter_data.get("blocked_links", []):
            if link and link.lower() in content_lower:
                return True, "link"
        
        return False, None

# ---------------- Create Manager Instances ----------------
config_manager = ConfigManager()
message_filter = MessageFilter()

# ---------------- Bot Class (Define AFTER managers) ----------------
class Bot(commands.Bot):
    """Custom bot class with additional utilities."""
    
    def __init__(self):
        super().__init__(
            command_prefix="~~",
            intents=intents,
            help_command=None,
            case_insensitive=True
        )
        self.start_time = datetime.now(timezone.utc)
        # Now ConfigManager and MessageFilter are defined, so we can use them
        self.config_manager = config_manager
        self.message_filter = message_filter
    
    async def on_ready(self):
        """Enhanced on_ready with more detailed startup info."""
        logging.info(f"✅ Bot is ready as {self.user} (ID: {self.user.id})")
        logging.info(f"📊 Connected to {len(self.guilds)} guild(s)")
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="~~help | Economy & Bar"
            ),
            status=discord.Status.online
        )

# Create bot instance AFTER everything is defined
bot = Bot()

# Register bot with web server for status monitoring
try:
    import webserver
    webserver.set_bot(bot)
    logging.info("✅ Bot registered with web server for status monitoring")
except Exception as e:
    logging.warning(f"❌ Could not register bot with web server: {e}")

# ---------------- Error Handling ----------------
@bot.event
async def on_command_error(ctx, error):
    """Global error handler with enhanced error reporting."""
    if hasattr(ctx.command, 'on_error'):
        return
    
    error_embed = discord.Embed(color=discord.Color.red())
    
    if isinstance(error, commands.MissingRequiredArgument):
        error_embed.title = "❌ Missing Argument"
        error_embed.description = f"Missing required argument: `{error.param.name}`"
        error_embed.set_footer(text=f"Use ~~help {ctx.command} for more info")
        
    elif isinstance(error, commands.BadArgument):
        error_embed.title = "❌ Invalid Argument"
        error_embed.description = "Invalid argument type or member not found."
        
    elif isinstance(error, commands.CommandNotFound):
        return
        
    elif isinstance(error, commands.MissingPermissions):
        error_embed.title = "❌ Missing Permissions"
        error_embed.description = "You do not have permission to use this command."
        
    elif isinstance(error, commands.CommandOnCooldown):
        error_embed.title = "⏰ Cooldown Active"
        error_embed.description = f"Please wait **{error.retry_after:.1f}s** before using this command again."
        error_embed.color = discord.Color.orange()
        
    elif isinstance(error, commands.BotMissingPermissions):
        error_embed.title = "❌ Bot Missing Permissions"
        error_embed.description = f"I need these permissions: {', '.join(error.missing_permissions)}"
        
    elif isinstance(error, commands.NoPrivateMessage):
        error_embed.title = "❌ Guild Only Command"
        error_embed.description = "This command can only be used in servers."
        
    else:
        logging.error(f"Unexpected error in command {ctx.command}: {error}", exc_info=error)
        error_embed.title = "⚠️ Unexpected Error"
        error_embed.description = "An unexpected error occurred. The issue has been logged."
        error_embed.color = discord.Color.orange()
    
    try:
        await ctx.send(embed=error_embed, delete_after=10)
    except discord.Forbidden:
        pass

# ---------------- Message Filtering ----------------
@bot.event
async def on_message(message):
    """Enhanced message handler with better filtering."""
    if message.author.bot or isinstance(message.channel, discord.DMChannel):
        return
    
    try:
        if bot.message_filter.is_spam(message.author.id):
            await message.delete()
            warning_msg = await message.channel.send(
                f"{message.author.mention}, slow down! ⏰ (Rate limit: {bot.message_filter.SPAM_LIMIT} messages per {bot.message_filter.SPAM_TIMEFRAME}s)",
                delete_after=5
            )
            return
        
        is_blocked, block_type = bot.message_filter.contains_blocked_content(message.content)
        if is_blocked:
            await message.delete()
            if block_type == "word":
                msg = f"{message.author.mention}, that word is not allowed! 🚫"
            else:
                msg = f"{message.author.mention}, that link is not allowed! 🔗"
            await message.channel.send(msg, delete_after=5)
            return
            
    except discord.Forbidden:
        logging.warning(f"Missing permissions in channel {message.channel.id}")
    except Exception as e:
        logging.warning(f"Message filter error: {e}")
    
    await bot.process_commands(message)

# ---------------- Auto Cleaner Task ----------------
@tasks.loop(minutes=1)
async def auto_cleaner():
    """Enhanced auto cleaner with better error handling and logging."""
    try:
        config = await bot.config_manager.load()
        auto_delete_config = config.get("auto_delete", {})
        
        if not auto_delete_config:
            return
        
        cleaned_total = 0
        
        for channel_id, settings in auto_delete_config.items():
            if not settings.get("enabled", False):
                continue
            
            channel = bot.get_channel(int(channel_id))
            if not channel or not isinstance(channel, discord.TextChannel):
                continue
            
            try:
                deleted_count = await _clean_channel(channel, settings)
                cleaned_total += deleted_count
                
                if deleted_count > 0:
                    logging.info(f"Auto-cleaned {deleted_count} messages from #{channel.name}")
                    
            except discord.Forbidden:
                logging.warning(f"No permission to clean channel #{channel.name}")
            except Exception as e:
                logging.error(f"Error cleaning channel {channel.id}: {e}")
        
        if cleaned_total > 0:
            logging.info(f"Auto-cleaner completed: {cleaned_total} messages cleaned total")
            
    except Exception as e:
        logging.error(f"Auto cleaner task error: {e}")

async def _clean_channel(channel, settings):
    """Clean a single channel based on settings."""
    deleted_count = 0
    now = datetime.now(timezone.utc)
    
    try:
        messages = [msg async for msg in channel.history(limit=100, oldest_first=True)]
    except discord.Forbidden:
        raise
    
    max_age = settings.get("max_age")
    if max_age:
        for msg in messages:
            age_seconds = (now - msg.created_at).total_seconds()
            if age_seconds > max_age:
                try:
                    await msg.delete()
                    deleted_count += 1
                    await asyncio.sleep(0.5)
                except discord.NotFound:
                    pass
                except Exception as e:
                    logging.warning(f"Error deleting old message: {e}")
    
    max_messages = settings.get("max_messages")
    if max_messages and len(messages) > max_messages:
        to_delete = messages[:len(messages) - max_messages]
        for msg in to_delete:
            try:
                await msg.delete()
                deleted_count += 1
                await asyncio.sleep(0.5)
            except discord.NotFound:
                pass
            except Exception as e:
                logging.warning(f"Error deleting excess message: {e}")
    
    return deleted_count

@auto_cleaner.before_loop
async def before_auto_cleaner():
    """Wait for bot to be ready before starting auto cleaner."""
    await bot.wait_until_ready()

# ---------------- Enhanced Help System ----------------
@bot.command(name="help")
async def help_command(ctx: commands.Context, category: str = None):
    """Main help command with categories. Use ~~help admin or ~~help economy."""
    if category and category.lower() in ["admin", "economy", "markets", "gambling", "bartender"]:
        await _show_category_help(ctx, category.lower())
    else:
        await _show_general_help(ctx)

async def _show_general_help(ctx: commands.Context):
    """Show general help with categorized commands."""
    embed = discord.Embed(
        title="🤖 Bot Help - Command Categories",
        description="Use `~~help <category>` for specific command lists.\n\n**Available Categories:**",
        color=discord.Color.blue()
    )
    
    # General Commands
    general_commands = [
        "`help` - Shows this message",
        "`ping` - Check bot latency",
        "`hello` - Say hello to the bot"
    ]
    
    embed.add_field(
        name="🔧 General Commands",
        value="\n".join(general_commands),
        inline=False
    )
    
    # Category Overview
    embed.add_field(
        name="📁 Command Categories",
        value=(
            "**~~help admin** - Moderation and server management\n"
            "**~~help economy** - Money, work, and daily rewards\n"
            "**~~help markets** - Stock market and gold trading\n"
            "**~~help gambling** - Games and betting\n"
            "**~~help bartender** - Bar and drinks system\n"  # ← NEW CATEGORY
            "**~~admin** - Direct admin commands\n"
            "**~~economy** - Direct economy commands\n"
            "**~~markets** - Direct market commands\n"
            "**~~gambling** - Direct gambling commands\n"
            "**~~bartender** - Direct bartender commands"  # ← NEW COMMAND
        ),
        inline=False
    )
    
    embed.add_field(
        name="💡 Quick Start",
        value=(
            "• Use `~~economy` to see money commands\n"
            "• Use `~~markets` for stock trading\n"
            "• Use `~~gambling` for fun games\n"
            "• Use `~~bartender` for drinks and bar\n"  # ← NEW LINE
            "• Use `~~admin` for moderation tools\n"
            "• Most commands have cooldowns for balance"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"Use ~~help <category> for detailed commands")
    await ctx.send(embed=embed)

async def _show_category_help(ctx: commands.Context, category: str):
    """Show help for a specific category."""
    if category == "admin":
        await _show_admin_help(ctx)
    elif category == "economy":
        await _show_economy_help(ctx)
    elif category == "markets":
        await _show_markets_help(ctx)
    elif category == "gambling":
        await _show_gambling_help(ctx)
    elif category == "bartender":  # ← NEW CATEGORY
        await _show_bartender_help(ctx)

async def _show_admin_help(ctx: commands.Context):
    """Show admin/moderation commands."""
    embed = discord.Embed(
        title="🛡️ Admin & Moderation Commands",
        description="Server management and moderation tools. Requires admin permissions.",
        color=discord.Color.red()
    )
    
    # Moderation Commands
    moderation_cmds = [
        "`kick <member> [reason]` - Kick a member",
        "`ban <member> [reason]` - Ban a member", 
        "`unban <user_id> [reason]` - Unban a user",
        "`mute <member> [reason]` - Mute a member",
        "`unmute <member> [reason]` - Unmute a member",
        "`clear <amount>` - Delete messages (1-100)",
        "`clearuser <member> <amount>` - Delete user messages"
    ]
    
    embed.add_field(
        name="🔨 Moderation",
        value="\n".join(moderation_cmds),
        inline=False
    )
    
    # Utility Commands
    utility_cmds = [
        "`serverinfo` - Show server information",
        "`userinfo [member]` - Show user information",
        "`setlogchannel [channel]` - Set mod log channel"
    ]
    
    embed.add_field(
        name="📊 Utility",
        value="\n".join(utility_cmds),
        inline=False
    )
    
    # Bot Management
    bot_cmds = [
        "`reloadcogs` - Reload all cogs",
        "`setstatus <status>` - Change bot status"
    ]
    
    embed.add_field(
        name="⚙️ Bot Management",
        value="\n".join(bot_cmds),
        inline=False
    )
    
    # Economy Admin Commands
    economy_admin = [
        "`economygive <member> <amount>` - Give money to user",
        "`economytake <member> <amount>` - Take money from user", 
        "`economyset <member> <wallet> <bank>` - Set user balance",
        "`economyreset <member>` - Reset user economy data",
        "`economystats` - View economy statistics"
    ]
    
    embed.add_field(
        name="💰 Economy Admin",
        value="\n".join(economy_admin),
        inline=False
    )
    
    embed.set_footer(text="Admin commands require bot-admin role or Administrator permissions")
    await ctx.send(embed=embed)

async def _show_economy_help(ctx: commands.Context):
    """Show economy and game commands."""
    embed = discord.Embed(
        title="💰 Economy Commands", 
        description="Money management, work, and daily rewards.",
        color=discord.Color.gold()
    )
    
    # Balance Management
    balance_cmds = [
        "`balance [member]` - Check balance",
        "`wallet [member]` - Check wallet only", 
        "`bank [member]` - Check bank only",
        "`networth [member]` - Check total net worth",
        "`deposit <amount|all|max>` - Deposit to bank",
        "`withdraw <amount|all>` - Withdraw from bank",
        "`upgrade <wallet/bank>` - Upgrade limits"
    ]
    
    embed.add_field(
        name="💵 Balance Management",
        value="\n".join(balance_cmds),
        inline=False
    )
    
    # Earning Commands
    earning_cmds = [
        "`daily` - Claim daily reward (24h cooldown)",
        "`work` - Work for money (1h cooldown)",
        "`beg` - Beg for small amounts of money (5min cooldown)"
    ]
    
    embed.add_field(
        name="💼 Earning Money",
        value="\n".join(earning_cmds),
        inline=False
    )
    
    # Shop & Inventory
    shop_cmds = [
        "`shop` - Browse the shop",
        "`buy <item_id>` - Purchase an item", 
        "`inventory` - View your inventory",
        "`use <item_id>` - Use an item",
        "`pay <member> <amount>` - Pay another user"
    ]
    
    embed.add_field(
        name="🛍️ Shop & Inventory",
        value="\n".join(shop_cmds),
        inline=False
    )
    
    embed.add_field(
        name="💡 Important Notes",
        value=(
            "• **Shop purchases use BANK money**\n"
            "• **Payments use WALLET money**\n"
            "• **Excess money is LOST** if over limits\n"
            "• **Penalty:** Lose 1£ for impossible deposits\n"
            "• Use `~~deposit` to move money to bank\n"
            "• Use `~~withdraw` to get money from bank"
        ),
        inline=False
    )
    
    embed.set_footer(text="Most commands have cooldowns - check individual command help")
    await ctx.send(embed=embed)

async def _show_markets_help(ctx: commands.Context):
    """Show market and trading commands."""
    embed = discord.Embed(
        title="🏛️ Market & Trading Commands",
        description="Stock market, gold trading, and investment portfolio management.",
        color=discord.Color.green()
    )
    
    # Market Information
    info_cmds = [
        "`market` - View current market status",
        "`stocks [symbol]` - View stock information",
        "`gold` - View gold market information",
        "`news` - View market news and events",
        "`topmovers` - View today's biggest stock movements"
    ]
    
    embed.add_field(
        name="📊 Market Information",
        value="\n".join(info_cmds),
        inline=False
    )
    
    # Trading Commands
    trading_cmds = [
        "`buy stock <symbol> <shares>` - Buy stock shares",
        "`buy gold <ounces>` - Buy gold ounces", 
        "`sell stock <symbol> <shares>` - Sell stock shares",
        "`sell gold <ounces>` - Sell gold ounces"
    ]
    
    embed.add_field(
        name="💹 Trading Commands",
        value="\n".join(trading_cmds),
        inline=False
    )
    
    # Portfolio Management
    portfolio_cmds = [
        "`portfolio [member]` - View investment portfolio",
        "`port [member]` - Shortcut for portfolio"
    ]
    
    embed.add_field(
        name="💼 Portfolio Management",
        value="\n".join(portfolio_cmds),
        inline=False
    )
    
    # Available Stocks
    stocks_list = "TECH, ENERGY, BANK, PHARMA, AUTO"
    embed.add_field(
        name="📈 Available Stocks",
        value=f"**Symbols:** {stocks_list}\nUse `~~stocks <symbol>` for details",
        inline=False
    )
    
    # Trading Information
    embed.add_field(
        name="💡 Trading Information",
        value=(
            "• **Market Hours:** 9 AM - 5 PM UTC\n"
            "• **Stock Fees:** 0.5% per transaction\n"
            "• **Gold Fees:** 1% per transaction\n"
            "• **Funding:** All trades use BANK money\n"
            "• **Portfolio:** Track your investments with `~~portfolio`"
        ),
        inline=False
    )
    
    embed.set_footer(text="Market prices update every 5 minutes during trading hours")
    await ctx.send(embed=embed)

async def _show_gambling_help(ctx: commands.Context):
    """Show gambling and game commands."""
    embed = discord.Embed(
        title="🎰 Gambling & Games Commands",
        description="Fun games with improved odds and rewards!",
        color=discord.Color.purple()
    )
    
    # Gambling Games
    gambling_cmds = [
        "`flip <heads/tails> <bet>` - Coin flip (55% win chance, 1.8x payout)",
        "`dice <bet>` - Dice game (50% win chance, multiple payouts)",
        "`slots <bet>` - Slot machine (better odds, two-matching wins)",
        "`rps <rock/paper/scissors> <bet>` - Rock Paper Scissors (2x win, tie returns bet)",
        "`beg` - Beg for money (5min cooldown)"
    ]
    
    embed.add_field(
        name="🎲 Gambling Games",
        value="\n".join(gambling_cmds),
        inline=False
    )
    
    # Game Details
    embed.add_field(
        name="💰 Coin Flip",
        value="**Win Chance:** 55%\n**Payout:** 1.8x your bet\n**Cooldown:** 3 seconds",
        inline=True
    )
    
    embed.add_field(
        name="🎯 Dice Game", 
        value="**Winning Numbers:** 4, 5, 6\n**Payouts:** 1.5x, 2x, 5x\n**Cooldown:** 4 seconds",
        inline=True
    )
    
    embed.add_field(
        name="🎰 Slots",
        value="**Three Matching:** Up to 30x\n**Two Matching:** 1.2x\n**Cooldown:** 5 seconds",
        inline=True
    )
    
    embed.add_field(
        name="✂️ Rock Paper Scissors",
        value="**Win:** 2x your bet\n**Tie:** Return your bet\n**Lose:** Lose your bet\n**Cooldown:** 3 seconds",
        inline=True
    )
    
    embed.add_field(
        name="🙏 Begging",
        value="**Amount:** 10-70£ randomly\n**Cooldown:** 5 minutes\n**Success Rate:** High",
        inline=True
    )
    
    embed.add_field(
        name="💡 Tips",
        value="• All games use WALLET money\n• Items can boost your chances\n• Don't bet more than you can afford!",
        inline=True
    )
    
    embed.set_footer(text="Games have improved odds for better player experience!")
    await ctx.send(embed=embed)

async def _show_bartender_help(ctx: commands.Context):  # ← NEW HELP CATEGORY
    """Show bartender and bar commands."""
    embed = discord.Embed(
        title="🍸 Bartender & Bar Commands",
        description="Order drinks, manage your bar tab, and enjoy social drinking!",
        color=discord.Color.orange()
    )
    
    # Drinking Commands
    drinking_cmds = [
        "`drink` - View drink menu or order a drink",
        "`drinkmenu` - Show detailed drink menu", 
        "`drinkinfo <drink>` - Get info about a specific drink",
        "`mydrinks [user]` - View your drink history and bar status",
        "`soberup` - Order water to sober up"
    ]
    
    embed.add_field(
        name="🍹 Drinking Commands",
        value="\n".join(drinking_cmds),
        inline=False
    )
    
    # Social Commands
    social_cmds = [
        "`drink buy <user> <drink>` - Buy a drink for someone",
        "`toast` - Start a group toast (coming soon)",
        "`cheers` - Cheer with everyone (coming soon)"
    ]
    
    embed.add_field(
        name="🎉 Social Features",
        value="\n".join(social_cmds),
        inline=False
    )
    
    # Bar Information
    embed.add_field(
        name="💡 Bar Information",
        value=(
            "• **All drinks use WALLET money**\n"
            "• **Drink prices:** 20-500£\n"
            "• **Tipsy meter:** Tracks your intoxication\n"
            "• **Water helps sober up**\n"
            "• **Try different drinks** to build your collection!"
        ),
        inline=False
    )
    
    embed.set_footer(text="🍻 Drink responsibly and have fun!")
    await ctx.send(embed=embed)

# ---------------- New Category Help Commands ----------------
@bot.command(name="admin")
async def admin_help(ctx: commands.Context):
    """Direct admin help command."""
    await _show_admin_help(ctx)

@bot.command(name="economy")
async def economy_help(ctx: commands.Context):
    """Direct economy help command."""
    await _show_economy_help(ctx)

@bot.command(name="markets")
async def markets_help(ctx: commands.Context):
    """Direct markets help command."""
    await _show_markets_help(ctx)

@bot.command(name="gambling")
async def gambling_help(ctx: commands.Context):
    """Direct gambling help command."""
    await _show_gambling_help(ctx)

@bot.command(name="bartender")  # ← NEW DIRECT COMMAND
async def bartender_help(ctx: commands.Context):
    """Direct bartender help command."""
    await _show_bartender_help(ctx)

# ---------------- Cog Loader ----------------
async def load_cogs():
    """Enhanced cog loader with dependency checking."""
    cogs = ["admin", "economy", "market", "gambling", "bartender"]  # ← ADDED "bartender"
    loaded_count = 0
    
    for cog in cogs:
        try:
            if cog == "economy":
                try:
                    import aiofiles
                    logging.info("✅ aiofiles dependency available for economy system")
                except ImportError:
                    logging.error("❌ aiofiles not installed. Economy features will be limited.")
                    continue
            
            await bot.load_extension(cog)
            logging.info(f"✅ Loaded cog: {cog}")
            loaded_count += 1
            
        except commands.ExtensionNotFound:
            logging.error(f"❌ Cog not found: {cog}")
        except commands.ExtensionFailed as e:
            logging.error(f"❌ Cog failed to load {cog}: {e}")
        except Exception as e:
            logging.error(f"❌ Unexpected error loading cog {cog}: {e}")
    
    logging.info(f"📊 Cogs loaded: {loaded_count}/{len(cogs)}")

async def reload_cogs():
    """Reload all cogs."""
    cogs = ["admin", "economy", "market", "gambling", "bartender"]  # ← ADDED "bartender"
    for cog in cogs:
        try:
            await bot.reload_extension(cog)
            logging.info(f"🔄 Reloaded cog: {cog}")
        except Exception as e:
            logging.error(f"❌ Failed to reload cog {cog}: {e}")

# ---------------- Bot Events ----------------
@bot.event
async def setup_hook():
    """Enhanced setup hook with data directory initialization."""
    logging.info("🔧 Starting bot setup...")
    
    os.makedirs("data", exist_ok=True)
    logging.info("📁 Data directory initialized")
    
    await load_cogs()
    auto_cleaner.start()
    
    logging.info("✅ Setup hook completed")

@bot.event
async def on_ready():
    """Enhanced on_ready with more detailed startup info."""
    logging.info(f"✅ Bot is ready as {bot.user} (ID: {bot.user.id})")
    logging.info(f"📊 Connected to {len(bot.guilds)} guild(s)")
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="~~help | Economy & Bar"  # ← UPDATED STATUS
        ),
        status=discord.Status.online
    )

@bot.event
async def on_guild_join(guild):
    """Log when bot joins a new guild."""
    logging.info(f"➕ Joined guild: {guild.name} (ID: {guild.id}) with {guild.member_count} members")

@bot.event
async def on_guild_remove(guild):
    """Log when bot leaves a guild."""
    logging.info(f"➖ Left guild: {guild.name} (ID: {guild.id})")

# ---------------- Utility Commands ----------------
@bot.command(name="ping", brief="Check bot latency")
async def ping(ctx):
    """Check the bot's latency and response time."""
    start_time = ctx.message.created_at
    msg = await ctx.send("🏓 Pinging...")
    end_time = msg.created_at
    
    bot_latency = round(bot.latency * 1000)
    response_time = round((end_time - start_time).total_seconds() * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        color=discord.Color.green()
    )
    embed.add_field(name="Bot Latency", value=f"{bot_latency}ms", inline=True)
    embed.add_field(name="Response Time", value=f"{response_time}ms", inline=True)
    
    await msg.edit(content=None, embed=embed)

@bot.command(name="reload", brief="Reload all cogs")
@commands.has_permissions(administrator=True)
async def reload(ctx):
    """Reload all cogs (Admin only)."""
    msg = await ctx.send("🔄 Reloading cogs...")
    await reload_cogs()
    await msg.edit(content="✅ All cogs reloaded successfully!")

@bot.command(name="hello")
async def hello(ctx):
    """Say hello to the bot"""
    await ctx.send(f'Hello {ctx.author.mention}! 👋')

# ---------------- Keep Alive ----------------
if KEEP_ALIVE:
    try:
        import webserver
        success = webserver.keep_alive()
        if success:
            logging.info("✅ Keep-alive web server initialized")
        else:
            logging.warning("❌ Keep-alive web server failed to start")
    except Exception as e:
        logging.error(f"❌ Keep-alive setup failed: {e}")

# ---------------- Run Bot ----------------
if __name__ == "__main__":
    try:
        logging.info("🚀 Starting bot...")
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logging.info("⏹️ Bot stopped by user")
    except discord.LoginFailure:
        logging.critical("❌ Invalid Discord token")
    except Exception as e:
        logging.critical(f"❌ Failed to start bot: {e}")
