import discord
from discord.ext import commands
import random
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from economy import db

class Gambling(commands.Cog):
    """Gambling games and entertainment commands."""
    
    def __init__(self, bot):
        self.bot = bot
        logging.info("✅ Gambling system initialized")
    
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
        """Beg for some money."""
        # Check cooldown
        remaining = await db.check_cooldown(ctx.author.id, "beg", 300)  # 5 minutes
        if remaining:
            embed = await self.create_gambling_embed("⏰ Already Begged Recently", discord.Color.orange())
            embed.description = f"You can beg again in **{int(remaining)} seconds**"
            return await ctx.send(embed=embed)
        
        # Random chance to succeed (80% success rate)
        if random.random() < 0.8:
            amount = random.randint(10, 70)
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
        
        await db.set_cooldown(ctx.author.id, "beg")
        await ctx.send(embed=embed)
    
    @commands.command(name="rps", aliases=["rockpaperscissors"])
    async def rps(self, ctx: commands.Context, choice: str = None, bet: int = None):
        """Play Rock Paper Scissors."""
        if not choice or not bet:
            embed = await self.create_gambling_embed("✂️ Rock Paper Scissors", discord.Color.blue())
            embed.description = "Play Rock Paper Scissors against the bot!\n\n**Usage:** `~~rps <rock/paper/scissors> <bet>`"
            embed.add_field(name="Example", value="`~~rps rock 100` - Bet 100£ on rock", inline=False)
            embed.add_field(name="Payout", value="**2x** your bet if you win!", inline=False)
            embed.add_field(name="Rules", value="• **Win:** 2x your bet\n• **Tie:** Return your bet\n• **Lose:** Lose your bet", inline=False)
            return await ctx.send(embed=embed)
        
        choice = choice.lower()
        if choice not in ["rock", "paper", "scissors"]:
            embed = await self.create_gambling_embed("❌ Invalid Choice", discord.Color.red())
            embed.description = "Please choose either `rock`, `paper`, or `scissors`."
            return await ctx.send(embed=embed)
        
        if bet <= 0:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = "Bet must be greater than 0."
            return await ctx.send(embed=embed)
        
        user_data = await db.get_user(ctx.author.id)
        
        # Check if user has enough money
        if user_data["wallet"] < bet:
            embed = await self.create_gambling_embed("❌ Insufficient Funds", discord.Color.red())
            embed.description = f"You only have {self.format_money(user_data['wallet'])} in your wallet."
            return await ctx.send(embed=embed)
        
        # Bot's choice
        bot_choice = random.choice(["rock", "paper", "scissors"])
        
        # Determine winner
        if choice == bot_choice:
            # Tie - return bet
            result_text = await db.update_balance(ctx.author.id, wallet_change=0)  # No change
            result = "tie"
        elif (choice == "rock" and bot_choice == "scissors") or \
             (choice == "paper" and bot_choice == "rock") or \
             (choice == "scissors" and bot_choice == "paper"):
            # Win - 2x payout
            winnings = bet * 2
            result_text = await db.update_balance(ctx.author.id, wallet_change=winnings - bet)
            result = "win"
        else:
            # Lose
            result_text = await db.update_balance(ctx.author.id, wallet_change=-bet)
            result = "lose"
        
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
        
        await ctx.send(embed=embed)

    @commands.command(name="highlow")
    async def high_low(self, ctx: commands.Context, bet: int = None):
        """Guess if the next card will be higher or lower."""
        if not bet:
            embed = await self.create_gambling_embed("🎴 High-Low Game", discord.Color.blue())
            embed.description = "Guess if the next card will be higher or lower!\n\n**Usage:** `~~highlow <bet>`\nThen react with ⬆️ for higher or ⬇️ for lower."
            embed.add_field(name="Payout", value="**2x** your bet if you guess correctly!", inline=False)
            embed.add_field(name="Cards", value="Ace (low) to King (high)", inline=False)
            return await ctx.send(embed=embed)
        
        if bet <= 0:
            embed = await self.create_gambling_embed("❌ Invalid Bet", discord.Color.red())
            embed.description = "Bet must be greater than 0."
            return await ctx.send(embed=embed)
        
        user_data = await db.get_user(ctx.author.id)
        
        # Check if user has enough money
        if user_data["wallet"] < bet:
            embed = await self.create_gambling_embed("❌ Insufficient Funds", discord.Color.red())
            embed.description = f"You only have {self.format_money(user_data['wallet'])} in your wallet."
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
                winnings = bet * 2
                result_text = await db.update_balance(ctx.author.id, wallet_change=winnings - bet)
                
                result_embed = await self.create_gambling_embed("🎉 You Won!", discord.Color.green())
                result_embed.description = f"First card: **{card_names[first_card]}**\nSecond card: **{card_names[second_card]}**\n\nYou guessed **{user_guess}** correctly and won {self.format_money(winnings)}!"
            else:
                # Lose
                result_text = await db.update_balance(ctx.author.id, wallet_change=-bet)
                
                result_embed = await self.create_gambling_embed("💸 You Lost!", discord.Color.red())
                result_embed.description = f"First card: **{card_names[first_card]}**\nSecond card: **{card_names[second_card]}**\n\nYou guessed **{user_guess}** but it was **{actual_result}**. You lost {self.format_money(bet)}."
            
            result_embed.add_field(name="💵 New Balance", value=f"{self.format_money(result_text['wallet'])} / {self.format_money(result_text['wallet_limit'])}", inline=False)
            
            await message.edit(embed=result_embed)
            await message.clear_reactions()
            
        except asyncio.TimeoutError:
            timeout_embed = await self.create_gambling_embed("⏰ Time's Up!", discord.Color.orange())
            timeout_embed.description = "You didn't make a choice in time. Your bet has been returned."
            await message.edit(embed=timeout_embed)
            await message.clear_reactions()

async def setup(bot):
    await bot.add_cog(Gambling(bot))
