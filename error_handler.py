import discord
from discord.ext import commands
import logging
from typing import Optional

class ErrorHandler:
    """Standardized error handling for all commands."""
    
    @staticmethod
    async def handle_command_error(ctx: commands.Context, error: Exception, command_name: str = "unknown"):
        """Handle command errors with consistent responses."""
        
        error_messages = {
            'missing_permissions': "You don't have permission to use this command.",
            'bot_missing_permissions': "I don't have the required permissions to execute this command.",
            'cooldown': "This command is on cooldown. Please wait {retry_after:.1f}s.",
            'invalid_input': "Invalid input provided. Please check the command usage.",
            'insufficient_funds': "You don't have enough money for this transaction.",
            'user_not_found': "The specified user was not found.",
            'market_closed': "The market is currently closed. Trading hours: 9 AM - 5 PM UTC.",
            'database_error': "A database error occurred. Please try again."
        }
        
        embed = discord.Embed(color=discord.Color.red())
        
        if isinstance(error, commands.MissingPermissions):
            embed.title = "❌ Missing Permissions"
            embed.description = error_messages['missing_permissions']
            
        elif isinstance(error, commands.BotMissingPermissions):
            embed.title = "❌ Bot Missing Permissions"
            embed.description = error_messages['bot_missing_permissions']
            if hasattr(error, 'missing_permissions'):
                embed.add_field(
                    name="Required Permissions", 
                    value=", ".join(error.missing_permissions),
                    inline=False
                )
            
        elif isinstance(error, commands.CommandOnCooldown):
            embed.title = "⏰ Cooldown Active"
            embed.description = error_messages['cooldown'].format(retry_after=error.retry_after)
            embed.color = discord.Color.orange()
            
        elif isinstance(error, commands.UserNotFound):
            embed.title = "❌ User Not Found"
            embed.description = error_messages['user_not_found']
            
        elif isinstance(error, commands.BadArgument):
            embed.title = "❌ Invalid Argument"
            embed.description = error_messages['invalid_input']
            
        else:
            # Log unexpected errors
            logging.error(f"Unexpected error in {command_name}: {error}", exc_info=True)
            embed.title = "⚠️ Unexpected Error"
            embed.description = "An unexpected error occurred. The issue has been logged."
            embed.color = discord.Color.orange()
        
        try:
            await ctx.send(embed=embed, delete_after=10)
        except discord.Forbidden:
            pass  # Cannot send messages
