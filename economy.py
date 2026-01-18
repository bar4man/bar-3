# economy.py
import discord
from discord.ext import commands
import motor.motor_asyncio
import asyncio
import random
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
import math
import json
from constants import EconomyConfig
import aiofiles
import glob
from error_handler import ErrorHandler
from admin import is_bot_admin

# ---------------- Backup Manager ----------------
class BackupManager:
    def __init__(self):
        self.backup_dir = "backups"
        self.max_backups = 10
        os.makedirs(self.backup_dir, exist_ok=True)
    
    async def create_backup(self, data: Dict[str, any], backup_type: str):
        """Create a backup of critical data asynchronously."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{self.backup_dir}/{backup_type}_backup_{timestamp}.json"
        
        try:
            async with aiofiles.open(filename, 'w') as f:
                # FIXED: Removed extra 'f' argument in json.dumps
                await f.write(json.dumps(data, indent=2, default=str))
            
            await self._cleanup_old_backups(backup_type)
            logging.info(f"✅ Backup created: {filename}")
            return True
        except Exception as e:
            logging.error(f"❌ Backup failed: {e}")
            return False
    
    async def _cleanup_old_backups(self, backup_type: str):
        """Remove old backups asynchronously to save space."""
        pattern = f"{self.backup_dir}/{backup_type}_backup_*.json"
        loop = asyncio.get_event_loop()
        
        try:
            backups = await loop.run_in_executor(None, glob.glob, pattern)
            if len(backups) > self.max_backups:
                backups.sort()
                for backup_file in backups[:-self.max_backups]:
                    try:
                        await loop.run_in_executor(None, os.remove, backup_file)
                        logging.info(f"🗑️ Removed old backup: {backup_file}")
                    except Exception as e:
                        logging.error(f"❌ Failed to remove backup {backup_file}: {e}")
        except Exception as e:
            logging.error(f"❌ Failed to cleanup backups: {e}")

# ---------------- Enhanced MongoDB Class ----------------
class MongoDB:
    """MongoDB database for economy data with atomic operations and locking."""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.connected = False
        self._locks = {}
        self._lock = asyncio.Lock()
        self._current_schema_version = 2
    
    async def connect(self):
        """Connect to MongoDB Atlas."""
        try:
            connection_string = os.getenv('MONGODB_URI')
            if not connection_string:
                logging.error("❌ MONGODB_URI environment variable not set")
                return False
            
            # Added tlsAllowInvalidCertificates for environments with strict DNS/SSL
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                connection_string,
                serverSelectionTimeoutMS=5000,
                tlsAllowInvalidCertificates=True 
            )
            self.db = self.client.get_database('discord_bot')
            
            await self.client.admin.command('ping')
            self.connected = True
            logging.info("✅ Connected to MongoDB Atlas successfully")
            return True
            
        except Exception as e:
            logging.error(f"❌ MongoDB connection failed: {e}")
            self.connected = False
            return False
    
    def _get_user_lock(self, user_id: int):
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]
    
    async def initialize_collections(self):
        if not self.connected:
            return False
            
        try:
            await self.db.users.create_index("user_id", unique=True)
            await self.db.inventory.create_index([("user_id", 1), ("item_id", 1)])
            await self.db.cooldowns.create_index("created_at", expireAfterSeconds=86400)
            
            shop_count = await self.db.shop.count_documents({})
            if shop_count == 0:
                default_shop = {
                    "items": [
                        {"id": 1, "name": "💰 Small Wallet Upgrade", "description": "Increase your wallet limit by 5,000£", "price": 2000, "type": "upgrade", "effect": {"wallet_limit": 5000}, "emoji": "💰", "stock": -1},
                        {"id": 2, "name": "💳 Medium Wallet Upgrade", "description": "Increase your wallet limit by 15,000£", "price": 8000, "type": "upgrade", "effect": {"wallet_limit": 15000}, "emoji": "💳", "stock": -1},
                        {"id": 3, "name": "💎 Large Wallet Upgrade", "description": "Increase your wallet limit by 50,000£", "price": 25000, "type": "upgrade", "effect": {"wallet_limit": 50000}, "emoji": "💎", "stock": -1},
                        {"id": 4, "name": "🏦 Small Bank Upgrade", "description": "Increase your bank limit by 50,000£", "price": 5000, "type": "upgrade", "effect": {"bank_limit": 50000}, "emoji": "🏦", "stock": -1},
                        {"id": 5, "name": "🏛️ Medium Bank Upgrade", "description": "Increase your bank limit by 150,000£", "price": 15000, "type": "upgrade", "effect": {"bank_limit": 150000}, "emoji": "🏛️", "stock": -1},
                        {"id": 6, "name": "🎯 Large Bank Upgrade", "description": "Increase your bank limit by 500,000£", "price": 50000, "type": "upgrade", "effect": {"bank_limit": 500000}, "emoji": "🎯", "stock": -1}
                    ],
                    "created_at": datetime.now()
                }
                await self.db.shop.insert_one(default_shop)
            
            await self.migrate_user_schema()
            return True
        except Exception as e:
            logging.error(f"❌ MongoDB initialization failed: {e}")
            return False
    
    async def migrate_user_schema(self):
        try:
            async for user in self.db.users.find({"$or": [{"wallet_limit": {"$exists": False}}, {"bank_limit": {"$exists": False}}, {"portfolio": {"$exists": False}}]}):
                update_data = {}
                if "wallet_limit" not in user: update_data["wallet_limit"] = EconomyConfig.DEFAULT_WALLET_LIMIT
                if "bank_limit" not in user: update_data["bank_limit"] = EconomyConfig.DEFAULT_BANK_LIMIT
                if "portfolio" not in user:
                    update_data["portfolio"] = {"gold_ounces": 0.0, "stocks": {}, "total_investment": 0, "total_value": 0, "daily_pnl": 0, "total_pnl": 0}
                update_data["_schema_version"] = self._current_schema_version
                if update_data:
                    await self.db.users.update_one({"_id": user["_id"]}, {"$set": update_data})
        except Exception as e:
            logging.error(f"❌ Error during user schema migration: {e}")
    
    async def get_user(self, user_id: int) -> Dict:
        if not self.connected: return self._get_default_user(user_id)
        try:
            user = await self.db.users.find_one({"user_id": str(user_id)})
            if not user:
                user = self._get_default_user(user_id)
                await self.db.users.insert_one(user)
            elif user.get("_schema_version", 1) < self._current_schema_version:
                user = await self._migrate_user_schema(user)
            return user
        except Exception as e:
            logging.error(f"❌ Error getting user {user_id}: {e}")
            return self._get_default_user(user_id)
    
    async def _migrate_user_schema(self, user: Dict) -> Dict:
        user["_schema_version"] = self._current_schema_version
        await self.update_user(user["user_id"], user)
        return user
    
    def _get_default_user(self, user_id: int) -> Dict:
        return {
            "user_id": str(user_id), "wallet": EconomyConfig.STARTING_MONEY, "wallet_limit": EconomyConfig.DEFAULT_WALLET_LIMIT,
            "bank": 0, "bank_limit": EconomyConfig.DEFAULT_BANK_LIMIT, "networth": EconomyConfig.STARTING_MONEY,
            "daily_streak": 0, "last_daily": None, "total_earned": 0,
            "portfolio": {"gold_ounces": 0.0, "stocks": {}, "total_investment": 0, "total_value": 0, "daily_pnl": 0, "total_pnl": 0},
            "bar_data": {"patron_level": 1, "favorite_drink": None, "drinks_tried": [], "total_drinks_ordered": 0, "bar_tab": 0, "tips_given": 0, "tips_received": 0, "sobering_cooldown": None, "unlocked_drinks": {}},
            "bartender_achievements": [], "created_at": datetime.now(), "last_active": datetime.now(), "_schema_version": self._current_schema_version
        }
    
    async def update_user(self, user_id: int, update_data: Dict):
        if not self.connected: return
        update_data["last_active"] = datetime.now()
        await self.db.users.update_one({"user_id": str(user_id)}, {"$set": update_data}, upsert=True)
    
    async def update_balance_atomic(self, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> Dict:
        async with self._get_user_lock(user_id):
            return await self._update_balance_internal(user_id, wallet_change, bank_change)
    
    async def _update_balance_internal(self, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> Dict:
        if not self.connected: return self._get_default_user(user_id)
        try:
            user = await self.get_user(user_id)
            new_wallet = max(0, user['wallet'] + wallet_change)
            new_bank = max(0, user['bank'] + bank_change)
            
            # Overflow Logic
            wallet_overflow = max(0, new_wallet - user['wallet_limit'])
            if wallet_overflow > 0:
                new_wallet = user['wallet_limit']
                new_bank += wallet_overflow
            
            new_bank = min(new_bank, user['bank_limit'])
            
            update_data = {"$set": {"wallet": new_wallet, "bank": new_bank, "networth": new_wallet + new_bank, "last_active": datetime.now()}}
            if wallet_change + bank_change > 0:
                update_data["$inc"] = {"total_earned": max(0, wallet_change + bank_change)}
                
            return await self.db.users.find_one_and_update({"user_id": str(user_id)}, update_data, return_document=True, upsert=True)
        except Exception as e:
            logging.error(f"❌ Atomic balance update failed for {user_id}: {e}")
            return self._get_default_user(user_id)

    async def check_cooldown(self, user_id: int, command: str, cooldown_seconds: int) -> Optional[float]:
        if not self.connected: return None
        cooldown = await self.db.cooldowns.find_one({"user_id": str(user_id), "command": command})
        if cooldown:
            time_passed = (datetime.now() - cooldown['created_at']).total_seconds()
            if time_passed < cooldown_seconds: return cooldown_seconds - time_passed
        return None

    async def set_cooldown(self, user_id: int, command: str):
        if not self.connected: return
        await self.db.cooldowns.update_one({"user_id": str(user_id), "command": command}, {"$set": {"created_at": datetime.now()}}, upsert=True)

    async def add_to_inventory(self, user_id: int, item: Dict):
        if not self.connected: return
        await self.db.inventory.insert_one({"user_id": str(user_id), "item_id": item["id"], "name": item["name"], "type": item["type"], "emoji": item["emoji"], "quantity": 1})

    async def get_inventory(self, user_id: int) -> List:
        if not self.connected: return []
        return await self.db.inventory.find({"user_id": str(user_id)}).to_list(length=100)

    async def get_inventory_item(self, user_id: int, item_id: int) -> Optional[Dict]:
        if not self.connected: return None
        return await self.db.inventory.find_one({"user_id": str(user_id), "item_id": item_id})

    async def use_item(self, user_id: int, item_id: int) -> bool:
        if not self.connected: return False
        res = await self.db.inventory.delete_one({"user_id": str(user_id), "item_id": item_id})
        return res.deleted_count > 0

    async def get_shop_items(self) -> List:
        if not self.connected: return self._get_default_shop_items()
        shop = await self.db.shop.find_one({})
        return shop.get('items', []) if shop else self._get_default_shop_items()

    def _get_default_shop_items(self) -> List:
        return [{"id": 1, "name": "💰 Small Wallet Upgrade", "price": 2000, "description": "Increase limit", "type": "upgrade", "effect": {"wallet_limit": 5000}, "emoji": "💰"}]

db = MongoDB()

# ---------------- Enhanced Economy Cog ----------------
class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ready = False
        self.backup_manager = BackupManager()

    async def cog_load(self):
        if await db.connect():
            await db.initialize_collections()
            self.ready = True

    async def get_user(self, user_id: int): return await db.get_user(user_id)
    async def update_balance(self, user_id: int, wallet_change: int = 0, bank_change: int = 0): return await db.update_balance_atomic(user_id, wallet_change, bank_change)
    async def check_cooldown(self, user_id: int, command: str, cd: int): return await db.check_cooldown(user_id, command, cd)
    async def set_cooldown(self, user_id: int, command: str): await db.set_cooldown(user_id, command)
    async def get_inventory(self, user_id: int): return await db.get_inventory(user_id)
    async def get_inventory_item(self, user_id: int, iid: int): return await db.get_inventory_item(user_id, iid)
    async def add_to_inventory(self, uid: int, item: Dict): await db.add_to_inventory(uid, item)
    async def use_item(self, uid: int, iid: int): return await db.use_item(uid, iid)
    async def get_shop_items(self): return await db.get_shop_items()

    def format_money(self, amount: int): return f"{amount:,}£"
    def format_time(self, seconds: float):
        if seconds < 60: return f"{int(seconds)}s"
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"

    # FIXED: Added description=None to handle 3 arguments
    async def create_economy_embed(self, title: str, color: discord.Color = discord.Color.gold(), description: str = None) -> discord.Embed:
        """Create a standardized economy embed."""
        database_status = "✅ MongoDB" if self.ready else "⚠️ Memory Only"
        embed = discord.Embed(title=title, color=color, description=description, timestamp=datetime.now(timezone.utc))
        embed.set_footer(text=f"Economy System | {database_status}")
        return embed

    @commands.command(name="balance", aliases=["bal"])
    async def balance(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        data = await self.get_user(member.id)
        embed = await self.create_economy_embed(f"💰 {member.display_name}'s Balance")
        embed.add_field(name="💵 Wallet", value=f"{self.format_money(data['wallet'])} / {self.format_money(data['wallet_limit'])}")
        embed.add_field(name="🏦 Bank", value=f"{self.format_money(data['bank'])} / {self.format_money(data['bank_limit'])}")
        await ctx.send(embed=embed)

    @commands.command(name="work")
    async def work(self, ctx):
        rem = await self.check_cooldown(ctx.author.id, "work", EconomyConfig.WORK_COOLDOWN)
        if rem and not is_bot_admin(ctx.author):
            return await ctx.send(embed=await self.create_economy_embed("⏰ Cooldown", discord.Color.orange(), f"Wait {self.format_time(rem)}"))
        
        amt = random.randint(EconomyConfig.WORK_MIN_EARN, EconomyConfig.WORK_MAX_EARN)
        res = await self.update_balance(ctx.author.id, wallet_change=amt)
        await self.set_cooldown(ctx.author.id, "work")
        await ctx.send(embed=await self.create_economy_embed("💼 Work", discord.Color.green(), f"Earned {self.format_money(amt)}"))

    @commands.command(name="inventory", aliases=["inv"])
    async def inventory(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        inv = await self.get_inventory(member.id)
        if not inv:
            # FIXED: This call will no longer crash
            return await ctx.send(embed=await self.create_economy_embed(f"🎒 {member.display_name}'s Inventory", discord.Color.orange(), "Inventory is empty."))
        
        embed = await self.create_economy_embed(f"🎒 {member.display_name}'s Inventory")
        for item in inv:
            embed.add_field(name=f"{item['emoji']} {item['name']}", value=f"ID: {item['item_id']}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="shop")
    async def shop(self, ctx):
        items = await self.get_shop_items()
        embed = await self.create_economy_embed("🛍️ Shop")
        for i in items:
            embed.add_field(name=f"{i['emoji']} {i['name']} (ID: {i['id']})", value=f"Price: {self.format_money(i['price'])}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="buy")
    async def buy(self, ctx, item_id: int):
        items = await self.get_shop_items()
        item = next((i for i in items if i['id'] == item_id), None)
        if not item: return await ctx.send("Item not found.")
        
        user = await self.get_user(ctx.author.id)
        if user['bank'] < item['price']: return await ctx.send("Not enough bank money.")
        
        await self.update_balance(ctx.author.id, bank_change=-item['price'])
        if item['type'] == 'upgrade':
            field = list(item['effect'].keys())[0]
            new_val = user[field] + item['effect'][field]
            await db.update_user(ctx.author.id, {field: new_val})
        else:
            await self.add_to_inventory(ctx.author.id, item)
        await ctx.send("Purchase successful!")

async def setup(bot):
    await bot.add_cog(Economy(bot))
