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

    # ... (rest of the existing methods remain the same, but update command examples to use ~ instead of ~~)

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
    async def whiskey_menu(self, commands.Context):
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

    # ... (rest of existing methods like order_drink, drink_info, etc. remain the same but update command examples)

async def setup(bot):
    await bot.add_cog(BartenderCog(bot))
