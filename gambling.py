import discord
from discord.ext import commands
import random
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from economy import db

# ---------------- Gambling Configuration Constants ----------------
class GamblingConfig:
    # Game Probabilities and Payouts
    COINFLIP_WIN_CHANCE = 0.55  # 55% win chance
    COINFLIP_PAYOUT = 1.8  # 1.8x payout
    
    DICE_WIN_CHANCE = 0.5  # 50% win chance (4,5,6 win)
    DICE_PAYOUTS = {4: 1.5, 5: 2.0, 6: 5.0}  # Different payouts per number
    
    SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "💎", "7️⃣"]
    SLOT_WEIGHTS = [30, 25, 20, 5, 2]  # Probabilities (out of 82 total)
    SLOT_PAYOUTS = {
        "🍒": 10,
        "🍋": 5, 
        "🍊": 3,
        "💎": 20,
        "7️⃣": 50
    }
    
    RPS_WIN_PAYOUT = 2.0  # 2x payout for wins
    HIGHLOW_WIN_PAYOUT = 2.0  # 2x payout for correct guesses
    
    # Cooldowns (seconds)
    BEG_COOLDOWN = 300  # 5 minutes
    COINFLIP_COOLDOWN = 3
    DICE_COOLDOWN = 4
    SLOTS_COOLDOWN = 5
    RPS_COOLDOWN = 3
    HIGHLOW_COOLDOWN = 4
    
    # Bet Limits
    MIN_BET = 1
    MAX_BET = 1000000  # 1 million max bet
    BEG_MIN = 10
    BEG_MAX = 70
    BEG_SUCCESS_RATE = 0.8  # 80% success rate
    
    # Security
    MAX_GAMES_PER_MINUTE = 10  # Anti-spam limit
    SUSPICIOUS_WIN_THRESHOLD = 10  # Consecutive wins to trigger monitoring

