import discord
from discord.ext import commands
from discord.ui import View, Button, button # <-- ADDED FOR BUTTONS
import random
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from economy import db
from constants import GamblingConfig
from error_handler import ErrorHandler
from admin import is_bot_admin # <-- IMPORTED ADMIN CHECK

class GamblingSecurityManager:
    """Security manager for gambling system to prevent exploits."""
    
    def __init__(self):
        self.cooldowns = {}
        self.bet_limits = {}
        self.suspicious_wins = {}
    
    async def check_cooldown(self, user_id: int, game_type: str, member: discord.Member = None) -> tuple[bool, float]:
        """Check if user can play a game (cooldown)."""
        # --- ADMIN BYPASS ---
        if member and is_bot_admin(member):
            return True, 0
        # --- END BYPASS ---
        
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

# ------------------- BLACKJACK GAME LOGIC -------------------

class BlackjackView(View):
    """A view for playing a game of Blackjack."""
    
    def __init__(self, cog, ctx, bet):
        super().__init__(timeout=120.0)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.deck = self.create_deck()
        self.player_hand = [self.draw_card(), self.draw_card()]
        self.dealer_hand = [self.draw_card(), self.draw_card()]
        self.game_over = False

    def create_deck(self):
        """Creates a standard 52-card deck."""
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [{'rank': rank, 'suit': suit} for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck

    def draw_card(self):
        """Draws a card from the deck."""
        if not self.deck:
            self.deck = self.create_deck() # Reshuffle if empty
        return self.deck.pop()

    def get_hand_value(self, hand):
        """Calculates the value of a hand."""
        value = 0
        aces = 0
        for card in hand:
            rank = card['rank']
            if rank in ['J', 'Q', 'K']:
                value += 10
            elif rank == 'A':
                aces += 1
                value += 11
            else:
                value += int(rank)
        
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        return value

    def format_hand(self, hand, hide_dealer_card=False):
        """Formats a hand into a readable string."""
        if hide_dealer_card:
            return f"[{hand[0]['rank']} {hand[0]['suit']}] [?]"
        return " ".join(f"[{card['rank']} {card['suit']}]" for card in hand)

    async def create_game_embed(self, status_message, color=discord.Color.blue()):
        """Creates the embed for the game state."""
        embed = await self.cog.create_gambling_embed("🃏 Blackjack", color)
        
        player_value = self.get_hand_value(self.player_hand)
        dealer_value = self.get_hand_value(self.dealer_hand)
        
        embed.description = f"**Bet:** {self.cog.format_money(self.bet)}\n{status_message}"
        
        if self.game_over:
            embed.add_field(name=f"Dealer's Hand ({dealer_value})", value=self.format_hand(self.dealer_hand), inline=False)
        else:
            embed.add_field(name="Dealer's Hand (?)", value=self.format_hand(self.dealer_hand, hide_dealer_card=True), inline=False)
            
        embed.add_field(name=f"{self.ctx.author.display_name}'s Hand ({player_value})", value=self.format_hand(self.player_hand), inline=False)
        
        return embed

    async def end_game(self, interaction: discord.Interaction, status_message: str, color: discord.Color, winnings: int):
        """Ends the game, disables buttons, and sends the final result."""
        self.game_over = True
        self.stop()
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True

        embed = await self.create_game_embed(status_message, color)
        await interaction.response.edit_message(embed=embed, view=self)

        if winnings > 0:
            # User won, add winnings (bet + winnings)
            result = await db.update_balance(self.ctx.author.id, wallet_change=winnings)
            embed.add_field(name="💵 New Balance", value=self.cog.format_money(result["wallet"]), inline=True)
        elif winnings == 0:
            # Push, return bet
            result = await db.update_balance(self.ctx.author.id, wallet_change=self.bet)
            embed.add_field(name="💵 New Balance", value=self.cog.format_money(result["wallet"]), inline=True)
        else:
            # Loss, do nothing as bet was already taken
            user_data = await db.get_user(self.ctx.author.id)
            embed.add_field(name="💵 Balance", value=self.cog.format_money(user_data["wallet"]), inline=True)
        
        await interaction.edit_original_response(embed=embed, view=self)

    @button(label="Hit", style=discord.ButtonStyle.green, custom_id="bj_hit")
    async def hit(self, interaction: discord.Interaction, button: Button):
        """Player draws another card."""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return

        self.player_hand.append(self.draw_card())
        player_value = self.get_hand_value(self.player_hand)

        if player_value > 21:
            await self.end_game(interaction, f"**BUST!** You drew a {self.player_hand[-1]['rank']} and went over 21. You lose {self.cog.format_money(self.bet)}.", discord.Color.red(), 0)
        else:
            embed = await self.create_game_embed("Hit or Stand?")
            await interaction.response.edit_message(embed=embed, view=self)

    @button(label="Stand", style=discord.ButtonStyle.red, custom_id="bj_stand")
    async def stand(self, interaction: discord.Interaction, button: Button):
        """Player stands, dealer plays."""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return

        dealer_value = self.get_hand_value(self.dealer_hand)
        player_value = self.get_hand_value(self.player_hand)

        # Dealer hits until 17 or more
        while dealer_value < 17:
            self.dealer_hand.append(self.draw_card())
            dealer_value = self.get_hand_value(self.dealer_hand)
        
        if dealer_value > 21:
            winnings = self.bet * 2 # Player wins 1:1
            await self.end_game(interaction, f"**Dealer BUSTS!** You win {self.cog.format_money(self.bet)}!", discord.Color.green(), winnings)
        elif dealer_value > player_value:
            await self.end_game(interaction, f"**Dealer Wins!** Dealer has {dealer_value}, you have {player_value}. You lose.", discord.Color.red(), 0)
        elif player_value > dealer_value:
            winnings = self.bet * 2 # Player wins 1:1
            await self.end_game(interaction, f"**You Win!** You have {player_value}, dealer has {dealer_value}. You win {self.cog.format_money(self.bet)}!", discord.Color.green(), winnings)
        else: # dealer_value == player_value
            await self.end_game(interaction, f"**PUSH!** You both have {player_value}. Your bet is returned.", discord.Color.orange(), self.bet)

# ------------------- PLAY AGAIN BUTTONS -------------------

class PlayAgainView(View):
    """A view for re-playing a game with the same bet."""
    
    def __init__(self, cog, ctx, bet, game_type):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.game_type = game_type
        self.original_message = None

    async def on_timeout(self):
        if self.original_message:
            # Remove buttons on timeout
            await self.original_message.edit(view=None)

    @button(label="Play Again", style=discord.ButtonStyle.primary, emoji="🔁")
    async def play_again(self, interaction: discord.Interaction, button: Button):
        """Re-runs the game command."""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return

        # Disable buttons on the current message
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Get the command and invoke it again
        if self.game_type == "dice":
            command = self.cog.bot.get_command("dice")
        elif self.game_type == "slots":
            command = self.cog.bot.get_command("slots")
        else:
            return

        # Create a new context and invoke the command
        new_ctx = await self.cog.bot.get_context(interaction.message)
        new_ctx.author = self.ctx.author # Ensure correct author
        await command.invoke(new_ctx, bet=self.bet)

# ------------------- GAMBLING COG -------------------

class GamblingCog(commands.Cog, name="Gambling"):
    """Gambling system with improved odds and security features."""
    
    def __init__(self, bot):
        self.bot = bot
        self.security_manager = GamblingSecurityManager()
        # --- LOTTERY DATA ---
        self.lottery_pot = 0
        self.lottery_ticket_price = 100 # Price per ticket
        self.lottery_entries = {} # {user_id: num_tickets}
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
        
        # Maximum bet limit for security (admin bypasses this check in practice by bypassing cooldowns)
        max_bet = min(100000, user_data["wallet_limit"] // 10)
        if bet > max_bet and not is_bot_admin(ctx.author):
            return False, f"Maximum bet allowed is {self.format_money(max_bet)} for security reasons."
        
        return True, "OK"

    # ========== GAMBLING COMMANDS ==========
    
    @commands.command(name="flip", aliases=["coinflip", "coin", "cf"])
    async def coin_flip(self, ctx: commands.Context, bet: int = None, *, choice: str = None):
        """Flip a coin with improved 60% win chance and 1.9x payout."""
        try:
            if not bet:
                embed = await self.create_gambling_embed("🎲 Coin Flip Game", discord.Color.blue())
                embed.description = (
                    "Flip a coin with improved 60% win chance!\n\n"
                    "**Usage:** `~flip <bet> [heads/tails]`\n"
                    "**Example:** `~flip 100 heads` or `~flip 100` (random choice)\n\n"
                    f"**Payout:** {GamblingConfig.COINFLIP_PAYOUT}x your bet\n"
                    f"**Win Chance:** {GamblingConfig.COINFLIP_WIN_CHANCE * 100:.0f}%\n"
                    "**Cooldown:** 3 seconds"
                )
                await ctx.send(embed=embed)
                return
            
            # --- MODIFIED: Handle random choice ---
            user_choice = choice.lower() if choice else None
            random_choice = False
            if user_choice not in ["heads", "tails"]:
                user_choice = random.choice(["heads", "tails"])
                random_choice = True
            
            # Check cooldown
            # --- MODIFIED: Pass member ---
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "flip", ctx.author)
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
            
            # --- *** LOGIC FIX *** ---
            # Determine outcome with true 60% win chance
            win = random.random() < GamblingConfig.COINFLIP_WIN_CHANCE  # 60% chance to win
            
            if win:
                # User wins!
                coin_result = user_choice # The coin lands on what they chose
                winnings = int(bet * GamblingConfig.COINFLIP_PAYOUT)
                result = await db.update_balance(ctx.author.id, wallet_change=winnings)
                
                embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                embed.description = f"The coin landed on **{coin_result}**! You won {self.format_money(winnings)}!"
                embed.add_field(name="💰 Winnings", value=self.format_money(winnings), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                embed.add_field(name="🎯 Choice", value=user_choice.title(), inline=True)
                
            else:
                # User loses
                coin_result = "tails" if user_choice == "heads" else "heads" # Coin lands on the opposite
                embed = await self.create_gambling_embed("💸 You Lost", discord.Color.red())
                embed.description = f"The coin landed on **{coin_result}**. Better luck next time!"
                embed.add_field(name="📉 Loss", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                embed.add_field(name="🎯 Choice", value=user_choice.title(), inline=True)
            # --- *** END OF FIX *** ---
            
            if random_choice:
                embed.set_footer(text=f"You didn't pick, so I picked {user_choice} for you! | Gamble responsibly")

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
                    "Roll a dice! Win on 3, 4, 5, or 6 with different payouts!\n\n"
                    "**Usage:** `~dice <bet>`\n"
                    "**Example:** `~dice 100`\n\n"
                    "**Winning Numbers & Payouts:**\n"
                    f"• **6**: {GamblingConfig.DICE_PAYOUTS[6]}x your bet\n"
                    f"• **5**: {GamblingConfig.DICE_PAYOUTS[5]}x your bet\n"
                    f"• **4**: {GamblingConfig.DICE_PAYOUTS[4]}x your bet\n"
                    f"• **3**: {GamblingConfig.DICE_PAYOUTS[3]}x your bet\n"
                    "• **1-2**: Lose your bet\n"
                    "**Cooldown:** 4 seconds"
                )
                await ctx.send(embed=embed)
                return
            
            # Check cooldown
            # --- MODIFIED: Pass member ---
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "dice", ctx.author)
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
            
            # --- MODIFIED: Add play again button ---
            view = PlayAgainView(self, ctx, bet, "dice")
            
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
            
            msg = await ctx.send(embed=embed, view=view)
            view.original_message = msg
            
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
                    f"• **Three 7️⃣**: {GamblingConfig.SLOT_PAYOUTS['three_7️⃣']}x\n"
                    f"• **Three 💎**: {GamblingConfig.SLOT_PAYOUTS['three_💎']}x\n"
                    f"• **Three 🍒**: {GamblingConfig.SLOT_PAYOUTS['three_🍒']}x\n"
                    "• **Three 🍊**: 5x\n"
                    "• **Three 🍋**: 3x\n"
                    f"• **Two Matching**: {GamblingConfig.SLOT_PAYOUTS['two_matching']}x\n"
                    "**Cooldown:** 5 seconds"
                )
                await ctx.send(embed=embed)
                return
            
            # Check cooldown
            # --- MODIFIED: Pass member ---
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "slots", ctx.author)
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
            
            # --- MODIFIED: Add play again button ---
            view = PlayAgainView(self, ctx, bet, "slots")
            
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
                embed.add_field(name="🎯 Multiplier", value=f"{GamblingConfig.SLOT_PAYOUTS['two_matching']}x", inline=True)
                
            else:
                # No win
                embed = await self.create_gambling_embed("💸 You Lost", discord.Color.red())
                embed.description = f"**{slot_display}**\n\nNo matches this time. Better luck next spin!"
                embed.add_field(name="📉 Loss", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
            
            # Set cooldown
            self.security_manager.set_cooldown(ctx.author.id, "slots", 5)
            
            msg = await ctx.send(embed=embed, view=view)
            view.original_message = msg
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "slots")
    
    @commands.command(name="rps", aliases=["rockpaperscissors"])
    async def rock_paper_scissors(self, ctx: commands.Context, bet: int = None, *, choice: str = None):
        """Play Rock Paper Scissors with fair rules."""
        try:
            if not bet:
                embed = await self.create_gambling_embed("✂️ Rock Paper Scissors", discord.Color.blue())
                embed.description = (
                    "Play Rock Paper Scissors with fair rules!\n\n"
                    "**Usage:** `~rps <bet> [rock/paper/scissors]`\n"
                    "**Example:** `~rps 100 rock` or `~rps 100` (random choice)\n\n"
                    "**Rules:**\n"
                    f"• **Win**: {GamblingConfig.RPS_PAYOUT}x your bet\n"
                    "• **Tie**: Return your bet\n"
                    "• **Lose**: Lose your bet\n"
                    "**Cooldown:** 3 seconds"
                )
                await ctx.send(embed=embed)
                return
            
            # --- MODIFIED: Handle random choice ---
            user_choice = choice.lower() if choice else None
            random_choice = False
            if user_choice not in ["rock", "paper", "scissors"]:
                user_choice = random.choice(["rock", "paper", "scissors"])
                random_choice = True
            
            # Check cooldown
            # --- MODIFIED: Pass member ---
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "rps", ctx.author)
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
            if user_choice == bot_choice:
                # Tie - return bet
                result = await db.update_balance(ctx.author.id, wallet_change=bet)
                
                embed = await self.create_gambling_embed("🤝 It's a Tie!", discord.Color.orange())
                embed.description = f"**You:** {user_choice.title()} | **Bot:** {bot_choice.title()}\n\nYour bet has been returned!"
                embed.add_field(name="💵 Bet Returned", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                
            elif (user_choice == "rock" and bot_choice == "scissors") or \
                 (user_choice == "paper" and bot_choice == "rock") or \
                 (user_choice == "scissors" and bot_choice == "paper"):
                # User wins
                winnings = int(bet * GamblingConfig.RPS_PAYOUT)
                result = await db.update_balance(ctx.author.id, wallet_change=winnings)
                
                embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                embed.description = f"**You:** {user_choice.title()} | **Bot:** {bot_choice.title()}\n\nYou won {self.format_money(winnings)}!"
                embed.add_field(name="💰 Winnings", value=self.format_money(winnings), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
                embed.add_field(name="🎯 Multiplier", value=f"{GamblingConfig.RPS_PAYOUT}x", inline=True)
                
            else:
                # User loses
                embed = await self.create_gambling_embed("💸 You Lost", discord.Color.red())
                embed.description = f"**You:** {user_choice.title()} | **Bot:** {bot_choice.title()}\n\nBetter luck next time!"
                embed.add_field(name="📉 Loss", value=self.format_money(bet), inline=True)
                embed.add_field(name="💵 New Balance", value=self.format_money(result["wallet"]), inline=True)
            
            if random_choice:
                embed.set_footer(text=f"You didn't pick, so I picked {user_choice} for you! | Gamble responsibly")

            # Set cooldown
            self.security_manager.set_cooldown(ctx.author.id, "rps", 3)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "rps")

    @commands.command(name="blackjack", aliases=["bj"])
    async def blackjack(self, ctx: commands.Context, bet: int = None):
        """Play a game of Blackjack with buttons."""
        try:
            if not bet:
                embed = await self.create_gambling_embed("🃏 Blackjack", discord.Color.blue())
                embed.description = (
                    "Play Blackjack against the dealer!\n\n"
                    "**Usage:** `~bj <bet>`\n"
                    "**Example:** `~bj 100`\n\n"
                    "**Rules:**\n"
                    "• Try to get closer to 21 than the dealer without going over.\n"
                    "• Aces are 1 or 11.\n"
                    "• Dealer stands on 17.\n"
                    "• **Payout:** 1:1\n"
                    "**Cooldown:** 10 seconds"
                )
                await ctx.send(embed=embed)
                return

            # Check cooldown
            can_play, cooldown_remaining = await self.security_manager.check_cooldown(ctx.author.id, "blackjack", ctx.author)
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

            # Remove bet from wallet
            await db.update_balance(ctx.author.id, wallet_change=-bet)

            # Create game view
            view = BlackjackView(self, ctx, bet)
            
            # Initial game state
            player_value = view.get_hand_value(view.player_hand)
            
            # Check for immediate Blackjack
            if player_value == 21:
                # Blackjack!
                winnings = int(bet * 2.5) # 3:2 payout for BJ
                await view.end_game(ctx, f"**BLACKJACK!** You win {self.format_money(winnings - bet)}!", discord.Color.gold(), winnings)
                self.security_manager.set_cooldown(ctx.author.id, "blackjack", 10)
                return

            embed = await view.create_game_embed("Hit or Stand?")
            await ctx.send(embed=embed, view=view)
            self.security_manager.set_cooldown(ctx.author.id, "blackjack", 10)

        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "blackjack")

    @commands.command(name="beg")
    async def beg(self, ctx: commands.Context):
        """Beg for money with a cooldown."""
        try:
            # Check cooldown
            remaining = await db.check_cooldown(ctx.author.id, "beg", 300)  # 5 minutes
            
            # --- MODIFIED: Add admin bypass ---
            if remaining and not is_bot_admin(ctx.author):
                embed = await self.create_gambling_embed("⏰ Already Begged Recently", discord.Color.orange())
                embed.description = f"You can beg again in **{int(remaining)} seconds**."
                await ctx.send(embed=embed)
                return
            
            user_data = await db.get_user(ctx.author.id)
            
            # Determine if begging is successful
            success = random.random() < 0.8  # 80% success rate
            
            if success:
                # Successful beg
                amount = random.randint(50, 150) # Increased reward
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
            
    # ------------------- LOTTERY COMMANDS -------------------

    @commands.group(name="lottery", invoke_without_command=True)
    async def lottery(self, ctx: commands.Context):
        """Main lottery command. Shows info."""
        await self.lottery_info(ctx)

    @lottery.command(name="info")
    async def lottery_info(self, ctx: commands.Context):
        """Shows the current lottery status."""
        embed = await self.create_gambling_embed("🎟️ Lottery Status", discord.Color.blue())
        
        total_tickets = sum(self.lottery_entries.values())
        user_tickets = self.lottery_entries.get(ctx.author.id, 0)
        
        win_chance = (user_tickets / total_tickets * 100) if total_tickets > 0 else 0
        
        embed.add_field(name="💰 Current Pot", value=self.format_money(self.lottery_pot), inline=True)
        embed.add_field(name="🎫 Ticket Price", value=self.format_money(self.lottery_ticket_price), inline=True)
        embed.add_field(name="📈 Total Tickets", value=f"{total_tickets:,}", inline=True)
        
        embed.add_field(name="👤 Your Tickets", value=f"{user_tickets:,}", inline=True)
        embed.add_field(name="🎯 Your Win Chance", value=f"{win_chance:.2f}%", inline=True)
        
        embed.set_footer(text="Use ~lottery buy <amount> to buy tickets!")
        await ctx.send(embed=embed)

    @lottery.command(name="buy")
    async def lottery_buy(self, ctx: commands.Context, amount: int = None):
        """Buy lottery tickets."""
        if not amount or amount <= 0:
            return await ctx.send("Please specify a positive number of tickets to buy.")
        
        cost = amount * self.lottery_ticket_price
        
        user_data = await db.get_user(ctx.author.id)
        if user_data["wallet"] < cost:
            return await ctx.send(f"You don't have enough money in your wallet. You need {self.format_money(cost)}.")
        
        # Take money and add tickets
        await db.update_balance(ctx.author.id, wallet_change=-cost)
        
        self.lottery_entries[ctx.author.id] = self.lottery_entries.get(ctx.author.id, 0) + amount
        self.lottery_pot += cost
        
        await ctx.send(f"✅ You successfully bought {amount:,} lottery ticket(s) for {self.format_money(cost)}!")

    @lottery.command(name="draw")
    @commands.check(lambda ctx: is_bot_admin(ctx.author))
    async def lottery_draw(self, ctx: commands.Context):
        """Draw the lottery winner (Admin only)."""
        if not self.lottery_entries:
            return await ctx.send("There are no entries in the lottery. Cannot draw a winner.")
        
        # Create a weighted list of all participants
        weighted_list = []
        for user_id, num_tickets in self.lottery_entries.items():
            weighted_list.extend([user_id] * num_tickets)
        
        if not weighted_list:
            return await ctx.send("Lottery is empty.")

        winner_id = random.choice(weighted_list)
        winner = self.bot.get_user(winner_id) or await self.bot.fetch_user(winner_id)
        
        winnings = self.lottery_pot
        
        # Give winnings to winner
        await db.update_balance(winner_id, wallet_change=winnings)
        
        embed = await self.create_gambling_embed("🎉 Lottery Winner!", discord.Color.gold())
        embed.description = f"**Congratulations {winner.mention}!**\n\nYou won the lottery pot of **{self.format_money(winnings)}**!"
        
        # Reset lottery
        self.lottery_pot = 0
        self.lottery_entries = {}
        
        await ctx.send(embed=embed)

    @lottery_draw.error
    async def draw_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ This command is for bot admins only.")
        else:
            await ErrorHandler.handle_command_error(ctx, error, "lottery draw")

async def setup(bot):
    await bot.add_cog(GamblingCog(bot))
