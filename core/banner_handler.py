import time
from core.logger import Logger
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from core.page_utils import PageUtils

class BannerFrameHandler:
    """Handles operations in the banner command frame."""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait

    def execute_command(self, command: str) -> bool:
        """
        Executes a command and switches to the new content handle (window or tab)
        using a unified approach that is stable for both Chrome and Firefox.
        """
        try:
            Logger.plain("Accessing banner frame")
            # Store the handle of the main window to differentiate from the new one.
            original_window = self.driver.current_window_handle
            
            # Switch into the banner frame where the command input is located.
            banner_frame = self.wait.until(EC.presence_of_element_located((By.XPATH, "//frame[contains(@id, 'banner')]")))
            self.driver.switch_to.frame(banner_frame)
            
            # Enter the command into the input field.
            input_field = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input#commandValue")))
            input_field.clear()
            input_field.send_keys(command)
            Logger.plain(f"Command: '{command}'")
            
            # Execute the command by clicking the 'Go' button.
            go_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='javascript:docommandLine()'] img")))
            go_button.click()
            
            # Wait until a new window or tab handle appears.
            self.wait.until(EC.number_of_windows_to_be(2))
            self.driver.switch_to.default_content()
            
            # Find the new handle by comparing it with the original one.
            new_handle = [handle for handle in self.driver.window_handles if handle != original_window][0]
            self.driver.switch_to.window(new_handle)
            Logger.plain("Switched to new window/tab content.")

            try:
                # Wait for the new page to be fully loaded and ready for interaction.
                self.wait.until(lambda d: d.current_url != "about:blank" and d.execute_script("return document.readyState") == "complete")
                Logger.debug(f"New content URL has loaded: {self.driver.current_url}")
            except Exception as e:
                Logger.error(f"New window/tab failed to navigate or load completely. Error: {e}")
                PageUtils(self.driver, self.wait).take_screenshot("screenshots/new_content_load_failed.png")
                return False

            # Final verification that the body of the new page is present.
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            return True
        except Exception as e:
            error_text = str(e).lower()
            # Handle a specific, expected alert that might appear during testing.
            if "unexpectedalertopenerror" in str(type(e)).lower() and "changes not saved" in error_text:
                Logger.warning("Ignored expected 'Changes Not Saved' alert during test mode.")
                self.driver.switch_to.default_content()
                return True 
            else:
                Logger.error(f"Command execution failed: {e}")
                self.driver.switch_to.default_content()
                return False