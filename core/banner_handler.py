import time
from core.logger import Logger
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# ===================================================================
# CLASS: Banner Frame Handler (DEFINITIVE FIX FOR POP-UP TIMING)
# ===================================================================
class BannerFrameHandler:
    """Handles operations in the banner command frame"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait

    def execute_command(self, command: str) -> bool:
        """Execute command in banner frame and switch to new window"""
        try:
            Logger.plain("Accessing banner frame")
            original_window = self.driver.current_window_handle
            
            # Locate banner frame
            banner_frame = self.wait.until(EC.presence_of_element_located((By.XPATH, "//frame[contains(@id, 'banner')]")))
            self.driver.switch_to.frame(banner_frame)
            
            # Input command
            input_field = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#commandValue")))
            input_field.clear()
            input_field.send_keys(command)
            Logger.plain(f"Command: '{command}'")
            
            # Execute command
            go_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='javascript:docommandLine()'] img")))
            go_button.click()
            
            # Wait for new window to appear
            self.wait.until(EC.number_of_windows_to_be(2))
            self.driver.switch_to.default_content()
            
            # Switch to new window
            for handle in self.driver.window_handles:
                if handle != original_window:
                    self.driver.switch_to.window(handle)
                    Logger.plain("Switched to new window\n")
                    break
            
            # Wait for new window content to load
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            return True
        except Exception as e:
            error_text = str(e).lower()
            if "unexpectedalertopenerror" in str(type(e)).lower() and "changes not saved" in error_text:
                Logger.warning("Ignored expected 'Changes Not Saved' alert during test mode.")
                self.driver.switch_to.default_content()
                return True 
            else:
                Logger.error(f"Command failed: {e}")
                self.driver.switch_to.default_content()
                return False