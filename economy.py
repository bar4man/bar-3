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
import aiofiles  # <-- ADDED IMPORT
import glob      # <-- ADDED IMPORT
from error_handler import ErrorHandler # <-- ADDED IMPORT
from admin import is_bot_admin # <-- IMPORTED ADMIN CHECK

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
            # Use aiofiles for async write
            async with aiofiles.open(filename, 'w') as f:
                await f.write(json.dumps(data, f, indent=2, default=str))
            
            # Clean up old backups
            await self._cleanup_old_backups(backup_type)
            
            logging.info(f"✅ Backup created: {filename}")
            return True
        except Exception as e:
            logging.error(f"❌ Backup failed: {e}")
            return False
    
    async def _cleanup_old_backups(self, backup_type: str):
        """Remove old backups asynchronously to save space."""
        pattern = f"{self.backup_dir}/{backup_type}_backup_*.json"
        
        # Run blocking I/O (glob, os.remove) in an executor thread
        loop = asyncio.get_event_loop()
        
        try:
            backups = await loop.run_in_executor(None, glob.glob, pattern)
            
            if len(backups) > self.max_backups:
                # Sort by timestamp (oldest first)
                backups.sort()
                # Remove oldest backups
                for backup_file in backups[:-self.max_backups]:
                    try:
                        await loop.run_in_executor(None, os.remove, backup_file)
                        logging.info(f"🗑️ Removed old backup: {backup_file}")
                    except Exception as e:
                        logging.error(f"❌ Failed to remove backup {backup_file}: {e}")
        except Exception as e:
            logging.error(f"❌ Failed to cleanup backups: {e}")
    
    async def restore_backup(self, filename: str) -> Dict[str, any]:
        """Restore data from backup asynchronously."""
        try:
            async with aiofiles.open(filename, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logging.error(f"❌ Restore failed: {e}")
            return {}

# ---------------- Enhanced MongoDB Class ----------------
class MongoDB:
    """MongoDB database for economy data with atomic operations and locking."""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.connected = False
        self._locks = {}  # User-level locks
        self._lock = asyncio.Lock()  # Global lock for critical operations
        self._schema_versions = {}  # Track schema versions per user
        self._current_schema_version = 2
    
    async def connect(self):
        """Connect to MongoDB Atlas."""
        try:
            connection_string = os.getenv('MONGODB_URI')
            if not connection_string:
                logging.error("❌ MONGODB_URI environment variable not set")
                return False
            
            self.client = motor.motor_asyncio.AsyncIOMotorClient(connection_string)
            self.db = self.client.get_database('discord_bot')
            
            # Test connection
            await self.client.admin.command('ping')
            self.connected = True
            logging.info("✅ Connected to MongoDB Atlas successfully")
            return True
            
        except Exception as e:
            logging.error(f"❌ MongoDB connection failed: {e}")
            self.connected = False
            return False
    
    def _get_user_lock(self, user_id: int):
        """Get or create a lock for a specific user."""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]
    
    async def initialize_collections(self):
        """Initialize collections with default data."""
        if not self.connected:
            return False
            
        try:
            # Create indexes
            await self.db.users.create_index("user_id", unique=True)
            await self.db.inventory.create_index([("user_id", 1), ("item_id", 1)])
            await self.db.cooldowns.create_index("created_at", expireAfterSeconds=86400)  # 24h TTL
            
            # Initialize shop if empty
            shop_count = await self.db.shop.count_documents({})
            if shop_count == 0:
                default_shop = {
                    "items": [
                        {
                            "id": 1,
                            "name": "💰 Small Wallet Upgrade",
                            "description": "Increase your wallet limit by 5,000£",
                            "price": 2000,
                            "type": "upgrade",
                            "effect": {"wallet_limit": 5000},
                            "emoji": "💰",
                            "stock": -1
                        },
                        {
                            "id": 2,
                            "name": "💳 Medium Wallet Upgrade", 
                            "description": "Increase your wallet limit by 15,000£",
                            "price": 8000,
                            "type": "upgrade",
                            "effect": {"wallet_limit": 15000},
                            "emoji": "💳",
                            "stock": -1
                        },
                        {
                            "id": 3,
                            "name": "💎 Large Wallet Upgrade",
                            "description": "Increase your wallet limit by 50,000£", 
                            "price": 25000,
                            "type": "upgrade",
                            "effect": {"wallet_limit": 50000},
                            "emoji": "💎",
                            "stock": -1
                        },
                        {
                            "id": 4,
                            "name": "🏦 Small Bank Upgrade",
                            "description": "Increase your bank limit by 50,000£",
                            "price": 5000,
                            "type": "upgrade",
                            "effect": {"bank_limit": 50000},
                            "emoji": "🏦",
                            "stock": -1
                        },
                        {
                            "id": 5,
                            "name": "🏛️ Medium Bank Upgrade",
                            "description": "Increase your bank limit by 150,000£",
                            "price": 15000,
                            "type": "upgrade",
                            "effect": {"bank_limit": 150000},
                            "emoji": "🏛️",
                            "stock": -1
                        },
                        {
                            "id": 6,
                            "name": "🎯 Large Bank Upgrade",
                            "description": "Increase your bank limit by 500,000£",
                            "price": 50000,
                            "type": "upgrade",
                            "effect": {"bank_limit": 500000},
                            "emoji": "🎯",
                            "stock": -1
                        }
                    ],
                    "created_at": datetime.now()
                }
                await self.db.shop.insert_one(default_shop)
                logging.info("✅ Default shop items created")
            
            # Migrate existing users to new schema
            await self.migrate_user_schema()
            
            logging.info("✅ MongoDB collections initialized")
            return True
            
        except Exception as e:
            logging.error(f"❌ MongoDB initialization failed: {e}")
            return False
    
    async def migrate_user_schema(self):
        """Migrate existing users to include wallet_limit, bank_limit, and portfolio fields."""
        try:
            # Find users missing the new fields
            async for user in self.db.users.find({
                "$or": [
                    {"wallet_limit": {"$exists": False}},
                    {"bank_limit": {"$exists": False}},
                    {"portfolio": {"$exists": False}}
                ]
            }):
                update_data = {}
                
                # Add missing wallet_limit with default value
                if "wallet_limit" not in user:
                    update_data["wallet_limit"] = EconomyConfig.DEFAULT_WALLET_LIMIT
                
                # Add missing bank_limit with default value  
                if "bank_limit" not in user:
                    update_data["bank_limit"] = EconomyConfig.DEFAULT_BANK_LIMIT
                
                # Add missing portfolio with default structure
                if "portfolio" not in user:
                    update_data["portfolio"] = {
                        "gold_ounces": 0.0,
                        "stocks": {},
                        "total_investment": 0,
                        "total_value": 0,
                        "daily_pnl": 0,
                        "total_pnl": 0
                    }
                
                # Add schema version
                update_data["_schema_version"] = self._current_schema_version
                
                if update_data:
                    await self.db.users.update_one(
                        {"_id": user["_id"]},
                        {"$set": update_data}
                    )
            
            logging.info("✅ User schema migration completed")
                
        except Exception as e:
            logging.error(f"❌ Error during user schema migration: {e}")
    
    # User management
    async def get_user(self, user_id: int) -> Dict:
        """Get user data or create if doesn't exist."""
        if not self.connected:
            return self._get_default_user(user_id)
        
        try:
            user = await self.db.users.find_one({"user_id": str(user_id)})
            
            if not user:
                user = self._get_default_user(user_id)
                user["_schema_version"] = self._current_schema_version
                await self.db.users.insert_one(user)
                logging.info(f"👤 New user created in MongoDB: {user_id}")
            else:
                # Check if schema needs migration
                if user.get("_schema_version", 1) < self._current_schema_version:
                    user = await self._migrate_user_schema(user)
            
            return user
        except Exception as e:
            logging.error(f"❌ Error getting user {user_id}: {e}")
            return self._get_default_user(user_id)
    
    async def _migrate_user_schema(self, user: Dict) -> Dict:
        """Migrate user schema efficiently."""
        current_version = user.get("_schema_version", 1)
        
        # Migration path
        migrations = {
            1: self._migrate_v1_to_v2,
        }
        
        for version in range(current_version, self._current_schema_version):
            migration_func = migrations.get(version)
            if migration_func:
                user = migration_func(user)
        
        user["_schema_version"] = self._current_schema_version
        await self.update_user(user["user_id"], user)
        
        return user
    
    def _migrate_v1_to_v2(self, user: Dict) -> Dict:
        """Migrate from schema v1 to v2."""
        default_user = self._get_default_user(int(user["user_id"]))
        
        # Add missing fields
        for key, value in default_user.items():
            if key not in user:
                user[key] = value
        
        return user
    
    def _get_default_user(self, user_id: int) -> Dict:
        """Return default user structure."""
        return {
            "user_id": str(user_id),
            "wallet": EconomyConfig.STARTING_MONEY,
            "wallet_limit": EconomyConfig.DEFAULT_WALLET_LIMIT,
            "bank": 0,
            "bank_limit": EconomyConfig.DEFAULT_BANK_LIMIT,
            "networth": EconomyConfig.STARTING_MONEY,
            "daily_streak": 0,
            "last_daily": None,
            "total_earned": 0,
            "portfolio": {
                "gold_ounces": 0.0,
                "stocks": {},
                "total_investment": 0,
                "total_value": 0,
                "daily_pnl": 0,
                "total_pnl": 0
            },
            "bar_data": {
                "patron_level": 1,
                "favorite_drink": None,
                "drinks_tried": [],
                "total_drinks_ordered": 0,
                "bar_tab": 0,
                "tips_given": 0,
                "tips_received": 0,
                "sobering_cooldown": None,
                "unlocked_drinks": {}
            },
            "bartender_achievements": [],
            "created_at": datetime.now(),
            "last_active": datetime.now(),
            "_schema_version": self._current_schema_version
        }
    
    async def update_user(self, user_id: int, update_data: Dict):
        """Update user data."""
        if not self.connected:
            return
            
        update_data["last_active"] = datetime.now()
        await self.db.users.update_one(
            {"user_id": str(user_id)},
            {"$set": update_data},
            upsert=True
        )
    
    # Atomic balance operations
    async def update_balance_atomic(self, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> Dict:
        """Atomic balance update with proper locking and overflow protection."""
        user_lock = self._get_user_lock(user_id)
        async with user_lock:
            return await self._update_balance_internal(user_id, wallet_change, bank_change)
    
    async def _update_balance_internal(self, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> Dict:
        """Internal balance update with overflow protection."""
        if not self.connected:
            return self._get_default_user(user_id)
        
        try:
            user = await self.get_user(user_id)
            original_wallet = user['wallet']
            original_bank = user['bank']
            
            # Calculate new balances with overflow handling
            new_wallet = user['wallet'] + wallet_change
            new_bank = user['bank'] + bank_change
            
            # Handle overflow - send excess to bank instead of losing it
            wallet_overflow = max(0, new_wallet - user['wallet_limit'])
            bank_overflow = max(0, new_bank - user['bank_limit'])
            
            overflow_handled = False
            actual_wallet_change = wallet_change
            actual_bank_change = bank_change
            
            if wallet_overflow > 0:
                # Try to move overflow to bank
                bank_capacity = user['bank_limit'] - user['bank']
                actual_bank_transfer = min(wallet_overflow, bank_capacity)
                
                new_wallet = user['wallet_limit']
                new_bank += actual_bank_transfer
                
                # Adjust changes for accurate tracking
                actual_wallet_change = user['wallet_limit'] - user['wallet']
                actual_bank_change = bank_change + actual_bank_transfer
                
                overflow_handled = True
                logging.info(f"💰 Wallet overflow handled for {user_id}: {wallet_overflow}£")
            
            if bank_overflow > 0:
                # Bank overflow - we have to lose money, but log it
                new_bank = user['bank_limit']
                actual_bank_change = user['bank_limit'] - user['bank']
                
                overflow_handled = True
                lost_amount = bank_overflow
                logging.warning(f"💰 Bank overflow for {user_id}: {lost_amount}£ lost")
            
            # Ensure non-negative
            new_wallet = max(0, new_wallet)
            new_bank = max(0, new_bank)
            
            # Update user with atomic operation
            update_data = {
                "$set": {
                    "wallet": new_wallet,
                    "bank": new_bank,
                    "networth": new_wallet + new_bank,
                    "last_active": datetime.now()
                }
            }
            
            # Only update total_earned if money was actually gained
            if (wallet_change > 0 or bank_change > 0) and (wallet_change + bank_change > 0):
                update_data["$inc"] = {"total_earned": actual_wallet_change + actual_bank_change}
            
            result = await self.db.users.find_one_and_update(
                {"user_id": str(user_id)},
                update_data,
                return_document=True,
                upsert=True
            )
            
            if overflow_handled:
                result["_overflow_handled"] = True
                result["_original_wallet_change"] = wallet_change
                result["_original_bank_change"] = bank_change
                result["_actual_wallet_change"] = actual_wallet_change
                result["_actual_bank_change"] = actual_bank_change
            
            return result
            
        except Exception as e:
            logging.error(f"❌ Atomic balance update failed for {user_id}: {e}")
            # Fallback to non-atomic update
            return await self.update_balance(user_id, wallet_change, bank_change)
    
    # Legacy method for compatibility
    async def update_balance(self, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> Dict:
        """Legacy balance update - use update_balance_atomic for new code."""
        return await self.update_balance_atomic(user_id, wallet_change, bank_change)
    
    async def transfer_money(self, from_user: int, to_user: int, amount: int) -> Tuple[bool, int]:
        """Transfer money between users (wallet to wallet) with atomic operations."""
        if amount <= 0:
            return False, 0
        
        # Get locks for both users to prevent deadlocks
        from_lock = self._get_user_lock(from_user)
        to_lock = self._get_user_lock(to_user)
        
        # Acquire locks in consistent order to prevent deadlocks
        lock1, lock2 = sorted([from_lock, to_lock], key=id)
        
        async with lock1:
            async with lock2:
                from_user_data = await self.get_user(from_user)
                to_user_data = await self.get_user(to_user)
                
                # Check if sender has enough in wallet
                if from_user_data['wallet'] < amount:
                    return False, 0
                
                # Check if receiver has wallet space
                transfer_amount = amount
                if to_user_data['wallet'] + amount > to_user_data['wallet_limit']:
                    transfer_amount = to_user_data['wallet_limit'] - to_user_data['wallet']
                
                # Perform atomic transfers
                await self.update_balance_atomic(from_user, wallet_change=-amount)
                await self.update_balance_atomic(to_user, wallet_change=transfer_amount)
                
                return True, transfer_amount
    
    # Cooldown management
    async def check_cooldown(self, user_id: int, command: str, cooldown_seconds: int) -> Optional[float]:
        """Check if user is on cooldown."""
        if not self.connected:
            return None
            
        try:
            cooldown = await self.db.cooldowns.find_one({
                "user_id": str(user_id),
                "command": command
            })
            
            if cooldown:
                last_used = cooldown['created_at']
                time_passed = (datetime.now() - last_used).total_seconds()
                
                if time_passed < cooldown_seconds:
                    return cooldown_seconds - time_passed
            
            return None
        except Exception as e:
            logging.error(f"❌ Error checking cooldown for user {user_id}: {e}")
            return None
    
    async def set_cooldown(self, user_id: int, command: str):
        """Set cooldown for a command."""
        if not self.connected:
            return
            
        try:
            await self.db.cooldowns.update_one(
                {"user_id": str(user_id), "command": command},
                {
                    "$set": {
                        "created_at": datetime.now(),
                        "expires_at": datetime.now() + timedelta(days=1)
                    }
                },
                upsert=True
            )
        except Exception as e:
            logging.error(f"❌ Error setting cooldown for user {user_id}: {e}")
    
    # Inventory management
    async def add_to_inventory(self, user_id: int, item: Dict):
        """Add item to user's inventory."""
        if not self.connected:
            return
            
        try:
            # Check if user already has this item (for stackable items)
            existing_item = await self.db.inventory.find_one({
                "user_id": str(user_id),
                "item_id": item["id"]
            })
            
            if existing_item and item.get("stackable", False):
                # Update quantity for stackable items
                await self.db.inventory.update_one(
                    {"user_id": str(user_id), "item_id": item["id"]},
                    {"$inc": {"quantity": 1}}
                )
            else:
                # Add new item
                inventory_item = {
                    "user_id": str(user_id),
                    "item_id": item["id"],
                    "name": item["name"],
                    "type": item["type"],
                    "effect": item["effect"],
                    "emoji": item["emoji"],
                    "quantity": 1,
                    "purchased_at": datetime.now(),
                    "uses_remaining": item.get("effect", {}).get("uses", 1) if item["type"] == "consumable" else None
                }
                await self.db.inventory.insert_one(inventory_item)
        except Exception as e:
            logging.error(f"❌ Error adding to inventory for user {user_id}: {e}")
    
    async def get_inventory(self, user_id: int) -> List:
        """Get user's inventory."""
        if not self.connected:
            return []
            
        try:
            cursor = self.db.inventory.find({"user_id": str(user_id)})
            return await cursor.to_list(length=100)
        except Exception as e:
            logging.error(f"❌ Error getting inventory for user {user_id}: {e}")
            return []
    
    async def get_inventory_item(self, user_id: int, item_id: int) -> Optional[Dict]:
        """Get specific item from user's inventory."""
        if not self.connected:
            return None
            
        try:
            return await self.db.inventory.find_one({"user_id": str(user_id), "item_id": item_id})
        except Exception as e:
            logging.error(f"❌ Error getting inventory item for user {user_id}: {e}")
            return None
    
    async def use_item(self, user_id: int, item_id: int) -> bool:
        """Use item from inventory."""
        if not self.connected:
            return False
            
        try:
            item = await self.get_inventory_item(user_id, item_id)
            if not item:
                return False
            
            if item.get("quantity", 1) > 1:
                # Decrement quantity for stackable items
                await self.db.inventory.update_one(
                    {"user_id": str(user_id), "item_id": item_id},
                    {"$inc": {"quantity": -1}}
                )
            elif item.get("uses_remaining") and item["uses_remaining"] > 1:
                # Decrement uses for multi-use items
                await self.db.inventory.update_one(
                    {"user_id": str(user_id), "item_id": item_id},
                    {"$inc": {"uses_remaining": -1}}
                )
            else:
                # Remove single-use items
                await self.db.inventory.delete_one({"user_id": str(user_id), "item_id": item_id})
            
            return True
        except Exception as e:
            logging.error(f"❌ Error using item for user {user_id}: {e}")
            return False
    
    async def update_inventory_item(self, user_id: int, item_id: int, update_data: Dict):
        """Update inventory item."""
        if not self.connected:
            return
            
        try:
            await self.db.inventory.update_one(
                {"user_id": str(user_id), "item_id": item_id},
                {"$set": update_data}
            )
        except Exception as e:
            logging.error(f"❌ Error updating inventory item for user {user_id}: {e}")
    
    # Shop methods
    async def get_shop_items(self) -> List:
        """Get all shop items."""
        if not self.connected:
            return self._get_default_shop_items()
            
        try:
            shop = await self.db.shop.find_one({})
            return shop.get('items', []) if shop else self._get_default_shop_items()
        except Exception as e:
            logging.error(f"❌ Error getting shop items: {e}")
            return self._get_default_shop_items()
    
    def _get_default_shop_items(self) -> List:
        """Return default shop items for fallback."""
        return [
            {
                "id": 1, "name": "💰 Small Wallet Upgrade", "price": 2000,
                "description": "Increase your wallet limit by 5,000£",
                "type": "upgrade", "effect": {"wallet_limit": 5000}, "emoji": "💰", "stock": -1
            },
            {
                "id": 2, "name": "💳 Medium Wallet Upgrade", "price": 8000,
                "description": "Increase your wallet limit by 15,000£", 
                "type": "upgrade", "effect": {"wallet_limit": 15000}, "emoji": "💳", "stock": -1
            },
            {
                "id": 3, "name": "💎 Large Wallet Upgrade", "price": 25000,
                "description": "Increase your wallet limit by 50,000£",
                "type": "upgrade", "effect": {"wallet_limit": 50000}, "emoji": "💎", "stock": -1
            },
            {
                "id": 4, "name": "🏦 Small Bank Upgrade", "price": 5000,
                "description": "Increase your bank limit by 50,000£",
                "type": "upgrade", "effect": {"bank_limit": 50000}, "emoji": "🏦", "stock": -1
            },
            {
                "id": 5, "name": "🏛️ Medium Bank Upgrade", "price": 15000,
                "description": "Increase your bank limit by 150,000£",
                "type": "upgrade", "effect": {"bank_limit": 150000}, "emoji": "🏛️", "stock": -1
            },
            {
                "id": 6, "name": "🎯 Large Bank Upgrade", "price": 50000,
                "description": "Increase your bank limit by 500,000£",
                "type": "upgrade", "effect": {"bank_limit": 500000}, "emoji": "🎯", "stock": -1
            }
        ]
    
    async def get_stats(self):
        """Get database statistics."""
        if not self.connected:
            return {"total_users": 0, "total_money": 0, "database": "disconnected"}
            
        try:
            total_users = await self.db.users.count_documents({})
            
            pipeline = [
                {
                    "$group": {
                        "_id": None,
                        "total_money": {
                            "$sum": {
                                "$add": ["$wallet", "$bank"]
                            }
                        }
                    }
                }
            ]
            
            result = await self.db.users.aggregate(pipeline).to_list(length=1)
            total_money = result[0]['total_money'] if result else 0
            
            return {
                "total_users": total_users,
                "total_money": total_money,
                "database": "mongodb"
            }
        except Exception as e:
            logging.error(f"❌ Error getting stats: {e}")
            return {"total_users": 0, "total_money": 0, "database": "error"}

# Global database instance
db = MongoDB()

# ---------------- Enhanced Economy Cog ----------------
class Economy(commands.Cog):
    """Enhanced economy system with atomic operations and overflow protection."""
    
    def __init__(self, bot):
        self.bot = bot
        self.ready = False
        self.active_effects = {}  # Track active item effects
        self.backup_manager = BackupManager()
        self._transaction_log = []
        logging.info("✅ Economy system initialized with atomic operations")
    
    async def cog_load(self):
        """Load data when cog is loaded."""
        # Connect to MongoDB with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            success = await db.connect()
            if success:
                await db.initialize_collections()
                self.ready = True
                logging.info("✅ Economy system loaded with MongoDB")
                return
            else:
                logging.warning(f"❌ MongoDB connection attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(2)
        
        logging.error("❌ Economy system using fallback mode (no persistence)")
        self.ready = False
    
    # Safe transaction system
    async def safe_transaction(self, user_id: int, operation: callable, *args, **kwargs):
        """Execute a transaction with rollback capability."""
        # Create backup before transaction
        user_backup = await self.get_user(user_id)
        transaction_id = f"{user_id}_{datetime.now().timestamp()}"
        
        try:
            result = await operation(*args, **kwargs)
            
            # Log successful transaction
            self._transaction_log.append({
                'id': transaction_id,
                'user_id': user_id,
                'operation': operation.__name__,
                'timestamp': datetime.now(),
                'status': 'success'
            })
            
            return result
            
        except Exception as e:
            # Rollback on failure
            await db.update_user(user_id, user_backup)
            
            # Log failed transaction
            self._transaction_log.append({
                'id': transaction_id,
                'user_id': user_id,
                'operation': operation.__name__,
                'timestamp': datetime.now(),
                'status': 'failed',
                'error': str(e)
            })
            
            logging.error(f"❌ Transaction failed, rolled back: {transaction_id}")
            raise e
    
    # User management methods
    async def get_user(self, user_id: int) -> Dict:
        """Get user data."""
        return await db.get_user(user_id)
    
    async def update_balance(self, user_id: int, wallet_change: int = 0, bank_change: int = 0) -> Dict:
        """Update user's wallet and bank balance using atomic operations."""
        return await db.update_balance_atomic(user_id, wallet_change, bank_change)
    
    async def transfer_money(self, from_user: int, to_user: int, amount: int) -> Tuple[bool, int]:
        """Transfer money between users with atomic operations."""
        return await db.transfer_money(from_user, to_user, amount)
    
    # Cooldown management
    async def check_cooldown(self, user_id: int, command: str, cooldown_seconds: int) -> Optional[float]:
        """Check if user is on cooldown."""
        return await db.check_cooldown(user_id, command, cooldown_seconds)
    
    async def set_cooldown(self, user_id: int, command: str):
        """Set cooldown for a command."""
        await db.set_cooldown(user_id, command)
    
    # Inventory management
    async def add_to_inventory(self, user_id: int, item: Dict):
        """Add item to user's inventory."""
        await db.add_to_inventory(user_id, item)
    
    async def get_inventory(self, user_id: int) -> List:
        """Get user's inventory."""
        return await db.get_inventory(user_id)
    
    async def get_inventory_item(self, user_id: int, item_id: int) -> Optional[Dict]:
        """Get specific item from user's inventory."""
        return await db.get_inventory_item(user_id, item_id)
    
    async def use_item(self, user_id: int, item_id: int) -> bool:
        """Use item from inventory."""
        return await db.use_item(user_id, item_id)
    
    # Shop methods
    async def get_shop_items(self) -> List:
        """Get all shop items."""
        return await db.get_shop_items()
    
    async def get_shop_item(self, item_id: int) -> Optional[Dict]:
        """Get specific shop item."""
        items = await self.get_shop_items()
        for item in items:
            if item['id'] == item_id:
                return item
        return None
    
    # Utility methods
    def format_money(self, amount: int) -> str:
        """Format money with commas and currency symbol."""
        return f"{amount:,}£"
    
    def format_time(self, seconds: float) -> str:
        """Format seconds into readable time."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    def calculate_upgrade_cost(self, current_limit: int, upgrade_type: str) -> int:
        """Calculate scaling cost for upgrades."""
        base_cost = 1000 if upgrade_type == "wallet" else 2000
        multiplier = (current_limit / EconomyConfig.DEFAULT_WALLET_LIMIT) if upgrade_type == "wallet" else (current_limit / EconomyConfig.DEFAULT_BANK_LIMIT)
        return int(base_cost * multiplier * 1.5)
    
    async def create_economy_embed(self, title: str, color: discord.Color = discord.Color.gold()) -> discord.Embed:
        """Create a standardized economy embed."""
        database_status = "✅ MongoDB" if self.ready else "⚠️ Memory Only"
        embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
        embed.set_footer(text=f"Economy System | {database_status}")
        return embed
    
    def get_active_effects(self, user_id: int) -> Dict:
        """Get active effects for a user."""
        return self.active_effects.get(user_id, {})
    
    def set_active_effect(self, user_id: int, effect_type: str, multiplier: float, duration: int = None):
        """Set an active effect for a user."""
        if user_id not in self.active_effects:
            self.active_effects[user_id] = {}
        
        self.active_effects[user_id][effect_type] = {
            "multiplier": multiplier,
            "expires_at": datetime.now() + timedelta(days=duration) if duration else None
        }

    # Portfolio management methods
    async def get_user_portfolio(self, user_id: int) -> Dict:
        """Get user's investment portfolio including gold."""
        user = await self.get_user(user_id)
        portfolio = user.get("portfolio", {
            "gold_ounces": 0.0,
            "stocks": {},
            "total_investment": 0,
            "total_value": 0,
            "daily_pnl": 0,
            "total_pnl": 0
        })
        return portfolio

    async def update_user_portfolio(self, user_id: int, portfolio: Dict):
        """Update user's investment portfolio."""
        user = await self.get_user(user_id)
        user["portfolio"] = portfolio
        await self.update_user(user_id, user)

    # Job tier system for balanced economy
    def _get_networth_tier(self, networth: int) -> str:
        """Get user's networth tier for job availability."""
        if networth >= 1_000_000:
            return "expert"
        elif networth >= 100_000:
            return "advanced" 
        elif networth >= 10_000:
            return "intermediate"
        else:
            return "beginner"
    
    def _get_available_jobs(self, tier: str) -> Dict:
        """Get available jobs based on user tier."""
        base_jobs = {
            "beginner": {
                "delivered packages": (EconomyConfig.WORK_MIN_EARN, EconomyConfig.WORK_MIN_EARN + 80),
                "worked at a café": (EconomyConfig.WORK_MIN_EARN - 20, EconomyConfig.WORK_MIN_EARN + 40),
                "helped with chores": (EconomyConfig.WORK_MIN_EARN - 40, EconomyConfig.WORK_MIN_EARN + 20)
            },
            "intermediate": {
                "drove for Uber": (EconomyConfig.WORK_MIN_EARN + 20, EconomyConfig.WORK_MIN_EARN + 120),
                "streamed on Twitch": (EconomyConfig.WORK_MIN_EARN + 70, EconomyConfig.WORK_MIN_EARN + 220),
                "designed graphics": (EconomyConfig.WORK_MIN_EARN + 40, EconomyConfig.WORK_MIN_EARN + 170)
            },
            "advanced": {
                "coded a website": (EconomyConfig.WORK_MIN_EARN + 120, EconomyConfig.WORK_MIN_EARN + 320),
                "consulted for a business": (EconomyConfig.WORK_MIN_EARN + 80, EconomyConfig.WORK_MIN_EARN + 270),
                "managed a project": (EconomyConfig.WORK_MIN_EARN + 140, EconomyConfig.WORK_MIN_EARN + 370)
            },
            "expert": {
                "invested in stocks": (EconomyConfig.WORK_MIN_EARN + 220, EconomyConfig.WORK_MAX_EARN),
                "developed an app": (EconomyConfig.WORK_MIN_EARN + 320, EconomyConfig.WORK_MAX_EARN + 200),
                "led a team": (EconomyConfig.WORK_MIN_EARN + 270, EconomyConfig.WORK_MAX_EARN + 100)
            }
        }
        
        return base_jobs.get(tier, base_jobs["beginner"])

    # ========== COMMANDS ==========
    
    @commands.command(name="balance", aliases=["bal", "money"])
    async def balance(self, ctx: commands.Context, member: discord.Member = None):
        """Check your or someone else's balance."""
        try:
            member = member or ctx.author
            user_data = await self.get_user(member.id)
            
            wallet = user_data["wallet"]
            wallet_limit = user_data["wallet_limit"]
            bank = user_data["bank"]
            bank_limit = user_data["bank_limit"]
            total = wallet + bank
            
            wallet_usage = (wallet / wallet_limit) * 100 if wallet_limit > 0 else 0
            bank_usage = (bank / bank_limit) * 100 if bank_limit > 0 else 0
            
            embed = await self.create_economy_embed(f"💰 {member.display_name}'s Balance")
            embed.set_thumbnail(url=member.display_avatar.url)
            
            embed.add_field(name="💵 Wallet", value=f"{self.format_money(wallet)} / {self.format_money(wallet_limit)}", inline=True)
            embed.add_field(name="🏦 Bank", value=f"{self.format_money(bank)} / {self.format_money(bank_limit)}", inline=True)
            embed.add_field(name="💎 Total", value=self.format_money(total), inline=True)
            
            # Usage bars
            wallet_bars = 10
            wallet_filled = min(wallet_bars, int(wallet_usage / 10))
            wallet_bar = "█" * wallet_filled + "░" * (wallet_bars - wallet_filled)
            
            bank_bars = 10
            bank_filled = min(bank_bars, int(bank_usage / 10))
            bank_bar = "█" * bank_filled + "░" * (bank_bars - bank_filled)
            
            embed.add_field(name="💵 Wallet Usage", value=f"`{wallet_bar}` {wallet_usage:.1f}%", inline=False)
            embed.add_field(name="🏦 Bank Usage", value=f"`{bank_bar}` {bank_usage:.1f}%", inline=False)
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "balance")

    @commands.command(name="work")
    async def work(self, ctx: commands.Context):
        """Work to earn money with balanced rewards based on net worth."""
        try:
            # Check cooldown
            remaining = await self.check_cooldown(ctx.author.id, "work", EconomyConfig.WORK_COOLDOWN)
            # --- MODIFIED: Add admin bypass ---
            if remaining and not is_bot_admin(ctx.author):
            # --- END MODIFICATION ---
                embed = await self.create_economy_embed("⏰ Already Worked Recently", discord.Color.orange())
                embed.description = f"You can work again in **{self.format_time(remaining)}**"
                return await ctx.send(embed=embed)
            
            user_data = await self.get_user(ctx.author.id)
            
            # Get appropriate jobs based on net worth tier
            networth_tier = self._get_networth_tier(user_data['networth'])
            jobs = self._get_available_jobs(networth_tier)
            
            job, (min_earn, max_earn) = random.choice(list(jobs.items()))
            
            # Apply active effects
            active_effects = self.get_active_effects(ctx.author.id)
            work_multiplier = active_effects.get("work_bonus", {}).get("multiplier", 1.0)
            
            base_earnings = random.randint(min_earn, max_earn)
            earnings = int(base_earnings * work_multiplier)
            
            # Critical work chance
            is_critical = random.random() < EconomyConfig.WORK_CRITICAL_CHANCE
            if is_critical:
                earnings *= 2
            
            # Use atomic balance update
            result = await self.update_balance(ctx.author.id, wallet_change=earnings)
            await self.set_cooldown(ctx.author.id, "work")
            
            embed = await self.create_economy_embed("💼 Work Complete!", discord.Color.blue())
            
            if is_critical:
                embed.description = f"🎯 **CRITICAL WORK!** You {job} and earned {self.format_money(earnings)}!"
                embed.color = discord.Color.gold()
            else:
                embed.description = f"You {job} and earned {self.format_money(earnings)}!"
            
            if work_multiplier > 1.0:
                embed.add_field(name="✨ Item Bonus", value=f"{work_multiplier}x multiplier applied!", inline=False)
            
            # Check if overflow was handled
            if result.get("_overflow_handled"):
                original_earnings = result.get("_original_wallet_change", earnings)
                actual_earnings = result.get("_actual_wallet_change", earnings)
                
                if actual_earnings < original_earnings:
                    lost_money = original_earnings - actual_earnings
                    embed.add_field(
                        name="💸 Overflow Protection", 
                        value=f"Wallet full! {self.format_money(actual_earnings)} earned, {self.format_money(lost_money)} moved to bank.",
                        inline=False
                    )
            
            embed.add_field(name="💵 New Balance", value=f"{self.format_money(result['wallet'])} / {self.format_money(result['wallet_limit'])}", inline=False)
            embed.set_footer(text=f"You can work again in {self.format_time(EconomyConfig.WORK_COOLDOWN)}!")
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "work")

    @commands.command(name="daily")
    async def daily(self, ctx: commands.Context):
        """Claim your daily reward and build a streak."""
        try:
            # Check cooldown
            remaining = await self.check_cooldown(ctx.author.id, "daily", EconomyConfig.DAILY_COOLDOWN)
            # --- MODIFIED: Add admin bypass ---
            if remaining and not is_bot_admin(ctx.author):
            # --- END MODIFICATION ---
                embed = await self.create_economy_embed("⏰ Daily Reward Claimed", discord.Color.orange())
                embed.description = f"You can claim your next daily reward in **{self.format_time(remaining)}**."
                return await ctx.send(embed=embed)
            
            user_data = await self.get_user(ctx.author.id)
            now = datetime.now(timezone.utc)
            
            base_reward = EconomyConfig.DAILY_REWARD
            streak = user_data.get("daily_streak", 0)
            last_daily_str = user_data.get("last_daily")
            
            # Check for streak
            if last_daily_str:
                last_daily = datetime.fromisoformat(last_daily_str)
                time_diff = now - last_daily
                
                if time_diff.days == 1:
                    streak += 1
                elif time_diff.days > 1:
                    streak = 1  # Streak broken
                else:
                    streak = 0 # Should not happen if cooldown is working, but as a fallback
            else:
                streak = 1  # First daily
                
            streak_bonus = streak * EconomyConfig.DAILY_STREAK_BONUS
            total_reward = base_reward + streak_bonus
            
            # Update user
            result = await self.update_balance(ctx.author.id, wallet_change=total_reward)
            await db.update_user(ctx.author.id, {
                "last_daily": now.isoformat(),
                "daily_streak": streak
            })
            await self.set_cooldown(ctx.author.id, "daily")
            
            # Send success embed
            embed = await self.create_economy_embed("🎉 Daily Reward Claimed!", discord.Color.green())
            embed.description = f"You claimed your daily reward of **{self.format_money(total_reward)}**!"
            
            embed.add_field(name="💰 Base Reward", value=self.format_money(base_reward), inline=True)
            embed.add_field(name="🔥 Streak Bonus", value=f"{self.format_money(streak_bonus)} ({streak} days)", inline=True)
            embed.add_field(name="💵 New Wallet", value=self.format_money(result['wallet']), inline=True)
            
            # Check for overflow
            if result.get("_overflow_handled"):
                embed.add_field(
                    name="💸 Overflow Protection", 
                    value="Your wallet was full! Part of your reward was moved to your bank.",
                    inline=False
                )
                
            embed.set_footer(text=f"Come back in {self.format_time(EconomyConfig.DAILY_COOLDOWN)} for your next reward!")
            await ctx.send(embed=embed)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "daily")

    @commands.command(name="pay", aliases=["give", "transfer"])
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: int):
        """Pay another user money from your WALLET with atomic transfers."""
        try:
            if member == ctx.author:
                embed = await self.create_economy_embed("❌ Invalid Action", discord.Color.red())
                embed.description = "You cannot pay yourself!"
                return await ctx.send(embed=embed)
            
            if member.bot:
                embed = await self.create_economy_embed("❌ Invalid Action", discord.Color.red())
                embed.description = "You cannot pay bots!"
                return await ctx.send(embed=embed)
            
            if amount <= 0:
                embed = await self.create_economy_embed("❌ Invalid Amount", discord.Color.red())
                embed.description = "Payment amount must be greater than 0."
                return await ctx.send(embed=embed)
            
            # Use atomic transfer
            success, actual_amount = await self.transfer_money(ctx.author.id, member.id, amount)
            
            if not success:
                # Check if sender has enough money
                user_data = await self.get_user(ctx.author.id)
                if user_data["wallet"] < amount:
                    embed = await self.create_economy_embed("❌ Insufficient Wallet Funds", discord.Color.red())
                    embed.description = f"You only have {self.format_money(user_data['wallet'])} in your wallet.\nUse `~withdraw` to get money from your bank."
                    return await ctx.send(embed=embed)
            
            if success and actual_amount == amount:
                embed = await self.create_economy_embed("💸 Payment Successful", discord.Color.green())
                embed.description = f"{ctx.author.mention} paid {self.format_money(amount)} to {member.mention} from their wallet!"
            elif success:
                # Partial transfer occurred (receiver's wallet was full)
                embed = await self.create_economy_embed("⚠️ Partial Payment", discord.Color.orange())
                embed.description = f"{ctx.author.mention} paid {self.format_money(actual_amount)} to {member.mention}.\n**Note:** {self.format_money(amount - actual_amount)} couldn't be transferred (receiver's wallet full)."
            else:
                embed = await self.create_economy_embed("❌ Transfer Failed", discord.Color.red())
                embed.description = "The transfer could not be completed. Please try again."
            
            embed.add_field(name="🔒 Security Note", value="All payments use wallet money. Shop purchases use bank money.", inline=False)
            embed.set_footer(text=f"Transaction completed at {datetime.now().strftime('%H:%M:%S')}")
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "pay")

    # -------------------- NEW COMMANDS --------------------
    
    @commands.command(name="deposit", aliases=["dep"])
    async def deposit(self, ctx: commands.Context, amount: str):
        """Deposit money from your wallet to your bank."""
        try:
            user_data = await self.get_user(ctx.author.id)
            wallet = user_data["wallet"]
            bank = user_data["bank"]
            bank_limit = user_data["bank_limit"]
            
            if wallet == 0:
                return await ctx.send(embed=await self.create_economy_embed("❌ Wallet Empty", discord.Color.red(), "Your wallet is empty."))
            
            if amount.lower() in ["all", "max"]:
                dep_amount = wallet
            else:
                try:
                    dep_amount = int(amount)
                except ValueError:
                    return await ctx.send(embed=await self.create_economy_embed("❌ Invalid Amount", discord.Color.red(), "Please enter a valid number or 'all'."))
            
            if dep_amount <= 0:
                return await ctx.send(embed=await self.create_economy_embed("❌ Invalid Amount", discord.Color.red(), "Amount must be positive."))
            
            if dep_amount > wallet:
                return await ctx.send(embed=await self.create_economy_embed("❌ Insufficient Funds", discord.Color.red(), f"You only have {self.format_money(wallet)} in your wallet."))
            
            bank_space = bank_limit - bank
            if bank_space <= 0:
                return await ctx.send(embed=await self.create_economy_embed("❌ Bank Full", discord.Color.red(), "Your bank is full."))
            
            # Only deposit what fits
            actual_dep = min(dep_amount, bank_space)
            
            result = await self.update_balance(ctx.author.id, wallet_change=-actual_dep, bank_change=actual_dep)
            
            embed = await self.create_economy_embed("✅ Deposit Successful", discord.Color.green())
            embed.description = f"You deposited {self.format_money(actual_dep)} into your bank."
            if actual_dep < dep_amount:
                embed.description += f"\nYour bank is now full. {self.format_money(dep_amount - actual_dep)} remains in your wallet."
            
            embed.add_field(name="💵 New Wallet", value=self.format_money(result["wallet"]), inline=True)
            embed.add_field(name="🏦 New Bank", value=f"{self.format_money(result['bank'])} / {self.format_money(result['bank_limit'])}", inline=True)
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "deposit")
    
    @commands.command(name="withdraw", aliases=["with"])
    async def withdraw(self, ctx: commands.Context, amount: str):
        """Withdraw money from your bank to your wallet."""
        try:
            user_data = await self.get_user(ctx.author.id)
            wallet = user_data["wallet"]
            bank = user_data["bank"]
            wallet_limit = user_data["wallet_limit"]
            
            if bank == 0:
                return await ctx.send(embed=await self.create_economy_embed("❌ Bank Empty", discord.Color.red(), "Your bank is empty."))
            
            if amount.lower() in ["all", "max"]:
                with_amount = bank
            else:
                try:
                    with_amount = int(amount)
                except ValueError:
                    return await ctx.send(embed=await self.create_economy_embed("❌ Invalid Amount", discord.Color.red(), "Please enter a valid number or 'all'."))
            
            if with_amount <= 0:
                return await ctx.send(embed=await self.create_economy_embed("❌ Invalid Amount", discord.Color.red(), "Amount must be positive."))
            
            if with_amount > bank:
                return await ctx.send(embed=await self.create_economy_embed("❌ Insufficient Funds", discord.Color.red(), f"You only have {self.format_money(bank)} in your bank."))
            
            wallet_space = wallet_limit - wallet
            if wallet_space <= 0:
                return await ctx.send(embed=await self.create_economy_embed("❌ Wallet Full", discord.Color.red(), "Your wallet is full."))
            
            # Only withdraw what fits
            actual_with = min(with_amount, wallet_space)
            
            result = await self.update_balance(ctx.author.id, wallet_change=actual_with, bank_change=-actual_with)
            
            embed = await self.create_economy_embed("✅ Withdrawal Successful", discord.Color.green())
            embed.description = f"You withdrew {self.format_money(actual_with)} from your bank."
            if actual_with < with_amount:
                embed.description += f"\nYour wallet is now full. {self.format_money(with_amount - actual_with)} remains in your bank."
            
            embed.add_field(name="💵 New Wallet", value=f"{self.format_money(result['wallet'])} / {self.format_money(result['wallet_limit'])}", inline=True)
            embed.add_field(name="🏦 New Bank", value=self.format_money(result["bank"]), inline=True)
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "withdraw")
    
    @commands.command(name="shop")
    async def shop(self, ctx: commands.Context):
        """Display the items available in the shop."""
        try:
            items = await self.get_shop_items()
            if not items:
                return await ctx.send(embed=await self.create_economy_embed("🛍️ Shop is Empty", discord.Color.orange(), "There are no items in the shop right now."))

            embed = await self.create_economy_embed("🛍️ Welcome to the Shop!", discord.Color.blue())
            embed.description = "Use `~buy <item_id>` to purchase an item.\n**All purchases use BANK money.**"
            
            for item in items:
                embed.add_field(
                    name=f"{item['emoji']} {item['name']} (ID: {item['id']})",
                    value=f"**Price:** {self.format_money(item['price'])}\n{item['description']}",
                    inline=False
                )
            await ctx.send(embed=embed)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "shop")

    @commands.command(name="buy")
    async def buy(self, ctx: commands.Context, item_id: int):
        """Buy an item from the shop using BANK money."""
        try:
            item = await self.get_shop_item(item_id)
            if not item:
                return await ctx.send(embed=await self.create_economy_embed("❌ Item Not Found", discord.Color.red(), f"No item with ID {item_id} found in the shop."))
            
            user_data = await self.get_user(ctx.author.id)
            if user_data["bank"] < item["price"]:
                return await ctx.send(embed=await self.create_economy_embed("❌ Insufficient Bank Funds", discord.Color.red(), f"You need {self.format_money(item['price'])} in your bank to buy this."))
            
            # Process purchase
            result = await self.update_balance(ctx.author.id, bank_change=-item["price"])
            
            if item["type"] == "upgrade":
                effect = item["effect"]
                new_limit = 0
                if "wallet_limit" in effect:
                    new_limit = user_data["wallet_limit"] + effect["wallet_limit"]
                    await db.update_user(ctx.author.id, {"wallet_limit": new_limit})
                    msg = f"Your wallet limit is now {self.format_money(new_limit)}!"
                elif "bank_limit" in effect:
                    new_limit = user_data["bank_limit"] + effect["bank_limit"]
                    await db.update_user(ctx.author.id, {"bank_limit": new_limit})
                    msg = f"Your bank limit is now {self.format_money(new_limit)}!"
                
                embed = await self.create_economy_embed("✅ Upgrade Purchased!", discord.Color.green())
                embed.description = f"You bought **{item['name']}** for {self.format_money(item['price'])}.\n{msg}"
                embed.add_field(name="🏦 New Bank", value=self.format_money(result["bank"]), inline=True)
                await ctx.send(embed=embed)
                
            else: # Add other item types like 'consumable' here
                await self.add_to_inventory(ctx.author.id, item)
                embed = await self.create_economy_embed("✅ Item Purchased!", discord.Color.green())
                embed.description = f"You bought **{item['name']}** for {self.format_money(item['price'])}.\nIt has been added to your inventory."
                embed.add_field(name="🏦 New Bank", value=self.format_money(result["bank"]), inline=True)
                await ctx.send(embed=embed)

        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "buy")

    @commands.command(name="inventory", aliases=["inv"])
    async def inventory(self, ctx: commands.Context, member: discord.Member = None):
        """Check your or someone else's inventory."""
        try:
            member = member or ctx.author
            inv = await self.get_inventory(member.id)
            
            if not inv:
                return await ctx.send(embed=await self.create_economy_embed(f"🎒 {member.display_name}'s Inventory", discord.Color.orange(), "Inventory is empty."))
            
            embed = await self.create_economy_embed(f"🎒 {member.display_name}'s Inventory", discord.Color.blue())
            embed.description = "Use `~use <item_id>` to use an item."
            
            for item in inv:
                item_desc = f"**ID:** {item['item_id']} | **Type:** {item['type'].title()}"
                if item.get("quantity", 1) > 1:
                    item_desc += f" | **Quantity:** {item['quantity']}"
                if item.get("uses_remaining"):
                    item_desc += f" | **Uses:** {item['uses_remaining']}"
                    
                embed.add_field(name=f"{item['emoji']} {item['name']}", value=item_desc, inline=False)
                
            await ctx.send(embed=embed)
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "inventory")

    @commands.command(name="use")
    async def use(self, ctx: commands.Context, item_id: int):
        """Use an item from your inventory."""
        try:
            item = await self.get_inventory_item(ctx.author.id, item_id)
            if not item:
                return await ctx.send(embed=await self.create_economy_embed("❌ Item Not Found", discord.Color.red(), "You don't have an item with that ID."))
            
            # Simple use logic (just remove it)
            # More complex logic would go here
            
            success = await self.use_item(ctx.author.id, item_id)
            
            if success:
                embed = await self.create_economy_embed("✨ Item Used!", discord.Color.green())
                embed.description = f"You used **{item['name']}**."
                # Add effect description here if any
                await ctx.send(embed=embed)
            else:
                raise Exception("Failed to use item from database.")
                
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "use")

    @commands.command(name="upgrade")
    async def upgrade(self, ctx: commands.Context, upgrade_type: str = None):
        """Upgrade your wallet or bank limit."""
        try:
            if not upgrade_type or upgrade_type.lower() not in ["wallet", "bank"]:
                embed = await self.create_economy_embed("🔧 Upgrade Center", discord.Color.blue())
                embed.description = "Use `~upgrade wallet` or `~upgrade bank` to see available upgrades.\nUpgrades are purchased from the `~shop`."
                
                items = await self.get_shop_items()
                wallet_upgrades = [i for i in items if i["type"] == "upgrade" and "wallet_limit" in i["effect"]]
                bank_upgrades = [i for i in items if i["type"] == "upgrade" and "bank_limit" in i["effect"]]
                
                if wallet_upgrades:
                    wallet_str = "\n".join([f"• {i['name']} (ID: {i['id']}) - {self.format_money(i['price'])}" for i in wallet_upgrades])
                    embed.add_field(name="💵 Wallet Upgrades", value=wallet_str, inline=False)
                if bank_upgrades:
                    bank_str = "\n".join([f"• {i['name']} (ID: {i['id']}) - {self.format_money(i['price'])}" for i in bank_upgrades])
                    embed.add_field(name="🏦 Bank Upgrades", value=bank_str, inline=False)
                    
                return await ctx.send(embed=embed)
            
            # Find the best available upgrade of that type
            items = await self.get_shop_items()
            if upgrade_type.lower() == "wallet":
                upgrades = [i for i in items if i["type"] == "upgrade" and "wallet_limit" in i["effect"]]
            else:
                upgrades = [i for i in items if i["type"] == "upgrade" and "bank_limit" in i["effect"]]
            
            if not upgrades:
                return await ctx.send(embed=await self.create_economy_embed("❌ No Upgrades", discord.Color.red(), f"No {upgrade_type} upgrades found in the shop."))
            
            # For simplicity, just show the list again
            embed = await self.create_economy_embed(f"🔧 {upgrade_type.title()} Upgrades", discord.Color.blue())
            embed.description = "Use `~buy <item_id>` to purchase one."
            upgrade_str = "\n".join([f"• {i['name']} (ID: {i['id']}) - {self.format_money(i['price'])}" for i in upgrades])
            embed.add_field(name=f"Available {upgrade_type.title()} Upgrades", value=upgrade_str, inline=False)
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "upgrade")
            
async def setup(bot):
    await bot.add_cog(Economy(bot))
