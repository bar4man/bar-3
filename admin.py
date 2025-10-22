import discord
from discord.ext import commands
import json
import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import aiofiles

class Admin(commands.Cog):
    """Enhanced administrative commands for bot management and moderation."""
    
    def __init__(self, bot):
        self.bot = bot
        self.log_channel_id: Optional[int] = None
        self.mod_actions: Dict[str, List[Dict]] = {}
        self._initialize_mod_logs()
    
    def _initialize_mod_logs(self):
        """Initialize moderation logs file."""
        if not os.path.exists("mod_logs.json"):
            with open("mod_logs.json", "w") as f:
                json.dump({}, f, indent=2)
    
    # -------------------- Permission System --------------------
    def is_admin(self, member: discord.Member) -> bool:
        """Check if member has admin permissions."""
        return (member.guild_permissions.administrator or 
                discord.utils.get(member.roles, name="bot-admin") is not None)
    
    def is_moderator(self, member: discord.Member) -> bool:
        """Check if member has moderator permissions."""
        return (self.is_admin(member) or
                discord.utils.get(member.roles, name="moderator") is not None)
    
    async def cog_check(self, ctx: commands.Context) -> bool:
        """Check permissions for all commands in this cog."""
        if not self.is_admin(ctx.author):
            embed = discord.Embed(
                title="🔒 Admin Only",
                description="This command requires the `bot-admin` role or Administrator permissions.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=10)
            return False
        return True
    
    async def log_mod_action(self, action: str, moderator: discord.Member, 
                           target: Optional[discord.Member] = None, 
                           reason: str = "No reason provided",
                           duration: Optional[str] = None) -> None:
        """Log moderation actions for audit purposes."""
        log_entry = {
            "action": action,
            "moderator": f"{moderator} (ID: {moderator.id})",
            "target": f"{target} (ID: {target.id})" if target else "N/A",
            "reason": reason,
            "duration": duration,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Save to file
        try:
            async with aiofiles.open("mod_logs.json", "r") as f:
                content = await f.read()
                logs = json.loads(content) if content else {}
        except (FileNotFoundError, json.JSONDecodeError):
            logs = {}
        
        guild_id = str(moderator.guild.id)
        if guild_id not in logs:
            logs[guild_id] = []
        
        logs[guild_id].append(log_entry)
        
        # Keep only last 1000 entries per guild
        if len(logs[guild_id]) > 1000:
            logs[guild_id] = logs[guild_id][-1000:]
        
        async with aiofiles.open("mod_logs.json", "w") as f:
            await f.write(json.dumps(logs, indent=2))
        
        # Send to log channel if set
        if self.log_channel_id:
            log_channel = self.bot.get_channel(self.log_channel_id)
            if log_channel:
                embed = self._create_mod_log_embed(log_entry)
                await log_channel.send(embed=embed)
    
    def _create_mod_log_embed(self, log_entry: Dict[str, Any]) -> discord.Embed:
        """Create an embed for moderation logs."""
        color = {
            "ban": discord.Color.red(),
            "kick": discord.Color.orange(),
            "mute": discord.Color.gold(),
            "warn": discord.Color.yellow(),
            "clear": discord.Color.blue()
        }.get(log_entry["action"], discord.Color.light_grey())
        
        embed = discord.Embed(
            title=f"🛡️ Moderation Action: {log_entry['action'].title()}",
            color=color,
            timestamp=datetime.fromisoformat(log_entry["timestamp"])
        )
        
        embed.add_field(name="Moderator", value=log_entry["moderator"], inline=False)
        embed.add_field(name="Target", value=log_entry["target"], inline=False)
        embed.add_field(name="Reason", value=log_entry["reason"], inline=False)
        
        if log_entry["duration"]:
            embed.add_field(name="Duration", value=log_entry["duration"], inline=False)
        
        return embed
    
    # -------------------- Enhanced Moderation Commands --------------------
    @commands.command(name="kick", brief="Kick a member from the server")
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Kick a member from the server with an optional reason."""
        try:
            # Check if we can kick the member
            if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="You cannot kick members with equal or higher roles.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            await member.kick(reason=f"Kicked by {ctx.author}: {reason}")
            
            # Log the action
            await self.log_mod_action("kick", ctx.author, member, reason)
            
            embed = discord.Embed(
                title="✅ Member Kicked",
                description=f"**{member}** has been kicked from the server.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
            
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have permission to kick members.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"Error kicking member: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to kick the member.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="ban", brief="Ban a member from the server")
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban a member from the server with an optional reason."""
        try:
            # Check if we can ban the member
            if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="You cannot ban members with equal or higher roles.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            await member.ban(reason=f"Banned by {ctx.author}: {reason}", delete_message_days=0)
            
            # Log the action
            await self.log_mod_action("ban", ctx.author, member, reason)
            
            embed = discord.Embed(
                title="✅ Member Banned",
                description=f"**{member}** has been banned from the server.",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
            
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have permission to ban members.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"Error banning member: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to ban the member.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="unban", brief="Unban a user from the server")
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "No reason provided"):
        """Unban a user from the server by their user ID."""
        try:
            user = discord.Object(id=user_id)
            await ctx.guild.unban(user, reason=f"Unbanned by {ctx.author}: {reason}")
            
            # Log the action
            await self.log_mod_action("unban", ctx.author, None, reason)
            
            embed = discord.Embed(
                title="✅ User Unbanned",
                description=f"User with ID `{user_id}` has been unbanned from the server.",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
            
            await ctx.send(embed=embed)
            
        except discord.NotFound:
            embed = discord.Embed(
                title="❌ User Not Banned",
                description="This user is not currently banned.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have permission to unban members.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"Error unbanning user: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to unban the user.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="mute", brief="Mute a member in the server")
    async def mute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Mute a member by removing their ability to send messages."""
        try:
            # Find or create muted role
            muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
            if not muted_role:
                # Create muted role
                muted_role = await ctx.guild.create_role(name="Muted", reason="Muted role for moderation")
                
                # Set permissions for all channels
                for channel in ctx.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False, speak=False)
            
            await member.add_roles(muted_role, reason=f"Muted by {ctx.author}: {reason}")
            
            # Log the action
            await self.log_mod_action("mute", ctx.author, member, reason)
            
            embed = discord.Embed(
                title="✅ Member Muted",
                description=f"**{member}** has been muted.",
                color=discord.Color.gold()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
            
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have permission to manage roles.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"Error muting member: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to mute the member.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="unmute", brief="Unmute a member in the server")
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Unmute a member by restoring their ability to send messages."""
        try:
            muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
            if not muted_role or muted_role not in member.roles:
                embed = discord.Embed(
                    title="❌ Not Muted",
                    description="This member is not currently muted.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            await member.remove_roles(muted_role, reason=f"Unmuted by {ctx.author}: {reason}")
            
            # Log the action
            await self.log_mod_action("unmute", ctx.author, member, reason)
            
            embed = discord.Embed(
                title="✅ Member Unmuted",
                description=f"**{member}** has been unmuted.",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
            
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have permission to manage roles.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"Error unmuting member: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to unmute the member.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    # -------------------- Enhanced Utility Commands --------------------
    @commands.command(name="clear", aliases=["purge", "clean"])
    async def clear(self, ctx: commands.Context, amount: int = 10):
        """Delete messages from channel with better filtering."""
        if amount <= 0 or amount > 100:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description="Please specify a number between 1 and 100.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
            return
        
        try:
            # Delete command message first
            await ctx.message.delete()
            
            # Delete messages
            deleted = await ctx.channel.purge(limit=amount)
            
            # Log the action
            await self.log_mod_action("clear", ctx.author, None, f"Cleared {len(deleted)} messages")
            
            # Send confirmation
            embed = discord.Embed(
                title="✅ Messages Cleared",
                description=f"Deleted **{len(deleted)}** messages.",
                color=discord.Color.green()
            )
            confirm = await ctx.send(embed=embed)
            await asyncio.sleep(3)
            await confirm.delete()
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have permission to delete messages in this channel.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
        except Exception as e:
            logging.error(f"Error clearing messages: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to delete messages.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
    
    @commands.command(name="clearuser", aliases=["purgeuser"])
    async def clear_user(self, ctx: commands.Context, member: discord.Member, amount: int = 10):
        """Delete messages from a specific user."""
        if amount <= 0 or amount > 100:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description="Please specify a number between 1 and 100.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
            return
        
        try:
            # Delete command message first
            await ctx.message.delete()
            
            # Check if we can delete messages
            def is_target_user(message):
                return message.author == member
            
            deleted = await ctx.channel.purge(limit=amount, check=is_target_user)
            
            # Log the action
            await self.log_mod_action("clear", ctx.author, member, f"Cleared {len(deleted)} messages from user")
            
            # Send confirmation
            embed = discord.Embed(
                title="✅ User Messages Cleared",
                description=f"Deleted **{len(deleted)}** messages from {member.mention}.",
                color=discord.Color.green()
            )
            confirm = await ctx.send(embed=embed)
            await asyncio.sleep(3)
            await confirm.delete()
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have permission to delete messages in this channel.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
        except Exception as e:
            logging.error(f"Error clearing user messages: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to delete messages.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
    
    # -------------------- Server Management --------------------
    @commands.command(name="setlogchannel", aliases=["logchannel"])
    async def set_log_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel for moderation logs."""
        channel = channel or ctx.channel
        self.log_channel_id = channel.id
        
        embed = discord.Embed(
            title="✅ Log Channel Set",
            description=f"Moderation logs will now be sent to {channel.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    
    @commands.command(name="serverinfo", aliases=["guildinfo"])
    async def serverinfo(self, ctx: commands.Context):
        """Display detailed server information."""
        guild = ctx.guild
        
        # Calculate various statistics
        online_members = sum(1 for m in guild.members if m.status != discord.Status.offline)
        bot_count = sum(1 for m in guild.members if m.bot)
        human_count = guild.member_count - bot_count
        
        # Role count (excluding @everyone)
        role_count = len(guild.roles) - 1
        
        # Server boost information
        boost_level = guild.premium_tier
        boost_count = guild.premium_subscription_count
        
        embed = discord.Embed(
            title=f"🏰 {guild.name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Server Information
        embed.add_field(name="🆔 Server ID", value=guild.id, inline=True)
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="📅 Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        
        # Member Statistics
        embed.add_field(name="👥 Total Members", value=guild.member_count, inline=True)
        embed.add_field(name="🟢 Online Members", value=online_members, inline=True)
        embed.add_field(name="🤖 Bots", value=bot_count, inline=True)
        
        # Channel Information
        embed.add_field(name="💬 Text Channels", value=len(guild.text_channels), inline=True)
        embed.add_field(name="🎧 Voice Channels", value=len(guild.voice_channels), inline=True)
        embed.add_field(name="📋 Categories", value=len(guild.categories), inline=True)
        
        # Other Information
        embed.add_field(name="🎭 Roles", value=role_count, inline=True)
        embed.add_field(name="🚀 Boosts", value=f"Level {boost_level} ({boost_count} boosts)", inline=True)
        embed.add_field(name="🔐 Verification", value=str(guild.verification_level).title(), inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="userinfo", aliases=["whois", "memberinfo"])
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        """Display detailed user information."""
        member = member or ctx.author
        
        # Calculate account age and server join age
        account_age = (datetime.now(timezone.utc) - member.created_at).days
        server_join_age = (datetime.now(timezone.utc) - member.joined_at).days if member.joined_at else 0
        
        # Get roles (excluding @everyone)
        roles = [role for role in member.roles if role.name != "@everyone"]
        roles.reverse()  # Show highest roles first
        
        embed = discord.Embed(
            title=f"👤 {member.display_name}",
            color=member.color,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Basic Information
        embed.add_field(name="🆔 User ID", value=member.id, inline=True)
        embed.add_field(name="📛 Username", value=f"{member.name}#{member.discriminator}", inline=True)
        embed.add_field(name="📅 Account Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        
        # Server Information
        embed.add_field(name="📥 Joined Server", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "Unknown", inline=True)
        embed.add_field(name="🕐 Account Age", value=f"{account_age} days", inline=True)
        embed.add_field(name="🕐 Server Age", value=f"{server_join_age} days", inline=True)
        
        # Status and Activity
        status_emoji = {
            discord.Status.online: "🟢",
            discord.Status.idle: "🟡", 
            discord.Status.dnd: "🔴",
            discord.Status.offline: "⚫"
        }
        embed.add_field(name="📱 Status", value=f"{status_emoji.get(member.status, '⚫')} {str(member.status).title()}", inline=True)
        
        # Roles
        if roles:
            roles_display = ", ".join([role.mention for role in roles[:5]])  # Show first 5 roles
            if len(roles) > 5:
                roles_display += f" ... and {len(roles) - 5} more"
            embed.add_field(name="🎭 Roles", value=roles_display, inline=False)
        else:
            embed.add_field(name="🎭 Roles", value="No roles", inline=False)
        
        # Permissions
        key_permissions = []
        if member.guild_permissions.administrator:
            key_permissions.append("Administrator")
        if member.guild_permissions.manage_guild:
            key_permissions.append("Manage Server")
        if member.guild_permissions.manage_roles:
            key_permissions.append("Manage Roles")
        if member.guild_permissions.manage_messages:
            key_permissions.append("Manage Messages")
            
        if key_permissions:
            embed.add_field(name="🔑 Key Permissions", value=", ".join(key_permissions), inline=False)
        
        await ctx.send(embed=embed)
    
    # -------------------- Bot Management --------------------
    @commands.command(name="reloadcogs", aliases=["cogreload"])
    async def reload_cogs(self, ctx: commands.Context):
        """Reload all bot cogs."""
        try:
            cogs = ["admin", "economy", "market", "gambling"]
            reloaded = []
            failed = []
            
            for cog in cogs:
                try:
                    await self.bot.reload_extension(cog)
                    reloaded.append(cog)
                except Exception as e:
                    failed.append(f"{cog}: {e}")
            
            embed = discord.Embed(
                title="🔄 Cog Reload Results",
                color=discord.Color.blue()
            )
            
            if reloaded:
                embed.add_field(name="✅ Reloaded", value=", ".join(reloaded), inline=False)
            if failed:
                embed.add_field(name="❌ Failed", value="\n".join(failed), inline=False)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error reloading cogs: {e}")
            embed = discord.Embed(
                title="❌ Reload Failed",
                description="An error occurred while reloading cogs.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="setstatus", aliases=["status"])
    async def set_status(self, ctx: commands.Context, *, status: str = None):
        """Change the bot's status."""
        if status:
            await self.bot.change_presence(activity=discord.Game(name=status))
            embed = discord.Embed(
                title="✅ Status Updated",
                description=f"Bot status changed to: **{status}**",
                color=discord.Color.green()
            )
        else:
            # Show current status
            current_activity = self.bot.activity
            status_text = current_activity.name if current_activity else "No activity set"
            
            embed = discord.Embed(
                title="🤖 Bot Status",
                color=discord.Color.blue()
            )
            embed.add_field(name="Current Activity", value=status_text, inline=False)
            embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=False)
            embed.add_field(name="Guilds", value=len(self.bot.guilds), inline=False)
            embed.add_field(name="Users", value=sum(g.member_count for g in self.bot.guilds), inline=False)
        
        await ctx.send(embed=embed)

    # -------------------- Economy Admin Commands --------------------
    @commands.command(name="economygive", aliases=["egive", "agive"])
    async def economy_give(self, ctx: commands.Context, member: discord.Member, amount: int):
        """Admin: Give money to a user's wallet."""
        economy_cog = self.bot.get_cog("Economy")
        if not economy_cog:
            embed = discord.Embed(
                title="❌ Economy System Unavailable",
                description="Economy cog is not loaded.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        try:
            await economy_cog.update_balance(member.id, wallet_change=amount)
            
            embed = discord.Embed(
                title="✅ Money Given",
                description=f"Gave {amount:,}£ to {member.mention}",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            
            # Log the action
            await self.log_mod_action("economy_give", ctx.author, member, f"Given {amount:,}£")
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error Giving Money",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="economytake", aliases=["etake", "atake"])
    async def economy_take(self, ctx: commands.Context, member: discord.Member, amount: int):
        """Admin: Take money from a user's wallet."""
        economy_cog = self.bot.get_cog("Economy")
        if not economy_cog:
            embed = discord.Embed(
                title="❌ Economy System Unavailable",
                description="Economy cog is not loaded.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        try:
            user_data = await economy_cog.get_user(member.id)
            taken = min(amount, user_data["wallet"])
            
            await economy_cog.update_balance(member.id, wallet_change=-taken)
            
            embed = discord.Embed(
                title="✅ Money Taken",
                description=f"Took {taken:,}£ from {member.mention}",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            
            await self.log_mod_action("economy_take", ctx.author, member, f"Taken {taken:,}£")
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error Taking Money",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="economyset", aliases=["eset", "aset"])
    async def economy_set(self, ctx: commands.Context, member: discord.Member, wallet: int = None, bank: int = None):
        """Admin: Set a user's wallet and/or bank balance."""
        if wallet is None and bank is None:
            embed = discord.Embed(
                title="❌ No Values Specified",
                description="Please specify at least one of: wallet amount, bank amount",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if (wallet is not None and wallet < 0) or (bank is not None and bank < 0):
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description="Amounts cannot be negative.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        economy_cog = self.bot.get_cog("Economy")
        if not economy_cog:
            embed = discord.Embed(
                title="❌ Economy System Unavailable",
                description="Economy cog is not loaded.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        try:
            user_data = await economy_cog.get_user(member.id)
            
            wallet_change = 0
            bank_change = 0
            
            if wallet is not None:
                wallet_change = wallet - user_data["wallet"]
            
            if bank is not None:
                bank_change = bank - user_data["bank"]
            
            await economy_cog.update_balance(member.id, wallet_change=wallet_change, bank_change=bank_change)
            
            embed = discord.Embed(
                title="✅ Balance Set",
                description=f"Updated {member.mention}'s balance",
                color=discord.Color.green()
            )
            
            if wallet is not None:
                embed.add_field(name="💵 Wallet", value=f"{wallet:,}£", inline=True)
            if bank is not None:
                embed.add_field(name="🏦 Bank", value=f"{bank:,}£", inline=True)
            
            await ctx.send(embed=embed)
            
            action_desc = f"Set wallet: {wallet}, bank: {bank}" if wallet and bank else f"Set wallet: {wallet}" if wallet else f"Set bank: {bank}"
            await self.log_mod_action("economy_set", ctx.author, member, action_desc)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error Setting Balance",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="economyreset", aliases=["ereset", "areset"])
    async def economy_reset(self, ctx: commands.Context, member: discord.Member):
        """Admin: Reset a user's entire economy data."""
        economy_cog = self.bot.get_cog("Economy")
        if not economy_cog:
            embed = discord.Embed(
                title="❌ Economy System Unavailable",
                description="Economy cog is not loaded.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        try:
            # Get the database from economy cog
            from economy import db
            
            if db.connected:
                # Reset user data in MongoDB
                reset_data = {
                    "wallet": 100,
                    "bank": 0,
                    "wallet_limit": 50000,
                    "bank_limit": 500000,
                    "networth": 100,
                    "daily_streak": 0,
                    "last_daily": None,
                    "total_earned": 0,
                    "created_at": datetime.now().isoformat(),
                    "last_active": datetime.now().isoformat()
                }
                
                await db.db.users.update_one(
                    {"user_id": member.id},
                    {"$set": reset_data}
                )
                
                # Remove inventory items
                await db.db.inventory.delete_many({"user_id": member.id})
                
                embed = discord.Embed(
                    title="✅ Economy Data Reset",
                    description=f"Reset all economy data for {member.mention}",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Database Not Connected",
                    description="Cannot reset data without database connection.",
                    color=discord.Color.red()
                )
            
            await ctx.send(embed=embed)
            await self.log_mod_action("economy_reset", ctx.author, member, "Reset all economy data")
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error Resetting Economy",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="economystats", aliases=["estats", "astats"])
    async def economy_stats(self, ctx: commands.Context):
        """Admin: View economy system statistics."""
        economy_cog = self.bot.get_cog("Economy")
        if not economy_cog:
            embed = discord.Embed(
                title="❌ Economy System Unavailable",
                description="Economy cog is not loaded.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        try:
            from economy import db
            stats = await db.get_stats()
            
            embed = discord.Embed(
                title="📊 Economy System Statistics",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(name="👥 Total Users", value=stats['total_users'], inline=True)
            embed.add_field(name="💰 Total Money in Circulation", value=f"{stats['total_money']:,}£", inline=True)
            embed.add_field(name="💾 Database", value=stats['database'], inline=True)
            
            # Calculate average wealth
            if stats['total_users'] > 0:
                avg_wealth = stats['total_money'] // stats['total_users']
                embed.add_field(name="📈 Average Wealth", value=f"{avg_wealth:,}£", inline=True)
            
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error Getting Stats",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))
