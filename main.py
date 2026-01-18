# main.py
import discord
from discord.ext import commands, tasks
import logging
from dotenv import load_dotenv
import os
import asyncio
import json
from datetime import datetime, timezone, timedelta
import webserver
import re
import aiofiles
from admin import is_bot_admin

# ---------------- Setup ----------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "true").lower() == "true"

# Enhanced logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("discord.log", encoding="utf-8", mode="a"),
        logging.StreamHandler()
    ]
)

# Discord intents with validation
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# ---------------- Security Constants ----------------
class SecurityConfig:
    SPAM_LIMIT = 5
    SPAM_TIMEFRAME = 5  # seconds
    MAX_TRACKED_USERS = 1000
    CLEANUP_INTERVAL = 60  # seconds

# ---------------- Manager Classes (Define FIRST) ----------------
class ConfigManager:
    def __init__(self, filename="config.json"):
        self.filename = filename
        self.default_config = {
            "auto_delete": {},
            "autorole": None,
            "grape_gifs": [],
            "member_numbers": {},
            "prefix": "~",
            "allowed_channels": [],
            "mod_log_channel": None
        }
        self._ensure_config_exists()
    
    def _ensure_config_exists(self):
        if not os.path.exists(self.filename):
            try:
                with open(self.filename, "w") as f:
                    json.dump(self.default_config, f, indent=2, ensure_ascii=False)
                logging.info(f"Created config: {self.filename}")
            except Exception as e:
                logging.error(f"Config creation error: {e}")
    
    async def load(self):
        try:
            async with aiofiles.open(self.filename, "r") as f:
                content = await f.read()
                config = json.loads(content)
            return {**self.default_config, **config}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"Config load error: {e}, using defaults")
            return self.default_config.copy()
    
    async def save(self, data):
        try:
            validated_data = {**self.default_config, **data}
            async with aiofiles.open(self.filename, "w") as f:
                await f.write(json.dumps(validated_data, indent=2, ensure_ascii=False))
            logging.info("Config saved")
            return True
        except Exception as e:
            logging.error(f"Config save error: {e}")
            return False

