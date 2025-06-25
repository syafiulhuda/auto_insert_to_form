from core.logger import Logger

from typing import Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from bs4 import BeautifulSoup

class PageUtils:
    """Provides common page interaction utilities for complex, frame-based pages."""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait

    def find_and_switch_to_frame_containing(self, by: str, value: str) -> bool:
        """
        Recursively finds an element and upon finding it, leaves the driver's
        context inside the correct frame. Returns True if successful, False otherwise.
        """
        self.driver.switch_to.default_content()

        # First, check if the element exists in the top-level document.
        if len(self.driver.find_elements(by, value)) > 0:
            Logger.debug(f"Landmark element '{value}' found in default content.")
            return True

        # If not found, begin a recursive search through all nested frames.
        def scan_frames_for_element():
            iframes = self.driver.find_elements(By.TAG_NAME, "frame")
            if not iframes:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")

            for iframe in iframes:
                try:
                    self.driver.switch_to.frame(iframe)
                    # If found, stop recursion and return True.
                    if len(self.driver.find_elements(by, value)) > 0:
                        return True
                    # If not, search deeper in nested frames.
                    if scan_frames_for_element():
                        return True
                    # If not found in this branch, go back to the parent frame.
                    self.driver.switch_to.parent_frame()
                except Exception:
                    # If switching fails (e.g., stale frame), go back and continue.
                    self.driver.switch_to.parent_frame()
            return False

        if scan_frames_for_element():
            Logger.info(f"Successfully found and switched to frame containing element: '{value}'")
            return True
        else:
            Logger.error(f"Could not find any frame containing the landmark element: '{value}'")
            return False
    
    def find_element_recursive(self, by: str, value: str, check_func=None) -> WebElement:
        """Find the first matching element by searching recursively through all frames."""
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
            return elements[0] if elements else None
        except:
            return None
        
    def find_elements_recursive(self, by: str, value: str, check_func=None) -> list:
        """Find all matching elements by searching recursively through all frames."""
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
        Selects a radio button by its name and value, searching in all frames.
        Returns a tuple of (success, changed).
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
            Logger.error(f"Radio button with value '{desired_value}' not found for name '{radio_name}'")
            return False, False 

        try:
            # If the desired option is already selected, do nothing to avoid unnecessary clicks.
            if target_radio.is_selected():
                Logger.plain(f"Radio '{desired_value}' already selected.")
                return True, False 
            # Otherwise, use JavaScript to click the radio button for maximum reliability.
            else:
                self.driver.execute_script("arguments[0].click();", target_radio)
                Logger.plain(f"Selected radio button '{desired_value}'.")
                return True, True 
        except Exception as e:
            Logger.error(f"Error selecting radio button: {e}")
            return False, False

    def wait_for_element(self, by: str, value: str, timeout: int = 15) -> WebElement:
        """Wait for a specific element to appear, searching recursively in all frames."""
        try:
            element = self.wait.until(
                lambda d: self.find_element_recursive(by, value)
            )
            return element
        except Exception:
            Logger.warning(f"Element '{value}' not found within {timeout}s")
            return None

    def save_page_source(self, filename: str):
        """Save the prettified HTML source of the current page for debugging."""
        try:
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(soup.prettify())
            Logger.success(f"Saved HTML source to: {filename}")
        except Exception as e:
            Logger.error(f"Failed to save HTML source: {e}")
    
    def take_screenshot(self, filename: str):
        """Capture a screenshot of the visible area."""
        try:
            self.driver.save_screenshot(filename)
            Logger.debug(f"Saved screenshot to: {filename}")
        except Exception as e:
            Logger.error(f"Failed to take screenshot: {e}")