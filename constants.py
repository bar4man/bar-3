# constants.py
# This file centralizes all configuration constants for your cogs.

class EconomyConfig:
    # --- Economy ---
    STARTING_MONEY = 500  # Increased
    DEFAULT_WALLET_LIMIT = 25000  # Increased
    DEFAULT_BANK_LIMIT = 100000  # Increased
    
    # --- Work ---
    WORK_COOLDOWN = 1800  # 30 minutes (Less restrictive)
    WORK_MIN_EARN = 100  # Increased
    WORK_MAX_EARN = 500  # Increased
    WORK_CRITICAL_CHANCE = 0.15  # 15% (Increased)
    
    # --- Daily ---
    DAILY_REWARD = 1000  # Increased
    DAILY_COOLDOWN = 86400  # 24 hours
    DAILY_STREAK_BONUS = 250  # Increased

class BartenderConfig:
    # --- Cooldowns ---
    DRINK_GLOBAL_COOLDOWN = 3  # 3 seconds (Less restrictive)
    DRINK_COOLDOWN = 15         # 15 seconds for the *same* drink (Less restrictive)
    GIFT_COOLDOWN = 5           # 5 seconds (Less restrictive)
    
    # --- Limits ---
    MAX_DRINK_ORDER_AMOUNT = 10 # (Less restrictive)
    MAX_INTOXICATION = 10
    FORCE_SOBER_LEVEL = 10        # (Less restrictive)
    INTOXICATION_DANGER_LEVEL = 9 # (Less restrictive)
    INTOXICATION_WARNING_LEVEL = 8  # (Less restrictive)
    
    # --- Sobering ---
    SOBERING_RATE = 2  # 2 points per 5 minutes (Faster)
    SOBERING_DRINKS = ["water"]
    
    # --- Other ---
    STRONG_DRINKS = ["whiskey", "vodka", "oldfashioned"]

class GamblingConfig:
    # --- Coinflip ---
    COINFLIP_WIN_CHANCE = 0.60  # 60% (More rewarding)
    COINFLIP_PAYOUT = 1.9       # (More rewarding)
    
    # --- Dice ---
    DICE_WIN_NUMBERS = [3, 4, 5, 6] # (Better odds)
    DICE_PAYOUTS = {
        3: 1.2,  # (New payout)
        4: 1.8,  # (More rewarding)
        5: 2.5,  # (More rewarding)
        6: 6.0   # (More rewarding)
    }
    
    # --- Slots ---
    SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "💎", "7️⃣"]
    SLOT_WEIGHTS = [30, 25, 20, 15, 10]  # Weights for symbols
    SLOT_PAYOUTS = {
        "three_7️⃣": 50.0,  # (More rewarding)
        "three_💎": 30.0,  # (More rewarding)
        "three_🍒": 15.0,  # (More rewarding)
        "three_🍊": 5.0,
        "three_🍋": 3.0,
        "two_matching": 1.5 # (More rewarding)
    }
    
    # --- RPS ---
    RPS_PAYOUT = 2.2 # (More rewarding)

class MarketConfig:
    TRADING_HOURS = {"open": 9, "close": 17}  # 9 AM - 5 PM UTC
    BASE_VOLATILITY = 0.02
    MAX_VOLATILITY = 0.05
    NEWS_COOLDOWN = 180  # 3 minutes (Less restrictive)
    MAX_STOCK_ORDER = 50000  # (Less restrictive)
    MAX_GOLD_ORDER = 5000    # (Less restrictive)
    MAX_PORTFOLIO_SIZE = 20  # (Less restrictive)
    NEWS_IMPACT_MULTIPLIER = 0.75 # (More impactful)
    MIN_GOLD_PRICE = 1500
    MAX_GOLD_PRICE = 2500
    STOCK_MIN_RATIO = 0.5
    STOCK_MAX_RATIO = 3.0

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
