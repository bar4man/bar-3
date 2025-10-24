"""
Configuration constants for the bot economy system.
"""

# Economy Constants
class EconomyConfig:
    # Wallet and Bank
    DEFAULT_WALLET_LIMIT = 50000
    DEFAULT_BANK_LIMIT = 500000
    MAX_WALLET_LIMIT = 10_000_000
    MAX_BANK_LIMIT = 100_000_000
    
    # Money Values
    STARTING_MONEY = 100
    DAILY_MIN = 1000
    DAILY_MAX = 2000
    DAILY_STREAK_BONUS = 100
    MAX_DAILY_STREAK = 7
    
    # Work System
    WORK_COOLDOWN = 3600  # 1 hour
    WORK_MIN_EARN = 80
    WORK_MAX_EARN = 600
    WORK_CRITICAL_CHANCE = 0.1
    
    # Begging System
    BEG_COOLDOWN = 300  # 5 minutes
    BEG_MIN = 10
    BEG_MAX = 70
    BEG_SUCCESS_RATE = 0.8

# Gambling Constants
class GamblingConfig:
    # Coin Flip
    COINFLIP_WIN_CHANCE = 0.55  # Improved from 0.5
    COINFLIP_PAYOUT = 1.8
    
    # Dice Game
    DICE_WIN_NUMBERS = [4, 5, 6]  # Winning numbers
    DICE_PAYOUTS = {4: 1.5, 5: 2.0, 6: 5.0}
    
    # Slots
    SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "💎", "7️⃣"]
    SLOT_WEIGHTS = [30, 25, 20, 5, 2]  # Probabilities
    SLOT_PAYOUTS = {
        "three_7️⃣": 30,
        "three_💎": 20,
        "three_🍒": 10,
        "three_🍊": 5,
        "three_🍋": 3,
        "two_matching": 1.2
    }
    
    # RPS
    RPS_PAYOUT = 2.0
    RPS_COOLDOWN = 3

# Market Constants  
class MarketConfig:
    TRADING_HOURS = {"open": 9, "close": 17}  # UTC
    PRE_MARKET_OPEN = 8
    AFTER_MARKET_CLOSE = 18
    
    # Fees and Limits
    STOCK_FEE = 0.005  # 0.5%
    GOLD_FEE = 0.01   # 1%
    MIN_GOLD_PURCHASE = 0.1
    MAX_STOCK_ORDER = 1000000
    MAX_GOLD_ORDER = 1000
    
    # Price bounds
    MIN_GOLD_PRICE = 100.0
    MAX_GOLD_PRICE = 5000.0
    STOCK_MIN_RATIO = 0.1
    STOCK_MAX_RATIO = 10.0
    
    # Security
    NEWS_COOLDOWN = 3600
    PRICE_UPDATE_INTERVAL = 300
    MAX_PORTFOLIO_SIZE = 50

# Bartender Constants
class BartenderConfig:
    MAX_INTOXICATION = 10
    SOBERING_RATE = 1  # points per 5 minutes
    INTOXICATION_WARNING_LEVEL = 5
    INTOXICATION_DANGER_LEVEL = 8
    FORCE_SOBER_LEVEL = 9
    
    # Drink Cooldowns
    DRINK_COOLDOWN = 30
    DRINK_GLOBAL_COOLDOWN = 10
    SOBER_UP_COOLDOWN = 300
    
    # Drink Effects
    MAX_MOOD_BOOST = 3
    SOBERING_DRINKS = ["water"]
    STRONG_DRINKS = ["whiskey", "vodka", "oldfashioned", "martini"]
    
    # Security
    MAX_DRINK_ORDER_AMOUNT = 10
    GIFT_COOLDOWN = 60

# Security Constants
class SecurityConfig:
    SPAM_LIMIT = 5
    SPAM_TIMEFRAME = 5  # seconds
    MAX_TRACKED_USERS = 1000
    CLEANUP_INTERVAL = 60  # seconds

# Admin Constants
class AdminConfig:
    # Role names for permission system
    ADMIN_ROLE_NAME = "bot-admin"
    MOD_ROLE_NAME = "moderator"
    MUTED_ROLE_NAME = "Muted"
    
    # Security settings
    MAX_CLEAR_MESSAGES = 100
    MIN_CLEAR_MESSAGES = 1
    CLEAR_CONFIRMATION_TIMEOUT = 3
    
    # Moderation limits
    MAX_REASON_LENGTH = 1000
    MAX_BAN_REASON_LENGTH = 512  # Discord limit
