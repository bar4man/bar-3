from pymongo import MongoClient
import os
import logging
from datetime import datetime

logger = logging.getLogger('discord_bot')

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.users = None
        self.market = None
        self.cooldowns = None
        self.jobs = None
        
    def connect(self):
        """Connect to MongoDB"""
        try:
            mongodb_uri = os.getenv('MONGODB_URI')
            if not mongodb_uri:
                logger.error("MONGODB_URI not found in environment variables!")
                return False
            
            self.client = MongoClient(mongodb_uri)
            self.db = self.client['discord_bot']
            
            # Collections
            self.users = self.db['users']
            self.market = self.db['market']
            self.cooldowns = self.db['cooldowns']
            self.jobs = self.db['jobs']
            
            # Test connection
            self.client.server_info()
            logger.info("Successfully connected to MongoDB!")
            
            # Initialize default data
            self._init_default_data()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
    
    def _init_default_data(self):
        """Initialize default market and jobs data if not exists"""
        try:
            # Initialize market if empty
            if self.market.count_documents({}) == 0:
                default_market = {
                    "stocks": {
                        "TECH": {"name": "Tech Corp", "price": 100, "history": []},
                        "FOOD": {"name": "Food Industries", "price": 50, "history": []},
                        "ENERGY": {"name": "Energy Solutions", "price": 75, "history": []},
                        "GAME": {"name": "Gaming Corp", "price": 120, "history": []},
                        "AUTO": {"name": "Auto Motors", "price": 90, "history": []}
                    },
                    "news": [],
                    "last_update": datetime.utcnow().isoformat()
                }
                self.market.insert_one(default_market)
                logger.info("Initialized default market data")
            
            # Initialize jobs if empty
            if self.jobs.count_documents({}) == 0:
                default_jobs = {
                    "available_jobs": [
                        {"name": "cashier", "pay": 50, "required_balance": 0, "cooldown": 3600, "emoji": "🏪"},
                        {"name": "delivery", "pay": 100, "required_balance": 500, "cooldown": 3600, "emoji": "🚚"},
                        {"name": "chef", "pay": 150, "required_balance": 1000, "cooldown": 5400, "emoji": "👨‍🍳"},
                        {"name": "manager", "pay": 250, "required_balance": 2500, "cooldown": 7200, "emoji": "💼"},
                        {"name": "engineer", "pay": 400, "required_balance": 5000, "cooldown": 10800, "emoji": "⚙️"},
                        {"name": "ceo", "pay": 750, "required_balance": 10000, "cooldown": 14400, "emoji": "👔"}
                    ]
                }
                self.jobs.insert_one(default_jobs)
                logger.info("Initialized default jobs data")
                
        except Exception as e:
            logger.error(f"Error initializing default data: {e}")
    
    # ==================== USER OPERATIONS ====================
    
    def get_user(self, user_id):
        """Get user data or create if doesn't exist"""
        try:
            user_id = str(user_id)
            user = self.users.find_one({"user_id": user_id})
            
            if not user:
                # Create new user
                user = {
                    "user_id": user_id,
                    "wallet": 0,
                    "bank": 0,
                    "total_earned": 0,
                    "inventory": {},
                    "stocks": {},
                    "current_job": None
                }
                self.users.insert_one(user)
                logger.info(f"Created new user: {user_id}")
            
            return user
            
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    def update_user(self, user_id, data):
        """Update user data"""
        try:
            user_id = str(user_id)
            self.users.update_one(
                {"user_id": user_id},
                {"$set": data},
                upsert=True
            )
            return True
            
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return False
    
    def get_all_users(self):
        """Get all users"""
        try:
            return list(self.users.find({}))
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    def delete_user(self, user_id):
        """Delete user data"""
        try:
            user_id = str(user_id)
            self.users.delete_one({"user_id": user_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            return False
    
    # ==================== MARKET OPERATIONS ====================
    
    def get_market(self):
        """Get market data"""
        try:
            market = self.market.find_one({})
            return market if market else {}
        except Exception as e:
            logger.error(f"Error getting market: {e}")
            return {}
    
    def update_market(self, data):
        """Update market data"""
        try:
            self.market.update_one(
                {},
                {"$set": data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error updating market: {e}")
            return False
    
    def update_stock_price(self, symbol, price):
        """Update specific stock price"""
        try:
            self.market.update_one(
                {},
                {"$set": {f"stocks.{symbol}.price": price}}
            )
            return True
        except Exception as e:
            logger.error(f"Error updating stock {symbol}: {e}")
            return False
    
    def add_stock(self, symbol, stock_data):
        """Add new stock to market"""
        try:
            self.market.update_one(
                {},
                {"$set": {f"stocks.{symbol}": stock_data}}
            )
            return True
        except Exception as e:
            logger.error(f"Error adding stock {symbol}: {e}")
            return False
    
    def add_news(self, news_item):
        """Add news to market"""
        try:
            self.market.update_one(
                {},
                {"$push": {"news": news_item}}
            )
            return True
        except Exception as e:
            logger.error(f"Error adding news: {e}")
            return False
    
    # ==================== COOLDOWN OPERATIONS ====================
    
    def get_cooldown(self, user_id, command):
        """Get cooldown for user command"""
        try:
            user_id = str(user_id)
            cooldown = self.cooldowns.find_one({"user_id": user_id})
            
            if cooldown and command in cooldown.get("commands", {}):
                return cooldown["commands"][command]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting cooldown for {user_id}: {e}")
            return None
    
    def set_cooldown(self, user_id, command, timestamp):
        """Set cooldown for user command"""
        try:
            user_id = str(user_id)
            self.cooldowns.update_one(
                {"user_id": user_id},
                {"$set": {f"commands.{command}": timestamp}},
                upsert=True
            )
            return True
            
        except Exception as e:
            logger.error(f"Error setting cooldown for {user_id}: {e}")
            return False
    
    # ==================== JOBS OPERATIONS ====================
    
    def get_jobs(self):
        """Get jobs data"""
        try:
            jobs = self.jobs.find_one({})
            return jobs if jobs else {"available_jobs": []}
        except Exception as e:
            logger.error(f"Error getting jobs: {e}")
            return {"available_jobs": []}
    
    def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

# Global database instance
db = Database()
