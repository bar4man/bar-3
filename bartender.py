import discord
from discord.ext import commands
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from economy import db
from constants import BartenderConfig  # <-- FIXED IMPORT
from error_handler import ErrorHandler # <-- ADDED IMPORT

# ---------------- Bartender Configuration Constants (REMOVED) ----------------
# All constants are now in constants.py

# ---------------- Bartender Security Manager ----------------
class BartenderSecurityManager:
    """Security manager for bartender system to prevent exploits."""
    
    def __init__(self):
        self.drink_cooldowns = {}
        self.gift_cooldowns = {}
        self.rapid_ordering = {}
    
    async def check_drink_cooldown(self, user_id: int, drink_key: str) -> tuple[bool, float]:
        """Check if user can order a drink (cooldown and global cooldown)."""
        now = datetime.now(timezone.utc).timestamp()
        
        # Global cooldown check
        global_key = f"{user_id}_global"
        if global_key in self.drink_cooldowns:
            global_remaining = self.drink_cooldowns[global_key] - now
            if global_remaining > 0:
                return False, global_remaining
        
        # Specific drink cooldown check
        drink_key_specific = f"{user_id}_{drink_key}"
        if drink_key_specific in self.drink_cooldowns:
            drink_remaining = self.drink_cooldowns[drink_key_specific] - now
            if drink_remaining > 0:
                return False, drink_remaining
        
        return True, 0
    
    def set_drink_cooldown(self, user_id: int, drink_key: str):
        """Set cooldowns for drink ordering."""
        now = datetime.now(timezone.utc).timestamp()
        
        # Set global cooldown
        global_key = f"{user_id}_global"
        self.drink_cooldowns[global_key] = now + BartenderConfig.DRINK_GLOBAL_COOLDOWN
        
        # Set specific drink cooldown
        drink_key_specific = f"{user_id}_{drink_key}"
        self.drink_cooldowns[drink_key_specific] = now + BartenderConfig.DRINK_COOLDOWN
        
        # Clean up old cooldowns periodically
        self._cleanup_old_cooldowns()
    
    async def check_gift_cooldown(self, user_id: int) -> tuple[bool, float]:
        """Check if user can gift a drink."""
        now = datetime.now(timezone.utc).timestamp()
        key = f"{user_id}_gift"
        
        if key in self.gift_cooldowns:
            remaining = self.gift_cooldowns[key] - now
            if remaining > 0:
                return False, remaining
        
        return True, 0
    
    def set_gift_cooldown(self, user_id: int):
        """Set cooldown for drink gifting."""
        now = datetime.now(timezone.utc).timestamp()
        key = f"{user_id}_gift"
        self.gift_cooldowns[key] = now + BartenderConfig.GIFT_COOLDOWN
        
        # Clean up old cooldowns
        self._cleanup_old_cooldowns()
    
    def _cleanup_old_cooldowns(self):
        """Clean up expired cooldowns to prevent memory leaks."""
        now = datetime.now(timezone.utc).timestamp()
        max_age = 3600  # 1 hour
        
        # Clean drink cooldowns
        self.drink_cooldowns = {
            k: v for k, v in self.drink_cooldowns.items() 
            if now - v < max_age
        }
        
        # Clean gift cooldowns
        self.gift_cooldowns = {
            k: v for k, v in self.gift_cooldowns.items() 
            if now - v < max_age
        }
    
    def validate_drink_order(self, user_id: int, drink_key: str, quantity: int = 1) -> tuple[bool, str]:
        """Validate drink order for security and limits."""
        # Check quantity limits
        if quantity <= 0:
            return False, "Quantity must be greater than 0."
        
        if quantity > BartenderConfig.MAX_DRINK_ORDER_AMOUNT:
            return False, f"Cannot order more than {BartenderConfig.MAX_DRINK_ORDER_AMOUNT} drinks at once."
        
        # Check for rapid ordering (anti-spam)
        now = datetime.now(timezone.utc).timestamp()
        key = f"{user_id}_order"
        
        if key not in self.rapid_ordering:
            self.rapid_ordering[key] = []
        
        # Remove old orders (last minute)
        self.rapid_ordering[key] = [t for t in self.rapid_ordering[key] if now - t < 60]
        
        # Check if ordering too rapidly
        if len(self.rapid_ordering[key]) >= 5:  # Max 5 orders per minute
            return False, "You're ordering drinks too rapidly. Please slow down."
        
        self.rapid_ordering[key].append(now)
        
        return True, "OK"

