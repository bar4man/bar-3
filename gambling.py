import discord
from discord.ext import commands
import random
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from economy import db
from constants import GamblingConfig
from error_handler import ErrorHandler

class GamblingSecurityManager:
    """Security manager for gambling system to prevent exploits."""
    
    def __init__(self):
        self.cooldowns = {}
        self.bet_limits = {}
        self.suspicious_wins = {}
    
    async def check_cooldown(self, user_id: int, game_type: str) -> tuple[bool, float]:
        """Check if user can play a game (cooldown)."""
        now = datetime.now(timezone.utc).timestamp()
        key = f"{user_id}_{game_type}"
        
        if key in self.cooldowns:
            remaining = self.cooldowns[key] - now
            if remaining > 0:
                return False, remaining
        
        return True, 0
    
    def set_cooldown(self, user_id: int, game_type: str, cooldown_seconds: int):
        """Set cooldown for a game."""
        now = datetime.now(timezone.utc).timestamp()
        key = f"{user_id}_{game_type}"
        self.cooldowns[key] = now + cooldown_seconds
        
        # Clean up old cooldowns
        self._cleanup_old_cooldowns()
    
    def _cleanup_old_cooldowns(self):
        """Clean up expired cooldowns to prevent memory leaks."""
        now = datetime.now(timezone.utc).timestamp()
        max_age = 3600  # 1 hour
        
        self.cooldowns = {
            k: v for k, v in self.cooldowns.items() 
            if now - v < max_age
        }

