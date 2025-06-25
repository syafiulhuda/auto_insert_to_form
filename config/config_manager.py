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
    # The specific version of the batch process to run (e.g., "sbii", "jamkrindo").
    batch_jobs: List[Tuple[str, List[str]]] = field(default_factory=list)
    batch_version: Optional[str] = None
    # Holds data for dynamic form fields, mapping table names to field lists.
    extractors: Dict[str, List[str]] = field(default_factory=dict)
    tables: List[str] = field(default_factory=list)

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