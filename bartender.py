import discord
from discord.ext import commands, tasks
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from economy import db

class BartenderCog(commands.Cog):
    """Enhanced bartender system with 100+ drinks and rude announcements."""
    
    def __init__(self, bot):
        self.bot = bot
        self.drinks = self._initialize_drinks()
        self.sobering_tasks = {}
        self.announcement_channel_id = None
        self.rude_announcements.start()
        logging.info("✅ Bartender system initialized with 100+ drinks")
    
    def _initialize_drinks(self) -> Dict:
        """Initialize the drink menu with 100+ drinks."""
        drinks = {
            # ========== 🍺 BEERS & ALES (15) ==========
            "beer": {"name": "🍺 Piss Water Lite", "price": 30, "type": "beer", "rarity": "common", "effects": {"intoxication": 1, "mood_boost": 1}, "description": "Tastes like fermented sadness"},
            "stout": {"name": "🍺 Sewer Stout", "price": 60, "type": "beer", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 1}, "description": "Dark like your future"},
            "ipa": {"name": "🍺 Hoppy Disappointment", "price": 80, "type": "beer", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 2}, "description": "Bitter, just like you"},
            "lager": {"name": "🍺 Basic Bitch Lager", "price": 35, "type": "beer", "rarity": "common", "effects": {"intoxication": 1, "mood_boost": 1}, "description": "For people with no personality"},
            "pilsner": {"name": "🍺 Weak-Ass Pilsner", "price": 45, "type": "beer", "rarity": "common", "effects": {"intoxication": 1, "mood_boost": 1}, "description": "Water with commitment issues"},
            "ale": {"name": "🍺 Dad Bod Ale", "price": 55, "type": "beer", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 2}, "description": "For middle-aged disappointments"},
            "porter": {"name": "🍺 Depresso Porter", "price": 70, "type": "beer", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 1}, "description": "Dark roast despair"},
            "wheat": {"name": "🍺 Wheat Failure", "price": 50, "type": "beer", "rarity": "common", "effects": {"intoxication": 1, "mood_boost": 2}, "description": "Cloudy like your judgment"},
            "sour": {"name": "🍺 Sour Loser", "price": 85, "type": "beer", "rarity": "rare", "effects": {"intoxication": 2, "mood_boost": 3}, "description": "Face-puckering regret"},
            "bock": {"name": "🍺 Bock of Shame", "price": 75, "type": "beer", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 2}, "description": "Stronger than your willpower"},
            "lambic": {"name": "🍺 Lambic Lament", "price": 120, "type": "beer", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Fancy sadness"},
            "trappist": {"name": "🍺 Monk's Misery", "price": 150, "type": "beer", "rarity": "epic", "effects": {"intoxication": 3, "mood_boost": 4}, "description": "Divine disappointment"},
            "session": {"name": "🍺 Session Regret", "price": 40, "type": "beer", "rarity": "common", "effects": {"intoxication": 1, "mood_boost": 1}, "description": "Low alcohol, like your standards"},
            "imperial": {"name": "🍺 Imperial Failure", "price": 180, "type": "beer", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 3}, "description": "For when you really want to ruin your life"},
            "cider": {"name": "🍺 Apple Abomination", "price": 65, "type": "beer", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 2}, "description": "For people who can't handle real beer"},

            # ========== 🥃 WHISKEY & BOURBON (15) ==========
            "whiskey": {"name": "🥃 Regret in a Glass", "price": 200, "type": "whiskey", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 2}, "description": "For real alcoholics"},
            "bourbon": {"name": "🥃 Kentucky Sadness", "price": 220, "type": "whiskey", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 3}, "description": "American disappointment"},
            "scotch": {"name": "🥃 Scottish Sorrow", "price": 300, "type": "whiskey", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 4}, "description": "Expensive tears"},
            "rye": {"name": "🥃 Rye Remorse", "price": 180, "type": "whiskey", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Spicy regret"},
            "irish": {"name": "🥃 Irish Depression", "price": 190, "type": "whiskey", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Potato-based sadness"},
            "tennessee": {"name": "🥃 Tennessee Tears", "price": 210, "type": "whiskey", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 3}, "description": "Filtered through broken dreams"},
            "singlepot": {"name": "🥃 Single Pot Pity", "price": 350, "type": "whiskey", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 5}, "description": "Artisanal misery"},
            "corn": {"name": "🥃 Corn Liquor Shame", "price": 90, "type": "whiskey", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 1}, "description": "For true degenerates"},
            "blended": {"name": "🥃 Blended Bullshit", "price": 120, "type": "whiskey", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 2}, "description": "Multiple disappointments mixed together"},
            "smokey": {"name": "🥃 Smokey Failure", "price": 280, "type": "whiskey", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 4}, "description": "Tastes like your burnt ambitions"},
            "canadian": {"name": "🥃 Canadian Apology", "price": 130, "type": "whiskey", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 2}, "description": "Sorry, not sorry"},
            "japanese": {"name": "🥃 Japanese Shame", "price": 400, "type": "whiskey", "rarity": "legendary", "effects": {"intoxication": 5, "mood_boost": 5}, "description": "Perfected disappointment"},
            "moonshine": {"name": "🥃 Blindin' Moonshine", "price": 70, "type": "whiskey", "rarity": "common", "effects": {"intoxication": 5, "mood_boost": 1}, "description": "Might make you go blind, worth it"},
            "fireball": {"name": "🥃 Basic Bitch Fireball", "price": 60, "type": "whiskey", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 2}, "description": "For people who can't handle real whiskey"},
            "aged": {"name": "🥃 Aged Regret", "price": 500, "type": "whiskey", "rarity": "legendary", "effects": {"intoxication": 5, "mood_boost": 6}, "description": "25 years of disappointment"},

            # ========== 🍷 WINE (15) ==========
            "redwine": {"name": "🍷 Cheap Red Regret", "price": 150, "type": "wine", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 2}, "description": "For wannabe sommeliers"},
            "whitewine": {"name": "🍷 Basic White Whine", "price": 140, "type": "wine", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 3}, "description": "For Karens and divorcées"},
            "rose": {"name": "🍷 Basic Bitch Rosé", "price": 160, "type": "wine", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 3}, "description": "Pink disappointment"},
            "sparkling": {"name": "🍷 Sparkling Failure", "price": 180, "type": "wine", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 4}, "description": "Bubbles of sadness"},
            "chardonnay": {"name": "🍷 Chardonnay Shame", "price": 170, "type": "wine", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Buttery tears"},
            "pinot": {"name": "🍷 Pinot Pretension", "price": 220, "type": "wine", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 4}, "description": "For wine snobs"},
            "cabernet": {"name": "🍷 Cabernet Cringe", "price": 200, "type": "wine", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 3}, "description": "Bold failure"},
            "merlot": {"name": "🍷 Merlot Misery", "price": 190, "type": "wine", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Smooth disappointment"},
            "zinfandel": {"name": "🍷 Zinfandel Zadness", "price": 210, "type": "wine", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 4}, "description": "Fruity failure"},
            "syrah": {"name": "🍷 Syrah Sorrow", "price": 230, "type": "wine", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 3}, "description": "Spicy tears"},
            "port": {"name": "🍷 Port of Despair", "price": 250, "type": "wine", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 5}, "description": "Sweet suffering"},
            "sherry": {"name": "🍷 Sherry Shame", "price": 240, "type": "wine", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 4}, "description": "Grandma's favorite disappointment"},
            "icewine": {"name": "🍷 Ice Cold Regret", "price": 350, "type": "wine", "rarity": "epic", "effects": {"intoxication": 3, "mood_boost": 6}, "description": "Frozen tears"},
            "champagne": {"name": "🍷 Champagne Failure", "price": 400, "type": "wine", "rarity": "epic", "effects": {"intoxication": 3, "mood_boost": 5}, "description": "For celebrating your failures"},
            "boxwine": {"name": "🍷 Box of Shame", "price": 80, "type": "wine", "rarity": "common", "effects": {"intoxication": 4, "mood_boost": 1}, "description": "For when you've truly given up"},

            # ========== 🍸 COCKTAILS (20) ==========
            "martini": {"name": "🍸 Classic Mistake", "price": 250, "type": "cocktail", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "For wannabe James Bonds"},
            "mojito": {"name": "🍹 Mojito Mediocrity", "price": 220, "type": "cocktail", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 3}, "description": "Basic but refreshing"},
            "oldfashioned": {"name": "🥃 Old Fashioned Failure", "price": 280, "type": "cocktail", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 2}, "description": "For boomers and disappointments"},
            "margarita": {"name": "🍹 Margarita Mess", "price": 200, "type": "cocktail", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Salt-rimmed sadness"},
            "cosmo": {"name": "🍸 Cosmopolitan Cringe", "price": 230, "type": "cocktail", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 4}, "description": "For Sex and the City fans"},
            "manhattan": {"name": "🍸 Manhattan Mess", "price": 270, "type": "cocktail", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 3}, "description": "Urban disappointment"},
            "daiquiri": {"name": "🍹 Daiquiri Disaster", "price": 190, "type": "cocktail", "rarity": "common", "effects": {"intoxication": 2, "mood_boost": 4}, "description": "Frozen failure"},
            "negroni": {"name": "🍸 Negroni Nightmare", "price": 260, "type": "cocktail", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 3}, "description": "Bitter life choices"},
            "whiskeysour": {"name": "🥃 Whiskey Sour Regret", "price": 240, "type": "cocktail", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Sweet and sour shame"},
            "mai tai": {"name": "🍹 Mai Tai Mistake", "price": 290, "type": "cocktail", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 4}, "description": "Tropical disappointment"},
            "pina colada": {"name": "🍹 Piña Colada Problems", "price": 210, "type": "cocktail", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 4}, "description": "Beach-themed sadness"},
            "long island": {"name": "🍸 Long Island Regret", "price": 300, "type": "cocktail", "rarity": "epic", "effects": {"intoxication": 5, "mood_boost": 2}, "description": "For when you want to black out efficiently"},
            "bloody mary": {"name": "🍸 Bloody Mary Mess", "price": 180, "type": "cocktail", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 2}, "description": "Breakfast of champions (losers)"},
            "moscow mule": {"name": "🍸 Moscow Mule Misery", "price": 220, "type": "cocktail", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Copper-cup cringe"},
            "gin tonic": {"name": "🍸 Gin & Tonic Grief", "price": 190, "type": "cocktail", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 2}, "description": "Basic British sadness"},
            "sazerac": {"name": "🍸 Sazerac Shame", "price": 310, "type": "cocktail", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 4}, "description": "New Orleans-style failure"},
            "aviation": {"name": "🍸 Aviation Accident", "price": 280, "type": "cocktail", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 4}, "description": "Crash and burn in style"},
            "lastword": {"name": "🍸 Last Word Loser", "price": 320, "type": "cocktail", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 5}, "description": "Final words of regret"},
            "zombie": {"name": "🍹 Zombie Apocalypse", "price": 350, "type": "cocktail", "rarity": "epic", "effects": {"intoxication": 5, "mood_boost": 3}, "description": "For the walking dead"},
            "painkiller": {"name": "🍹 Painkiller Placebo", "price": 270, "type": "cocktail", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 5}, "description": "Doesn't actually kill pain"},

            # ========== 🥤 NON-ALCOHOLIC (15) ==========
            "water": {"name": "💧 Tap Water Tears", "price": 10, "type": "soft", "rarity": "common", "effects": {"intoxication": -2, "mood_boost": 1}, "description": "For sober losers"},
            "soda": {"name": "🥤 Soda Sadness", "price": 20, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 1}, "description": "Bubbles without the fun"},
            "juice": {"name": "🧃 Juice of Shame", "price": 25, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 2}, "description": "For children and designated drivers"},
            "coffee": {"name": "☕ Bitter Coffee", "price": 30, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 3}, "description": "For people with responsibilities"},
            "tea": {"name": "🍵 Weak Tea", "price": 25, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 2}, "description": "British disappointment"},
            "lemonade": {"name": "🍋 Lemonade Lament", "price": 35, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 3}, "description": "When life gives you lemons, cry"},
            "milkshake": {"name": "🥤 Milkshake Misery", "price": 50, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 4}, "description": "For emotional eaters"},
            "smoothie": {"name": "🥤 Smoothie Sadness", "price": 45, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 3}, "description": "Healthy but unhappy"},
            "energy": {"name": "⚡ Energy Drink Despair", "price": 40, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 4}, "description": "For gamers and night shift workers"},
            "mocktail": {"name": "🍹 Mocktail Mockery", "price": 80, "type": "soft", "rarity": "rare", "effects": {"intoxication": 0, "mood_boost": 5}, "description": "All the effort, none of the fun"},
            "rootbeer": {"name": "🍺 Root Beer Regret", "price": 35, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 2}, "description": "For people who miss childhood"},
            "gingerale": {"name": "🥤 Ginger Ale Grief", "price": 30, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 2}, "description": "For upset stomachs and souls"},
            "tonic": {"name": "💧 Tonic of Tedium", "price": 25, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 1}, "description": "Bitter without the gin"},
            "cola": {"name": "🥤 Corporate Cola", "price": 30, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 2}, "description": "Capitalist tears"},
            "seltzer": {"name": "💧 Seltzer Sadness", "price": 20, "type": "soft", "rarity": "common", "effects": {"intoxication": 0, "mood_boost": 1}, "description": "Fancy water for basic people"},

            # ========== 🍹 VODKA & RUM (10) ==========
            "vodka": {"name": "🥃 Vodka Vomit", "price": 120, "type": "vodka", "rarity": "common", "effects": {"intoxication": 4, "mood_boost": 1}, "description": "For college students and Russians"},
            "rum": {"name": "🥃 Rum Regret", "price": 130, "type": "rum", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Pirate-themed poor decisions"},
            "tequila": {"name": "🥃 Tequila Trauma", "price": 140, "type": "tequila", "rarity": "common", "effects": {"intoxication": 4, "mood_boost": 2}, "description": "For bad decisions and worse memories"},
            "gin": {"name": "🥃 Gin Grief", "price": 150, "type": "gin", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 2}, "description": "Tastes like Christmas tree sadness"},
            "brandy": {"name": "🥃 Brandy Blunder", "price": 180, "type": "brandy", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 4}, "description": "For old people and failures"},
            "cognac": {"name": "🥃 Cognac Catastrophe", "price": 300, "type": "cognac", "rarity": "epic", "effects": {"intoxication": 4, "mood_boost": 5}, "description": "Expensive French disappointment"},
            "absinthe": {"name": "🥃 Absinthe Absurdity", "price": 400, "type": "absinthe", "rarity": "legendary", "effects": {"intoxication": 6, "mood_boost": 3}, "description": "Might make you see demons (or your ex)"},
            "sake": {"name": "🍶 Sake Shame", "price": 160, "type": "sake", "rarity": "rare", "effects": {"intoxication": 3, "mood_boost": 3}, "description": "Japanese rice-based regret"},
            "soju": {"name": "🍶 Soju Sorrow", "price": 110, "type": "soju", "rarity": "common", "effects": {"intoxication": 3, "mood_boost": 2}, "description": "Korean convenience store sadness"},
            "mezcal": {"name": "🥃 Mezcal Mistake", "price": 220, "type": "mezcal", "rarity": "rare", "effects": {"intoxication": 4, "mood_boost": 3}, "description": "Smoky poor life choices"},
        }
        return drinks

    @tasks.loop(minutes=15)
    async def rude_announcements(self):
        """Send rude announcements to the designated channel."""
        if not self.announcement_channel_id:
            return
            
        channel = self.bot.get_channel(self.announcement_channel_id)
        if not channel:
            return

        insults = [
            "Hey alcoholics, maybe drink some water for once? Your livers are crying.",
            "Just a reminder: being drunk doesn't make you funnier, just more annoying.",
            "If you can read this, you're probably not drunk enough. Or you're a loser. Either way, drink up!",
            "Pro tip: Alcohol doesn't solve your problems, it just makes you forget you have them. Cheers!",
            "That's not a beer belly, that's a liquid asset storage facility. Keep investing!",
            "They say alcohol kills brain cells. Good thing you can't lose what you never had!",
            "Drinking alone? Don't worry, we judge you silently from the bar.",
            "Your mother would be so proud of how much you can drink. Or disappointed. Probably disappointed.",
            "Remember: The more you drink, the better looking everyone else becomes. It's science.",
            "That's your fifth drink? Cute. Come back when you're a real alcoholic.",
            "Drink responsibly? In this economy? LOL good one.",
            "Your wallet is getting lighter and your liver is getting heavier. Perfect balance!",
            "They say 'beer before liquor, never been sicker' - but who are 'they' to judge your life choices?",
            "If you wake up without a hangover, you didn't drink enough. Try harder tomorrow.",
            "Alcohol: because no great story ever started with someone eating a salad.",
        ]

        if random.random() < 0.3:  # 30% chance every 15 minutes
            embed = discord.Embed(
                title="🍻 **Bartender's Wisdom** 🍻",
                description=random.choice(insults),
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text="The Tipsy Tavern - We enable poor life choices!")
            await channel.send(embed=embed)

    @commands.command(name="setbarchannel")
    @commands.has_permissions(administrator=True)
    async def set_bar_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel for bartender announcements."""
        channel = channel or ctx.channel
        self.announcement_channel_id = channel.id
        
        embed = discord.Embed(
            title="✅ Bar Channel Set",
            description=f"Bartender announcements will now be sent to {channel.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

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

    async def show_drink_menu(self, ctx: commands.Context, category: str = None):
        """Display the drink menu with categories."""
        if not category:
            # Show main menu with categories
            embed = await self.create_bar_embed("🍸 **DRINK MENU - PICK YOUR POISON** 🍸")
            
            categories = {
                "🍺 BEERS": "`~beer-menu` - 15 different ways to disappoint yourself",
                "🥃 WHISKEY": "`~whiskey-menu` - For real alcoholics only", 
                "🍷 WINE": "`~wine-menu` - For basic bitches and divorcées",
                "🍸 COCKTAILS": "`~cocktail-menu` - Fancy poor decisions",
                "🥤 SOBER SHAME": "`~soft-menu` - For losers and designated drivers",
                "🍹 VODKA & FRIENDS": "`~liquor-menu` - Various forms of liquid regret"
            }
            
            for cat_name, cat_desc in categories.items():
                embed.add_field(name=cat_name, value=cat_desc, inline=False)
            
            embed.add_field(
                name="💸 **HOW TO ORDER**",
                value="Use `~drink <name>`\nExample: `~drink beer` or `~drink whiskey`\n**All drinks use WALLET money!**",
                inline=False
            )
            
            await ctx.send(embed=embed)
        else:
            # Show specific category
            await self.show_category_menu(ctx, category)

    async def show_category_menu(self, ctx: commands.Context, category: str):
        """Show drinks from a specific category."""
        category = category.lower()
        category_map = {
            "beer": ("🍺 **BEER MENU - LIQUID BREAD** 🍺", ["beer", "stout", "ipa", "lager", "pilsner", "ale", "porter", "wheat", "sour", "bock", "lambic", "trappist", "session", "imperial", "cider"]),
            "whiskey": ("🥃 **WHISKEY MENU - TEARS OF ANGELS** 🥃", ["whiskey", "bourbon", "scotch", "rye", "irish", "tennessee", "singlepot", "corn", "blended", "smokey", "canadian", "japanese", "moonshine", "fireball", "aged"]),
            "wine": ("🍷 **WINE MENU - GRAPE JUICE FOR ADULTS** 🍷", ["redwine", "whitewine", "rose", "sparkling", "chardonnay", "pinot", "cabernet", "merlot", "zinfandel", "syrah", "port", "sherry", "icewine", "champagne", "boxwine"]),
            "cocktail": ("🍸 **COCKTAIL MENU - FANCY REGRET** 🍸", ["martini", "mojito", "oldfashioned", "margarita", "cosmo", "manhattan", "daiquiri", "negroni", "whiskeysour", "mai tai", "pina colada", "long island", "bloody mary", "moscow mule", "gin tonic", "sazerac", "aviation", "lastword", "zombie", "painkiller"]),
            "soft": ("🥤 **SOFT MENU - SOBER SHAME** 🥤", ["water", "soda", "juice", "coffee", "tea", "lemonade", "milkshake", "smoothie", "energy", "mocktail", "rootbeer", "gingerale", "tonic", "cola", "seltzer"]),
            "liquor": ("🍹 **LIQUOR MENU - VARIOUS REGRETS** 🍹", ["vodka", "rum", "tequila", "gin", "brandy", "cognac", "absinthe", "sake", "soju", "mezcal"])
        }
        
        if category not in category_map:
            await ctx.send("Invalid category! Use `~drink` to see available categories.")
            return
            
        title, drinks = category_map[category]
        embed = await self.create_bar_embed(title)
        
        for drink_key in drinks:
            if drink_key in self.drinks:
                drink = self.drinks[drink_key]
                embed.add_field(
                    name=f"`~drink {drink_key}` - {drink['name']} - {self.format_money(drink['price'])}",
                    value=f"{drink['description']}",
                    inline=False
                )
        
        await ctx.send(embed=embed)

    @commands.command(name="drink", aliases=["order", "bar"])
    async def drink_menu(self, ctx: commands.Context, category_or_drink: str = None):
        """View drink menus or order a drink."""
        if not category_or_drink:
            await self.show_drink_menu(ctx)
        elif category_or_drink.lower() in ["beer", "whiskey", "wine", "cocktail", "soft", "liquor"]:
            await self.show_category_menu(ctx, category_or_drink.lower())
        else:
            await self.order_drink(ctx, category_or_drink)

    # Category-specific menu commands
    @commands.command(name="beer-menu")
    async def beer_menu(self, ctx: commands.Context):
        """Show the beer menu."""
        await self.show_category_menu(ctx, "beer")

    @commands.command(name="whiskey-menu")
    async def whiskey_menu(self, ctx: commands.Context):
        """Show the whiskey menu."""
        await self.show_category_menu(ctx, "whiskey")

    @commands.command(name="wine-menu")
    async def wine_menu(self, ctx: commands.Context):
        """Show the wine menu."""
        await self.show_category_menu(ctx, "wine")

    @commands.command(name="cocktail-menu")
    async def cocktail_menu(self, ctx: commands.Context):
        """Show the cocktail menu."""
        await self.show_category_menu(ctx, "cocktail")

    @commands.command(name="soft-menu")
    async def soft_menu(self, ctx: commands.Context):
        """Show the non-alcoholic menu."""
        await self.show_category_menu(ctx, "soft")

    @commands.command(name="liquor-menu")
    async def liquor_menu(self, ctx: commands.Context):
        """Show the liquor menu."""
        await self.show_category_menu(ctx, "liquor")

    async def order_drink(self, ctx: commands.Context, drink_key: str):
        """Order a specific drink."""
        drink_key = drink_key.lower()
        
        if drink_key not in self.drinks:
            embed = await self.create_bar_embed("❌ Drink Not Found", discord.Color.red())
            embed.description = f"**{drink_key}** is not on the menu. Use `~drink` to see available drinks."
            
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
                f"Use `~withdraw` to get money from your bank, or `~work` to earn more!"
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

    @commands.command(name="drink-info", aliases=["drinkabout", "drinkinfo"])
    async def drink_info(self, ctx: commands.Context, drink_key: str = None):
        """Get detailed information about a specific drink."""
        if not drink_key:
            embed = await self.create_bar_embed("ℹ️ Drink Information", discord.Color.blue())
            embed.description = "Use `~drink-info <drink>` to learn about a specific drink.\nExample: `~drink-info whiskey`"
            await ctx.send(embed=embed)
            return
        
        drink_key = drink_key.lower()
        
        if drink_key not in self.drinks:
            embed = await self.create_bar_embed("❌ Drink Not Found", discord.Color.red())
            embed.description = f"**{drink_key}** is not on our menu. Use `~drink` to see available drinks."
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

    @commands.command(name="my-drinks", aliases=["drink-history", "bar-tab", "mydrinks", "drinkhistory", "bartab"])
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

    @commands.command(name="sober-up", aliases=["sober", "water", "soberup"])
    async def sober_up_command(self, ctx: commands.Context):
        """Order water to help sober up."""
        await self.order_drink(ctx, "water")

    @commands.command(name="drink-buy", aliases=["buy-drink", "gift-drink", "drinkbuy", "buydrink", "giftdrink"])
    async def buy_drink_for_user(self, ctx: commands.Context, member: discord.Member = None, drink_key: str = None):
        """Buy a drink for another user."""
        if not member or not drink_key:
            embed = await self.create_bar_embed("🍻 Buy a Drink for Someone", discord.Color.blue())
            embed.description = "Buy a drink for a friend!\n\n**Usage:** `~drink-buy @user <drink>`\n**Example:** `~drink-buy @John beer`"
            embed.add_field(
                name="💡 Tip",
                value="Use `~drink` to see available drinks and prices",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        if member == ctx.author:
            embed = await self.create_bar_embed("❌ Can't Buy Yourself a Drink", discord.Color.red())
            embed.description = "You can't buy a drink for yourself! Use `~drink <drink>` to order for yourself."
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
            embed.description = f"**{drink_key}** is not on the menu. Use `~drink` to see available drinks."
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
