import discord
from discord.ext import commands, tasks
import random
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import math
from economy import db

# ---------------- Market Configuration Constants ----------------
class MarketConfig:
    # Trading Hours
    TRADING_HOURS = {"open": 9, "close": 17}  # UTC
    PRE_MARKET_OPEN = 8  # 8 AM UTC
    AFTER_MARKET_CLOSE = 18  # 6 PM UTC
    
    # Fees and Limits
    STOCK_FEE = 0.005  # 0.5%
    GOLD_FEE = 0.01    # 1%
    MIN_GOLD_PURCHASE = 0.1
    MAX_STOCK_ORDER = 1000000  # 1 million shares
    MAX_GOLD_ORDER = 1000  # 1000 ounces
    
    # Price bounds
    MIN_GOLD_PRICE = 100.0
    MAX_GOLD_PRICE = 5000.0
    STOCK_MIN_RATIO = 0.1   # Can drop to 10% of original
    STOCK_MAX_RATIO = 10.0  # Can grow to 10x original
    
    # Market Volatility
    BASE_VOLATILITY = 0.02  # 2% daily volatility base
    MAX_VOLATILITY = 0.10   # 10% maximum daily volatility
    NEWS_IMPACT_MULTIPLIER = 0.5
    
    # Security
    NEWS_COOLDOWN = 3600  # 1 hour between forced news
    PRICE_UPDATE_INTERVAL = 300  # 5 minutes
    MAX_PORTFOLIO_SIZE = 50  # Maximum different stocks per user

# ---------------- Market Security Manager ----------------
class MarketSecurityManager:
    """Security manager for market system to prevent exploits and manipulation."""
    
    def __init__(self):
        self.news_cooldowns = {}
        self.trade_limits = {}
        self.suspicious_activity = {}
    
    async def check_trade_limit(self, user_id: int, asset_type: str, amount: float) -> tuple[bool, str]:
        """Check if user is within trade limits."""
        now = datetime.now(timezone.utc).timestamp()
        key = f"{user_id}_{asset_type}"
        
        # Initialize tracking
        if key not in self.trade_limits:
            self.trade_limits[key] = {"count": 0, "last_reset": now, "volume": 0}
        
        # Reset daily limits
        if now - self.trade_limits[key]["last_reset"] > 86400:  # 24 hours
            self.trade_limits[key] = {"count": 0, "last_reset": now, "volume": 0}
        
        # Check trade count limit (max 100 trades per day per asset type)
        if self.trade_limits[key]["count"] >= 100:
            return False, "Daily trade limit reached for this asset type (100 trades)"
        
        # Check volume limits
        if asset_type == "stock" and amount > MarketConfig.MAX_STOCK_ORDER:
            return False, f"Cannot trade more than {MarketConfig.MAX_STOCK_ORDER:,} shares at once"
        
        if asset_type == "gold" and amount > MarketConfig.MAX_GOLD_ORDER:
            return False, f"Cannot trade more than {MarketConfig.MAX_GOLD_ORDER:,} ounces at once"
        
        # Check for rapid trading (anti-manipulation)
        rapid_key = f"{user_id}_rapid"
        if rapid_key not in self.suspicious_activity:
            self.suspicious_activity[rapid_key] = []
        
        # Remove old trades (last 5 minutes)
        self.suspicious_activity[rapid_key] = [t for t in self.suspicious_activity[rapid_key] if now - t < 300]
        
        # Check if trading too rapidly (more than 10 trades in 5 minutes)
        if len(self.suspicious_activity[rapid_key]) >= 10:
            return False, "Trading too rapidly. Please slow down to prevent market manipulation."
        
        self.suspicious_activity[rapid_key].append(now)
        self.trade_limits[key]["count"] += 1
        self.trade_limits[key]["volume"] += amount
        
        return True, "OK"
    
    async def check_news_cooldown(self, command: str) -> tuple[bool, float]:
        """Check if news generation is on cooldown."""
        now = datetime.now(timezone.utc).timestamp()
        
        if command in self.news_cooldowns:
            remaining = self.news_cooldowns[command] - now
            if remaining > 0:
                return False, remaining
        
        return True, 0
    
    def set_news_cooldown(self, command: str):
        """Set cooldown for news generation."""
        now = datetime.now(timezone.utc).timestamp()
        self.news_cooldowns[command] = now + MarketConfig.NEWS_COOLDOWN
        
        # Clean up old cooldowns
        self._cleanup_old_cooldowns()
    
    def _cleanup_old_cooldowns(self):
        """Clean up expired cooldowns to prevent memory leaks."""
        now = datetime.now(timezone.utc).timestamp()
        max_age = 86400  # 24 hours
        
        self.news_cooldowns = {
            k: v for k, v in self.news_cooldowns.items() 
            if now - v < max_age
        }
        
        self.trade_limits = {
            k: v for k, v in self.trade_limits.items()
            if now - v["last_reset"] < max_age * 2  # Keep for 2 days for monitoring
        }
        
        # Clean suspicious activity (keep only last hour)
        self.suspicious_activity = {
            k: [t for t in timestamps if now - t < 3600]
            for k, timestamps in self.suspicious_activity.items()
        }
        self.suspicious_activity = {k: v for k, v in self.suspicious_activity.items() if v}
    
    def validate_portfolio_size(self, portfolio: Dict, new_symbol: str = None) -> tuple[bool, str]:
        """Validate portfolio size to prevent excessive diversification."""
        stocks_count = len(portfolio.get("stocks", {}))
        
        if new_symbol and new_symbol not in portfolio.get("stocks", {}):
            stocks_count += 1
        
        if stocks_count > MarketConfig.MAX_PORTFOLIO_SIZE:
            return False, f"Cannot hold more than {MarketConfig.MAX_PORTFOLIO_SIZE} different stocks"
        
        return True, "OK"

