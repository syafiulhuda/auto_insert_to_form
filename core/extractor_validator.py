from core.banner_handler import BannerFrameHandler
from core.logger import Logger

from typing import Tuple, List, Set
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC


class ExtractorValidator:
    """
    Validates if extractor fields exist on a table's STANDARD.SELECTION page.
    """
    def __init__(self, driver, wait, banner_handler: BannerFrameHandler):
        self.driver = driver
        self.wait = wait
        self.banner_handler = banner_handler

    def _get_available_fields_from_ss_page(self) -> Set[str]:
        """
        Scans the STANDARD.SELECTION page using a single, optimized JavaScript
        execution that leverages XPath for maximum accuracy and speed.
        """
        Logger.info("Scanning STANDARD.SELECTION page for available fields...")
        
        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH, 
                "//table[@id='datagrid'] | //div[@id='outer'] | //form[@id='appreq']"
            )))
        except Exception:
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # =====================================================================
        js_xpath_scanner = """
        const fields = new Set();
        
        // Helper function to run an XPath query and iterate over the results.
        const runXpath = (xpath) => {
            const iterator = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
            let node;
            const result = [];
            while (node = iterator.iterateNext()) {
                result.push(node);
            }
            return result;
        };

        // Strategy 1: Get field names from the 'javascript:help' links.
        // This finds fields that are also labels on the left side.
        const linkFields = runXpath("//a[starts-with(@id, 'fieldCaption:')]");
        linkFields.forEach(link => {
            try {
                const href = link.getAttribute('href');
                if (href && href.includes('javascript:help')) {
                    const fieldName = href.split("'")[1];
                    if (fieldName) fields.add(fieldName);
                }
            } catch (e) { /* Ignore errors on individual elements */ }
        });

        // Strategy 2: Get field names from the values of 'Sys Field Name'.
        // This is the most critical part for getting fields like '@ID', 'CURRENCY.CODE', etc.
        const valueSpans = runXpath("//tr[.//a[starts-with(text(), 'Sys Field Name')]]//span[contains(@class, 'disabled_dealbox')]");
        valueSpans.forEach(span => {
            const text = span.textContent.trim();
            if (text) fields.add(text);
        });
        
        // Return all unique fields found as an array.
        return Array.from(fields);
        """
        
        try:
            list_of_fields = self.driver.execute_script(js_xpath_scanner)
            available_fields = set(list_of_fields)
            # Logger.success(f"Found {len(available_fields)} unique fields on the page.")
            return available_fields
        except Exception as e:
            Logger.error(f"JavaScript XPath scanner failed: {e}")
            return set()
        # =====================================================================

    def validate_extractors_for_table(self, table_name: str, required_extractors: List[str]) -> Tuple[List[str], List[str]]:
        """
        Navigates to the STANDARD.SELECTION page, validates extractors, and returns the result.
        """

        # ! UPDATE THIS FOR PROD ENV
        clean_table_name = table_name
        if clean_table_name.startswith("ST.") and clean_table_name.endswith(".TEST"):
            clean_table_name = clean_table_name[3:-5] 
        elif clean_table_name.startswith("ST.") and clean_table_name.endswith(".JMK"):
            clean_table_name = clean_table_name[3:-4]
        elif clean_table_name.startswith("ST."):
            clean_table_name = clean_table_name[3:]

        command = f"SS, S {clean_table_name}"
        
        Logger.plain("-" * 50)
        Logger.info(f"Validating extractors for '{table_name}' using command: '{command}'")

        main_window = self.driver.current_window_handle
        
        if not self.banner_handler.execute_command(command):
            Logger.error("Could not execute command to open STANDARD.SELECTION page.")
            return [], required_extractors

        available_fields_on_page = self._get_available_fields_from_ss_page()
        
        valid_extractors = []
        invalid_extractors = []

        for extractor in required_extractors:
            if extractor in available_fields_on_page:
                valid_extractors.append(extractor)
            else:
                invalid_extractors.append(extractor)
        
        if self.driver.current_window_handle != main_window:
            self.driver.close()
        self.driver.switch_to.window(main_window)
        Logger.info("Validation complete. Returned to main window.")
        return valid_extractors, invalid_extractors