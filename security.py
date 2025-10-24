import re
import logging
from typing import List, Optional

class SecurityManager:
    """Enhanced security manager for input validation and sanitization."""
    
    def __init__(self):
        self.suspicious_patterns = [
            r"\b(admin|root|system)\b.*\b(password|passwd|pwd)\b",
            r"eval\s*\(",
            r"exec\s*\(",
            r"__import__",
            r"subprocess",
            r"os\.system",
            r"curl\s+",
            r"wget\s+",
            r"bash\s+",
            r"sh\s+",
            r"cmd\s+",
            r"powershell\s+",
            r"<script.*?>",
            r"javascript:",
            r"onload\s*=",
            r"onerror\s*=",
        ]
    
    def validate_input(self, input_str: str, max_length: int = 1000) -> bool:
        """Validate user input for potential security issues."""
        if not input_str or len(input_str) > max_length:
            return False
        
        # Check for suspicious patterns
        for pattern in self.suspicious_patterns:
            if re.search(pattern, input_str, re.IGNORECASE):
                logging.warning(f"🚨 Suspicious input detected: {input_str[:100]}...")
                return False
        
        return True
    
    def sanitize_username(self, username: str) -> str:
        """Sanitize username for safe display."""
        # Remove or escape potentially dangerous characters
        sanitized = re.sub(r'[<>"\'&]', '', username)
        return sanitized[:32]  # Limit length
    
    def validate_amount(self, amount: int, max_amount: int = 10_000_000) -> bool:
        """Validate monetary amounts for security."""
        try:
            amount_int = int(amount)
            return 0 < amount_int <= max_amount
        except (ValueError, TypeError):
            return False
    
    def sanitize_reason(self, reason: str, max_length: int = 500) -> str:
        """Sanitize moderation reasons."""
        if not reason:
            return "No reason provided"
        
        # Remove dangerous content
        dangerous_patterns = ["```", "`", "@everyone", "@here", "http://", "https://", "discord.gg/"]
        sanitized = reason
        
        for pattern in dangerous_patterns:
            sanitized = sanitized.replace(pattern, "")
        
        # Limit length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length-3] + "..."
        
        return sanitized.strip()

# Global security instance
security_manager = SecurityManager()
