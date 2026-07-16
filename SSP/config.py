"""
Configuration Module for SSP (Self-Service Printer) Application

Loads application configuration from a .env file and provides type-safe access
to configuration values. Application will exit if .env file is not found.

Configuration Categories:
- Page Pricing: Prices for black & white and color printing
- Printer Settings: Printer name, timeout, and retry attempts
- System Settings: Color mode, copy limits
- Analysis Settings: PDF analysis DPI, color tolerance, thresholds
"""

import os
import sys
from typing import TypeVar, Union, cast

ValueType = TypeVar("ValueType", str, int, float, bool)


class Config:
    """
    Configuration class that loads and provides access to settings from .env file.
    
    All configuration values are loaded from environment variables and are
    accessible via properties with automatic type conversion.
    """
    
    def __init__(self, env_file: str = ".env"):
        """
        Initialize configuration from .env file.
        
        Args:
            env_file: Path to .env configuration file (default: ".env")
            
        Raises:
            SystemExit: If .env file is not found
        """
        self.env_file = env_file
        self._check_env_file_exists()
        self._load_env_file()
    
    def _check_env_file_exists(self):
        """
        Verify that .env file exists.
        
        Exits application with error message if file is not found.
        """
        if not os.path.exists(self.env_file):
            print(f"❌ Configuration file '{self.env_file}' not found!")
            print("Please create a .env file with your configuration settings.")
            sys.exit(1)
    
    def _load_env_file(self):
        """
        Load environment variables from .env file.
        
        Parses key=value pairs and sets them as environment variables.
        Supports comments (lines starting with #) and quoted values.
        """
        with open(self.env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse key=value pairs
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Strip inline comments (e.g. KEY=value  # comment)
                    if '#' in value:
                        value = value.split('#')[0].strip()

                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # Shell env takes precedence over .env (allows SIM_MODE=true make run-sim)
                    os.environ.setdefault(key, value)
    
    def get(self, key: str, value_type: type[ValueType] = str) -> ValueType:
        """
        Get configuration value with type conversion.
        
        Args:
            key: Configuration key
            value_type: Type to convert the value to (str, int, float, bool)
        
        Returns:
            Configuration value converted to specified type
        
        Raises:
            KeyError: If the configuration key is not found
            ValueError: If the value cannot be converted to the specified type
        """
        if key not in os.environ:
            raise KeyError(f"Configuration key '{key}' not found in .env file")
        
        value = os.environ[key]
        
        try:
            if value_type is bool:
                return cast(ValueType, value.lower() in ('true', '1', 'yes', 'on'))
            elif value_type is int:
                return cast(ValueType, int(value))
            elif value_type is float:
                return cast(ValueType, float(value))
            else:
                return cast(ValueType, str(value))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Could not convert '{key}={value}' to {value_type.__name__}: {e}")
    
    # Page pricing configuration
    
    @property
    def black_and_white_price(self) -> float:
        """Get price per page for black and white printing."""
        return self.get('BLACK_AND_WHITE_PRICE', float)
    
    @property
    def color_price(self) -> float:
        """Get price per page for color printing."""
        return self.get('COLOR_PRICE', float)
    
    # Printer configuration
    
    @property
    def printer_name(self) -> str:
        """Get CUPS printer name."""
        return self.get('PRINTER_NAME', str)
    
    @property
    def printer_timeout(self) -> int:
        """Get printer command timeout in seconds."""
        return self.get('PRINTER_TIMEOUT', int)
    
    @property
    def printer_retry_attempts(self) -> int:
        """Get number of printer retry attempts."""
        return self.get('PRINTER_RETRY_ATTEMPTS', int)
    
    # System settings
    
    @property
    def default_color_mode(self) -> str:
        """Get default color mode ('Color' or 'Black and White')."""
        return self.get('DEFAULT_COLOR_MODE', str)
    
    @property
    def max_copies(self) -> int:
        """Get maximum number of copies allowed per print job."""
        return self.get('MAX_COPIES', int)
    
    @property
    def min_copies(self) -> int:
        """Get minimum number of copies required per print job."""
        return self.get('MIN_COPIES', int)
    
    # Analysis settings
    
    @property
    def pdf_analysis_dpi(self) -> int:
        """Get DPI used for PDF analysis (higher = more accurate but slower)."""
        return self.get('PDF_ANALYSIS_DPI', int)
    
    @property
    def color_tolerance(self) -> int:
        """Get color tolerance for distinguishing color vs grayscale (0-255)."""
        return self.get('COLOR_TOLERANCE', int)
    
    @property
    def pixel_count_threshold(self) -> int:
        """Get minimum pixel count threshold for color detection."""
        return self.get('PIXEL_COUNT_THRESHOLD', int)

    # SMS / hardware settings

    @property
    def phone_number(self) -> str:
        """Get admin phone number for SMS alerts."""
        return self.get('PHONE_NUMBER', str)

    @property
    def coin_pin(self) -> int:
        """Get GPIO pin number for coin acceptor pulse input."""
        return self.get('COIN_PIN', int)

    @property
    def bill_pin(self) -> int:
        """Get GPIO pin number for bill acceptor pulse input."""
        return self.get('BILL_PIN', int)

    @property
    def coin_inhibit_pin(self) -> int:
        """Get GPIO pin number for coin acceptor inhibit/enable (active high)."""
        return self.get('COIN_INHIBIT_PIN', int)

    @property
    def bill_inhibit_pin(self) -> int:
        """Get GPIO pin number for bill acceptor inhibit/enable (active low)."""
        return self.get('BILL_INHIBIT_PIN', int)

    # Display settings
    
    @property
    def force_fullscreen(self) -> bool:
        """Force fullscreen mode regardless of screen size."""
        return self.get('FORCE_FULLSCREEN', bool)
    
    @property
    def window_width(self) -> int:
        """Get preferred window width for windowed mode."""
        return self.get('WINDOW_WIDTH', int)
    
    @property
    def window_height(self) -> int:
        """Get preferred window height for windowed mode."""
        return self.get('WINDOW_HEIGHT', int)
    
    @property
    def fullscreen_threshold_width(self) -> int:
        """Get screen width threshold below which fullscreen is used."""
        return self.get('FULLSCREEN_THRESHOLD_WIDTH', int)
    
    @property
    def fullscreen_threshold_height(self) -> int:
        """Get screen height threshold below which fullscreen is used."""
        return self.get('FULLSCREEN_THRESHOLD_HEIGHT', int)

    @property
    def sim_mode(self) -> bool:
        """Skip GPIO, CUPS, and modem — set SIM_MODE=true for laptop development."""
        try:
            return self.get('SIM_MODE', bool)
        except KeyError:
            return False

    # Web backend (FastAPI) settings

    @property
    def docs_enabled(self) -> bool:
        """Serve /docs and /redoc — must be false in production (see project_objectives.txt)."""
        try:
            return self.get('API_DOCS_ENABLED', bool)
        except KeyError:
            return False

    # Wi-Fi upload portal (webapp/routers/upload.py)

    @property
    def wifi_upload_dir(self) -> str:
        """Directory uploaded PDFs are saved to before being handed to SessionManager."""
        try:
            return self.get('WIFI_UPLOAD_DIR', str)
        except KeyError:
            return "SSP/database/wifi_uploads"

    @property
    def max_upload_size_mb(self) -> int:
        """Reject Wi-Fi uploads larger than this (megabytes)."""
        try:
            return self.get('MAX_UPLOAD_SIZE_MB', int)
        except KeyError:
            return 25

    # Email intake (managers/adapters/email_adapter.py) — defaults below match
    # the greenmail dev server in managers/adapters/greenmail/docker-compose.yml.
    # Override all of these in .env before pointing at the real dedicated
    # Gmail account (Gmail needs EMAIL_USE_SSL=true, IMAP port 993, an app
    # password, etc.) — no code changes required for that swap.

    @property
    def email_imap_host(self) -> str:
        try:
            return self.get('EMAIL_IMAP_HOST', str)
        except KeyError:
            return "127.0.0.1"

    @property
    def email_imap_port(self) -> int:
        try:
            return self.get('EMAIL_IMAP_PORT', int)
        except KeyError:
            return 3143

    @property
    def email_smtp_host(self) -> str:
        try:
            return self.get('EMAIL_SMTP_HOST', str)
        except KeyError:
            return "127.0.0.1"

    @property
    def email_smtp_port(self) -> int:
        try:
            return self.get('EMAIL_SMTP_PORT', int)
        except KeyError:
            return 3025

    @property
    def email_use_ssl(self) -> bool:
        try:
            return self.get('EMAIL_USE_SSL', bool)
        except KeyError:
            return False

    @property
    def email_user(self) -> str:
        try:
            return self.get('EMAIL_USER', str)
        except KeyError:
            return "test@example.com"

    @property
    def email_password(self) -> str:
        try:
            return self.get('EMAIL_PASSWORD', str)
        except KeyError:
            return "test"

    @property
    def email_mailbox(self) -> str:
        try:
            return self.get('EMAIL_MAILBOX', str)
        except KeyError:
            return "INBOX"

    @property
    def email_subject_keyword(self) -> str:
        """Required in the subject line for an email to be treated as a print request."""
        try:
            return self.get('EMAIL_SUBJECT_KEYWORD', str)
        except KeyError:
            return "DEMO_TRIGGER"

    @property
    def email_poll_interval_seconds(self) -> int:
        try:
            return self.get('EMAIL_POLL_INTERVAL_SECONDS', int)
        except KeyError:
            return 10

    @property
    def email_upload_dir(self) -> str:
        try:
            return self.get('EMAIL_UPLOAD_DIR', str)
        except KeyError:
            return "SSP/database/email_uploads"

    @property
    def email_max_attachment_size_mb(self) -> int:
        try:
            return self.get('EMAIL_MAX_ATTACHMENT_SIZE_MB', int)
        except KeyError:
            return 25


# Global configuration instance
config = Config()


def get_config() -> Config:
    """
    Get the global configuration instance.
    
    Returns:
        Global Config object with loaded settings
    """
    return config
