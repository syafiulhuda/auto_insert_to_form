from core.logger import Logger

import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

class TransactionInputHandler:
    """Handles entering a new transaction ID to navigate to the next record."""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    def input_transaction(self, table_name: str) -> bool:
        """Input transaction ID into the transaction box and submit."""
        try:
            self.wait.until(
                lambda d: d.execute_script("return document.readyState") == "complete")
            
            transaction_input = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input#transactionId.idbox")))
            
            ActionChains(self.driver).move_to_element(transaction_input).pause(0.5).perform()
            transaction_input.click()
            transaction_input.clear()
            transaction_input.send_keys(table_name)
            transaction_input.send_keys(Keys.RETURN)
            Logger.info(f"Submitted transaction: {table_name}")
            time.sleep(3) # Allow a moment for the page transition.
            return True
        except Exception as e:
            Logger.error(f"Transaction input error: {e}")
            return False