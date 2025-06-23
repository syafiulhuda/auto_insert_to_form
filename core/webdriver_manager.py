from core.logger import Logger
from config.config_manager import AppConfig

import os

from selenium import webdriver
from screeninfo import get_monitors
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService

class WebDriverManager:
    """Manages browser initialization and lifecycle"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.driver = None
        self.wait = None

    def initialize(self):
        """Initialize WebDriver with configuration settings"""
        if self.driver is not None:
            return
            
        # Common options for all browsers
        common_options = {
            "window_size": "--window-size=1920,1080",
            "headless": "--headless=new" if self.config.headless else None,
            "log_level": "--log-level=3",
            "exclude_switches": "excludeSwitches",
        }

        if self.config.browser_choice.lower() == "firefox":
            options = webdriver.FirefoxOptions()
            
            # Apply common options
            if common_options["window_size"]:
                options.add_argument(common_options["window_size"])
            if common_options["headless"] and self.config.headless:
                options.add_argument(common_options["headless"])
            if common_options["log_level"]:
                options.add_argument(common_options["log_level"])

            # Firefox-specific preferences
            options.set_preference("devtools.console.stdout.content", True)
            options.set_preference("security.tls.version.enable-deprecated", True)
            
            # Chrome-like behavior emulation
            options.set_preference("browser.download.folderList", 2)
            options.set_preference("browser.download.manager.showWhenStarting", False)
            options.set_preference("browser.download.dir", os.getcwd())
            options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/octet-stream")
            
            service = FirefoxService(log_path=os.devnull)
            self.driver = webdriver.Firefox(service=service, options=options)
        else:  # Chrome
            options = webdriver.ChromeOptions()
            if common_options["window_size"]:
                options.add_argument(common_options["window_size"])
            if common_options["headless"] and self.config.headless:
                options.add_argument(common_options["headless"])
            if common_options["log_level"]:
                options.add_argument(common_options["log_level"])
            options.add_experimental_option(common_options["exclude_switches"], ['enable-logging'])
            service = ChromeService(log_path=os.devnull)
            self.driver = webdriver.Chrome(service=service, options=options)
            Logger.info("Chrome initialized")

        self.wait = WebDriverWait(self.driver, self.config.timeout)

        # Window management
        if not self.config.headless:
            monitor = get_monitors()[0]
            browser_width = monitor.width // 2
            browser_height = monitor.height // 2
            
            self.driver.set_window_size(browser_width, browser_height)
            self.driver.set_window_position(0, 0)
            Logger.debug(f"Browser resized to {browser_width}x{browser_height}")

        # Navigate to target URL
        self.driver.get(self.config.url)
        Logger.info(f"Loaded URL: {self.config.url}")
            
    def get_driver_and_wait(self):
        """Get driver and wait objects"""
        return self.driver, self.wait
    
    def quit(self):
        """Cleanup WebDriver resources"""
        if self.driver:
            self.driver.quit()
            Logger.info("Browser closed")