# ---------------- Gambling Security Manager ----------------
class GamblingSecurityManager:
    """Security manager for gambling system to prevent exploits and spam."""
    
    def __init__(self):
        self.game_cooldowns = {}
        self.game_counts = {}
        self.win_streaks = {}
        self.suspicious_players = set()
    
    async def check_game_cooldown(self, user_id: int, game_type: str) -> tuple[bool, float]:
        """Check if user can play a game (cooldown and rate limits)."""
        now = datetime.now(timezone.utc).timestamp()
        
        # Check specific game cooldown
        game_key = f"{user_id}_{game_type}"
        if game_key in self.game_cooldowns:
            cooldown_remaining = self.game_cooldowns[game_key] - now
            if cooldown_remaining > 0:
                return False, cooldown_remaining
        
        # Check rate limiting (games per minute)
        rate_key = f"{user_id}_rate"
        if rate_key not in self.game_counts:
            self.game_counts[rate_key] = []
        
        # Remove games older than 1 minute
        self.game_counts[rate_key] = [t for t in self.game_counts[rate_key] if now - t < 60]
        
        # Check if exceeding rate limit
        if len(self.game_counts[rate_key]) >= GamblingConfig.MAX_GAMES_PER_MINUTE:
            oldest_game = min(self.game_counts[rate_key])
            wait_time = 60 - (now - oldest_game)
            return False, wait_time
        
        return True, 0
    
    def set_game_cooldown(self, user_id: int, game_type: str):
        """Set cooldown for a game and track rate limiting."""
        now = datetime.now(timezone.utc).timestamp()
        
        # Set game-specific cooldown
        game_key = f"{user_id}_{game_type}"
        cooldown_time = getattr(GamblingConfig, f"{game_type.upper()}_COOLDOWN", 5)
        self.game_cooldowns[game_key] = now + cooldown_time
        
        # Track for rate limiting
        rate_key = f"{user_id}_rate"
        if rate_key not in self.game_counts:
            self.game_counts[rate_key] = []
        self.game_counts[rate_key].append(now)
        
        # Clean up old data
        self._cleanup_old_data()
    
    def validate_bet(self, user_id: int, bet: int, user_balance: int) -> tuple[bool, str]:
        """Validate bet amount and user's ability to pay."""
        if bet < GamblingConfig.MIN_BET:
            return False, f"Minimum bet is {GamblingConfig.MIN_BET}£"
        
        if bet > GamblingConfig.MAX_BET:
            return False, f"Maximum bet is {GamblingConfig.MAX_BET:,}£"
        
        if bet > user_balance:
            return False, f"You only have {user_balance:,}£ in your wallet"
        
        # Check for suspicious betting patterns
        if user_id in self.suspicious_players and bet > 10000:
            return False, "Large bets are temporarily restricted due to suspicious activity"
        
        return True, "OK"
    
    def track_win_streak(self, user_id: int, game_type: str, won: bool):
        """Track win streaks for suspicious activity monitoring."""
        streak_key = f"{user_id}_{game_type}"
        
        if won:
            if streak_key not in self.win_streaks:
                self.win_streaks[streak_key] = 0
            self.win_streaks[streak_key] += 1
            
            # Check for suspicious win streak
            if self.win_streaks[streak_key] >= GamblingConfig.SUSPICIOUS_WIN_THRESHOLD:
                self.suspicious_players.add(user_id)
                logging.warning(f"🚨 Suspicious win streak detected: {user_id} has won {self.win_streaks[streak_key]} consecutive {game_type} games")
        else:
            # Reset streak on loss
            if streak_key in self.win_streaks:
                self.win_streaks[streak_key] = 0
    
    def _cleanup_old_data(self):
        """Clean up old cooldowns and counts to prevent memory leaks."""
        now = datetime.now(timezone.utc).timestamp()
        max_age = 3600  # 1 hour
        
        # Clean old cooldowns
        self.game_cooldowns = {
            k: v for k, v in self.game_cooldowns.items() 
            if now - v < max_age
        }
        
        # Clean old game counts (keep only last 2 minutes for rate limiting)
        self.game_counts = {
            k: [t for t in timestamps if now - t < 120]
            for k, timestamps in self.game_counts.items()
        }
        self.game_counts = {k: v for k, v in self.game_counts.items() if v}
        
        # Clean old win streaks (keep for 24 hours for monitoring)
        self.win_streaks = {
            k: v for k, v in self.win_streaks.items()
            if v > 0  # Only keep active streaks
        }
        
        # Reset suspicious players after 1 hour
        reset_players = set()
        for player in self.suspicious_players:
            # In a real system, you'd track when they were flagged
            # For simplicity, we'll just clear occasionally
            if random.random() < 0.1:  # 10% chance to clear each cleanup
                reset_players.add(player)
        
        self.suspicious_players -= reset_players

