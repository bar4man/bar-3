# constants.py
# This file centralizes all configuration constants for your cogs.

class EconomyConfig:
    # --- Economy ---
    STARTING_MONEY = 100
    DEFAULT_WALLET_LIMIT = 10000
    DEFAULT_BANK_LIMIT = 50000
    
    # --- Work ---
    WORK_COOLDOWN = 3600  # 1 hour
    WORK_MIN_EARN = 50
    WORK_MAX_EARN = 300
    WORK_CRITICAL_CHANCE = 0.1  # 10%
    
    # --- Daily ---
    DAILY_REWARD = 500
    DAILY_COOLDOWN = 86400  # 24 hours
    DAILY_STREAK_BONUS = 100  # Extra 100 per streak day

class BartenderConfig:
    # --- Cooldowns ---
    DRINK_GLOBAL_COOLDOWN = 5  # 5 seconds
    DRINK_COOLDOWN = 30         # 30 seconds for the *same* drink
    GIFT_COOLDOWN = 10          # 10 seconds
    
    # --- Limits ---
    MAX_DRINK_ORDER_AMOUNT = 5
    MAX_INTOXICATION = 10
    FORCE_SOBER_LEVEL = 9
    INTOXICATION_DANGER_LEVEL = 8
    INTOXICATION_WARNING_LEVEL = 7
    
    # --- Sobering ---
    SOBERING_RATE = 1  # 1 point per 5 minutes
    SOBERING_DRINKS = ["water"]
    
    # --- Other ---
    STRONG_DRINKS = ["whiskey", "vodka", "oldfashioned"]

class GamblingConfig:
    # --- Coinflip ---
    COINFLIP_WIN_CHANCE = 0.55  # 55%
    COINFLIP_PAYOUT = 1.8
    
    # --- Dice ---
    DICE_WIN_NUMBERS = [4, 5, 6]
    DICE_PAYOUTS = {
        4: 1.5,
        5: 2.0,
        6: 5.0
    }
    
    # --- Slots ---
    SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "💎", "7️⃣"]
    SLOT_WEIGHTS = [30, 25, 20, 15, 10]  # Weights for symbols
    SLOT_PAYOUTS = {
        "three_7️⃣": 30.0,
        "three_💎": 20.0,
        "three_🍒": 10.0,
        "three_🍊": 5.0,
        "three_🍋": 3.0,
        "two_matching": 1.2
    }
    
    # --- RPS ---
    RPS_PAYOUT = 2.0
