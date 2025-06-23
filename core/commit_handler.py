from core.logger import Logger
from core.page_utils import PageUtils

import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

class CommitHandler:
    """Handles form commit operations"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    def execute_commit(self) -> bool:
        """Execute form commit action"""
        try:
            # Locate commit button using multiple identifiers
            commit_button = self.wait.until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//img[@alt='Commit the deal' or @title='Commit the deal'] | "
                    "//a[contains(@href,'doToolbar')]/img[contains(@src,'txncommit.gif')]"
                )))
            
            # Scroll into view and click
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                commit_button)
            time.sleep(0.5)
            commit_button.click()
            Logger.info("Commit executed")

            # Verify successful commit
            confirmation_xpath = "//*[contains(text(), 'Txn Complete') or contains(text(), 'Transaction Complete') or contains(text(), 'LIVE RECORD NOT CHANGED')]"
            confirmation_element = self.wait.until(EC.presence_of_element_located((By.XPATH, confirmation_xpath)))
            Logger.success(f"Transaction confirmed: '{confirmation_element.text}'")
            return True
        except Exception as e:
            Logger.error(f"Commit failed: {e}")
            PageUtils(self.driver, self.wait).take_screenshot("screenshots/commit_failed.png")
            return False