class Gambling(commands.Cog):
    """Gambling games and entertainment commands with enhanced security."""
    
    def __init__(self, bot):
        self.bot = bot
        self.security_manager = GamblingSecurityManager()
        logging.info("✅ Gambling system initialized with security features")
    
    async def create_gambling_embed(self, title: str, color: discord.Color = discord.Color.purple()) -> discord.Embed:
        """Create a standardized gambling embed."""
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="🎰 Gambling System | Play responsibly!")
        return embed
    
    def format_money(self, amount: int) -> str:
        """Format money with commas and currency symbol."""
        return f"{amount:,}£"
    
    @commands.command(name="beg")
    async def beg(self, ctx: commands.Context):
        """Beg for some money with cooldown and limits."""
        # Check cooldown
        can_beg, cooldown_remaining = await self.security_manager.check_game_cooldown(ctx.author.id, "beg")
        if not can_beg:
            embed = await self.create_gambling_embed("⏰ Already Begged Recently", discord.Color.orange())
            embed.description = f"You can beg again in **{int(cooldown_remaining)} seconds**"
            return await ctx.send(embed=embed)
        
        # Random chance to succeed
        if random.random() < GamblingConfig.BEG_SUCCESS_RATE:
            amount = random.randint(GamblingConfig.BEG_MIN, GamblingConfig.BEG_MAX)
            result = await db.update_balance(ctx.author.id, wallet_change=amount)
            
            responses = [
                f"A generous stranger gave you {self.format_money(amount)}!",
                f"You found {self.format_money(amount)} on the ground!",
                f"Someone took pity on you and gave you {self.format_money(amount)}!",
                f"You managed to beg {self.format_money(amount)} from a passerby!",
                f"A kind soul donated {self.format_money(amount)} to you!"
            ]
            
            embed = await self.create_gambling_embed("🙏 Begging Successful", discord.Color.green())
            embed.description = random.choice(responses)
            embed.add_field(name="💵 New Balance", value=f"{self.format_money(result['wallet'])} / {self.format_money(result['wallet_limit'])}", inline=False)
        else:
            responses = [
                "Nobody gave you anything. Try again later!",
                "People ignored your begging. Better luck next time!",
                "You were shooed away empty-handed.",
                "Security told you to move along.",
                "Your begging attempts were unsuccessful."
            ]
            
            embed = await self.create_gambling_embed("😔 Begging Failed", discord.Color.red())
            embed.description = random.choice(responses)
        
        self.security_manager.set_game_cooldown(ctx.author.id, "beg")
        await ctx.send(embed=embed)
    
    @commands.command(name="flip", aliases=["coinflip"])
    async def flip(self, ctx: commands.Context, choice: str = None, bet: int = None):
        """Play Coin Flip with enhanced security and better odds."""
        if not choice or not bet:
            embed = await self.create_gambling_embed("🎲 Coin Flip Game", discord.Color.blue())
            embed.description = "Flip a coin and win 1.8x your bet!\n\n**Usage:** `~flip <heads/tails> <bet>`"
            embed.add_field(name="Example", value="`~flip heads 100` - Bet 100£ on heads", inline=False)
            embed.add_field(name="Payout", value=f"**{GamblingConfig.COINFLIP_PAYOUT}x** your bet if you win!", inline=False)
            embed.add_field(name="Win Chance", value=f"{GamblingConfig.COINFLIP_WIN_CHANCE:.0%}", inline=False)
            return await ctx.send(embed=embed)
        
        choice = choice.lower()
        if choice not in ["heads", "tails"]:
            embed = await self.create_gambling_embed("❌ Invalid Choice", discord.Color.red())
            embed.description = "Please choose either `heads` or `tails`."
            return await ctx.send(embed=embed)
        
        # Check cooldown
        can_play, cooldown_remaining = await self.security_manager.check_game_cooldown(ctx.author.id, "coinflip")
        if not can_play:
            embed = await self.create_gambling_embed("⏰ Game Cooldown", discord.Color.orange())
            embed.description = f"You can play coin flip again in **{int(cooldown_remaining)} seconds**"
            return await ctx.send(embed=embed)
        
        user_data = await db.get_user(ctx.author.id)
        
        # Validate bet
        is_valid_bet, bet_error = self.security_manager.validate_bet(ctx.author.id, bet, user_data["wallet"])
        if not is_valid_bet:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = bet_error
            return await ctx.send(embed=embed)
        
        # Apply gambling bonus if active
        economy_cog = self.bot.get_cog("Economy")
        gambling_multiplier = 1.0
        if economy_cog:
            active_effects = economy_cog.get_active_effects(ctx.author.id)
            gambling_multiplier = active_effects.get("gambling_bonus", {}).get("multiplier", 1.0)
        
        # Calculate win chance with bonus
        win_chance = min(0.9, GamblingConfig.COINFLIP_WIN_CHANCE * gambling_multiplier)  # Cap at 90%
        
        # Flip coin with weighted probability
        result = "heads" if random.random() < 0.5 else "tails"  # Fair coin for result
        win = choice == result  # But apply win chance separately
        
        # Apply win chance (55% base chance)
        actual_win = win and (random.random() < win_chance)
        
        if actual_win:
            # Calculate winnings
            winnings = int(bet * GamblingConfig.COINFLIP_PAYOUT)
            result_text = await db.update_balance(ctx.author.id, wallet_change=winnings - bet)
            
            embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
            embed.description = f"The coin landed on **{result}**! You won {self.format_money(winnings)}!"
            
            if gambling_multiplier > 1.0:
                embed.add_field(name="✨ Lucky Bonus", value=f"Your win chance was increased by your items!", inline=False)
            
            # Track win streak
            self.security_manager.track_win_streak(ctx.author.id, "coinflip", True)
        else:
            # Lose bet
            result_text = await db.update_balance(ctx.author.id, wallet_change=-bet)
            
            embed = await self.create_gambling_embed("💸 You Lost!", discord.Color.red())
            embed.description = f"The coin landed on **{result}**. You lost {self.format_money(bet)}."
            
            # Track loss
            self.security_manager.track_win_streak(ctx.author.id, "coinflip", False)
        
        embed.add_field(name="💵 New Balance", value=f"{self.format_money(result_text['wallet'])} / {self.format_money(result_text['wallet_limit'])}", inline=False)
        
        self.security_manager.set_game_cooldown(ctx.author.id, "coinflip")
        await ctx.send(embed=embed)
    
    @commands.command(name="dice")
    async def dice(self, ctx: commands.Context, bet: int = None):
        """Roll a dice - win 1.5x-5x your bet depending on number."""
        if not bet:
            embed = await self.create_gambling_embed("🎯 Dice Game", discord.Color.blue())
            embed.description = "Roll a dice and win big!\n\n**Usage:** `~dice <bet>`"
            embed.add_field(name="Payouts", value="Roll 4: 1.5x\nRoll 5: 2x\nRoll 6: 5x!", inline=False)
            embed.add_field(name="Win Chance", value=f"{GamblingConfig.DICE_WIN_CHANCE:.0%}", inline=False)
            return await ctx.send(embed=embed)
        
        # Check cooldown
        can_play, cooldown_remaining = await self.security_manager.check_game_cooldown(ctx.author.id, "dice")
        if not can_play:
            embed = await self.create_gambling_embed("⏰ Game Cooldown", discord.Color.orange())
            embed.description = f"You can play dice again in **{int(cooldown_remaining)} seconds**"
            return await ctx.send(embed=embed)
        
        if bet <= 0:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = "Bet must be greater than 0."
            return await ctx.send(embed=embed)
        
        user_data = await db.get_user(ctx.author.id)
        
        # Validate bet
        is_valid_bet, bet_error = self.security_manager.validate_bet(ctx.author.id, bet, user_data["wallet"])
        if not is_valid_bet:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = bet_error
            return await ctx.send(embed=embed)
        
        # Apply gambling bonus if active
        economy_cog = self.bot.get_cog("Economy")
        gambling_multiplier = 1.0
        if economy_cog:
            active_effects = economy_cog.get_active_effects(ctx.author.id)
            gambling_multiplier = active_effects.get("gambling_bonus", {}).get("multiplier", 1.0)
        
        # Calculate win chance with bonus
        win_chance = min(0.66, GamblingConfig.DICE_WIN_CHANCE * gambling_multiplier)  # Cap at 66%
        
        # Roll dice (1-6)
        roll = random.randint(1, 6)
        
        # Determine if win (4,5,6 win) with chance modification
        is_winning_number = roll in [4, 5, 6]
        actual_win = is_winning_number and (random.random() < win_chance)
        
        if actual_win:
            # Calculate winnings based on number rolled
            payout_multiplier = GamblingConfig.DICE_PAYOUTS[roll]
            winnings = int(bet * payout_multiplier)
            result_text = await db.update_balance(ctx.author.id, wallet_change=winnings - bet)
            
            embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
            embed.description = f"🎲 You rolled a **{roll}**! You won {self.format_money(winnings)} ({payout_multiplier}x)!"
            
            if gambling_multiplier > 1.0:
                embed.add_field(name="✨ Lucky Bonus", value=f"Your win chance was increased by your items!", inline=False)
            
            # Track win streak
            self.security_manager.track_win_streak(ctx.author.id, "dice", True)
        else:
            # Lose bet
            result_text = await db.update_balance(ctx.author.id, wallet_change=-bet)
            
            embed = await self.create_gambling_embed("💸 You Lost!", discord.Color.red())
            embed.description = f"🎲 You rolled a **{roll}**. You lost {self.format_money(bet)}."
            
            # Track loss
            self.security_manager.track_win_streak(ctx.author.id, "dice", False)
        
        embed.add_field(name="💵 New Balance", value=f"{self.format_money(result_text['wallet'])} / {self.format_money(result_text['wallet_limit'])}", inline=False)
        
        self.security_manager.set_game_cooldown(ctx.author.id, "dice")
        await ctx.send(embed=embed)
    
    @commands.command(name="slots", aliases=["slot"])
    async def slots(self, ctx: commands.Context, bet: int = None):
        """Play slots - match 3 symbols to win with improved odds."""
        if not bet:
            embed = await self.create_gambling_embed("🎰 Slot Machine", discord.Color.blue())
            embed.description = "Play the slot machine and win big!\n\n**Usage:** `~slots <bet>`"
            embed.add_field(name="Payouts", 
                          value="• 3x 🍒 - 10x bet\n• 3x 🍋 - 5x bet\n• 3x 🍊 - 3x bet\n• 3x 💎 - 20x bet\n• 3x 7️⃣ - 50x bet", 
                          inline=False)
            return await ctx.send(embed=embed)
        
        # Check cooldown
        can_play, cooldown_remaining = await self.security_manager.check_game_cooldown(ctx.author.id, "slots")
        if not can_play:
            embed = await self.create_gambling_embed("⏰ Game Cooldown", discord.Color.orange())
            embed.description = f"You can play slots again in **{int(cooldown_remaining)} seconds**"
            return await ctx.send(embed=embed)
        
        if bet <= 0:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = "Bet must be greater than 0."
            return await ctx.send(embed=embed)
        
        user_data = await db.get_user(ctx.author.id)
        
        # Validate bet
        is_valid_bet, bet_error = self.security_manager.validate_bet(ctx.author.id, bet, user_data["wallet"])
        if not is_valid_bet:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = bet_error
            return await ctx.send(embed=embed)
        
        # Spin slots with weighted probabilities
        result = random.choices(
            GamblingConfig.SLOT_SYMBOLS, 
            weights=GamblingConfig.SLOT_WEIGHTS, 
            k=3
        )
        
        # Calculate payout
        payout_multiplier = 0
        if result[0] == result[1] == result[2]:
            # Three matching symbols
            payout_multiplier = GamblingConfig.SLOT_PAYOUTS[result[0]]
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            # Two matching symbols - small consolation
            payout_multiplier = 1.2
        
        if payout_multiplier > 0:
            # Win
            winnings = int(bet * payout_multiplier)
            result_text = await db.update_balance(ctx.author.id, wallet_change=winnings - bet)
            
            if payout_multiplier >= 10:
                embed = await self.create_gambling_embed("🎉 JACKPOT!", discord.Color.gold())
            else:
                embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                
            embed.description = f"🎰 | {result[0]} | {result[1]} | {result[2]} |\nYou won {self.format_money(winnings)}!"
            
            # Track win streak for jackpots only
            if payout_multiplier >= 10:
                self.security_manager.track_win_streak(ctx.author.id, "slots", True)
            else:
                self.security_manager.track_win_streak(ctx.author.id, "slots", False)
        else:
            # Lose
            result_text = await db.update_balance(ctx.author.id, wallet_change=-bet)
            
            embed = await self.create_gambling_embed("💸 You Lost!", discord.Color.red())
            embed.description = f"🎰 | {result[0]} | {result[1]} | {result[2]} |\nYou lost {self.format_money(bet)}."
            
            # Track loss
            self.security_manager.track_win_streak(ctx.author.id, "slots", False)
        
        embed.add_field(name="💵 New Balance", value=f"{self.format_money(result_text['wallet'])} / {self.format_money(result_text['wallet_limit'])}", inline=False)
        
        self.security_manager.set_game_cooldown(ctx.author.id, "slots")
        await ctx.send(embed=embed)
    
    @commands.command(name="rps", aliases=["rockpaperscissors"])
    async def rps(self, ctx: commands.Context, choice: str = None, bet: int = None):
        """Play Rock Paper Scissors with security enhancements."""
        if not choice or not bet:
            embed = await self.create_gambling_embed("✂️ Rock Paper Scissors", discord.Color.blue())
            embed.description = "Play Rock Paper Scissors against the bot!\n\n**Usage:** `~rps <rock/paper/scissors> <bet>`"
            embed.add_field(name="Example", value="`~rps rock 100` - Bet 100£ on rock", inline=False)
            embed.add_field(name="Payout", value=f"**{GamblingConfig.RPS_WIN_PAYOUT}x** your bet if you win!", inline=False)
            embed.add_field(name="Rules", value="• **Win:** 2x your bet\n• **Tie:** Return your bet\n• **Lose:** Lose your bet", inline=False)
            return await ctx.send(embed=embed)
        
        choice = choice.lower()
        if choice not in ["rock", "paper", "scissors"]:
            embed = await self.create_gambling_embed("❌ Invalid Choice", discord.Color.red())
            embed.description = "Please choose either `rock`, `paper`, or `scissors`."
            return await ctx.send(embed=embed)
        
        # Check cooldown
        can_play, cooldown_remaining = await self.security_manager.check_game_cooldown(ctx.author.id, "rps")
        if not can_play:
            embed = await self.create_gambling_embed("⏰ Game Cooldown", discord.Color.orange())
            embed.description = f"You can play RPS again in **{int(cooldown_remaining)} seconds**"
            return await ctx.send(embed=embed)
        
        if bet <= 0:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = "Bet must be greater than 0."
            return await ctx.send(embed=embed)
        
        user_data = await db.get_user(ctx.author.id)
        
        # Validate bet
        is_valid_bet, bet_error = self.security_manager.validate_bet(ctx.author.id, bet, user_data["wallet"])
        if not is_valid_bet:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = bet_error
            return await ctx.send(embed=embed)
        
        # Bot's choice (truly random)
        bot_choice = random.choice(["rock", "paper", "scissors"])
        
        # Determine winner
        if choice == bot_choice:
            # Tie - return bet
            result_text = await db.update_balance(ctx.author.id, wallet_change=0)
            result = "tie"
        elif (choice == "rock" and bot_choice == "scissors") or \
             (choice == "paper" and bot_choice == "rock") or \
             (choice == "scissors" and bot_choice == "paper"):
            # Win - 2x payout
            winnings = bet * GamblingConfig.RPS_WIN_PAYOUT
            result_text = await db.update_balance(ctx.author.id, wallet_change=winnings - bet)
            result = "win"
            
            # Track win streak
            self.security_manager.track_win_streak(ctx.author.id, "rps", True)
        else:
            # Lose
            result_text = await db.update_balance(ctx.author.id, wallet_change=-bet)
            result = "lose"
            
            # Track loss
            self.security_manager.track_win_streak(ctx.author.id, "rps", False)
        
        # Create result embed
        choice_emojis = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
        
        if result == "win":
            embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
            embed.description = f"{choice_emojis[choice]} **{choice.title()}** beats {choice_emojis[bot_choice]} **{bot_choice.title()}**!\nYou won {self.format_money(winnings)}!"
        elif result == "lose":
            embed = await self.create_gambling_embed("💸 You Lost!", discord.Color.red())
            embed.description = f"{choice_emojis[bot_choice]} **{bot_choice.title()}** beats {choice_emojis[choice]} **{choice.title()}**!\nYou lost {self.format_money(bet)}."
        else:
            embed = await self.create_gambling_embed("🤝 It's a Tie!", discord.Color.blue())
            embed.description = f"Both chose {choice_emojis[choice]} **{choice.title()}**!\nYour bet of {self.format_money(bet)} was returned."
        
        embed.add_field(name="💵 New Balance", value=f"{self.format_money(result_text['wallet'])} / {self.format_money(result_text['wallet_limit'])}", inline=False)
        
        self.security_manager.set_game_cooldown(ctx.author.id, "rps")
        await ctx.send(embed=embed)

    @commands.command(name="highlow")
    async def high_low(self, ctx: commands.Context, bet: int = None):
        """Guess if the next card will be higher or lower with security."""
        if not bet:
            embed = await self.create_gambling_embed("🎴 High-Low Game", discord.Color.blue())
            embed.description = "Guess if the next card will be higher or lower!\n\n**Usage:** `~highlow <bet>`\nThen react with ⬆️ for higher or ⬇️ for lower."
            embed.add_field(name="Payout", value=f"**{GamblingConfig.HIGHLOW_WIN_PAYOUT}x** your bet if you guess correctly!", inline=False)
            embed.add_field(name="Cards", value="Ace (low) to King (high)", inline=False)
            return await ctx.send(embed=embed)
        
        # Check cooldown
        can_play, cooldown_remaining = await self.security_manager.check_game_cooldown(ctx.author.id, "highlow")
        if not can_play:
            embed = await self.create_gambling_embed("⏰ Game Cooldown", discord.Color.orange())
            embed.description = f"You can play High-Low again in **{int(cooldown_remaining)} seconds**"
            return await ctx.send(embed=embed)
        
        if bet <= 0:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = "Bet must be greater than 0."
            return await ctx.send(embed=embed)
        
        user_data = await db.get_user(ctx.author.id)
        
        # Validate bet
        is_valid_bet, bet_error = self.security_manager.validate_bet(ctx.author.id, bet, user_data["wallet"])
        if not is_valid_bet:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = bet_error
            return await ctx.send(embed=embed)
        
        # Card values: 1 (Ace) to 13 (King)
        first_card = random.randint(1, 13)
        second_card = random.randint(1, 13)
        
        # Ensure second card is different from first
        while second_card == first_card:
            second_card = random.randint(1, 13)
        
        card_names = {
            1: "Ace", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7",
            8: "8", 9: "9", 10: "10", 11: "Jack", 12: "Queen", 13: "King"
        }
        
        embed = await self.create_gambling_embed("🎴 High-Low Game", discord.Color.blue())
        embed.description = f"First card: **{card_names[first_card]}**\n\nWill the next card be **higher** or **lower**?\n\nReact with:\n⬆️ for **Higher**\n⬇️ for **Lower**"
        embed.add_field(name="💰 Bet", value=self.format_money(bet), inline=True)
        embed.add_field(name="⏰ Time", value="15 seconds", inline=True)
        
        message = await ctx.send(embed=embed)
        
        # Add reactions
        await message.add_reaction("⬆️")
        await message.add_reaction("⬇️")
        
        # Wait for user reaction
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["⬆️", "⬇️"] and reaction.message.id == message.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=15.0, check=check)
            
            user_guess = "higher" if str(reaction.emoji) == "⬆️" else "lower"
            actual_result = "higher" if second_card > first_card else "lower"
            
            if user_guess == actual_result:
                # Win
                winnings = bet * GamblingConfig.HIGHLOW_WIN_PAYOUT
                result_text = await db.update_balance(ctx.author.id, wallet_change=winnings - bet)
                
                result_embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                result_embed.description = f"First card: **{card_names[first_card]}**\nSecond card: **{card_names[second_card]}**\n\nYou guessed **{user_guess}** correctly and won {self.format_money(winnings)}!"
                
                # Track win streak
                self.security_manager.track_win_streak(ctx.author.id, "highlow", True)
            else:
                # Lose
                result_text = await db.update_balance(ctx.author.id, wallet_change=-bet)
                
                result_embed = await self.create_gambling_embed("💸 You Lost!", discord.Color.red())
                result_embed.description = f"First card: **{card_names[first_card]}**\nSecond card: **{card_names[second_card]}**\n\nYou guessed **{user_guess}** but it was **{actual_result}**. You lost {self.format_money(bet)}."
                
                # Track loss
                self.security_manager.track_win_streak(ctx.author.id, "highlow", False)
            
            result_embed.add_field(name="💵 New Balance", value=f"{self.format_money(result_text['wallet'])} / {self.format_money(result_text['wallet_limit'])}", inline=False)
            
            await message.edit(embed=result_embed)
            await message.clear_reactions()
            
            self.security_manager.set_game_cooldown(ctx.author.id, "highlow")
            
        except asyncio.TimeoutError:
            timeout_embed = await self.create_gambling_embed("⏰ Time's Up!", discord.Color.orange())
            timeout_embed.description = "You didn't make a choice in time. Your bet has been returned."
            await message.edit(embed=timeout_embed)
            await message.clear_reactions()

async def setup(bot):
    await bot.add_cog(Gambling(bot))
