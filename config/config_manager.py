import configparser
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

@dataclass
class AppConfig:
    """Stores and manages application configuration settings."""
    mode: str
    url: str
    username: str
    password: str
    screenshot_dir: str
    inspect_dir: str
    timeout: int
    headless: bool
    browser_choice: str = ""
    file_path: str = ""
    batch_jobs: List[Tuple[str, List[str]]] = field(default_factory=list)
    batch_version: Optional[str] = None
    extractors: Dict[str, List[str]] = field(default_factory=dict)
    tables: List[str] = field(default_factory=list)

    # --- PIPELINE MODE ---
    # Attributes to hold sub-configurations
    param_config: Optional['AppConfig'] = None
    mapping_config: Optional['AppConfig'] = None
    batch_config: Optional['AppConfig'] = None
    commit_enabled: bool = False

    @classmethod
    def from_config_file(cls, config_path: str, mode: str):
        """Initialize configuration from INI file."""
        config = configparser.ConfigParser()
        config.read(config_path)
        
        return cls(
            mode=mode,
            url=config.get('WEB', 'url'),
            username=config.get('WEB', 'username'),
            password=config.get('WEB', 'password', fallback=''),
            screenshot_dir=config.get('PATHS', 'screenshot_dir'),
            inspect_dir=config.get('PATHS', 'inspect_dir'),
            file_path=config.get('PATHS', 'file_path', fallback=''),
            timeout=config.getint('SETTINGS', 'timeout', fallback=15),
            headless=config.getboolean('SETTINGS', 'headless', fallback=False),
        )