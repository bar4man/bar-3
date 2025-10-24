import discord
from discord.ext import commands
import json
import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import aiofiles

# ---------------- Security Constants ----------------
class AdminConfig:
    # Role names for permission system
    ADMIN_ROLE_NAME = "bot-admin"
    MOD_ROLE_NAME = "moderator"
    MUTED_ROLE_NAME = "Muted"
    
    # Security settings
    MAX_CLEAR_MESSAGES = 100
    MIN_CLEAR_MESSAGES = 1
    CLEAR_CONFIRMATION_TIMEOUT = 3
    
    # Moderation limits
    MAX_REASON_LENGTH = 1000
    MAX_BAN_REASON_LENGTH = 512  # Discord limit

# ---------------- Security Manager for Admin ----------------
class AdminSecurityManager:
    """Security manager for admin commands with enhanced validation."""
    
    def __init__(self):
        self.suspicious_actions = {}
        self.action_cooldowns = {}
    
    async def can_moderate_member(self, ctx: commands.Context, target: discord.Member, action: str) -> tuple[bool, str]:
        """Check if moderator can take action on target member."""
        # Cannot moderate self
        if target == ctx.author:
            return False, "You cannot moderate yourself."
        
        # Cannot moderate the bot
        if target == ctx.guild.me:
            return False, "You cannot moderate the bot."
        
        # Cannot moderate server owner
        if target == ctx.guild.owner:
            return False, "You cannot moderate the server owner."
        
        # Check if target is a bot (with exceptions)
        if target.bot and action not in ["kick", "ban"]:  # Allow kicking/banning bots
            return False, "You cannot moderate bots with this action."
        
        # Check role hierarchy - moderator must have higher role than target
        if ctx.author.top_role <= target.top_role and ctx.author != ctx.guild.owner:
            return False, "You cannot moderate members with equal or higher roles."
        
        # Check if bot has higher role than target
        if ctx.guild.me.top_role <= target.top_role:
            return False, "I don't have a high enough role to moderate this member."
        
        # Check if bot has necessary permissions
        bot_permissions = ctx.channel.permissions_for(ctx.guild.me)
        required_permissions = self._get_required_permissions(action)
        
        missing_permissions = [perm for perm in required_permissions if not getattr(bot_permissions, perm)]
        if missing_permissions:
            return False, f"I'm missing required permissions: {', '.join(missing_permissions)}"
        
        # Rate limiting check
        if not await self._check_action_cooldown(ctx.author.id, action):
            return False, "You're performing this action too frequently. Please wait a moment."
        
        return True, "OK"
    
    def _get_required_permissions(self, action: str) -> List[str]:
        """Get required permissions for each moderation action."""
        permissions_map = {
            "kick": ["kick_members"],
            "ban": ["ban_members"],
            "unban": ["ban_members"],
            "mute": ["manage_roles"],
            "unmute": ["manage_roles"],
            "clear": ["manage_messages", "read_message_history"],
            "clearuser": ["manage_messages", "read_message_history"]
        }
        return permissions_map.get(action, [])
    
    async def _check_action_cooldown(self, user_id: int, action: str) -> bool:
        """Check if user is spamming moderation commands."""
        now = datetime.now(timezone.utc).timestamp()
        key = f"{user_id}_{action}"
        
        if key in self.action_cooldowns:
            last_time = self.action_cooldowns[key]
            # 5 second cooldown for moderation actions
            if now - last_time < 5:
                return False
        
        self.action_cooldowns[key] = now
        return True
    
    def validate_reason(self, reason: str, max_length: int = AdminConfig.MAX_REASON_LENGTH) -> tuple[bool, str]:
        """Validate moderation reason for security."""
        if not reason or reason.strip() == "":
            return True, "No reason provided"  # Default reason is OK
        
        if len(reason) > max_length:
            return False, f"Reason too long (max {max_length} characters)"
        
        # Check for potentially dangerous content
        dangerous_patterns = [
            "```", "`", "@everyone", "@here", "http://", "https://", "discord.gg/"
        ]
        
        for pattern in dangerous_patterns:
            if pattern in reason.lower():
                return False, "Reason contains potentially dangerous content"
        
        return True, reason
    
    async def log_suspicious_action(self, ctx: commands.Context, action: str, target: Optional[discord.Member] = None, details: str = ""):
        """Log suspicious moderation actions for audit."""
        log_entry = {
            "action": action,
            "moderator": f"{ctx.author} (ID: {ctx.author.id})",
            "target": f"{target} (ID: {target.id})" if target else "N/A",
            "channel": f"{ctx.channel} (ID: {ctx.channel.id})",
            "guild": f"{ctx.guild.name} (ID: {ctx.guild.id})",
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logging.warning(f"🚨 Suspicious admin action: {log_entry}")

class Admin(commands.Cog):
    """Enhanced administrative commands for bot management and moderation."""
    
    def __init__(self, bot):
        self.bot = bot
        self.log_channel_id: Optional[int] = None
        self.mod_actions: Dict[str, List[Dict]] = {}
        self.security_manager = AdminSecurityManager()
        self._initialize_mod_logs()
    
    def _initialize_mod_logs(self):
        """Initialize moderation logs file."""
        if not os.path.exists("mod_logs.json"):
            with open("mod_logs.json", "w") as f:
                json.dump({}, f, indent=2)
    
    # -------------------- Enhanced Permission System --------------------
    def is_admin(self, member: discord.Member) -> bool:
        """Check if member has admin permissions with enhanced security."""
        # Server administrators always have access
        if member.guild_permissions.administrator:
            return True
        
        # Check for bot-admin role
        bot_admin_role = discord.utils.get(member.roles, name=AdminConfig.ADMIN_ROLE_NAME)
        if bot_admin_role:
            return True
        
        # Server owner always has access
        if member == member.guild.owner:
            return True
        
        return False
    
    def is_moderator(self, member: discord.Member) -> bool:
        """Check if member has moderator permissions."""
        # Admins are automatically moderators
        if self.is_admin(member):
            return True
        
        # Check for moderator role
        moderator_role = discord.utils.get(member.roles, name=AdminConfig.MOD_ROLE_NAME)
        if moderator_role:
            return True
        
        # Check for specific moderation permissions
        required_permissions = ["kick_members", "ban_members", "manage_messages"]
        member_permissions = member.guild_permissions
        
        has_mod_permissions = any(getattr(member_permissions, perm) for perm in required_permissions)
        if has_mod_permissions:
            return True
        
        return False
    
    async def cog_check(self, ctx: commands.Context) -> bool:
        """Enhanced permission check for all commands in this cog."""
        if not self.is_admin(ctx.author):
            embed = discord.Embed(
                title="🔒 Admin Only",
                description=f"This command requires the `{AdminConfig.ADMIN_ROLE_NAME}` role or Administrator permissions.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=10)
            return False
        
        # Additional security: Check if command is being used in a guild
        if not ctx.guild:
            embed = discord.Embed(
                title="❌ Guild Only",
                description="This command can only be used in servers.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=10)
            return False
        
        return True
    
    async def log_mod_action(self, action: str, moderator: discord.Member, 
                           target: Optional[discord.Member] = None, 
                           reason: str = "No reason provided",
                           duration: Optional[str] = None) -> None:
        """Enhanced moderation action logging with security checks."""
        # Validate reason
        is_valid_reason, valid_reason = self.security_manager.validate_reason(reason)
        if not is_valid_reason:
            valid_reason = "Invalid reason provided - security filter activated"
        
        log_entry = {
            "action": action,
            "moderator": f"{moderator} (ID: {moderator.id})",
            "target": f"{target} (ID: {target.id})" if target else "N/A",
            "reason": valid_reason,
            "duration": duration,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "guild": f"{moderator.guild.name} (ID: {moderator.guild.id})"
        }
        
        # Save to file with error handling
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
        
        # Save with error handling
        try:
            async with aiofiles.open("mod_logs.json", "w") as f:
                await f.write(json.dumps(logs, indent=2))
        except Exception as e:
            logging.error(f"Failed to save mod logs: {e}")
        
        # Send to log channel if set
        if self.log_channel_id:
            await self._send_log_to_channel(log_entry)
    
    async def _send_log_to_channel(self, log_entry: Dict[str, Any]):
        """Send moderation log to designated channel with error handling."""
        try:
            log_channel = self.bot.get_channel(self.log_channel_id)
            if log_channel and isinstance(log_channel, discord.TextChannel):
                embed = self._create_mod_log_embed(log_entry)
                await log_channel.send(embed=embed)
        except discord.Forbidden:
            logging.warning(f"Missing permissions to send logs to channel {self.log_channel_id}")
        except Exception as e:
            logging.error(f"Failed to send log to channel: {e}")
    
    def _create_mod_log_embed(self, log_entry: Dict[str, Any]) -> discord.Embed:
        """Create an embed for moderation logs with security formatting."""
        color = {
            "ban": discord.Color.red(),
            "kick": discord.Color.orange(),
            "mute": discord.Color.gold(),
            "warn": discord.Color.yellow(),
            "clear": discord.Color.blue(),
            "unban": discord.Color.green(),
            "unmute": discord.Color.green()
        }.get(log_entry["action"], discord.Color.light_grey())
        
        embed = discord.Embed(
            title=f"🛡️ Moderation Action: {log_entry['action'].title()}",
            color=color,
            timestamp=datetime.fromisoformat(log_entry["timestamp"])
        )
        
        # Safely format fields to avoid abuse
        embed.add_field(name="Moderator", value=log_entry["moderator"], inline=False)
        embed.add_field(name="Target", value=log_entry["target"], inline=False)
        
        # Truncate long reasons
        reason = log_entry["reason"]
        if len(reason) > 256:
            reason = reason[:253] + "..."
        embed.add_field(name="Reason", value=reason, inline=False)
        
        if log_entry["duration"]:
            embed.add_field(name="Duration", value=log_entry["duration"], inline=False)
        
        embed.add_field(name="Guild", value=log_entry["guild"], inline=False)
        
        return embed
    
    # -------------------- Enhanced Moderation Commands --------------------
    @commands.command(name="kick", brief="Kick a member from the server")
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Kick a member from the server with enhanced security checks."""
        # Security validation
        can_moderate, error_message = await self.security_manager.can_moderate_member(ctx, member, "kick")
        if not can_moderate:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_message,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Validate reason
        is_valid_reason, valid_reason = self.security_manager.validate_reason(reason, AdminConfig.MAX_BAN_REASON_LENGTH)
        if not is_valid_reason:
            embed = discord.Embed(
                title="❌ Invalid Reason",
                description=valid_reason,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # DM the user before kicking (with error handling)
            try:
                dm_embed = discord.Embed(
                    title="🚪 You have been kicked",
                    description=f"You were kicked from **{ctx.guild.name}**",
                    color=discord.Color.orange()
                )
                dm_embed.add_field(name="Reason", value=valid_reason, inline=False)
                dm_embed.add_field(name="Moderator", value=ctx.author.display_name, inline=False)
                await member.send(embed=dm_embed)
            except discord.Forbidden:
                logging.info(f"Could not DM kick notification to {member}")
            except Exception as e:
                logging.warning(f"Error sending kick DM: {e}")
            
            # Perform the kick
            await member.kick(reason=f"Kicked by {ctx.author} ({ctx.author.id}): {valid_reason}")
            
            # Log the action
            await self.log_mod_action("kick", ctx.author, member, valid_reason)
            
            # Success message
            embed = discord.Embed(
                title="✅ Member Kicked",
                description=f"**{member}** has been kicked from the server.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Reason", value=valid_reason, inline=False)
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
            logging.error(f"Error kicking member {member}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to kick the member.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="ban", brief="Ban a member from the server")
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban a member from the server with enhanced security checks."""
        # Security validation
        can_moderate, error_message = await self.security_manager.can_moderate_member(ctx, member, "ban")
        if not can_moderate:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_message,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Validate reason
        is_valid_reason, valid_reason = self.security_manager.validate_reason(reason, AdminConfig.MAX_BAN_REASON_LENGTH)
        if not is_valid_reason:
            embed = discord.Embed(
                title="❌ Invalid Reason",
                description=valid_reason,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # DM the user before banning (with error handling)
            try:
                dm_embed = discord.Embed(
                    title="🔨 You have been banned",
                    description=f"You were banned from **{ctx.guild.name}**",
                    color=discord.Color.red()
                )
                dm_embed.add_field(name="Reason", value=valid_reason, inline=False)
                dm_embed.add_field(name="Moderator", value=ctx.author.display_name, inline=False)
                await member.send(embed=dm_embed)
            except discord.Forbidden:
                logging.info(f"Could not DM ban notification to {member}")
            except Exception as e:
                logging.warning(f"Error sending ban DM: {e}")
            
            # Perform the ban
            await member.ban(reason=f"Banned by {ctx.author} ({ctx.author.id}): {valid_reason}", delete_message_days=0)
            
            # Log the action
            await self.log_mod_action("ban", ctx.author, member, valid_reason)
            
            embed = discord.Embed(
                title="✅ Member Banned",
                description=f"**{member}** has been banned from the server.",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=valid_reason, inline=False)
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
            logging.error(f"Error banning member {member}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to ban the member.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="unban", brief="Unban a user from the server")
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "No reason provided"):
        """Unban a user from the server by their user ID with security checks."""
        # Validate user_id
        if user_id == ctx.author.id:
            embed = discord.Embed(
                title="❌ Invalid User",
                description="You cannot unban yourself.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if user_id == ctx.guild.me.id:
            embed = discord.Embed(
                title="❌ Invalid User",
                description="You cannot unban the bot.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Validate reason
        is_valid_reason, valid_reason = self.security_manager.validate_reason(reason)
        if not is_valid_reason:
            embed = discord.Embed(
                title="❌ Invalid Reason",
                description=valid_reason,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Check if user is actually banned
            bans = [ban async for ban in ctx.guild.bans()]
            user_to_unban = None
            
            for ban in bans:
                if ban.user.id == user_id:
                    user_to_unban = ban.user
                    break
            
            if not user_to_unban:
                embed = discord.Embed(
                    title="❌ User Not Banned",
                    description="This user is not currently banned.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            # Perform unban
            user = discord.Object(id=user_id)
            await ctx.guild.unban(user, reason=f"Unbanned by {ctx.author} ({ctx.author.id}): {valid_reason}")
            
            # Log the action
            await self.log_mod_action("unban", ctx.author, None, valid_reason)
            
            embed = discord.Embed(
                title="✅ User Unbanned",
                description=f"**{user_to_unban}** has been unbanned from the server.",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=valid_reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
            
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have permission to unban members.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"Error unbanning user {user_id}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to unban the user.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="mute", brief="Mute a member in the server")
    async def mute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Mute a member by removing their ability to send messages with security checks."""
        # Security validation
        can_moderate, error_message = await self.security_manager.can_moderate_member(ctx, member, "mute")
        if not can_moderate:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_message,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Validate reason
        is_valid_reason, valid_reason = self.security_manager.validate_reason(reason)
        if not is_valid_reason:
            embed = discord.Embed(
                title="❌ Invalid Reason",
                description=valid_reason,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Find or create muted role
            muted_role = discord.utils.get(ctx.guild.roles, name=AdminConfig.MUTED_ROLE_NAME)
            if not muted_role:
                # Create muted role with proper permissions
                muted_role = await ctx.guild.create_role(
                    name=AdminConfig.MUTED_ROLE_NAME, 
                    reason="Muted role for moderation",
                    color=discord.Color.dark_gray()
                )
                
                # Set permissions for all channels
                for channel in ctx.guild.channels:
                    if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                        await channel.set_permissions(
                            muted_role, 
                            send_messages=False,
                            speak=False,
                            add_reactions=False,
                            create_public_threads=False,
                            create_private_threads=False,
                            send_messages_in_threads=False
                        )
            
            # Check if member is already muted
            if muted_role in member.roles:
                embed = discord.Embed(
                    title="❌ Already Muted",
                    description="This member is already muted.",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return
            
            await member.add_roles(muted_role, reason=f"Muted by {ctx.author} ({ctx.author.id}): {valid_reason}")
            
            # Log the action
            await self.log_mod_action("mute", ctx.author, member, valid_reason)
            
            embed = discord.Embed(
                title="✅ Member Muted",
                description=f"**{member}** has been muted.",
                color=discord.Color.gold()
            )
            embed.add_field(name="Reason", value=valid_reason, inline=False)
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
            logging.error(f"Error muting member {member}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to mute the member.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    @commands.command(name="unmute", brief="Unmute a member in the server")
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Unmute a member by restoring their ability to send messages."""
        # Security validation
        can_moderate, error_message = await self.security_manager.can_moderate_member(ctx, member, "unmute")
        if not can_moderate:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_message,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Validate reason
        is_valid_reason, valid_reason = self.security_manager.validate_reason(reason)
        if not is_valid_reason:
            embed = discord.Embed(
                title="❌ Invalid Reason",
                description=valid_reason,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        try:
            muted_role = discord.utils.get(ctx.guild.roles, name=AdminConfig.MUTED_ROLE_NAME)
            if not muted_role or muted_role not in member.roles:
                embed = discord.Embed(
                    title="❌ Not Muted",
                    description="This member is not currently muted.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            await member.remove_roles(muted_role, reason=f"Unmuted by {ctx.author} ({ctx.author.id}): {valid_reason}")
            
            # Log the action
            await self.log_mod_action("unmute", ctx.author, member, valid_reason)
            
            embed = discord.Embed(
                title="✅ Member Unmuted",
                description=f"**{member}** has been unmuted.",
                color=discord.Color.green()
            )
            embed.add_field(name="Reason", value=valid_reason, inline=False)
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
            logging.error(f"Error unmuting member {member}: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while trying to unmute the member.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    # -------------------- Enhanced Utility Commands --------------------
    @commands.command(name="clear", aliases=["purge", "clean"])
    async def clear(self, ctx: commands.Context, amount: int = 10):
        """Delete messages from channel with enhanced security and limits."""
        # Security validation
        can_moderate, error_message = await self.security_manager.can_moderate_member(ctx, ctx.guild.me, "clear")
        if not can_moderate:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_message,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
            return
        
        # Validate amount
        if amount < AdminConfig.MIN_CLEAR_MESSAGES or amount > AdminConfig.MAX_CLEAR_MESSAGES:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description=f"Please specify a number between {AdminConfig.MIN_CLEAR_MESSAGES} and {AdminConfig.MAX_CLEAR_MESSAGES}.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
            return
        
        try:
            # Delete command message first
            await ctx.message.delete()
            
            # Delete messages with safety limits
            deleted = await ctx.channel.purge(limit=amount + 1)  # +1 to include command message
            
            # Log the action
            actual_deleted = len(deleted) - 1  # Exclude command message
            await self.log_mod_action("clear", ctx.author, None, f"Cleared {actual_deleted} messages in #{ctx.channel.name}")
            
            # Send confirmation
            embed = discord.Embed(
                title="✅ Messages Cleared",
                description=f"Deleted **{actual_deleted}** messages.",
                color=discord.Color.green()
            )
            confirm = await ctx.send(embed=embed)
            await asyncio.sleep(AdminConfig.CLEAR_CONFIRMATION_TIMEOUT)
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
        """Delete messages from a specific user with security checks."""
        # Security validation for both clear and target member
        can_moderate_clear, error_clear = await self.security_manager.can_moderate_member(ctx, ctx.guild.me, "clearuser")
        can_moderate_member, error_member = await self.security_manager.can_moderate_member(ctx, member, "clearuser")
        
        if not can_moderate_clear:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_clear,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
            return
        
        if not can_moderate_member:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_member,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, delete_after=5)
            return
        
        # Validate amount
        if amount < AdminConfig.MIN_CLEAR_MESSAGES or amount > AdminConfig.MAX_CLEAR_MESSAGES:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description=f"Please specify a number between {AdminConfig.MIN_CLEAR_MESSAGES} and {AdminConfig.MAX_CLEAR_MESSAGES}.",
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
            await self.log_mod_action("clear", ctx.author, member, f"Cleared {len(deleted)} messages from user in #{ctx.channel.name}")
            
            # Send confirmation
            embed = discord.Embed(
                title="✅ User Messages Cleared",
                description=f"Deleted **{len(deleted)}** messages from {member.mention}.",
                color=discord.Color.green()
            )
            confirm = await ctx.send(embed=embed)
            await asyncio.sleep(AdminConfig.CLEAR_CONFIRMATION_TIMEOUT)
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
        """Set the channel for moderation logs with validation."""
        channel = channel or ctx.channel
        
        # Validate channel permissions
        bot_permissions = channel.permissions_for(ctx.guild.me)
        if not all([bot_permissions.send_messages, bot_permissions.embed_links, bot_permissions.read_message_history]):
            embed = discord.Embed(
                title="❌ Invalid Channel",
                description="I need `Send Messages`, `Embed Links`, and `Read Message History` permissions in that channel.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        self.log_channel_id = channel.id
        
        embed = discord.Embed(
            title="✅ Log Channel Set",
            description=f"Moderation logs will now be sent to {channel.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    
    # ... (rest of the serverinfo, userinfo, and bot management commands remain similar but with enhanced security)
    
    # -------------------- Economy Admin Commands --------------------
    @commands.command(name="economygive", aliases=["egive", "agive"])
    async def economy_give(self, ctx: commands.Context, member: discord.Member, amount: int):
        """Admin: Give money to a user's wallet with security checks."""
        # Security validation
        can_moderate, error_message = await self.security_manager.can_moderate_member(ctx, member, "economy_give")
        if not can_moderate:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_message,
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        # Validate amount
        if amount <= 0:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description="Amount must be greater than 0.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        if amount > 1_000_000_000:  # Reasonable limit
            embed = discord.Embed(
                title="❌ Amount Too Large",
                description="Cannot give more than 1,000,000,000£ at once.",
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
            # Use the economy cog's atomic balance update
            result = await economy_cog.update_balance(member.id, wallet_change=amount)
            
            embed = discord.Embed(
                title="✅ Money Given",
                description=f"Gave {amount:,}£ to {member.mention}",
                color=discord.Color.green()
            )
            
            # Check if overflow was handled
            if result.get("_overflow_handled"):
                original_amount = result.get("_original_wallet_change", amount)
                actual_amount = result.get("_actual_wallet_change", amount)
                
                if actual_amount < original_amount:
                    embed.add_field(
                        name="💸 Overflow Protection", 
                        value=f"Wallet full! {actual_amount:,}£ given, {original_amount - actual_amount:,}£ moved to bank.",
                        inline=False
                    )
            
            embed.add_field(name="💵 New Wallet", value=f"{result['wallet']:,}£ / {result['wallet_limit']:,}£", inline=True)
            embed.add_field(name="🏦 Bank", value=f"{result['bank']:,}£", inline=True)
            
            await ctx.send(embed=embed)
            
            # Log the action
            await self.log_mod_action("economy_give", ctx.author, member, f"Given {amount:,}£")
        except Exception as e:
            logging.error(f"Error in economy_give: {e}")
            embed = discord.Embed(
                title="❌ Error Giving Money",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # ... (other economy admin commands would have similar security enhancements)

async def setup(bot):
    await bot.add_cog(Admin(bot))