class MarketSystem:
    """Enhanced market system with optimized algorithms and exploit prevention."""
    
    def __init__(self):
        self.market_open = False
        self.market_hours = MarketConfig.TRADING_HOURS
        self.last_update = datetime.now(timezone.utc)
        self.volatility = MarketConfig.BASE_VOLATILITY
        self.market_sentiment = 0.0  # -1 to 1 scale
        
        # Gold market specifics
        self.gold_price = 1850.0  # Starting price per ounce
        self.gold_volatility = 0.015
        self.gold_demand = 0.0
        
        # Stock definitions with more realistic data
        self.stocks = {
            "TECH": {
                "name": "Quantum Tech Inc.",
                "sector": "Technology",
                "price": 150.0,
                "previous_price": 150.0,
                "volatility": 0.025,
                "dividend_yield": 0.012,
                "market_cap": 500000000,
                "pe_ratio": 25.0,
                "description": "Leading AI and quantum computing company",
                "volume": 0,
                "day_high": 150.0,
                "day_low": 150.0,
                "base_price": 150.0  # For min/max calculations
            },
            "ENERGY": {
                "name": "SolarFlare Energy",
                "sector": "Energy", 
                "price": 85.0,
                "previous_price": 85.0,
                "volatility": 0.018,
                "dividend_yield": 0.032,
                "market_cap": 200000000,
                "pe_ratio": 15.0,
                "description": "Renewable energy solutions provider",
                "volume": 0,
                "day_high": 85.0,
                "day_low": 85.0,
                "base_price": 85.0
            },
            "BANK": {
                "name": "Global Trust Bank",
                "sector": "Financial",
                "price": 45.0,
                "previous_price": 45.0,
                "volatility": 0.015,
                "dividend_yield": 0.045,
                "market_cap": 800000000,
                "pe_ratio": 12.0,
                "description": "International banking and financial services",
                "volume": 0,
                "day_high": 45.0,
                "day_low": 45.0,
                "base_price": 45.0
            },
            "PHARMA": {
                "name": "BioGen Pharmaceuticals", 
                "sector": "Healthcare",
                "price": 120.0,
                "previous_price": 120.0,
                "volatility": 0.022,
                "dividend_yield": 0.008,
                "market_cap": 350000000,
                "pe_ratio": 30.0,
                "description": "Biotechnology and pharmaceutical research",
                "volume": 0,
                "day_high": 120.0,
                "day_low": 120.0,
                "base_price": 120.0
            },
            "AUTO": {
                "name": "EcoMotion Motors",
                "sector": "Automotive",
                "price": 65.0,
                "previous_price": 65.0,
                "volatility": 0.020,
                "dividend_yield": 0.015,
                "market_cap": 150000000,
                "pe_ratio": 18.0,
                "description": "Electric vehicle manufacturer",
                "volume": 0,
                "day_high": 65.0,
                "day_low": 65.0,
                "base_price": 65.0
            }
        }
        
        # Economic indicators
        self.inflation_rate = 0.025
        self.interest_rate = 0.035
        self.gdp_growth = 0.028
        
        # News events that affect markets
        self.news_events = []
        self.market_trend = "stable"  # bull, bear, stable
        self._news_impact_cache = {}  # Cache for news impacts
        self.generate_news_events()
        
        # Trading volume tracking
        self.daily_volume = 0
        self.market_cap_total = sum(stock["market_cap"] for stock in self.stocks.values())
    
    def generate_news_events(self):
        """Generate random news events that affect market sentiment."""
        positive_events = [
            {"type": "positive", "impact": 0.1, "text": "Strong economic growth reported across sectors"},
            {"type": "positive", "impact": 0.08, "text": "Consumer confidence reaches all-time high"},
            {"type": "positive", "impact": 0.12, "text": "Government announces major infrastructure spending"},
            {"type": "positive", "impact": 0.06, "text": "Unemployment rate drops to record low"},
            {"type": "positive", "impact": 0.09, "text": "Global markets show strong recovery signs"}
        ]
        
        negative_events = [
            {"type": "negative", "impact": -0.08, "text": "Inflation concerns rise among investors"},
            {"type": "negative", "impact": -0.11, "text": "Global trade tensions escalate"},
            {"type": "negative", "impact": -0.07, "text": "Manufacturing data shows slowdown"},
            {"type": "negative", "impact": -0.09, "text": "Housing market shows signs of cooling"},
            {"type": "negative", "impact": -0.13, "text": "Geopolitical tensions affect global markets"}
        ]
        
        sector_events = [
            {"type": "sector", "sector": "TECH", "impact": 0.15, "text": "Breakthrough in quantum computing announced"},
            {"type": "sector", "sector": "TECH", "impact": -0.12, "text": "Tech sector faces regulatory scrutiny"},
            {"type": "sector", "sector": "ENERGY", "impact": 0.14, "text": "Renewable energy adoption exceeds expectations"},
            {"type": "sector", "sector": "ENERGY", "impact": -0.10, "text": "Oil supply disruptions affect energy sector"},
            {"type": "sector", "sector": "BANK", "impact": 0.08, "text": "Banks report strong quarterly earnings"},
            {"type": "sector", "sector": "BANK", "impact": -0.11, "text": "Interest rate concerns weigh on banking stocks"},
            {"type": "sector", "sector": "PHARMA", "impact": 0.18, "text": "New drug approval boosts pharmaceutical sector"},
            {"type": "sector", "sector": "PHARMA", "impact": -0.09, "text": "Clinical trial results disappoint investors"},
            {"type": "sector", "sector": "AUTO", "impact": 0.12, "text": "Electric vehicle sales surge globally"},
            {"type": "sector", "sector": "AUTO", "impact": -0.08, "text": "Supply chain issues affect auto manufacturers"}
        ]
        
        gold_events = [
            {"type": "gold", "impact": 0.15, "text": "Gold demand surges as safe haven asset"},
            {"type": "gold", "impact": -0.08, "text": "Strong dollar pressures gold prices downward"},
            {"type": "gold", "impact": 0.12, "text": "Central banks increase gold reserves"},
            {"type": "gold", "impact": -0.06, "text": "Improved economic outlook reduces gold appeal"}
        ]
        
        # Mix events for variety (3-5 events)
        all_events = positive_events + negative_events + sector_events + gold_events
        num_events = random.randint(3, 5)
        self.news_events = random.sample(all_events, num_events)
        
        # Pre-calculate news impacts for performance
        self._precalculate_news_impacts()
        
        # Determine market trend based on news
        total_impact = sum(event["impact"] for event in self.news_events)
        if total_impact > 0.1:
            self.market_trend = "bull"
        elif total_impact < -0.1:
            self.market_trend = "bear"
        else:
            self.market_trend = "stable"
    
    def _precalculate_news_impacts(self):
        """Pre-calculate news impacts for optimized price updates."""
        self._news_impact_cache = {}
        
        for event in self.news_events:
            if event["type"] == "sector":
                sector = event["sector"]
                if sector not in self._news_impact_cache:
                    self._news_impact_cache[sector] = 0
                self._news_impact_cache[sector] += event["impact"] * MarketConfig.NEWS_IMPACT_MULTIPLIER
            elif event["type"] == "gold":
                if "gold" not in self._news_impact_cache:
                    self._news_impact_cache["gold"] = 0
                self._news_impact_cache["gold"] += event["impact"] * MarketConfig.NEWS_IMPACT_MULTIPLIER
    
    def calculate_market_sentiment(self):
        """Calculate current market sentiment based on various factors."""
        base_sentiment = random.uniform(-0.2, 0.2)
        
        # Economic factors
        if self.gdp_growth > 0.03:
            base_sentiment += 0.1
        elif self.gdp_growth < 0.02:
            base_sentiment -= 0.1
            
        if self.inflation_rate > 0.03:
            base_sentiment -= 0.15
        elif self.inflation_rate < 0.02:
            base_sentiment += 0.05
            
        if self.interest_rate > 0.04:
            base_sentiment -= 0.1
        elif self.interest_rate < 0.03:
            base_sentiment += 0.05
            
        # News impact (use cached values)
        for event in self.news_events:
            if event["type"] in ["positive", "negative"]:
                base_sentiment += event["impact"]
        
        # Market trend influence
        if self.market_trend == "bull":
            base_sentiment += 0.1
        elif self.market_trend == "bear":
            base_sentiment -= 0.1
        
        # Keep within bounds
        self.market_sentiment = max(-1.0, min(1.0, base_sentiment))
        return self.market_sentiment
    
    def update_prices(self):
        """Optimized price updates with pre-calculated news impacts."""
        if not self.market_open:
            return
            
        sentiment = self.calculate_market_sentiment()
        
        # Update gold price
        gold_change = random.gauss(0, self.gold_volatility)
        gold_change += sentiment * 0.01  # Market sentiment effect
        gold_change += self.gold_demand * 0.005  # Demand effect
        
        # Apply cached gold news effects
        gold_news_impact = self._news_impact_cache.get("gold", 0)
        gold_change += gold_news_impact
        
        # Update gold price with bounds
        old_gold_price = self.gold_price
        self.gold_price *= (1 + gold_change)
        self.gold_price = max(MarketConfig.MIN_GOLD_PRICE, min(MarketConfig.MAX_GOLD_PRICE, self.gold_price))
        
        # Batch update stocks using cached news impacts
        for symbol, stock in self.stocks.items():
            # Store previous price
            stock["previous_price"] = stock["price"]
            
            # Base random movement with volatility clamping
            volatility = min(stock["volatility"], MarketConfig.MAX_VOLATILITY)
            change = random.gauss(0, volatility)
            
            # Market sentiment effect
            change += sentiment * volatility * 2
            
            # Sector-specific news (optimized using cache)
            sector_impact = self._news_impact_cache.get(symbol, 0)
            change += sector_impact
            
            # Company-specific factors
            earnings_surprise = random.gauss(0, 0.02)
            change += earnings_surprise
            
            # Apply change with realistic bounds
            new_price = stock["price"] * (1 + change)
            
            # Calculate min/max prices based on base price
            min_price = stock["base_price"] * MarketConfig.STOCK_MIN_RATIO
            max_price = stock["base_price"] * MarketConfig.STOCK_MAX_RATIO
            
            stock["price"] = max(min_price, min(max_price, new_price))
            
            # Update day high/low
            stock["day_high"] = max(stock["day_high"], stock["price"])
            stock["day_low"] = min(stock["day_low"], stock["price"])
            
            # Simulate some trading volume
            stock["volume"] += random.randint(1000, 10000)
        
        # Calculate total daily volume
        self.daily_volume = sum(stock["volume"] for stock in self.stocks.values())
        self.last_update = datetime.now(timezone.utc)
    
    def get_price_change(self, symbol):
        """Calculate price change percentage for a stock."""
        if symbol in self.stocks:
            stock = self.stocks[symbol]
            if stock["previous_price"] > 0:
                return ((stock["price"] - stock["previous_price"]) / stock["previous_price"]) * 100
        return 0
    
    def get_market_status(self):
        """Get current market status and trends."""
        # Calculate overall market change
        total_change = 0
        valid_stocks = 0
        
        for symbol in self.stocks:
            change = self.get_price_change(symbol)
            if not math.isnan(change) and not math.isinf(change):
                total_change += change
                valid_stocks += 1
        
        avg_change = total_change / valid_stocks if valid_stocks > 0 else 0
        
        status = {
            "market_open": self.market_open,
            "sentiment": self.market_sentiment,
            "trend": self.market_trend,
            "gold_price": self.gold_price,
            "market_change": avg_change,
            "daily_volume": self.daily_volume,
            "last_update": self.last_update,
            "news": self.news_events
        }
        return status

