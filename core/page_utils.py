from core.logger import Logger

from typing import Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from bs4 import BeautifulSoup

class PageUtils:
    """Provides common page interaction utilities"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait

    def find_element_recursive(self, by: str, value: str, check_func=None) -> WebElement:
        """Find element recursively in all frames"""
        def scan_frames():
            elements = []
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                self.driver.switch_to.frame(iframe)
                try:
                    found = self.driver.find_elements(by, value)
                    if check_func:
                        elements.extend(el for el in found if check_func(el))
                    else:
                        elements.extend(found)
                    # Recursively search nested frames
                    elements.extend(scan_frames())
                except:
                    pass
                finally:
                    self.driver.switch_to.parent_frame()
            return elements

        self.driver.switch_to.default_content()
        try:
            elements = self.driver.find_elements(by, value)
            if check_func:
                elements = [el for el in elements if check_func(el)]
            elements.extend(scan_frames())
            return elements[0] if elements else None
        except:
            return None
    
    def find_elements_recursive(self, by: str, value: str, check_func=None) -> list:
        """Find all matching elements recursively in frames"""
        def scan_frames():
            elements = []
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                self.driver.switch_to.frame(iframe)
                try:
                    found = self.driver.find_elements(by, value)
                    if check_func:
                        elements.extend(el for el in found if check_func(el))
                    else:
                        elements.extend(found)
                    elements.extend(scan_frames())
                except:
                    pass
                finally:
                    self.driver.switch_to.parent_frame()
            return elements

        self.driver.switch_to.default_content()
        try:
            elements = self.driver.find_elements(by, value)
            if check_func:
                elements = [el for el in elements if check_func(el)]
            elements.extend(scan_frames())
            return elements
        except:
            return []
        
    def select_radio_value_recursive(self, radio_name: str, desired_value: str) -> Tuple[bool, bool]:
        """
        Selects a radio button and returns a tuple (success, changed).
        - success: True if the operation didn't fail.
        - changed: True only if a click was performed.
        """
        radio_buttons = self.find_elements_recursive(By.NAME, radio_name)
        if not radio_buttons:
            radio_buttons = self.find_elements_recursive(
                By.CSS_SELECTOR, 
                f"input[type='radio'][name='{radio_name}']"
            )

        if not radio_buttons:
            Logger.debug(f"Fallback to XPath for radio buttons with name: {radio_name}")
            radio_buttons = self.find_elements_recursive(
                By.XPATH,
                f"//input[@type='radio' and @name='{radio_name}']"
            )
        
        target_radio = None
        for radio in radio_buttons:
            if radio.get_attribute("value") == desired_value:
                target_radio = radio
                break
        if not target_radio:
            for radio in radio_buttons:
                if radio.get_attribute("value").upper() == desired_value.upper():
                    target_radio = radio
                    break
        
        if not target_radio:
            Logger.error(f"Radio '{desired_value}' not found")
            return False, False 

        try:
            if target_radio.is_selected():
                Logger.plain(f"Radio '{desired_value}' already selected")
                return True, False 
            else:
                self.driver.execute_script("arguments[0].click();", target_radio)
                Logger.plain(f"Selected '{desired_value}'")
                return True, True 
        except Exception as e:
            Logger.error(f"Error selecting radio: {e}")
            return False, False

    def wait_for_element(self, by: str, value: str, timeout: int = 15) -> WebElement:
        """Wait for element to appear with recursive search"""
        try:
            element = self.wait.until(
                lambda d: self.find_element_recursive(by, value)
            )
            return element
        except Exception:
            Logger.warning(f"Element '{value}' not found within {timeout}s")
            return None

    def save_page_source(self, filename: str):
        """Save prettified HTML source of current page"""
        try:
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(soup.prettify())
            Logger.success(f"Saved HTML: {filename}")
        except Exception as e:
            Logger.error(f"Failed to save HTML: {e}")
    
    def take_screenshot(self, filename: str):
        """Capture visible area screenshot"""
        try:
            self.driver.save_screenshot(filename)
            Logger.debug(f"Saved screenshot: {filename}")
        except Exception as e:
            Logger.error(f"Failed to take screenshot: {e}")