class GamblingCog(commands.Cog):
    """Gambling system with improved odds and security features."""
    
    def __init__(self, bot):
        self.bot = bot
        self.security_manager = GamblingSecurityManager()
        logging.info("✅ Gambling system initialized with security features")
    
    def format_money(self, amount: int) -> str:
        """Format money using main bot's system."""
        return f"{amount:,}£"
    
    async def create_gambling_embed(self, title: str, color: discord.Color = discord.Color.purple()) -> discord.Embed:
        """Create a standardized gambling embed."""
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="🎰 Good luck! | Gamble responsibly")
        return embed
    
    async def validate_bet(self, ctx: commands.Context, bet: int) -> tuple[bool, str]:
        """Validate a bet amount with security checks."""
        if bet <= 0:
            return False, "Bet must be greater than 0."
        
        user_data = await db.get_user(ctx.author.id)
        
        if user_data["wallet"] < bet:
            return False, f"You don't have enough money in your wallet. You have {self.format_money(user_data['wallet'])} but tried to bet {self.format_money(bet)}."
        
        # Maximum bet limit for security
        max_bet = min(100000, user_data["wallet_limit"] // 10)
        if bet > max_bet:
            return False, f"Maximum bet allowed is {self.format_money(max_bet)} for security reasons."
        
        return True, "OK"

    # ========== GAMBLING COMMANDS ==========
    
    @commands.command(name="flip", aliases=["coinflip", "coin"])
    async def coin_flip(self, ctx: commands.Context, choice: str = None, bet: int = None):
        """Flip a coin with improved 55% win chance and 1.8x payout."""
        try:
            if not choice or not bet:
                embed = await self.create_gambling_embed("🎲 Coin Flip Game", discord.Color.blue())
                embed.description = (
                    "Flip a coin with improved 55% win chance!\n\n"
                    "**Usage:** `~flip <heads/tails> <bet>`\n"
                    "**Example:** `~flip heads 100`\n\n"
                    "**Payout:** 1.8x your bet\n"
                    "**Win Chance:** 55%\n"
                    "**Cooldown:** 3 seconds"
                )
                await ctx.send(embed=embed)
                return
            
            choice = choice.lower()
            if choice not in ["heads", "tails"]:
                embed = await self.create_gambling_embed("❌ Invalid Choice", discord.Color.red())
                embed.description = "Please choose either `heads` or `tails`."
                await ctx.send(embed=embed)
                return
            
            # Check cooldown
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "flip")
            if not can_play:
                embed = await self.create_gambling_embed("⏰ Cooldown Active", discord.Color.orange())
                embed.description = f"You can flip again in {int(cooldown_remaining)} seconds."
                await ctx.send(embed=embed)
                return
            
            # Validate bet
            is_valid_bet, bet_error = await self.validate_bet(ctx, bet)
            if not is_valid_bet:
                embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
                embed.description = bet_error
                await ctx.send(embed=embed)
                return
            
            # Process the game
            user_data = await db.get_user(ctx.author.id)
            
            # Remove bet from wallet
            result = await db.update_balance(ctx.author.id, wallet_change=-bet)
            
            # Determine outcome with improved odds
            win = random.random() < GamblingConfig.COINFLIP_WIN_CHANCE  # 55% chance to win
            coin_result = random.choice(["heads", "tails"])
            
            # Check if user won
            if win and choice == coin_result:
                # User wins!
                winnings = int(bet * GamblingConfig.COINFLIP_PAYOUT)
                result = await db.update_balance(ctx.author.id, wallet_change=winnings)
                
                embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                embed.description = f"The coin landed on **{coin_result}**! You won {self.format_money(winnings)}!"
                embed.add_field(name="💰 Winnings", value=self.format_money(winnings), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                embed.add_field(name="🎯 Choice", value=choice.title(), inline=True)
                
            else:
                # User loses
                embed = await self.create_gambling_embed("💸 You Lost", discord.Color.red())
                embed.description = f"The coin landed on **{coin_result}**. Better luck next time!"
                embed.add_field(name="📉 Loss", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                embed.add_field(name="🎯 Choice", value=choice.title(), inline=True)
            
            # Set cooldown
            self.security_manager.set_cooldown(ctx.author.id, "flip", 3)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "flip")
    
    @commands.command(name="dice", aliases=["rolldice"])
    async def dice_game(self, ctx: commands.Context, bet: int = None):
        """Roll a dice with multiple winning numbers and payouts."""
        try:
            if not bet:
                embed = await self.create_gambling_embed("🎯 Dice Game", discord.Color.blue())
                embed.description = (
                    "Roll a dice! Win on 4, 5, or 6 with different payouts!\n\n"
                    "**Usage:** `~dice <bet>`\n"
                    "**Example:** `~dice 100`\n\n"
                    "**Winning Numbers & Payouts:**\n"
                    "• **6**: 5x your bet\n"
                    "• **5**: 2x your bet\n"
                    "• **4**: 1.5x your bet\n"
                    "• **1-3**: Lose your bet\n"
                    "**Cooldown:** 4 seconds"
                )
                await ctx.send(embed=embed)
                return
            
            # Check cooldown
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "dice")
            if not can_play:
                embed = await self.create_gambling_embed("⏰ Cooldown Active", discord.Color.orange())
                embed.description = f"You can roll again in {int(cooldown_remaining)} seconds."
                await ctx.send(embed=embed)
                return
            
            # Validate bet
            is_valid_bet, bet_error = await self.validate_bet(ctx, bet)
            if not is_valid_bet:
                embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
                embed.description = bet_error
                await ctx.send(embed=embed)
                return
            
            # Process the game
            user_data = await db.get_user(ctx.author.id)
            
            # Remove bet from wallet
            result = await db.update_balance(ctx.author.id, wallet_change=-bet)
            
            # Roll the dice (1-6)
            dice_roll = random.randint(1, 6)
            
            # Check if user won and calculate payout
            if dice_roll in GamblingConfig.DICE_WIN_NUMBERS:
                # User wins!
                payout_multiplier = GamblingConfig.DICE_PAYOUTS[dice_roll]
                winnings = int(bet * payout_multiplier)
                result = await db.update_balance(ctx.author.id, wallet_change=winnings)
                
                embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                embed.description = f"You rolled a **{dice_roll}**! You won {self.format_money(winnings)}!"
                embed.add_field(name="🎲 Roll", value=dice_roll, inline=True)
                embed.add_field(name="💰 Winnings", value=self.format_money(winnings), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                
            else:
                # User loses
                embed = await self.create_gambling_embed("💸 You Lost", discord.Color.red())
                embed.description = f"You rolled a **{dice_roll}**. Better luck next time!"
                embed.add_field(name="🎲 Roll", value=dice_roll, inline=True)
                embed.add_field(name="📉 Loss", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
            
            # Set cooldown
            self.security_manager.set_cooldown(ctx.author.id, "dice", 4)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "dice")
    
    @commands.command(name="slots", aliases=["slot"])
    async def slot_machine(self, ctx: commands.Context, bet: int = None):
        """Play the slot machine with improved odds."""
        try:
            if not bet:
                embed = await self.create_gambling_embed("🎰 Slot Machine", discord.Color.blue())
                embed.description = (
                    "Spin the slot machine with better odds!\n\n"
                    "**Usage:** `~slots <bet>`\n"
                    "**Example:** `~slots 100`\n\n"
                    "**Payouts:**\n"
                    "• **Three 7️⃣**: 30x\n"
                    "• **Three 💎**: 20x\n"
                    "• **Three 🍒**: 10x\n"
                    "• **Three 🍊**: 5x\n"
                    "• **Three 🍋**: 3x\n"
                    "• **Two Matching**: 1.2x\n"
                    "**Cooldown:** 5 seconds"
                )
                await ctx.send(embed=embed)
                return
            
            # Check cooldown
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "slots")
            if not can_play:
                embed = await self.create_gambling_embed("⏰ Cooldown Active", discord.Color.orange())
                embed.description = f"You can spin again in {int(cooldown_remaining)} seconds."
                await ctx.send(embed=embed)
                return
            
            # Validate bet
            is_valid_bet, bet_error = await self.validate_bet(ctx, bet)
            if not is_valid_bet:
                embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
                embed.description = bet_error
                await ctx.send(embed=embed)
                return
            
            # Process the game
            user_data = await db.get_user(ctx.author.id)
            
            # Remove bet from wallet
            result = await db.update_balance(ctx.author.id, wallet_change=-bet)
            
            # Generate slot results
            symbols = random.choices(
                GamblingConfig.SLOT_SYMBOLS,
                weights=GamblingConfig.SLOT_WEIGHTS,
                k=3
            )
            
            slot_display = " | ".join(symbols)
            
            # Check for wins
            if symbols[0] == symbols[1] == symbols[2]:
                # Three matching symbols
                payout_key = f"three_{symbols[0]}"
                payout_multiplier = GamblingConfig.SLOT_PAYOUTS.get(payout_key, 1)
                winnings = int(bet * payout_multiplier)
                result = await db.update_balance(ctx.author.id, wallet_change=winnings)
                
                embed = await self.create_gambling_embed("🎉 JACKPOT!", discord.Color.green())
                embed.description = f"**{slot_display}**\n\nThree {symbols[0]}! You won {self.format_money(winnings)}!"
                embed.add_field(name="💰 Winnings", value=self.format_money(winnings), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                embed.add_field(name="🎯 Multiplier", value=f"{payout_multiplier}x", inline=True)
                
            elif symbols[0] == symbols[1] or symbols[1] == symbols[2] or symbols[0] == symbols[2]:
                # Two matching symbols
                winnings = int(bet * GamblingConfig.SLOT_PAYOUTS["two_matching"])
                result = await db.update_balance(ctx.author.id, wallet_change=winnings)
                
                embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                embed.description = f"**{slot_display}**\n\nTwo matching! You won {self.format_money(winnings)}!"
                embed.add_field(name="💰 Winnings", value=self.format_money(winnings), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                embed.add_field(name="🎯 Multiplier", value="1.2x", inline=True)
                
            else:
                # No win
                embed = await self.create_gambling_embed("💸 You Lost", discord.Color.red())
                embed.description = f"**{slot_display}**\n\nNo matches this time. Better luck next spin!"
                embed.add_field(name="📉 Loss", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
            
            # Set cooldown
            self.security_manager.set_cooldown(ctx.author.id, "slots", 5)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "slots")
    
    @commands.command(name="rps", aliases=["rockpaperscissors"])
    async def rock_paper_scissors(self, ctx: commands.Context, choice: str = None, bet: int = None):
        """Play Rock Paper Scissors with fair rules."""
        try:
            if not choice or not bet:
                embed = await self.create_gambling_embed("✂️ Rock Paper Scissors", discord.Color.blue())
                embed.description = (
                    "Play Rock Paper Scissors with fair rules!\n\n"
                    "**Usage:** `~rps <rock/paper/scissors> <bet>`\n"
                    "**Example:** `~rps rock 100`\n\n"
                    "**Rules:**\n"
                    "• **Win**: 2x your bet\n"
                    "• **Tie**: Return your bet\n"
                    "• **Lose**: Lose your bet\n"
                    "**Cooldown:** 3 seconds"
                )
                await ctx.send(embed=embed)
                return
            
            choice = choice.lower()
            if choice not in ["rock", "paper", "scissors"]:
                embed = await self.create_gambling_embed("❌ Invalid Choice", discord.Color.red())
                embed.description = "Please choose either `rock`, `paper`, or `scissors`."
                await ctx.send(embed=embed)
                return
            
            # Check cooldown
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "rps")
            if not can_play:
                embed = await self.create_gambling_embed("⏰ Cooldown Active", discord.Color.orange())
                embed.description = f"You can play again in {int(cooldown_remaining)} seconds."
                await ctx.send(embed=embed)
                return
            
            # Validate bet
            is_valid_bet, bet_error = await self.validate_bet(ctx, bet)
            if not is_valid_bet:
                embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
                embed.description = bet_error
                await ctx.send(embed=embed)
                return
            
            # Process the game
            user_data = await db.get_user(ctx.author.id)
            
            # Remove bet from wallet
            result = await db.update_balance(ctx.author.id, wallet_change=-bet)
            
            # Bot's choice
            bot_choice = random.choice(["rock", "paper", "scissors"])
            
            # Determine winner
            if choice == bot_choice:
                # Tie - return bet
                result = await db.update_balance(ctx.author.id, wallet_change=bet)
                
                embed = await self.create_gambling_embed("🤝 It's a Tie!", discord.Color.orange())
                embed.description = f"**You:** {choice.title()} | **Bot:** {bot_choice.title()}\n\nYour bet has been returned!"
                embed.add_field(name="💵 Bet Returned", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                
            elif (choice == "rock" and bot_choice == "scissors") or \
                 (choice == "paper" and bot_choice == "rock") or \
                 (choice == "scissors" and bot_choice == "paper"):
                # User wins
                winnings = int(bet * GamblingConfig.RPS_PAYOUT)
                result = await db.update_balance(ctx.author.id, wallet_change=winnings)
                
                embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                embed.description = f"**You:** {choice.title()} | **Bot:** {bot_choice.title()}\n\nYou won {self.format_money(winnings)}!"
                embed.add_field(name="💰 Winnings", value=self.format_money(winnings), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                embed.add_field(name="🎯 Multiplier", value="2x", inline=True)
                
            else:
                # User loses
                embed = await self.create_gambling_embed("💸 You Lost", discord.Color.red())
                embed.description = f"**You:** {choice.title()} | **Bot:** {bot_choice.title()}\n\nBetter luck next time!"
                embed.add_field(name="📉 Loss", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
            
            # Set cooldown
            self.security_manager.set_cooldown(ctx.author.id, "rps", 3)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "rps")
    
    @commands.command(name="beg")
    async def beg(self, ctx: commands.Context):
        """Beg for money with a cooldown."""
        try:
            # Check cooldown
            remaining = await db.check_cooldown(ctx.author.id, "beg", 300)  # 5 minutes
            if remaining:
                embed = await self.create_gambling_embed("⏰ Already Begged Recently", discord.Color.orange())
                embed.description = f"You can beg again in **{int(remaining)} seconds**."
                await ctx.send(embed=embed)
                return
            
            user_data = await db.get_user(ctx.author.id)
            
            # Determine if begging is successful
            success = random.random() < 0.8  # 80% success rate
            
            if success:
                # Successful beg
                amount = random.randint(10, 70)
                result = await db.update_balance(ctx.author.id, wallet_change=amount)
                
                beg_responses = [
                    "A kind stranger gave you",
                    "You found",
                    "Someone took pity and gave you",
                    "You managed to get",
                    "A generous person donated"
                ]
                
                embed = await self.create_gambling_embed("🙏 Begging Successful", discord.Color.green())
                embed.description = f"{random.choice(beg_responses)} {self.format_money(amount)}!"
                embed.add_field(name="💰 Received", value=self.format_money(amount), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                
            else:
                # Failed beg
                fail_responses = [
                    "Nobody gave you anything...",
                    "People ignored your begging...",
                    "You got nothing but strange looks...",
                    "No one was feeling generous today...",
                    "Your begging was unsuccessful..."
                ]
                
                embed = await self.create_gambling_embed("😔 Begging Failed", discord.Color.red())
                embed.description = random.choice(fail_responses)
                embed.add_field(name="💵 Current Balance", value=self.format_money(user_data["wallet"]), inline=True)
            
            await db.set_cooldown(ctx.author.id, "beg")
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "beg")

async def setup(bot):
    await bot.add_cog(GamblingCog(bot))
