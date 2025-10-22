import discord
from discord.ext import commands
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from economy import db

class BartenderCog(commands.Cog):
    """Bartender system integrated with main bot economy."""
    
    def __init__(self, bot):
        self.bot = bot
        self.drinks = self._initialize_drinks()
        self.sobering_tasks = {}
        logging.info("✅ Bartender system initialized")
    
    def _initialize_drinks(self) -> Dict:
        """Initialize the drink menu with integrated pricing."""
        return {
            # 🍺 Beers & Ales
            "beer": {
                "name": "🍺 Classic Ale",
                "price": 50,
                "type": "beer",
                "rarity": "common",
                "effects": {"intoxication": 1, "mood_boost": 1},
                "description": "A reliable classic brew"
            },
            "stout": {
                "name": "🍺 Dark Stout", 
                "price": 75,
                "type": "beer",
                "rarity": "common",
                "effects": {"intoxication": 2, "mood_boost": 1},
                "description": "Rich and creamy dark beer"
            },
            "ipa": {
                "name": "🍺 Hoppy IPA",
                "price": 100,
                "type": "beer", 
                "rarity": "common",
                "effects": {"intoxication": 2, "mood_boost": 2},
                "description": "Bitter and aromatic craft beer"
            },
            
            # 🍷 Wines & Spirits
            "redwine": {
                "name": "🍷 House Red",
                "price": 150,
                "type": "wine",
                "rarity": "common", 
                "effects": {"intoxication": 3, "mood_boost": 2},
                "description": "Smooth red wine"
            },
            "whiskey": {
                "name": "🥃 Aged Whiskey",
                "price": 200,
                "type": "spirit",
                "rarity": "rare",
                "effects": {"intoxication": 4, "mood_boost": 2},
                "description": "Premium aged whiskey"
            },
            "vodka": {
                "name": "🥃 Crystal Vodka", 
                "price": 180,
                "type": "spirit",
                "rarity": "common",
                "effects": {"intoxication": 4, "mood_boost": 1},
                "description": "Clear and crisp vodka"
            },
            
            # 🍸 Cocktails
            "martini": {
                "name": "🍸 Classic Martini",
                "price": 250,
                "type": "cocktail",
                "rarity": "rare",
                "effects": {"intoxication": 3, "mood_boost": 3},
                "description": "Sophisticated and clean"
            },
            "mojito": {
                "name": "🍹 Fresh Mojito",
                "price": 220,
                "type": "cocktail",
                "rarity": "common",
                "effects": {"intoxication": 2, "mood_boost": 3},
                "description": "Refreshing mint cocktail"
            },
            "oldfashioned": {
                "name": "🥃 Old Fashioned",
                "price": 280,
                "type": "cocktail", 
                "rarity": "rare",
                "effects": {"intoxication": 4, "mood_boost": 2},
                "description": "Timeless whiskey classic"
            },
            
            # 🥤 Non-Alcoholic
            "soda": {
                "name": "🥤 Sparkling Soda",
                "price": 30,
                "type": "soft",
                "rarity": "common",
                "effects": {"intoxication": 0, "mood_boost": 1},
                "description": "Bubbly and refreshing"
            },
            "juice": {
                "name": "🧃 Fresh Juice",
                "price": 40,
                "type": "soft",
                "rarity": "common", 
                "effects": {"intoxication": 0, "mood_boost": 2},
                "description": "Vitamin-packed fruit juice"
            },
            "water": {
                "name": "💧 Mineral Water", 
                "price": 20,
                "type": "soft",
                "rarity": "common",
                "effects": {"intoxication": -1, "mood_boost": 1},
                "description": "Hydrates and sobers up"
            }
        }
    
    def format_money(self, amount: int) -> str:
        """Format money using main bot's system."""
        return f"{amount:,}£"
    
    async def create_bar_embed(self, title: str, color: discord.Color = discord.Color.orange()) -> discord.Embed:
        """Create a standardized bar-themed embed."""
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="🍸 The Tipsy Tavern | Drink responsibly!")
        return embed
    
    async def update_bar_data(self, user_id: int, update_data: Dict):
        """Update user's bar data in the database."""
        user_data = await db.get_user(user_id)
        if "bar_data" not in user_data:
            user_data["bar_data"] = {}
        
        # Merge updates into bar_data
        user_data["bar_data"].update(update_data)
        await db.update_user(user_id, user_data)
    
    async def get_intoxication_level(self, user_id: int) -> int:
        """Get user's current intoxication level."""
        user_data = await db.get_user(user_id)
        return user_data.get("bar_data", {}).get("intoxication_level", 0)
    
    async def apply_drink_effects(self, user_id: int, drink: Dict):
        """Apply drink effects to user."""
        effects = drink["effects"]
        current_intoxication = await self.get_intoxication_level(user_id)
        
        new_intoxication = max(0, current_intoxication + effects["intoxication"])
        
        await self.update_bar_data(user_id, {
            "intoxication_level": new_intoxication,
            "last_drink_time": datetime.now().isoformat()
        })
        
        # Start sobering task if not already running
        if user_id not in self.sobering_tasks:
            self.sobering_tasks[user_id] = asyncio.create_task(
                self.sober_up(user_id)
            )
        
        return new_intoxication
    
    async def sober_up(self, user_id: int):
        """Gradually reduce intoxication over time."""
        await asyncio.sleep(300)  # 5 minutes
        
        user_data = await db.get_user(user_id)
        current_intoxication = user_data.get("bar_data", {}).get("intoxication_level", 0)
        
        if current_intoxication > 0:
            new_intoxication = max(0, current_intoxication - 1)
            await self.update_bar_data(user_id, {
                "intoxication_level": new_intoxication
            })
            
            # Continue sobering if still intoxicated
            if new_intoxication > 0:
                self.sobering_tasks[user_id] = asyncio.create_task(
                    self.sober_up(user_id)
                )
            else:
                del self.sobering_tasks[user_id]
        else:
            del self.sobering_tasks[user_id]
    
    def get_drink_suggestions(self, intoxication: int) -> List[str]:
        """Get appropriate drink suggestions based on intoxication level."""
        if intoxication >= 5:
            return ["water", "soda", "juice"]  # Sobering drinks
        elif intoxication >= 3:
            return ["beer", "soda", "juice"]   # Light drinks
        else:
            return list(self.drinks.keys())    # All drinks
    
    # ========== CORE COMMANDS ==========
    
    @commands.command(name="drink", aliases=["order", "bar"])
    async def drink_menu(self, ctx: commands.Context, drink_type: str = None):
        """View the drink menu or order a drink."""
        if not drink_type:
            await self.show_drink_menu(ctx)
        else:
            await self.order_drink(ctx, drink_type)
    
    async def show_drink_menu(self, ctx: commands.Context):
        """Display the drink menu."""
        embed = await self.create_bar_embed("🍸 Drink Menu")
        
        # Group drinks by type
        drink_types = {}
        for key, drink in self.drinks.items():
            drink_type = drink["type"]
            if drink_type not in drink_types:
                drink_types[drink_type] = []
            drink_types[drink_type].append(drink)
        
        # Add drinks to embed by type
        for drink_type, drinks in drink_types.items():
            drinks_text = ""
            for drink in drinks:
                drinks_text += f"{drink['name']} - {self.format_money(drink['price'])}\n"
            
            type_emoji = {
                "beer": "🍺", "wine": "🍷", "spirit": "🥃", 
                "cocktail": "🍸", "soft": "🥤"
            }.get(drink_type, "🍹")
            
            embed.add_field(
                name=f"{type_emoji} {drink_type.title()}",
                value=drinks_text,
                inline=True
            )
        
        embed.add_field(
            name="💡 How to Order",
            value="Use `~~drink <name>` to order a drink!\nExample: `~~drink beer` or `~~drink martini`",
            inline=False
        )
        
        # Add intoxication-aware suggestions
        intoxication = await self.get_intoxication_level(ctx.author.id)
        if intoxication > 0:
            suggestions = self.get_drink_suggestions(intoxication)
            suggested_drinks = [self.drinks[s]["name"] for s in suggestions[:3]]
            embed.add_field(
                name="🎯 Recommended",
                value=", ".join(suggested_drinks),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    async def order_drink(self, ctx: commands.Context, drink_key: str):
        """Order a specific drink."""
        drink_key = drink_key.lower()
        
        if drink_key not in self.drinks:
            embed = await self.create_bar_embed("❌ Drink Not Found", discord.Color.red())
            embed.description = f"**{drink_key}** is not on the menu. Use `~~drink` to see available drinks."
            
            # Suggest similar drinks
            similar = [k for k in self.drinks.keys() if drink_key in k]
            if similar:
                embed.add_field(
                    name="💡 Did you mean?",
                    value=", ".join(similar[:3]),
                    inline=False
                )
            
            await ctx.send(embed=embed)
            return
        
        drink = self.drinks[drink_key]
        user_data = await db.get_user(ctx.author.id)
        
        # Check if user has enough money
        if user_data["wallet"] < drink["price"]:
            embed = await self.create_bar_embed("❌ Insufficient Funds", discord.Color.red())
            embed.description = (
                f"{drink['name']} costs {self.format_money(drink['price'])}, "
                f"but you only have {self.format_money(user_data['wallet'])} in your wallet.\n\n"
                f"Use `~~withdraw` to get money from your bank, or `~~work` to earn more!"
            )
            await ctx.send(embed=embed)
            return
        
        # Check intoxication level for strong drinks
        intoxication = await self.get_intoxication_level(ctx.author.id)
        if intoxication >= 5 and drink["effects"]["intoxication"] > 0:
            embed = await self.create_bar_embed("🚫 Maybe Slow Down?", discord.Color.orange())
            embed.description = (
                f"You're already quite tipsy! Maybe try a non-alcoholic drink instead?\n\n"
                f"**Recommendations:**\n"
                f"💧 Water - {self.format_money(self.drinks['water']['price'])}\n"
                f"🥤 Soda - {self.format_money(self.drinks['soda']['price'])}\n"
                f"🧃 Juice - {self.format_money(self.drinks['juice']['price'])}"
            )
            await ctx.send(embed=embed)
            return
        
        # Process the drink order
        result = await db.update_balance(ctx.author.id, wallet_change=-drink["price"])
        
        # Update bar data
        new_intoxication = await self.apply_drink_effects(ctx.author.id, drink)
        
        # Track drink in user's history
        bar_updates = {
            "total_drinks_ordered": user_data.get("bar_data", {}).get("total_drinks_ordered", 0) + 1
        }
        
        # Add to drinks tried if new
        drinks_tried = user_data.get("bar_data", {}).get("drinks_tried", [])
        if drink_key not in drinks_tried:
            drinks_tried.append(drink_key)
            bar_updates["drinks_tried"] = drinks_tried
        
        await self.update_bar_data(ctx.author.id, bar_updates)
        
        # Create success embed
        embed = await self.create_bar_embed("🍹 Drink Served!", discord.Color.green())
        embed.description = f"Here's your {drink['name']}! {drink['description']}"
        
        embed.add_field(name="💰 Cost", value=self.format_money(drink["price"]), inline=True)
        embed.add_field(name="💵 Remaining Wallet", value=self.format_money(result["wallet"]), inline=True)
        
        # Show intoxication effect
        if drink["effects"]["intoxication"] > 0:
            intoxication_emoji = "😊" if new_intoxication < 3 else "🥴" if new_intoxication < 5 else "🤪"
            embed.add_field(
                name="🎭 Tipsy Meter", 
                value=f"{intoxication_emoji} Level {new_intoxication}/10",
                inline=True
            )
        
        # Fun responses based on drink type
        responses = {
            "beer": "Cheers! 🍻",
            "wine": "To your health! 🍷", 
            "spirit": "Bottoms up! 🥃",
            "cocktail": "Enjoy your cocktail! 🍸",
            "soft": "Refreshing choice! 🥤"
        }
        
        embed.set_footer(text=responses.get(drink["type"], "Enjoy your drink! 🍹"))
        
        await ctx.send(embed=embed)
    
    @commands.command(name="drinkmenu", aliases=["menu", "barmenu"])
    async def drink_menu_detailed(self, ctx: commands.Context):
        """Show the detailed drink menu."""
        await self.show_drink_menu(ctx)
    
    @commands.command(name="drinkinfo", aliases=["drinkabout"])
    async def drink_info(self, ctx: commands.Context, drink_key: str = None):
        """Get detailed information about a specific drink."""
        if not drink_key:
            embed = await self.create_bar_embed("ℹ️ Drink Information", discord.Color.blue())
            embed.description = "Use `~~drinkinfo <drink>` to learn about a specific drink.\nExample: `~~drinkinfo whiskey`"
            await ctx.send(embed=embed)
            return
        
        drink_key = drink_key.lower()
        
        if drink_key not in self.drinks:
            embed = await self.create_bar_embed("❌ Drink Not Found", discord.Color.red())
            embed.description = f"**{drink_key}** is not on our menu. Use `~~drink` to see available drinks."
            await ctx.send(embed=embed)
            return
        
        drink = self.drinks[drink_key]
        embed = await self.create_bar_embed(f"ℹ️ {drink['name']} Info", discord.Color.blue())
        
        embed.description = drink["description"]
        
        embed.add_field(name="💰 Price", value=self.format_money(drink["price"]), inline=True)
        embed.add_field(name="🎯 Type", value=drink["type"].title(), inline=True)
        embed.add_field(name="⭐ Rarity", value=drink["rarity"].title(), inline=True)
        
        # Effects
        effects_text = ""
        if drink["effects"]["intoxication"] > 0:
            effects_text += f"🍺 Intoxication: +{drink['effects']['intoxication']}\n"
        elif drink["effects"]["intoxication"] < 0:
            effects_text += f"💧 Sobers: {abs(drink['effects']['intoxication'])}\n"
        
        if drink["effects"]["mood_boost"] > 0:
            effects_text += f"😊 Mood Boost: +{drink['effects']['mood_boost']}\n"
        
        if effects_text:
            embed.add_field(name="⚡ Effects", value=effects_text, inline=False)
        
        # Check if user has tried this drink
        user_data = await db.get_user(ctx.author.id)
        drinks_tried = user_data.get("bar_data", {}).get("drinks_tried", [])
        
        if drink_key in drinks_tried:
            embed.add_field(
                name="✅ Drink History", 
                value="You've tried this drink before!",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="mydrinks", aliases=["drinkhistory", "bartab"])
    async def my_drinks(self, ctx: commands.Context, member: discord.Member = None):
        """View your drink history and bar status."""
        member = member or ctx.author
        user_data = await db.get_user(member.id)
        bar_data = user_data.get("bar_data", {})
        
        embed = await self.create_bar_embed(f"🍸 {member.display_name}'s Bar Profile")
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Basic stats
        total_drinks = bar_data.get("total_drinks_ordered", 0)
        drinks_tried = bar_data.get("drinks_tried", [])
        intoxication = bar_data.get("intoxication_level", 0)
        
        embed.add_field(
            name="📊 Bar Stats",
            value=(
                f"**Total Drinks:** {total_drinks}\n"
                f"**Unique Drinks:** {len(drinks_tried)}/{len(self.drinks)}\n"
                f"**Favorite:** {bar_data.get('favorite_drink', 'None yet')}\n"
                f"**Tips Given:** {self.format_money(bar_data.get('tips_given', 0))}\n"
                f"**Tips Received:** {self.format_money(bar_data.get('tips_received', 0))}"
            ),
            inline=True
        )
        
        # Intoxication meter
        intoxication_emoji = "😶" if intoxication == 0 else "😊" if intoxication < 3 else "🥴" if intoxication < 5 else "🤪" if intoxication < 8 else "💀"
        embed.add_field(
            name="🎭 Current State",
            value=(
                f"**Tipsy Level:** {intoxication_emoji} {intoxication}/10\n"
                f"**Wallet:** {self.format_money(user_data['wallet'])}\n"
                f"**Can afford:** {sum(1 for d in self.drinks.values() if d['price'] <= user_data['wallet'])} drinks"
            ),
            inline=True
        )
        
        # Recently tried drinks (last 5)
        if drinks_tried:
            recent_drinks = drinks_tried[-5:] if len(drinks_tried) > 5 else drinks_tried
            recent_text = "\n".join([self.drinks[d]["name"] for d in recent_drinks if d in self.drinks])
            
            embed.add_field(
                name="🕐 Recently Tried",
                value=recent_text or "None yet",
                inline=False
            )
        
        # Patron level based on drinks tried
        patron_level = "Newcomer"
        if len(drinks_tried) >= 10:
            patron_level = "Regular 🥉"
        if len(drinks_tried) >= 20:
            patron_level = "VIP 🥈"  
        if len(drinks_tried) >= 30:
            patron_level = "Bar Legend 🥇"
        
        embed.add_field(
            name="🏆 Patron Status",
            value=patron_level,
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="soberup", aliases=["sober", "water"])
    async def sober_up_command(self, ctx: commands.Context):
        """Order water to help sober up."""
        await self.order_drink(ctx, "water")

    @commands.command(name="drinkbuy", aliases=["buydrink", "giftdrink"])
    async def buy_drink_for_user(self, ctx: commands.Context, member: discord.Member = None, drink_key: str = None):
        """Buy a drink for another user."""
        if not member or not drink_key:
            embed = await self.create_bar_embed("🍻 Buy a Drink for Someone", discord.Color.blue())
            embed.description = "Buy a drink for a friend!\n\n**Usage:** `~~drinkbuy @user <drink>`\n**Example:** `~~drinkbuy @John beer`"
            embed.add_field(
                name="💡 Tip",
                value="Use `~~drink` to see available drinks and prices",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        if member == ctx.author:
            embed = await self.create_bar_embed("❌ Can't Buy Yourself a Drink", discord.Color.red())
            embed.description = "You can't buy a drink for yourself! Use `~~drink <drink>` to order for yourself."
            await ctx.send(embed=embed)
            return
        
        if member.bot:
            embed = await self.create_bar_embed("❌ Can't Buy Bots Drinks", discord.Color.red())
            embed.description = "Bots don't drink! Try buying for a real person."
            await ctx.send(embed=embed)
            return
        
        drink_key = drink_key.lower()
        
        if drink_key not in self.drinks:
            embed = await self.create_bar_embed("❌ Drink Not Found", discord.Color.red())
            embed.description = f"**{drink_key}** is not on the menu. Use `~~drink` to see available drinks."
            await ctx.send(embed=embed)
            return
        
        drink = self.drinks[drink_key]
        user_data = await db.get_user(ctx.author.id)
        
        # Check if user has enough money
        if user_data["wallet"] < drink["price"]:
            embed = await self.create_bar_embed("❌ Insufficient Funds", discord.Color.red())
            embed.description = (
                f"{drink['name']} costs {self.format_money(drink['price'])}, "
                f"but you only have {self.format_money(user_data['wallet'])} in your wallet."
            )
            await ctx.send(embed=embed)
            return
        
        # Process the payment and drink gift
        result = await db.update_balance(ctx.author.id, wallet_change=-drink["price"])
        
        # Update bar data for both users
        await self.update_bar_data(ctx.author.id, {
            "tips_given": user_data.get("bar_data", {}).get("tips_given", 0) + drink["price"]
        })
        
        receiver_data = await db.get_user(member.id)
        await self.update_bar_data(member.id, {
            "tips_received": receiver_data.get("bar_data", {}).get("tips_received", 0) + drink["price"],
            "total_drinks_ordered": receiver_data.get("bar_data", {}).get("total_drinks_ordered", 0) + 1
        })
        
        # Add to receiver's drinks tried if new
        drinks_tried = receiver_data.get("bar_data", {}).get("drinks_tried", [])
        if drink_key not in drinks_tried:
            drinks_tried.append(drink_key)
            await self.update_bar_data(member.id, {"drinks_tried": drinks_tried})
        
        # Create success embed
        embed = await self.create_bar_embed("🎁 Drink Gift Sent!", discord.Color.green())
        embed.description = f"You bought {member.mention} a {drink['name']}! 🍹"
        
        embed.add_field(name="💰 Cost", value=self.format_money(drink["price"]), inline=True)
        embed.add_field(name="💵 Your Wallet", value=self.format_money(result["wallet"]), inline=True)
        embed.add_field(name="🎁 For", value=member.display_name, inline=True)
        
        # Fun gift messages
        gift_messages = [
            f"Cheers to {member.display_name}! 🥂",
            f"That's very generous of you! 💝",
            f"What a great friend! 👏",
            f"Spread the cheer! 🎉"
        ]
        
        embed.set_footer(text=random.choice(gift_messages))
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(BartenderCog(bot))