class MessageFilter:
    def __init__(self):
        self.spam_tracker = {}
        self.SPAM_TIMEFRAME = SecurityConfig.SPAM_TIMEFRAME
        self.SPAM_LIMIT = SecurityConfig.SPAM_LIMIT
        self._last_cleanup = datetime.now(timezone.utc).timestamp()
        self._cleanup_interval = SecurityConfig.CLEANUP_INTERVAL
        self._max_tracker_size = SecurityConfig.MAX_TRACKED_USERS
        self._cleanup_task = None
        logging.info("Message filter initialized")
    
    async def start_cleanup_task(self):
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    def stop_cleanup_task(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
    
    async def _periodic_cleanup(self):
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                self._cleanup_old_entries()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Cleanup error: {e}")
    
    def is_spam(self, user_id):
        now = datetime.now(timezone.utc).timestamp()
        
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_entries()
            self._last_cleanup = now
        
        if len(self.spam_tracker) > self._max_tracker_size:
            self._evict_oldest_entries()
        
        user_id_str = str(user_id)
        self.spam_tracker.setdefault(user_id_str, [])
        
        self.spam_tracker[user_id_str] = [
            t for t in self.spam_tracker[user_id_str] 
            if now - t < self.SPAM_TIMEFRAME
        ]
        
        self.spam_tracker[user_id_str].append(now)
        return len(self.spam_tracker[user_id_str]) > self.SPAM_LIMIT
    
    def _cleanup_old_entries(self):
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - 300
        
        users_to_remove = []
        for user_id, timestamps in self.spam_tracker.items():
            self.spam_tracker[user_id] = [t for t in timestamps if t > cutoff]
            if not self.spam_tracker[user_id]:
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self.spam_tracker[user_id]
        
        if users_to_remove:
            logging.debug(f"🧹 Cleaned up {len(users_to_remove)} users")
    
    def _evict_oldest_entries(self):
        if len(self.spam_tracker) <= self._max_tracker_size:
            return
        
        entries_to_remove = max(1, len(self.spam_tracker) // 10)
        user_last_activity = {uid: max(ts) if ts else 0 for uid, ts in self.spam_tracker.items()}
        sorted_users = sorted(user_last_activity.items(), key=lambda x: x[1])
        
        for user_id, _ in sorted_users[:entries_to_remove]:
            del self.spam_tracker[user_id]
        
        logging.info(f"Evicted {entries_to_remove} oldest entries")
    
    def _load_filter_data(self):
        """Load filter data from file with caching."""
        try:
            with open("filter.json", "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Create default filter file
            default_filter = {"blocked_links": [], "blocked_words": []}
            with open("filter.json", "w") as f:
                json.dump(default_filter, f, indent=2)
            return default_filter
    
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

# ---------------- Security Manager ----------------
class SecurityManager:
    def __init__(self):
        self.suspicious_patterns = [
            r"\b(admin|root|system)\b.*\b(password|passwd|pwd)\b",
            r"eval\s*\(|exec\s*\(|__import__|subprocess|os\.system",
            r"curl\s+|wget\s+|bash\s+|sh\s+|cmd\s+|powershell\s+",
            r"<script.*?>|javascript:|onload\s*=|onerror\s*=",
        ]
    
    def validate_input(self, input_str: str, max_length: int = 1000) -> bool:
        if not input_str or len(input_str) > max_length:
            return False
        for pattern in self.suspicious_patterns:
            if re.search(pattern, input_str, re.IGNORECASE):
                logging.warning(f"🚨 Suspicious input: {input_str[:100]}...")
                return False
        return True
    
    def sanitize_username(self, username: str) -> str:
        return re.sub(r'[<>"\'&]', '', username)[:32]
    
    def validate_amount(self, amount, max_amount=10_000_000):
        try:
            return 0 < int(amount) <= max_amount
        except (ValueError, TypeError):
            return False
    
    def sanitize_reason(self, reason: str, max_length: int = 500) -> str:
        if not reason:
            return "No reason provided"
        return reason.replace("sanitized = reason", "")[:max_length-3] + "..." if len(reason) > max_length else reason

# ---------------- Create Manager Instances ----------------
config_manager = ConfigManager()
message_filter = MessageFilter()
security_manager = SecurityManager()

# ---------------- Bot Class (Define AFTER managers) ----------------
class Bot(commands.Bot):
    """Custom bot class with additional utilities."""
    
    def __init__(self):
        super().__init__(
            command_prefix="~",
            intents=intents,
            help_command=None,
            case_insensitive=True
        )
        self.start_time = datetime.now(timezone.utc)
        self.config_manager = config_manager
        self.message_filter = message_filter
        self.security_manager = security_manager
    
    async def on_ready(self):
        """Enhanced on_ready with more detailed startup info."""
        logging.info(f"Bot ready: {self.user} ({self.user.id})")
        logging.info(f"📊 Connected to {len(self.guilds)} guild(s)")
        
        # Start cleanup task now that event loop is running
        await self.message_filter.start_cleanup_task()
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="~help | Economy & Bar"
            ),
            status=discord.Status.online
        )
    
    async def close(self):
        """Clean up when bot shuts down."""
        self.message_filter.stop_cleanup_task()
        await super().close()

# Create bot instance AFTER everything is defined
bot = Bot()

# Register bot with web server for status monitoring
try:
    import webserver
    webserver.set_bot(bot)
    logging.info("Bot registered with web server")
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
        error_embed.set_footer(text=f"Use ~help {ctx.command} for more info")
        
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
    """Enhanced message handler with better filtering and security."""
    if message.author.bot or isinstance(message.channel, discord.DMChannel):
        return
        
    # --- ADMIN BYPASS ---
    # Check if the author is a bot admin
    if is_bot_admin(message.author):
        # If they are an admin, just process commands and skip all filters
        await bot.process_commands(message)
        return
    # --- END BYPASS ---
    
    try:
        # Security validation
        if not bot.security_manager.validate_input(message.content):
            await message.delete()
            warning_msg = await message.channel.send(
                f"{message.author.mention}, that message contains suspicious content! 🚫",
                delete_after=5
            )
            return
        
        # Spam checking
        if bot.message_filter.is_spam(message.author.id):
            await message.delete()
            warning_msg = await message.channel.send(
                f"{message.author.mention}, slow down! ⏰ (Rate limit: {bot.message_filter.SPAM_LIMIT} messages per {bot.message_filter.SPAM_TIMEFRAME}s)",
                delete_after=5
            )
            return
        
        # Content filtering
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
            # FIX for offset-naive and offset-aware datetimes
            if msg.created_at.tzinfo is None:
                msg_time = msg.created_at.replace(tzinfo=timezone.utc)
            else:
                msg_time = msg.created_at
                
            age_seconds = (now - msg_time).total_seconds()
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
    """Main help command with categories. Use ~help admin or ~help economy."""
    if category and category.lower() in ["admin", "economy", "markets", "gambling", "bartender"]:
        await _show_category_help(ctx, category.lower())
    else:
        await _show_general_help(ctx)

async def _show_general_help(ctx: commands.Context):
    """Show general help with categorized commands."""
    embed = discord.Embed(
        title="🤖 Bot Help - Command Categories",
        description="Use `~help <category>` for specific command lists.\n\n**Available Categories:**",
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
            "**~help admin** - Moderation and server management\n"
            "**~help economy** - Money, work, and daily rewards\n"
            "**~help markets** - Stock market and gold trading\n"
            "**~help gambling** - Games and betting\n"
            "**~help bartender** - Bar and drinks system\n"
            "**~admin** - Direct admin commands\n"
            "**~economy** - Direct economy commands\n"
            "**~markets** - Direct market commands\n"
            "**~gambling** - Direct gambling commands\n"
            "**~bartender** - Direct bartender commands"
        ),
        inline=False
    )
    
    embed.add_field(
        name="💡 Quick Start",
        value=(
            "• Use `~economy` to see money commands\n"
            "• Use `~markets` for stock trading\n"
            "• Use `~gambling` for fun games\n"
            "• Use `~bartender` for drinks and bar\n"
            "• Use `~admin` for moderation tools\n"
            "• Most commands have cooldowns for balance"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"Use ~help <category> for detailed commands")
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
    elif category == "bartender":
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
        "`reload` - Reload all cogs",
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
        "`deposit <amount|all|max>` - Deposit to bank",
        "`withdraw <amount|all>` - Withdraw from bank",
        "`pay <member> <amount>` - Pay another user"
    ]
    
    embed.add_field(
        name="💵 Balance Management",
        value="\n".join(balance_cmds),
        inline=False
    )
    
    # Earning Commands
    earning_cmds = [
        "`daily` - Claim daily reward (24h cooldown)",
        "`work` - Work for money (30m cooldown)",
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
        "`upgrade <wallet/bank>` - Easily buy upgrades"
    ]
    
    embed.add_field(
        name="🛍️ Shop & Inventory",
        value="\n".join(shop_cmds),
        inline=False
    )
    
    embed.add_field(
        name="💡 Important Notes",
        value=(
            "• **Shop/Upgrades use BANK money**\n"
            "• **Payments/Games use WALLET money**\n"
            "• **Rewards go to your WALLET**\n"
            "• Use `~deposit` to keep your wallet safe!"
        ),
        inline=False
    )
    
    embed.set_footer(text="Rewards and limits have been increased!")
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
        "`gold` - View gold market information"
    ]
    
    embed.add_field(
        name="📊 Market Information",
        value="\n".join(info_cmds),
        inline=False
    )
    
    # Trading Commands
    trading_cmds = [
        "`buyinvest stock <symbol> <shares>` - Buy stock shares",
        "`buyinvest gold <ounces>` - Buy gold ounces", 
        "`sellinvest stock <symbol> <shares>` - Sell stock shares",
        "`sellinvest gold <ounces>` - Sell gold ounces"
    ]
    
    embed.add_field(
        name="💹 Trading Commands",
        value="\n".join(trading_cmds),
        inline=False
    )
    
    # Portfolio Management
    portfolio_cmds = [
        "`portfolio [member]` - View investment portfolio",
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
        value=f"**Symbols:** {stocks_list}\nUse `~stocks <symbol>` for details",
        inline=False
    )
    
    # Trading Information
    embed.add_field(
        name="💡 Trading Information",
        value=(
            "• **Market Hours:** 9 AM - 5 PM UTC\n"
            "• **All trades use BANK money**\n"
            "• **Limits are much higher!** (e.g., 50k stocks)"
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
    
    # --- MODIFIED: Updated help text for new games/features ---
    gambling_cmds = [
        "`cf <bet> [choice]` - Coinflip (60% win, 1.9x payout)",
        "`dice <bet>` - Dice game (Win on 3-6, up to 6x payout)",
        "`slots <bet>` - Slot machine (Better odds, 1.5x for two)",
        "`rps <bet> [choice]` - Rock Paper Scissors (2.2x win)",
        "`bj <bet>` - Play a game of Blackjack",
        "`lottery info` - View the current lottery",
        "`lottery buy <#> S` - Buy lottery tickets",
        "`beg` - Beg for money (50-150£)"
    ]
    
    embed.add_field(
        name="🎲 Gambling Games",
        value="\n".join(gambling_cmds),
        inline=False
    )
    
    embed.add_field(
        name="💡 Tips",
        value="• All games use WALLET money\n• Odds & payouts have been buffed!\n• Don't bet more than you can afford!",
        inline=True
    )
    
    embed.set_footer(text="Games have improved odds for better player experience!")
    await ctx.send(embed=embed)

async def _show_bartender_help(ctx: commands.Context):
    """Show bartender and bar commands."""
    embed = discord.Embed(
        title="🍸 Bartender & Bar Commands",
        description="Order drinks, manage your bar tab, and enjoy social drinking!",
        color=discord.Color.orange()
    )
    
    # Drinking Commands
    drinking_cmds = [
        "`~drink` - View drink menu or order a drink",
        "`~drink-menu` - Show detailed drink menu", 
        "`~drink-info <drink>` - Get info about a specific drink",
        "`~my-drinks [user]` - View your drink history and bar status",
        "`~sober-up` - Order water to sober up"
    ]
    
    embed.add_field(
        name="🍹 Drinking Commands",
        value="\n".join(drinking_cmds),
        inline=False
    )
    
    # Social Commands
    social_cmds = [
        "`~drink-buy <user> <drink>` - Buy a drink for someone",
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
            "• **Cooldowns are much shorter!**\n"
            "• **Sobering is 2x faster!**"
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

@bot.command(name="bartender")
async def bartender_help(ctx: commands.Context):
    """Direct bartender help command."""
    await _show_bartender_help(ctx)

# ---------------- Cog Loader ----------------
async def load_cogs():
    """Enhanced cog loader with dependency checking."""
    cogs = ["admin", "economy", "market", "gambling", "bartender"]
    loaded_count = 0
    
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logging.info(f"Loaded cog: {cog}")
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
    cogs = ["admin", "economy","market", "gambling", "bartender"]
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
    
    # Create necessary files in main directory
    required_files = {
        "config.json": json.dumps(config_manager.default_config, indent=2),
        "filter.json": json.dumps({"blocked_links": [], "blocked_words": []}, indent=2)
    }
    
    for filename, default_content in required_files.items():
        if not os.path.exists(filename):
            try:
                async with aiofiles.open(filename, "w") as f:
                    await f.write(default_content)
                logging.info(f"📁 Created {filename}")
            except Exception as e:
                logging.error(f"Failed to create {filename}: {e}")
    
    await load_cogs()
    auto_cleaner.start()
    
    logging.info("Setup hook completed")

# --- BUG FIX: Removed redundant on_ready event ---
# The on_ready logic is already handled inside the Bot class

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
            logging.info("Keep-alive web server initialized")
        else:
            logging.warning("❌ Keep-alive web server failed to start")
    except Exception as e:
        logging.error(f"❌ Keep-alive setup failed: {e}")

# ---------------- Run Bot ----------------
if __name__ == "__main__":
    if not TOKEN:
        logging.critical("❌ DISCORD_TOKEN environment variable not set")
        exit(1)
        
    try:
        logging.info("🚀 Starting bot...")
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logging.info("⏹️ Bot stopped by user")
    except discord.LoginFailure:
        logging.critical("❌ Invalid Discord token")
    except Exception as e:
        logging.critical(f"❌ Failed to start bot: {e}")
