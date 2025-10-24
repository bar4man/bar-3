import discord
from discord.ext import commands, tasks
import random
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import math
from economy import db
from error_handler import ErrorHandler # <-- ADDED IMPORT

# ---------------- Market Configuration ----------------
class MarketConfig:
    TRADING_HOURS = {"open": 9, "close": 17}  # 9 AM - 5 PM UTC
    BASE_VOLATILITY = 0.02
    MAX_VOLATILITY = 0.05
    NEWS_COOLDOWN = 300  # 5 minutes
    MAX_STOCK_ORDER = 10000
    MAX_GOLD_ORDER = 1000
    MAX_PORTFOLIO_SIZE = 10
    NEWS_IMPACT_MULTIPLIER = 0.5
    MIN_GOLD_PRICE = 1500
    MAX_GOLD_PRICE = 2500
    STOCK_MIN_RATIO = 0.5
    STOCK_MAX_RATIO = 3.0

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
        self.gold_demand = 0.0  # <-- This will now be changed by buy/sell
        
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
        
        # --- FIXED GOLD DEMAND ---
        # Add demand decay
        self.gold_demand *= 0.95  # Decays demand by 5% each update
        
        # Update gold price
        gold_change = random.gauss(0, self.gold_volatility)
        gold_change += sentiment * 0.01  # Market sentiment effect
        gold_change += self.gold_demand * 0.005  # Demand effect (NOW FUNCTIONAL)
        
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
            sector_impact = self._news_impact_cache.get(symbol, 0) # <-- BUGFIX: was using sector, should be symbol
            if stock["sector"] in self._news_impact_cache:
                 change += self._news_impact_cache[stock["sector"]]

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
        """Announce market news periodically."""
        if self.announcement_channel_id and self.market.market_open:
            try:
                channel = self.bot.get_channel(self.announcement_channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    # Only announce if there are significant news events
                    significant_events = [event for event in self.market.news_events if abs(event["impact"]) > 0.1]
                    
                    if significant_events:
                        embed = discord.Embed(
                            title="📰 Market News Update",
                            color=discord.Color.blue(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        
                        for event in significant_events[:3]:  # Max 3 events
                            impact_emoji = "📈" if event["impact"] > 0 else "📉"
                            embed.add_field(
                                name=f"{impact_emoji} {event['type'].title()} News",
                                value=event["text"],
                                inline=False
                            )
                        
                        embed.set_footer(text="Market news may affect stock and gold prices")
                        await channel.send(embed=embed)
                        
            except Exception as e:
                logging.error(f"Error announcing market news: {e}")
    
    async def send_market_announcement(self, message: str):
        """Send market announcement to the designated channel."""
        if self.announcement_channel_id:
            try:
                channel = self.bot.get_channel(self.announcement_channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    await channel.send(message)
            except Exception as e:
                logging.error(f"Error sending market announcement: {e}")
    
    @commands.command(name="market", aliases=["mkt"])
    async def market_status(self, ctx: commands.Context):
        """Get current market status and trends."""
        status = self.market.get_market_status()
        
        embed = discord.Embed(
            title="🏛️ Market Status",
            color=discord.Color.blue() if status["market_open"] else discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Market status
        status_emoji = "🟢" if status["market_open"] else "🔴"
        embed.add_field(
            name="Market Status",
            value=f"{status_emoji} {'OPEN' if status['market_open'] else 'CLOSED'}",
            inline=True
        )
        
        # Market sentiment
        sentiment_emoji = "📈" if status["sentiment"] > 0.1 else "📉" if status["sentiment"] < -0.1 else "➡️"
        embed.add_field(
            name="Sentiment",
            value=f"{sentiment_emoji} {status['trend'].title()}",
            inline=True
        )
        
        # Gold price
        embed.add_field(
            name="Gold Price",
            value=f"${status['gold_price']:,.2f}/oz",
            inline=True
        )
        
        # Market change
        change_color = discord.Color.green() if status["market_change"] > 0 else discord.Color.red()
        change_emoji = "📈" if status["market_change"] > 0 else "📉"
        embed.add_field(
            name="Market Change",
            value=f"{change_emoji} {status['market_change']:+.2f}%",
            inline=True
        )
        
        # Daily volume
        embed.add_field(
            name="Daily Volume",
            value=f"{status['daily_volume']:,} shares",
            inline=True
        )
        
        # Trading hours
        embed.add_field(
            name="Trading Hours",
            value=f"{MarketConfig.TRADING_HOURS['open']}:00 - {MarketConfig.TRADING_HOURS['close']}:00 UTC",
            inline=True
        )
        
        # News highlights
        if status["news"]:
            news_text = "\n".join([f"• {event['text']}" for event in status["news"][:2]])
            embed.add_field(
                name="📰 Market News",
                value=news_text,
                inline=False
            )
        
        embed.set_footer(text="Use ~stocks <symbol> for individual stock info")
        await ctx.send(embed=embed)
    
    @commands.command(name="stocks")
    async def stock_info(self, ctx: commands.Context, symbol: str = None):
        """Get information about specific stocks or list all available stocks."""
        if not symbol:
            # Show all available stocks
            embed = discord.Embed(
                title="📈 Available Stocks",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            for symbol, stock in self.market.stocks.items():
                change = self.market.get_price_change(symbol)
                change_emoji = "📈" if change > 0 else "📉"
                embed.add_field(
                    name=f"{stock['name']} ({symbol})",
                    value=f"${stock['price']:.2f} {change_emoji} {change:+.2f}%",
                    inline=True
                )
            
            embed.set_footer(text="Use ~stocks <symbol> for detailed information")
            await ctx.send(embed=embed)
            return
        
        symbol = symbol.upper()
        if symbol not in self.market.stocks:
            embed = discord.Embed(
                title="❌ Stock Not Found",
                description=f"Stock symbol '{symbol}' not found. Available symbols: {', '.join(self.market.stocks.keys())}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        stock = self.market.stocks[symbol]
        change = self.market.get_price_change(symbol)
        change_color = discord.Color.green() if change > 0 else discord.Color.red()
        
        embed = discord.Embed(
            title=f"📊 {stock['name']} ({symbol})",
            description=stock["description"],
            color=change_color,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Price information
        embed.add_field(name="💰 Current Price", value=f"${stock['price']:.2f}", inline=True)
        embed.add_field(name="📈 Change", value=f"{change:+.2f}%", inline=True)
        embed.add_field(name="📊 Volume", value=f"{stock['volume']:,}", inline=True)
        
        # Day range
        embed.add_field(name="📅 Day Range", value=f"${stock['day_low']:.2f} - ${stock['day_high']:.2f}", inline=True)
        
        # Company info
        embed.add_field(name="🏢 Sector", value=stock["sector"], inline=True)
        embed.add_field(name="💵 Dividend Yield", value=f"{stock['dividend_yield']:.1%}", inline=True)
        embed.add_field(name="📊 P/E Ratio", value=f"{stock['pe_ratio']:.1f}", inline=True)
        embed.add_field(name="💰 Market Cap", value=f"${stock['market_cap']:,}", inline=True)
        
        # Volatility indicator
        volatility_level = "Low" if stock["volatility"] < 0.015 else "Medium" if stock["volatility"] < 0.03 else "High"
        embed.add_field(name="⚡ Volatility", value=volatility_level, inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="gold")
    async def gold_info(self, ctx: commands.Context):
        """Get current gold market information."""
        status = self.market.get_market_status()
        
        embed = discord.Embed(
            title="🥇 Gold Market",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="💰 Current Price", value=f"${self.market.gold_price:,.2f}/oz", inline=True)
        embed.add_field(name="📈 Demand", value=f"{self.market.gold_demand:+.2f}", inline=True)
        embed.add_field(name="⚡ Volatility", value=f"{self.market.gold_volatility:.1%}", inline=True)
        
        # Price range
        embed.add_field(
            name="📊 Price Range", 
            value=f"${MarketConfig.MIN_GOLD_PRICE:,.0f} - ${MarketConfig.MAX_GOLD_PRICE:,.0f}", 
            inline=True
        )
        
        # Safe haven status
        safe_haven = "🛡️ Strong" if status["sentiment"] < -0.2 else "🛡️ Moderate" if status["sentiment"] < 0 else "📉 Weak"
        embed.add_field(name="🛡️ Safe Haven Status", value=safe_haven, inline=True)
        
        # Market correlation
        correlation = "Inverse" if status["sentiment"] < 0 else "Positive" if status["sentiment"] > 0.2 else "Neutral"
        embed.add_field(name="📈 Market Correlation", value=correlation, inline=True)
        
        embed.set_footer(text="Gold often moves inversely to stock markets during uncertainty")
        await ctx.send(embed=embed)

    # -------------------- NEW TRADING COMMANDS --------------------

    @commands.command(name="buyinvest", aliases=["ibuy"])
    async def buy_invest(self, ctx: commands.Context, asset_type: str, symbol_or_ounces: str, amount: int):
        """Buy stocks or gold. Usage: ~buyinvest <stock/gold> <SYMBOL/ounces> <amount>"""
        try:
            asset_type = asset_type.lower()
            
            if not self.market.market_open and asset_type == "stock":
                await ErrorHandler.handle_command_error(ctx, Exception("market_closed"), "buyinvest")
                return
            
            if amount <= 0:
                return await ctx.send("Amount must be greater than 0.")
                
            user_data = await db.get_user(ctx.author.id)
            total_cost = 0
            
            if asset_type == "stock":
                symbol = symbol_or_ounces.upper()
                if symbol not in self.market.stocks:
                    return await ctx.send(f"Stock symbol '{symbol}' not found.")
                
                # Check portfolio size limit
                portfolio = user_data.get("portfolio", {})
                is_valid_size, size_error = self.security_manager.validate_portfolio_size(portfolio, new_symbol=symbol)
                if not is_valid_size:
                    return await ctx.send(size_error)
                
                stock = self.market.stocks[symbol]
                total_cost = stock["price"] * amount
                
            elif asset_type == "gold":
                total_cost = self.market.gold_price * amount
                
            else:
                return await ctx.send("Invalid asset type. Use 'stock' or 'gold'.")

            # Check if user has enough in bank
            if user_data["bank"] < total_cost:
                return await ctx.send(f"Insufficient funds in bank. You need {total_cost:,.2f}£ but only have {user_data['bank']:,.2f}£.")

            # --- Process Transaction ---
            # 1. Remove money from bank
            await db.update_balance_atomic(ctx.author.id, bank_change=-total_cost)
            
            # 2. Add asset to portfolio
            user_portfolio = user_data.get("portfolio", db._get_default_user(0)["portfolio"]) # Get default structure
            
            if asset_type == "stock":
                user_portfolio["stocks"].setdefault(symbol, {"shares": 0, "avg_price": 0.0})
                
                # Calculate new average price
                old_shares = user_portfolio["stocks"][symbol]["shares"]
                old_avg_price = user_portfolio["stocks"][symbol]["avg_price"]
                new_shares = old_shares + amount
                
                user_portfolio["stocks"][symbol]["avg_price"] = ((old_shares * old_avg_price) + (amount * stock["price"])) / new_shares
                user_portfolio["stocks"][symbol]["shares"] = new_shares
                
                # Update market demand
                self.market.stocks[symbol]["volume"] += amount

            elif asset_type == "gold":
                user_portfolio["gold_ounces"] = user_portfolio.get("gold_ounces", 0.0) + amount
                
                # --- THIS IS THE FIX for GOLD DEMAND ---
                self.market.gold_demand += (amount / 1000) # Increase demand (scaled)
            
            # 3. Save portfolio back to database
            await db.update_user(ctx.author.id, {"portfolio": user_portfolio})
            
            await ctx.send(f"✅ Successfully purchased {amount:,} {'shares of' if asset_type == 'stock' else 'oz of'} {symbol_or_ounces.upper()} for {total_cost:,.2f}£.")

        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "buyinvest")

    @commands.command(name="sellinvest", aliases=["isell"])
    async def sell_invest(self, ctx: commands.Context, asset_type: str, symbol_or_ounces: str, amount: int):
        """Sell stocks or gold. Usage: ~sellinvest <stock/gold> <SYMBOL/ounces> <amount>"""
        try:
            asset_type = asset_type.lower()
            
            if not self.market.market_open and asset_type == "stock":
                await ErrorHandler.handle_command_error(ctx, Exception("market_closed"), "sellinvest")
                return
                
            if amount <= 0:
                return await ctx.send("Amount must be greater than 0.")
                
            user_data = await db.get_user(ctx.author.id)
            user_portfolio = user_data.get("portfolio", db._get_default_user(0)["portfolio"])
            total_sale = 0
            
            if asset_type == "stock":
                symbol = symbol_or_ounces.upper()
                if symbol not in self.market.stocks:
                    return await ctx.send(f"Stock symbol '{symbol}' not found.")
                
                if symbol not in user_portfolio.get("stocks", {}) or user_portfolio["stocks"][symbol]["shares"] < amount:
                    return await ctx.send(f"You don't own {amount:,} shares of {symbol}.")
                
                stock = self.market.stocks[symbol]
                total_sale = stock["price"] * amount
                
                # Update portfolio
                user_portfolio["stocks"][symbol]["shares"] -= amount
                if user_portfolio["stocks"][symbol]["shares"] == 0:
                    del user_portfolio["stocks"][symbol] # Remove if 0 shares
                
                # Update market demand
                self.market.stocks[symbol]["volume"] += amount

            elif asset_type == "gold":
                if user_portfolio.get("gold_ounces", 0.0) < amount:
                    return await ctx.send(f"You don't own {amount:,} oz of gold.")
                
                total_sale = self.market.gold_price * amount
                
                # Update portfolio
                user_portfolio["gold_ounces"] -= amount
                
                # --- THIS IS THE FIX for GOLD DEMAND ---
                self.market.gold_demand -= (amount / 1000) # Decrease demand (scaled)

            else:
                return await ctx.send("Invalid asset type. Use 'stock' or 'gold'.")

            # --- Process Transaction ---
            # 1. Add money to bank
            await db.update_balance_atomic(ctx.author.id, bank_change=total_sale)
            
            # 2. Save portfolio back to database
            await db.update_user(ctx.author.id, {"portfolio": user_portfolio})
            
            await ctx.send(f"✅ Successfully sold {amount:,} {'shares of' if asset_type == 'stock' else 'oz of'} {symbol_or_ounces.upper()} for {total_sale:,.2f}£.")

        except Exception as e:
            await ErrorHandler.handle_command_error(ctx, e, "sellinvest")
            
async def setup(bot):
    await bot.add_cog(MarketCog(bot))
