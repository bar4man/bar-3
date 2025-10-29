# error_handler.py
import discord
import logging
from datetime import datetime, timezone

class ErrorHandler:
    
    @staticmethod
    async def handle_command_error(ctx, error, command_name):
        """A centralized handler for cog-level command errors."""
        
        logging.error(f"Error in command '{command_name}': {error}", exc_info=error)
        
        embed = discord.Embed(
            title="⚠️ An Error Occurred",
            description=f"An unexpected error occurred while running the `{command_name}` command. The developers have been notified.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="We apologize for the inconvenience.")
        
        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            pass # Can't send messages
        except Exception as e:
            logging.error(f"Failed to send error message: {e}")