class MarketCog(commands.Cog):
    """Enhanced market trading system with security and performance improvements."""
    
    def __init__(self, bot):
        self.bot = bot
        self.market = MarketSystem()
        self.security_manager = MarketSecurityManager()
        self.price_update_task = self.update_market_prices.start()
        self.market_hours_task = self.manage_market_hours.start()
        self.news_announcement_task = self.announce_market_news.start()
        self.announcement_channel_id = None
        logging.info("✅ Market system initialized with security features")
    
    def cog_unload(self):
        """Cleanup tasks when cog is unloaded."""
        self.price_update_task.cancel()
        self.market_hours_task.cancel()
        self.news_announcement_task.cancel()
    
    @tasks.loop(minutes=5)
    async def update_market_prices(self):
        """Update market prices every 5 minutes when market is open."""
        if self.market.market_open:
            self.market.update_prices()
            logging.debug("📈 Market prices updated")
    
    @tasks.loop(minutes=1)
    async def manage_market_hours(self):
        """Manage market opening/closing based on UTC time with extended hours."""
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        
        # Market hours: 9 AM to 5 PM UTC, with pre/after market
        if MarketConfig.TRADING_HOURS["open"] <= current_hour < MarketConfig.TRADING_HOURS["close"]:
            if not self.market.market_open:
                self.market.market_open = True
                self.market.generate_news_events()  # New events each day
                # Reset daily stats
                for stock in self.market.stocks.values():
                    stock["day_high"] = stock["price"]
                    stock["day_low"] = stock["price"]
                    stock["volume"] = 0
                self.market.daily_volume = 0
                logging.info("🏛️ Market opened for trading")
                
                # Send market open announcement
                await self.send_market_announcement("🔔 **Market Open**\nTrading is now active for the day!")
        else:
            if self.market.market_open:
                self.market.market_open = False
                logging.info("🏛️ Market closed for the day")
                
                # Send market close announcement with daily summary
                await self.send_market_announcement("🔔 **Market Closed**\nTrading has ended for the day.")
    
    @tasks.loop(minutes=30)
    async def announce_market_news(self):
        """Automatically send market news and updates with reduced frequency."""
        if not self.market.market_open:
            return
            
        # 15% chance to send news every 30 minutes when market is open (reduced from 20%)
        if random.random() < 0.15:
            await self.send_market_update()
    
    async def send_market_announcement(self, message):
        """Send announcement to configured channel with error handling."""
        if self.announcement_channel_id:
            try:
                channel = self.bot.get_channel(self.announcement_channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    embed = await self.create_market_embed("🏛️ Market Announcement", discord.Color.gold())
                    embed.description = message
                    
                    # Add current market status for open/close announcements
                    if "open" in message.lower() or "close" in message.lower():
                        status = self.market.get_market_status()
                        trend_emoji = "📈" if status["trend"] == "bull" else "📉" if status["trend"] == "bear" else "➡️"
                        embed.add_field(
                            name="📊 Market Overview",
                            value=f"Sentiment: {status['sentiment']:+.2f}\nTrend: {status['trend'].title()} {trend_emoji}",
                            inline=True
                        )
                        
                        # Top movers
                        movers = self.get_top_movers()
                        if movers:
                            movers_text = "\n".join([f"**{symbol}**: {change:+.1f}%" for symbol, change in movers[:3]])
                            embed.add_field(name="🚀 Top Movers", value=movers_text, inline=True)
                    
                    await channel.send(embed=embed)
            except Exception as e:
                logging.error(f"Error sending market announcement: {e}")
    
    async def send_market_update(self):
        """Send periodic market updates with importance filtering."""
        if not self.announcement_channel_id:
            return
            
        try:
            channel = self.bot.get_channel(self.announcement_channel_id)
            if not channel:
                return
                
            status = self.market.get_market_status()
            
            # Only send updates if there's significant movement or important news
            significant_movement = abs(status["market_change"]) > 1.5  # Increased threshold
            important_news = any(abs(event["impact"]) > 0.15 for event in status["news"])  # Higher impact threshold
            
            if significant_movement or important_news:
                embed = await self.create_market_embed("📰 Market Update", discord.Color.blue())
                
                # Market summary
                change_emoji = "📈" if status["market_change"] > 0 else "📉" if status["market_change"] < 0 else "➡️"
                embed.add_field(
                    name="📊 Market Summary",
                    value=f"Overall Change: {status['market_change']:+.2f}% {change_emoji}\nGold: ${status['gold_price']:,.2f}/oz",
                    inline=False
                )
                
                # Top movers
                movers = self.get_top_movers()
                if movers:
                    movers_text = "\n".join([f"**{symbol}**: {change:+.1f}%" for symbol, change in movers[:3]])
                    embed.add_field(name="🚀 Top Movers", value=movers_text, inline=True)
                
                # Latest news highlight
                if status["news"]:
                    latest_news = max(status["news"], key=lambda x: abs(x["impact"]))
                    impact_emoji = "📈" if latest_news["impact"] > 0 else "📉" if latest_news["impact"] < 0 else "📰"
                    embed.add_field(
                        name=f"{impact_emoji} Market News",
                        value=latest_news["text"],
                        inline=False
                    )
                
                await channel.send(embed=embed)
        except Exception as e:
            logging.error(f"Error sending market update: {e}")
    
    def get_top_movers(self, count=5):
        """Get top gaining and losing stocks with validation."""
        movers = []
        for symbol in self.market.stocks:
            change = self.market.get_price_change(symbol)
            # Filter out invalid changes
            if not math.isnan(change) and not math.isinf(change):
                movers.append((symbol, change))
        
        # Sort by absolute change (biggest movers first)
        movers.sort(key=lambda x: abs(x[1]), reverse=True)
        return movers[:count]
    
    async def get_user_portfolio(self, user_id: int) -> Dict:
        """Get user's investment portfolio using economy cog with validation."""
        economy_cog = self.bot.get_cog("Economy")
        if economy_cog:
            portfolio = await economy_cog.get_user_portfolio(user_id)
            # Validate portfolio structure
            if not isinstance(portfolio.get("stocks"), dict):
                portfolio["stocks"] = {}
            if not isinstance(portfolio.get("gold_ounces"), (int, float)) or portfolio["gold_ounces"] < 0:
                portfolio["gold_ounces"] = 0.0
            return portfolio
        return {
            "gold_ounces": 0.0,
            "stocks": {},
            "total_investment": 0,
            "total_value": 0,
            "daily_pnl": 0,
            "total_pnl": 0
        }
    
    async def update_user_portfolio(self, user_id: int, portfolio: Dict):
        """Update user's investment portfolio with security validation."""
        # Validate portfolio before update
        is_valid, error_msg = self.security_manager.validate_portfolio_size(portfolio)
        if not is_valid:
            logging.warning(f"Invalid portfolio update for user {user_id}: {error_msg}")
            # Don't update if portfolio would be too large
            return
        
        economy_cog = self.bot.get_cog("Economy")
        if economy_cog:
            await economy_cog.update_user_portfolio(user_id, portfolio)
    
    async def create_market_embed(self, title: str, color: discord.Color = discord.Color.blue()) -> discord.Embed:
        """Create a standardized market embed."""
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        
        status = "🟢 OPEN" if self.market.market_open else "🔴 CLOSED"
        sentiment_emoji = "📈" if self.market.market_sentiment > 0 else "📉" if self.market.market_sentiment < 0 else "➡️"
        
        embed.set_footer(text=f"Market: {status} | Sentiment: {sentiment_emoji}")
        return embed

    # ========== MARKET COMMANDS ==========
    
    @commands.command(name="setmarketchannel")
    @commands.has_permissions(administrator=True)
    async def set_market_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel for market announcements and news with validation."""
        channel = channel or ctx.channel
        
        # Validate channel permissions
        bot_permissions = channel.permissions_for(ctx.guild.me)
        if not all([bot_permissions.send_messages, bot_permissions.embed_links, bot_permissions.read_message_history]):
            embed = await self.create_market_embed("❌ Invalid Channel", discord.Color.red())
            embed.description = "I need `Send Messages`, `Embed Links`, and `Read Message History` permissions in that channel."
            await ctx.send(embed=embed)
            return
        
        self.announcement_channel_id = channel.id
        
        embed = await self.create_market_embed("✅ Market Channel Set", discord.Color.green())
        embed.description = f"Market announcements and news will now be sent to {channel.mention}"
        await ctx.send(embed=embed)
    
    @commands.command(name="market", aliases=["mkt"])
    async def market_status(self, ctx: commands.Context):
        """View current market status and prices with optimized rendering."""
        status = self.market.get_market_status()
        
        embed = await self.create_market_embed("🏛️ Financial Markets")
        
        # Market overview
        status_text = "**OPEN** 🟢" if status["market_open"] else "**CLOSED** 🔴"
        trend_emoji = "📈" if status["trend"] == "bull" else "📉" if status["trend"] == "bear" else "➡️"
        
        embed.add_field(
            name="📊 Market Overview",
            value=(
                f"Status: {status_text}\n"
                f"Trend: {status['trend'].title()} {trend_emoji}\n"
                f"Sentiment: {status['sentiment']:+.2f}\n"
                f"Daily Volume: {status['daily_volume']:,}\n"
                f"Gold: ${status['gold_price']:,.2f}/oz"
            ),
            inline=False
        )
        
        # Stock prices with changes (limited to 5 for performance)
        stocks_text = ""
        stock_count = 0
        for symbol, stock in self.market.stocks.items():
            if stock_count >= 5:  # Limit to 5 stocks in main view
                break
            change = self.market.get_price_change(symbol)
            change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            stocks_text += f"**{symbol}**: ${stock['price']:,.2f} ({change:+.1f}%) {change_emoji}\n"
            stock_count += 1
        
        if stocks_text:
            embed.add_field(name="💹 Stocks", value=stocks_text, inline=True)
        
        # Top movers
        movers = self.get_top_movers(3)
        if movers:
            movers_text = "\n".join([f"**{symbol}**: {change:+.1f}%" for symbol, change in movers])
            embed.add_field(name="🚀 Top Movers", value=movers_text, inline=True)
        
        # Economic indicators
        econ_text = (
            f"Inflation: {self.market.inflation_rate:.1%}\n"
            f"Interest Rate: {self.market.interest_rate:.1%}\n"
            f"GDP Growth: {self.market.gdp_growth:.1%}"
        )
        embed.add_field(name="📈 Economy", value=econ_text, inline=True)
        
        # News highlights (limited to 2)
        if status["news"]:
            news_text = "\n".join([f"• {event['text']}" for event in status["news"][:2]])
            embed.add_field(name="📰 Market News", value=news_text, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(name="buyinvest", aliases=["investbuy", "ibuy"])
    async def buy_investment(self, ctx: commands.Context, asset_type: str, *, args: str):
        """Buy stocks or gold for investment with security checks."""
        if asset_type.lower() not in ["stock", "gold"]:
            embed = await self.create_market_embed("❌ Invalid Asset Type", discord.Color.red())
            embed.description = "Please specify either `stock` or `gold`.\n\n**Examples:**\n`~buyinvest stock TECH 10` - Buy 10 shares of TECH\n`~buyinvest gold 5` - Buy 5 ounces of gold"
            return await ctx.send(embed=embed)
        
        if not self.market.market_open:
            embed = await self.create_market_embed("❌ Market Closed", discord.Color.red())
            embed.description = "Trading is only available during market hours (9 AM - 5 PM UTC)."
            return await ctx.send(embed=embed)
        
        try:
            if asset_type.lower() == "stock":
                parts = args.split()
                if len(parts) < 2:
                    embed = await self.create_market_embed("❌ Invalid Syntax", discord.Color.red())
                    embed.description = "Usage: `~buyinvest stock <symbol> <shares>`\nExample: `~buyinvest stock TECH 10`"
                    return await ctx.send(embed=embed)
                
                symbol = parts[0].upper()
                try:
                    shares = int(parts[1])
                except ValueError:
                    embed = await self.create_market_embed("❌ Invalid Share Amount", discord.Color.red())
                    embed.description = "Number of shares must be a whole number."
                    return await ctx.send(embed=embed)
                
                if symbol not in self.market.stocks:
                    embed = await self.create_market_embed("❌ Invalid Stock Symbol", discord.Color.red())
                    embed.description = f"Available stocks: {', '.join(self.market.stocks.keys())}"
                    return await ctx.send(embed=embed)
                
                if shares <= 0:
                    embed = await self.create_market_embed("❌ Invalid Share Amount", discord.Color.red())
                    embed.description = "Number of shares must be greater than 0."
                    return await ctx.send(embed=embed)
                
                # Security check
                can_trade, error_msg = await self.security_manager.check_trade_limit(ctx.author.id, "stock", shares)
                if not can_trade:
                    embed = await self.create_market_embed("❌ Trade Limit", discord.Color.red())
                    embed.description = error_msg
                    return await ctx.send(embed=embed)
                
                stock = self.market.stocks[symbol]
                total_cost = stock["price"] * shares
                fee = total_cost * MarketConfig.STOCK_FEE
                total_with_fee = total_cost + fee
                
                # Check if user has enough money in bank
                user_data = await db.get_user(ctx.author.id)
                if user_data["bank"] < total_with_fee:
                    embed = await self.create_market_embed("❌ Insufficient Funds", discord.Color.red())
                    embed.description = f"You need ${total_with_fee:,.2f} in your bank (including {MarketConfig.STOCK_FEE:.1%} fee), but only have ${user_data['bank']:,.2f}."
                    return await ctx.send(embed=embed)
                
                # Check portfolio size limit
                portfolio = await self.get_user_portfolio(ctx.author.id)
                can_diversify, diversify_error = self.security_manager.validate_portfolio_size(portfolio, symbol)
                if not can_diversify:
                    embed = await self.create_market_embed("❌ Portfolio Limit", discord.Color.red())
                    embed.description = diversify_error
                    return await ctx.send(embed=embed)
                
                # Process purchase
                await db.update_balance(ctx.author.id, bank_change=-total_with_fee)
                
                # Update portfolio
                portfolio["stocks"][symbol] = portfolio["stocks"].get(symbol, 0) + shares
                portfolio["total_investment"] = portfolio.get("total_investment", 0) + total_with_fee
                await self.update_user_portfolio(ctx.author.id, portfolio)
                
                embed = await self.create_market_embed("✅ Stock Purchase Complete", discord.Color.green())
                embed.description = f"Bought {shares:,} shares of {symbol} for ${total_cost:,.2f}"
                embed.add_field(name="💰 Cost", value=f"${total_cost:,.2f}", inline=True)
                embed.add_field(name="💸 Fee", value=f"${fee:,.2f} ({MarketConfig.STOCK_FEE:.1%})", inline=True)
                embed.add_field(name="💳 Total", value=f"${total_with_fee:,.2f}", inline=True)
                embed.add_field(name="📈 Price per Share", value=f"${stock['price']:,.2f}", inline=True)
                embed.add_field(name="💼 New Holdings", value=f"{portfolio['stocks'][symbol]:,} shares", inline=True)
                
            else:  # gold
                try:
                    ounces = float(args)
                    if ounces <= 0:
                        embed = await self.create_market_embed("❌ Invalid Amount", discord.Color.red())
                        embed.description = "Ounces must be greater than 0."
                        return await ctx.send(embed=embed)
                    
                    if ounces < MarketConfig.MIN_GOLD_PURCHASE:
                        embed = await self.create_market_embed("❌ Minimum Not Met", discord.Color.red())
                        embed.description = f"Minimum gold purchase is {MarketConfig.MIN_GOLD_PURCHASE} ounces."
                        return await ctx.send(embed=embed)
                    
                    # Security check
                    can_trade, error_msg = await self.security_manager.check_trade_limit(ctx.author.id, "gold", ounces)
                    if not can_trade:
                        embed = await self.create_market_embed("❌ Trade Limit", discord.Color.red())
                        embed.description = error_msg
                        return await ctx.send(embed=embed)
                    
                    total_cost = self.market.gold_price * ounces
                    fee = total_cost * MarketConfig.GOLD_FEE
                    total_with_fee = total_cost + fee
                    
                    # Check if user has enough money in bank
                    user_data = await db.get_user(ctx.author.id)
                    if user_data["bank"] < total_with_fee:
                        embed = await self.create_market_embed("❌ Insufficient Funds", discord.Color.red())
                        embed.description = f"You need ${total_with_fee:,.2f} in your bank (including {MarketConfig.GOLD_FEE:.1%} fee), but only have ${user_data['bank']:,.2f}."
                        return await ctx.send(embed=embed)
                    
                    # Process purchase
                    result = await db.update_balance(ctx.author.id, bank_change=-total_with_fee)
                    
                    # Update portfolio
                    portfolio = await self.get_user_portfolio(ctx.author.id)
                    portfolio["gold_ounces"] = portfolio.get("gold_ounces", 0) + ounces
                    portfolio["total_investment"] = portfolio.get("total_investment", 0) + total_with_fee
                    await self.update_user_portfolio(ctx.author.id, portfolio)
                    
                    embed = await self.create_market_embed("✅ Gold Purchase Complete", discord.Color.green())
                    embed.description = f"Bought {ounces:,.2f} ounces of gold for ${total_cost:,.2f}"
                    embed.add_field(name="💰 Cost", value=f"${total_cost:,.2f}", inline=True)
                    embed.add_field(name="💸 Fee", value=f"${fee:,.2f} ({MarketConfig.GOLD_FEE:.1%})", inline=True)
                    embed.add_field(name="💳 Total", value=f"${total_with_fee:,.2f}", inline=True)
                    embed.add_field(name="💎 Price per Ounce", value=f"${self.market.gold_price:,.2f}", inline=True)
                    embed.add_field(name="🥇 New Holdings", value=f"{portfolio['gold_ounces']:,.2f} ounces", inline=True)
                    embed.add_field(name="🏦 Remaining Bank", value=f"${result['bank']:,.2f}", inline=True)
                    
                except ValueError:
                    embed = await self.create_market_embed("❌ Invalid Amount", discord.Color.red())
                    embed.description = "Please provide a valid number of ounces.\nExample: `~buyinvest gold 2.5`"
                    return await ctx.send(embed=embed)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error in buy command: {e}")
            embed = await self.create_market_embed("❌ Transaction Failed", discord.Color.red())
            embed.description = "An error occurred during the transaction. Please try again."
            await ctx.send(embed=embed)

    # ... (sellinvest command would have similar security enhancements)

    @commands.command(name="forcnews")
    @commands.has_permissions(administrator=True)
    async def force_news(self, ctx: commands.Context):
        """Force generate new market news with cooldown and security."""
        # Cooldown check
        can_generate, cooldown_remaining = await self.security_manager.check_news_cooldown("force_news")
        if not can_generate:
            embed = await self.create_market_embed("⏰ News Cooldown", discord.Color.orange())
            embed.description = f"You can force news generation again in {int(cooldown_remaining//60)} minutes."
            return await ctx.send(embed=embed)
        
        # Generate news
        self.market.generate_news_events()
        self.security_manager.set_news_cooldown("force_news")
        
        embed = await self.create_market_embed("📰 News Regenerated", discord.Color.green())
        embed.description = f"Market news has been refreshed! ({int(MarketConfig.NEWS_COOLDOWN//60)} minute cooldown)"
        
        if self.market.news_events:
            # Show most impactful news
            impactful_news = sorted(self.market.news_events, key=lambda x: abs(x["impact"]), reverse=True)[:2]
            news_text = "\n".join([f"• {event['text']} (Impact: {event['impact']:+.2f})" for event in impactful_news])
            embed.add_field(name="Latest News", value=news_text, inline=False)
        
        await ctx.send(embed=embed)

    # ... (other market commands would have similar security enhancements)

async def setup(bot):
    await bot.add_cog(MarketCog(bot))
