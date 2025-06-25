from core.logger import Logger

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

class AuthenticationService:
    """Handles login operations."""
    
    def __init__(self, driver, wait, config):
        self.driver = driver
        self.wait = wait
        self.config = config
    
    def login(self) -> bool:
        """Perform login with configured credentials."""
        try:
            # Locate username field by its specific ID and wait for it to be present.
            username_field = self.wait.until(
                EC.presence_of_element_located((By.ID, "signOnName")))
            username_field.send_keys(self.config.username)
            
            # Locate password field and enter the password.
            password_field = self.driver.find_element(By.ID, "password")
            password_field.send_keys(self.config.password)
            
            # Find and click the main sign-in button.
            login_button = self.driver.find_element(By.ID, "sign-in")
            login_button.click()
            
            Logger.success("Login successful")
            return True
        except Exception as e:
            Logger.error(f"Login failed: {e}")
            return False