class BartenderCog(commands.Cog):
    """Bartender system with intoxication limits and exploit prevention."""
    
    def __init__(self, bot):
        self.bot = bot
        self.drinks = self._initialize_drinks()
        self.sobering_tasks = {}
        self.security_manager = BartenderSecurityManager()
        self._cooldowns = {}
        logging.info("✅ Bartender system initialized with security features")
    
    def _initialize_drinks(self) -> Dict:
        """Initialize the drink menu with integrated pricing and effects."""
        return {
            # 🍺 Beers & Ales
            "beer": {
                "name": "🍺 Classic Ale",
                "price": 50,
                "type": "beer",
                "rarity": "common",
                "effects": {"intoxication": 1, "mood_boost": 1},
                "description": "A reliable classic brew",
                "cooldown_multiplier": 1.0
            },
            "stout": {
                "name": "🍺 Dark Stout", 
                "price": 75,
                "type": "beer",
                "rarity": "common",
                "effects": {"intoxication": 2, "mood_boost": 1},
                "description": "Rich and creamy dark beer",
                "cooldown_multiplier": 1.2
            },
            "ipa": {
                "name": "🍺 Hoppy IPA",
                "price": 100,
                "type": "beer", 
                "rarity": "common",
                "effects": {"intoxication": 2, "mood_boost": 2},
                "description": "Bitter and aromatic craft beer",
                "cooldown_multiplier": 1.3
            },
            
            # 🍷 Wines & Spirits
            "redwine": {
                "name": "🍷 House Red",
                "price": 150,
                "type": "wine",
                "rarity": "common", 
                "effects": {"intoxication": 3, "mood_boost": 2},
                "description": "Smooth red wine",
                "cooldown_multiplier": 1.5
            },
            "whiskey": {
                "name": "🥃 Aged Whiskey",
                "price": 200,
                "type": "spirit",
                "rarity": "rare",
                "effects": {"intoxication": 4, "mood_boost": 2},
                "description": "Premium aged whiskey",
                "cooldown_multiplier": 2.0
            },
            "vodka": {
                "name": "🥃 Crystal Vodka", 
                "price": 180,
                "type": "spirit",
                "rarity": "common",
                "effects": {"intoxication": 4, "mood_boost": 1},
                "description": "Clear and crisp vodka",
                "cooldown_multiplier": 1.8
            },
            
            # 🍸 Cocktails
            "martini": {
                "name": "🍸 Classic Martini",
                "price": 250,
                "type": "cocktail",
                "rarity": "rare",
                "effects": {"intoxication": 3, "mood_boost": 3},
                "description": "Sophisticated and clean",
                "cooldown_multiplier": 1.7
            },
            "mojito": {
                "name": "🍹 Fresh Mojito",
                "price": 220,
                "type": "cocktail",
                "rarity": "common",
                "effects": {"intoxication": 2, "mood_boost": 3},
                "description": "Refreshing mint cocktail",
                "cooldown_multiplier": 1.4
            },
            "oldfashioned": {
                "name": "🥃 Old Fashioned",
                "price": 280,
                "type": "cocktail", 
                "rarity": "rare",
                "effects": {"intoxication": 4, "mood_boost": 2},
                "description": "Timeless whiskey classic",
                "cooldown_multiplier": 2.0
            },
            
            # 🥤 Non-Alcoholic
            "soda": {
                "name": "🥤 Sparkling Soda",
                "price": 30,
                "type": "soft",
                "rarity": "common",
                "effects": {"intoxication": 0, "mood_boost": 1},
                "description": "Bubbly and refreshing",
                "cooldown_multiplier": 0.5
            },
            "juice": {
                "name": "🧃 Fresh Juice",
                "price": 40,
                "type": "soft",
                "rarity": "common", 
                "effects": {"intoxication": 0, "mood_boost": 2},
                "description": "Vitamin-packed fruit juice",
                "cooldown_multiplier": 0.5
            },
            "water": {
                "name": "💧 Mineral Water", 
                "price": 20,
                "type": "soft",
                "rarity": "common",
                "effects": {"intoxication": -2, "mood_boost": 1},
                "description": "Hydrates and sobers up quickly",
                "cooldown_multiplier": 0.3
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
        """Update user's bar data in the database with validation."""
        user_data = await db.get_user(user_id)
        if "bar_data" not in user_data:
            user_data["bar_data"] = self._get_default_bar_data()
        
        # Validate intoxication level
        if "intoxication_level" in update_data:
            update_data["intoxication_level"] = max(0, min(
                BartenderConfig.MAX_INTOXICATION, 
                update_data["intoxication_level"]
            ))
        
        # Merge updates into bar_data
        user_data["bar_data"].update(update_data)
        await db.update_user(user_id, user_data)
    
    def _get_default_bar_data(self) -> Dict:
        """Get default bar data structure."""
        return {
            "intoxication_level": 0,
            "patron_level": 1,
            "favorite_drink": None,
            "drinks_tried": [],
            "total_drinks_ordered": 0,
            "bar_tab": 0,
            "tips_given": 0,
            "tips_received": 0,
            "sobering_cooldown": None,
            "unlocked_drinks": {},
            "last_drink_time": None,
            "total_spent": 0
        }
    
    async def get_intoxication_level(self, user_id: int) -> int:
        """Get user's current intoxication level with validation."""
        user_data = await db.get_user(user_id)
        intoxication = user_data.get("bar_data", {}).get("intoxication_level", 0)
        return max(0, min(BartenderConfig.MAX_INTOXICATION, intoxication))
    
    async def apply_drink_effects(self, user_id: int, drink: Dict) -> int:
        """Apply drink effects to user with safety limits."""
        effects = drink["effects"]
        current_intoxication = await self.get_intoxication_level(user_id)
        
        # Calculate new intoxication with limits
        intoxication_change = effects["intoxication"]
        new_intoxication = current_intoxication + intoxication_change
        
        # Apply hard limits
        new_intoxication = max(0, min(BartenderConfig.MAX_INTOXICATION, new_intoxication))
        
        await self.update_bar_data(user_id, {
            "intoxication_level": new_intoxication,
            "last_drink_time": datetime.now().isoformat()
        })
        
        # Start sobering task if not already running and not drinking water
        if user_id not in self.sobering_tasks and drink["name"] != "💧 Mineral Water":
            self.sobering_tasks[user_id] = asyncio.create_task(
                self.sober_up(user_id)
            )
        
        # Force sober up if reaching dangerous levels
        if new_intoxication >= BartenderConfig.FORCE_SOBER_LEVEL:
            await self.force_sober_up(user_id)
        
        return new_intoxication
    
    async def sober_up(self, user_id: int):
        """Gradually reduce intoxication over time."""
        await asyncio.sleep(300)  # 5 minutes
        
        # Check if user still exists and needs sobering
        try:
            user_data = await db.get_user(user_id)
            current_intoxication = user_data.get("bar_data", {}).get("intoxication_level", 0)
            
            if current_intoxication > 0:
                new_intoxication = max(0, current_intoxication - BartenderConfig.SOBERING_RATE)
                await self.update_bar_data(user_id, {
                    "intoxication_level": new_intoxication
                })
                
                # Continue sobering if still intoxicated
                if new_intoxication > 0:
                    self.sobering_tasks[user_id] = asyncio.create_task(
                        self.sober_up(user_id)
                    )
                else:
                    if user_id in self.sobering_tasks:
                        del self.sobering_tasks[user_id]
            else:
                if user_id in self.sobering_tasks:
                    del self.sobering_tasks[user_id]
                
        except Exception as e:
            logging.error(f"Error in sober_up for user {user_id}: {e}")
            if user_id in self.sobering_tasks:
                del self.sobering_tasks[user_id]
    
    async def force_sober_up(self, user_id: int):
        """Force sober up for highly intoxicated users."""
        logging.warning(f"🚨 Force sobering up user {user_id} - reached dangerous intoxication levels")
        
        await self.update_bar_data(user_id, {
            "intoxication_level": BartenderConfig.INTOXICATION_WARNING_LEVEL
        })
        
        # Cancel any existing sobering tasks
        if user_id in self.sobering_tasks:
            self.sobering_tasks[user_id].cancel()
            await asyncio.sleep(0.1)  # Allow cancellation to process
        
        # Start rapid sobering
        self.sobering_tasks[user_id] = asyncio.create_task(
            self.rapid_sober_up(user_id)
        )
    
    async def rapid_sober_up(self, user_id: int):
        """Rapid sobering for highly intoxicated users."""
        logging.info(f"🚑 Starting rapid sobering for user {user_id}")
        
        for i in range(3):  # Sober up 3 points quickly
            await asyncio.sleep(30)  # Every 30 seconds
            
            try:
                current = await self.get_intoxication_level(user_id)
                if current > BartenderConfig.INTOXICATION_WARNING_LEVEL:
                    new_level = max(BartenderConfig.INTOXICATION_WARNING_LEVEL, current - 1)
                    await self.update_bar_data(user_id, {
                        "intoxication_level": new_level
                    })
                    logging.info(f"🚑 Rapid sobering {i+1}/3 for user {user_id}: {current} -> {new_level}")
            except Exception as e:
                logging.error(f"Error in rapid_sober_up step {i} for user {user_id}: {e}")
                break
        
        # Continue with normal sobering if still needed
        try:
            current = await self.get_intoxication_level(user_id)
            if current > 0:
                self.sobering_tasks[user_id] = asyncio.create_task(
                    self.sober_up(user_id)
                )
                logging.info(f"🔁 Continuing normal sobering for user {user_id} at level {current}")
            else:
                if user_id in self.sobering_tasks:
                    del self.sobering_tasks[user_id]
                logging.info(f"✅ Completed sobering for user {user_id}")
        except Exception as e:
            logging.error(f"Error finishing rapid sobering for user {user_id}: {e}")
            if user_id in self.sobering_tasks:
                del self.sobering_tasks[user_id]
    
    def get_drink_suggestions(self, intoxication: int) -> List[str]:
        """Get appropriate drink suggestions based on intoxication level."""
        if intoxication >= BartenderConfig.FORCE_SOBER_LEVEL:
            return ["water"]  # Only water when forced sobering
        
        if intoxication >= BartenderConfig.INTOXICATION_DANGER_LEVEL:
            return BartenderConfig.SOBERING_DRINKS + ["soda", "juice"]
        
        if intoxication >= BartenderConfig.INTOXICATION_WARNING_LEVEL:
            return ["beer", "soda", "juice"] + BartenderConfig.SOBERING_DRINKS
        
        # Normal state - all drinks available
        return list(self.drinks.keys())
    
    def get_intoxication_warning(self, level: int) -> Optional[str]:
        """Get warning message based on intoxication level."""
        if level >= BartenderConfig.FORCE_SOBER_LEVEL:
            return "🚨 **HEALTH WARNING!** You've had too much to drink! For your safety, you're being automatically sobered up. Please drink water and take a break."
        
        if level >= BartenderConfig.INTOXICATION_DANGER_LEVEL:
            return "⚠️ **DANGER!** You're heavily intoxicated! Consider switching to non-alcoholic drinks for your health."
        
        if level >= BartenderConfig.INTOXICATION_WARNING_LEVEL:
            return "🔶 **Warning:** You're quite tipsy! Maybe slow down and have some water?"
        
        return None
    
    # ========== CORE COMMANDS ==========
    
    @commands.command(name="drink", aliases=["order", "bar"])
    async def drink_menu(self, ctx: commands.Context, drink_type: str = None):
        """View the drink menu or order a drink with security checks."""
        try:
            if not drink_type:
                await self.show_drink_menu(ctx)
            else:
                await self.order_drink(ctx, drink_type)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "drink")
    
    async def show_drink_menu(self, ctx: commands.Context):
        """Display the drink menu with intoxication-aware suggestions."""
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
            value="Use `~drink <name>` to order a drink!\nExample: `~drink beer` or `~drink martini`",
            inline=False
        )
        
        # Add intoxication-aware suggestions
        intoxication = await self.get_intoxication_level(ctx.author.id)
        if intoxication > 0:
            suggestions = self.get_drink_suggestions(intoxication)
            suggested_drinks = [self.drinks[s]["name"] for s in suggestions[:3] if s in self.drinks]
            
            if suggested_drinks:
                embed.add_field(
                    name="🎯 Recommended Drinks",
                    value=", ".join(suggested_drinks),
                    inline=False
                )
            
            # Add warning if needed
            warning = self.get_intoxication_warning(intoxication)
            if warning:
                embed.add_field(
                    name="🚨 Health Notice",
                    value=warning,
                    inline=False
                )
        
        await ctx.send(embed=embed)
    
    async def order_drink(self, ctx: commands.Context, drink_key: str):
        """Order a specific drink with comprehensive security checks."""
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
        
        # Security validation
        can_order, cooldown_remaining = await self.security_manager.check_drink_cooldown(ctx.author.id, drink_key)
        if not can_order:
            embed = await self.create_bar_embed("⏰ Drink Cooldown", discord.Color.orange())
            embed.description = f"You've ordered this drink too recently. Please wait {int(cooldown_remaining)} seconds."
            await ctx.send(embed=embed)
            return
        
        # Validate order security
        is_valid_order, order_error = self.security_manager.validate_drink_order(ctx.author.id, drink_key)
        if not is_valid_order:
            embed = await self.create_bar_embed("❌ Order Limit", discord.Color.red())
            embed.description = order_error
            await ctx.send(embed=embed)
            return
        
        drink = self.drinks[drink_key]
        user_data = await db.get_user(ctx.author.id)
        intoxication = await self.get_intoxication_level(ctx.author.id)
        
        # Check intoxication limits
        if intoxication >= BartenderConfig.FORCE_SOBER_LEVEL:
            embed = await self.create_bar_embed("🚫 Health Safety Lock", discord.Color.red())
            embed.description = (
                "**HEALTH PROTECTION ACTIVATED!**\n\n"
                "You've reached dangerous intoxication levels. For your safety, "
                "you cannot order more alcoholic drinks until you sober up.\n\n"
                "**Please order:**\n"
                "💧 Water - To help sober up quickly\n"
                "🥤 Soda - For something refreshing\n"
                "🧃 Juice - For vitamins and energy"
            )
            await ctx.send(embed=embed)
            return
        
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
        
        # Warning for high intoxication
        warning_embed = None
        if intoxication >= BartenderConfig.INTOXICATION_WARNING_LEVEL and drink["effects"]["intoxication"] > 0:
            warning_embed = await self.create_bar_embed("🚫 Maybe Slow Down?", discord.Color.orange())
            warning_embed.description = (
                f"You're already at intoxication level {intoxication}/10. "
                f"Consider ordering a non-alcoholic drink instead?\n\n"
                f"**Recommendations:**\n"
                f"💧 Water - {self.format_money(self.drinks['water']['price'])} (sobers you up)\n"
                f"🥤 Soda - {self.format_money(self.drinks['soda']['price'])}\n"
                f"🧃 Juice - {self.format_money(self.drinks['juice']['price'])}"
            )
        
        # Process the drink order
        result = await db.update_balance(ctx.author.id, wallet_change=-drink["price"])
        
        # Update bar data
        new_intoxication = await self.apply_drink_effects(ctx.author.id, drink)
        
        # Track drink in user's history
        bar_updates = {
            "total_drinks_ordered": user_data.get("bar_data", {}).get("total_drinks_ordered", 0) + 1,
            "total_spent": user_data.get("bar_data", {}).get("total_spent", 0) + drink["price"]
        }
        
        # Add to drinks tried if new
        drinks_tried = user_data.get("bar_data", {}).get("drinks_tried", [])
        if drink_key not in drinks_tried:
            drinks_tried.append(drink_key)
            bar_updates["drinks_tried"] = drinks_tried
        
        await self.update_bar_data(ctx.author.id, bar_updates)
        
        # Set cooldown
        self.security_manager.set_drink_cooldown(ctx.author.id, drink_key)
        
        # Create success embed
        embed = await self.create_bar_embed("🍹 Drink Served!", discord.Color.green())
        embed.description = f"Here's your {drink['name']}! {drink['description']}"
        
        embed.add_field(name="💰 Cost", value=self.format_money(drink["price"]), inline=True)
        embed.add_field(name="💵 Remaining Wallet", value=self.format_money(result["wallet"]), inline=True)
        
        # Show intoxication effect
        if drink["effects"]["intoxication"] != 0:
            intoxication_emoji = "🍺" if drink["effects"]["intoxication"] > 0 else "💧"
            intoxication_text = f"+{drink['effects']['intoxication']}" if drink["effects"]["intoxication"] > 0 else str(drink["effects"]["intoxication"])
            
            intoxication_levels = {
                0: "😶 Sober",
                1: "😊 Buzzed",
                2: "😄 Tipsy", 
                3: "🥴 Happy",
                4: "🎉 Merry",
                5: "🤪 Feeling Good",
                6: "🚀 Lit",
                7: "🌪️ Wasted",
                8: "💫 Gone",
                9: "🚑 Danger",
                10: "🏥 Hospital"
            }
            
            embed.add_field(
                name="🎭 Tipsy Meter", 
                value=f"{intoxication_emoji} {intoxication_text} → {intoxication_levels.get(new_intoxication, 'Unknown')} ({new_intoxication}/10)",
                inline=True
            )
        
        # Show cooldown information for strong drinks
        if drink_key in BartenderConfig.STRONG_DRINKS:
            embed.add_field(
                name="⏰ Next Order", 
                value=f"Wait {BartenderConfig.DRINK_COOLDOWN}s before ordering this drink again",
                inline=False
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
        
        # Send warning first if needed, then success message
        if warning_embed:
            warning_msg = await ctx.send(embed=warning_embed)
            await asyncio.sleep(3)  # Show warning for 3 seconds
            await warning_msg.delete()
        
        await ctx.send(embed=embed)
    
    @commands.command(name="drink-menu", aliases=["menu", "bar-menu", "drinkmenu"])
    async def drink_menu_detailed(self, ctx: commands.Context):
        """Show the detailed drink menu."""
        try:
            await self.show_drink_menu(ctx)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "drink-menu")
    
    @commands.command(name="drink-info", aliases=["drinkabout", "drinkinfo"])
    async def drink_info(self, ctx: commands.Context, drink_key: str = None):
        """Get detailed information about a specific drink."""
        try:
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
            
            # Cooldown information
            if drink.get("cooldown_multiplier", 1.0) > 1.0:
                actual_cooldown = int(BartenderConfig.DRINK_COOLDOWN * drink["cooldown_multiplier"])
                embed.add_field(name="⏰ Cooldown", value=f"{actual_cooldown}s (longer for strong drinks)", inline=False)
            
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
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "drink-info")
    
    @commands.command(name="my-drinks", aliases=["drink-history", "bar-tab", "mydrinks", "drinkhistory", "bartab"])
    async def my_drinks(self, ctx: commands.Context, member: discord.Member = None):
        """View your drink history and bar status with safety information."""
        try:
            member = member or ctx.author
            user_data = await db.get_user(member.id)
            bar_data = user_data.get("bar_data", {})
            
            embed = await self.create_bar_embed(f"🍸 {member.display_name}'s Bar Profile")
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Basic stats
            total_drinks = bar_data.get("total_drinks_ordered", 0)
            drinks_tried = bar_data.get("drinks_tried", [])
            intoxication = await self.get_intoxication_level(member.id)
            total_spent = bar_data.get("total_spent", 0)
            
            embed.add_field(
                name="📊 Bar Stats",
                value=(
                    f"**Total Drinks:** {total_drinks}\n"
                    f"**Unique Drinks:** {len(drinks_tried)}/{len(self.drinks)}\n"
                    f"**Total Spent:** {self.format_money(total_spent)}\n"
                    f"**Favorite:** {bar_data.get('favorite_drink', 'None yet')}\n"
                    f"**Tips Given:** {self.format_money(bar_data.get('tips_given', 0))}\n"
                    f"**Tips Received:** {self.format_money(bar_data.get('tips_received', 0))}"
                ),
                inline=True
            )
            
            # Intoxication meter with safety information
            intoxication_emoji = "😶" if intoxication == 0 else "😊" if intoxication < 3 else "🥴" if intoxication < 5 else "🤪" if intoxication < 8 else "💫" if intoxication < 10 else "🚑"
            
            safety_status = "🟢 Sober" if intoxication == 0 else \
                           "🟡 Buzzed" if intoxication < 3 else \
                           "🟠 Tipsy" if intoxication < 5 else \
                           "🔴 Drunk" if intoxication < 8 else \
                           "🚨 Danger" if intoxication < 10 else \
                           "🏥 Emergency"
            
            embed.add_field(
                name="🎭 Current State",
                value=(
                    f"**Tipsy Level:** {intoxication_emoji} {intoxication}/10\n"
                    f"**Safety:** {safety_status}\n"
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
            patron_level = "🍶 Newcomer"
            if len(drinks_tried) >= 10:
                patron_level = "🍺 Regular 🥉"
            if len(drinks_tried) >= 20:
                patron_level = "🍷 VIP 🥈"  
            if len(drinks_tried) >= 30:
                patron_level = "🍾 Bar Legend 🥇"
            
            embed.add_field(
                name="🏆 Patron Status",
                value=patron_level,
                inline=False
            )
            
            # Safety warning if highly intoxicated
            warning = self.get_intoxication_warning(intoxication)
            if warning:
                embed.add_field(
                    name="🚨 Health Notice",
                    value=warning,
                    inline=False
                )
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "my-drinks")
    
    @commands.command(name="sober-up", aliases=["sober", "water"])
    async def sober_up_command(self, ctx: commands.Context):
        """Order water to help sober up with cooldown."""
        try:
            # Check cooldown for sober-up command
            can_order, cooldown_remaining = await self.security_manager.check_drink_cooldown(ctx.author.id, "sober_up")
            if not can_order:
                embed = await self.create_bar_embed("⏰ Cooldown Active", discord.Color.orange())
                embed.description = f"You can use sober-up again in {int(cooldown_remaining)} seconds."
                await ctx.send(embed=embed)
                return
            
            # Set cooldown
            self.security_manager..set_drink_cooldown(ctx.author.id, "sober_up")
            
            # Order water
            await self.order_drink(ctx, "water")
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "sober-up")

    @commands.command(name="drink-buy", aliases=["buy-drink", "gift-drink", "drinkbuy", "buydrink", "giftdrink"])
    async def buy_drink_for_user(self, ctx: commands.Context, member: discord.Member = None, drink_key: str = None):
        """Buy a drink for another user with security checks."""
        try:
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
            
            # Check gift cooldown
            can_gift, cooldown_remaining = await self.security_manager.check_gift_cooldown(ctx.author.id)
            if not can_gift:
                embed = await self.create_bar_embed("⏰ Gift Cooldown", discord.Color.orange())
                embed.description = f"You're sending gifts too quickly! Please wait {int(cooldown_remaining)} seconds."
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
            
            # Check if recipient is too intoxicated for alcoholic drinks
            recipient_intoxication = await self.get_intoxication_level(member.id)
            if recipient_intoxication >= BartenderConfig.FORCE_SOBER_LEVEL and drink["effects"]["intoxication"] > 0:
                embed = await self.create_bar_embed("🚫 Recipient Too Intoxicated", discord.Color.red())
                embed.description = (
                    f"{member.display_name} is too intoxicated for alcoholic drinks right now. "
                    f"Consider buying them a non-alcoholic drink instead for their health."
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
            
            # Apply drink effects to recipient (but don't allow them to get too drunk from gifts)
            if drink["effects"]["intoxication"] > 0:
                current_intoxication = await self.get_intoxication_level(member.id)
                if current_intoxication < BartenderConfig.FORCE_SOBER_LEVEL:
                    await self.apply_drink_effects(member.id, drink)
            
            # Add to receiver's drinks tried if new
            drinks_tried = receiver_data.get("bar_data", {}).get("drinks_tried", [])
            if drink_key not in drinks_tried:
                drinks_tried.append(drink_key)
                await self.update_bar_data(member.id, {"drinks_tried": drinks_tried})
            
            # Set gift cooldown
            self.security_manager.set_gift_cooldown(ctx.author.id)
            
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
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "drink-buy")

async def setup(bot):
    await bot.add_cog(BartenderCog(bot))
