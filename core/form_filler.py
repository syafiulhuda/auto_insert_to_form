from core.logger import Logger
from core.page_utils import PageUtils
from core.data_manager import DataManager
from config.config_manager import AppConfig

import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from typing import Optional, Set

class BaseBatchFormFiller:
    """Base class for filling batch processing forms with common logic."""

    def __init__(self, driver, wait, utils: PageUtils, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.utils = utils
        self.config = config
        self.batch_file_path = config.file_path

    def _get_initial_data_value(self) -> str:
        """Returns the specific data value for the first FDS.COB.FLAG job (e.g., 'JEACS', 'SEACS')."""
        raise NotImplementedError

    def _get_first_extractor_verification(self) -> Optional[str]:
        """Returns the verification value for the first EB.EXTRACTOR job. Returns None if not needed."""
        raise NotImplementedError
    
    def _add_final_mandatory_rows(self, state: dict) -> bool:
        """Adds the specific sequence of mandatory rows at the end of the form."""
        raise NotImplementedError

    def _scan_form_for_all_tables(self) -> dict:
        """Scan form to detect existing table configurations"""
        Logger.info("Scanning form structure...")
        state = {
            "main_tables": {}, 
            "concat_tables": {}, 
            "concat_row_index": 0,
            "last_sub_value_index": 0, 
            "all_tables": set(),
        }

        all_job_fields = self.utils.find_elements_recursive(By.XPATH, "//input[starts-with(@name, 'fieldName:JOB.NAME:')]")
        all_data_fields = self.utils.find_elements_recursive(By.XPATH, "//input[starts-with(@name, 'fieldName:DATA:')]")
        job_name_map = {int(f.get_attribute("name").split(":")[-1]): f.get_attribute("value") for f in all_job_fields}
        
        data_map = {}
        for f in all_data_fields:
            try:
                parts = f.get_attribute("name").split(":")
                row_index = int(parts[2])
                if row_index not in data_map:
                    data_map[row_index] = []
                data_map[row_index].append(f.get_attribute("value"))
            except (IndexError, ValueError):
                continue

        for row_index, job_name in job_name_map.items():
            if job_name == "FDS.CBR.CONCAT.FILE.MT":
                state["concat_row_index"] = row_index
                if row_index in data_map:
                    state["last_sub_value_index"] = len(data_map[row_index])
                    for val in [v for v in data_map[row_index] if v]:
                        state["concat_tables"][val] = row_index
                        state["all_tables"].add(val)
            elif job_name: 
                if row_index in data_map and data_map[row_index]:
                    val = data_map[row_index][0]
                    if val:
                        state["main_tables"][val] = row_index
                        state["all_tables"].add(val)

        Logger.info(f"Found {len(state['main_tables'])} main table, {len(state['concat_tables'])} concat tables")
        return state

    def _click_expand_on_row(self, row_index: int) -> bool:
        """Expand multi-value row using JavaScript click"""
        try:
            xpath = f"//input[@name='fieldName:JOB.NAME:{row_index}']/ancestor::tr[1]//img[contains(@title, 'Expand Multi Value')]"
            expand_button = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            self.driver.execute_script("arguments[0].click();", expand_button)
            
            new_row_index = row_index + 1
            self.wait.until(EC.presence_of_element_located((By.NAME, f"fieldName:JOB.NAME:{new_row_index}")))
            return True
        except Exception as e:
            Logger.error(f"Expand click failed: {e}")
            return False

    def _click_sub_value_expand_button(self, row_index: int, last_sub_value_index: int) -> bool:
        """Expand sub-values in concat rows"""
        try:
            possible_xpaths = [
                f"//input[@name='fieldName:DATA:{row_index}:{last_sub_value_index}']/ancestor::tr[1]//img[@title='Expand Sub Value']",
                f"//input[@name='fieldName:DATA:{row_index}:{last_sub_value_index}']/parent::td/following-sibling::td//img[@title='Expand Sub Value']",
                f"//input[@name='fieldName:DATA:{row_index + 1}:{last_sub_value_index}']/ancestor::tr[1]//img[@title='Expand Sub Value']",
                f"//input[@name='fieldName:DATA:{row_index + 1}:{last_sub_value_index}']/parent::td/following-sibling::td//img[@title='Expand Sub Value']",
            ]

            expand_button = None
            xpath_found = None
            for xpath in possible_xpaths:
                expand_button = self.utils.find_element_recursive(By.XPATH, xpath)
                if expand_button:
                    xpath_found = xpath
                    break

            if not expand_button:
                Logger.error("Expand Sub Value button not found")
                self.utils.save_page_source(f"{self.config.inspect_dir}/expand_failed.html")
                return False

            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", expand_button)
            
            expand_link_xpath = f"({xpath_found})/ancestor::a[1]"
            expand_link = self.utils.find_element_recursive(By.XPATH, expand_link_xpath)
            
            if expand_link:
                javascript_code = expand_link.get_attribute('href')
                if javascript_code and javascript_code.startswith("javascript:"):
                    js_to_execute = javascript_code.split("javascript:", 1)[1]
                    self.driver.execute_script(js_to_execute)
                else:
                    expand_button.click()
            else:
                expand_button.click()

            time.sleep(1.5)
            return True
        except Exception as e:
            Logger.error(f"Expand sub-value failed: {e}")
            return False

    def _fill_field_by_name(self, field_name: str, value: str) -> bool:
        """Fill form field by name attribute"""
        try:
            field = self.utils.wait_for_element(By.NAME, field_name, timeout=10)
            if not field:
                Logger.error(f"Field not found: {field_name}")
                return False
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", field)
            field.clear()
            field.send_keys(value)
            return True
        except Exception as e:
            Logger.error(f"Field fill failed: {field_name} - {e}")
            return False
            
    def _perform_initial_setup(self, state: dict) -> bool:
        """Performs the initial setup if the form is empty."""
        is_form_truly_empty = not state["main_tables"] and not state["concat_tables"]
        if not is_form_truly_empty:
            return False

        Logger.info("Form is empty. Performing initial setup...")
        initial_data_value = self._get_initial_data_value()
        
        if not self.utils.select_radio_value_recursive("radio:tab1:BATCH.ENVIRONMENT", "F"): return False
        if not self._fill_field_by_name("fieldName:JOB.NAME:1", "FDS.COB.FLAG"): return False
        if not self._fill_field_by_name("fieldName:FREQUENCY:1", "D"): return False
        if not self._fill_field_by_name("fieldName:DATA:1:1", initial_data_value): return False
        
        state['main_tables'][initial_data_value] = 1
        state['all_tables'].add(initial_data_value)
        Logger.success(f"Initial setup complete with data: {initial_data_value}")
        return True

    def execute_filling_process(self) -> bool:
        """Main batch form filling workflow"""
        try:
            Logger.info(f"Starting form filling process for version: {self.config.batch_version.upper()}")
            changes_made = False
            table_names_from_file = DataManager.load_batch_tables(self.batch_file_path)

            state = self._scan_form_for_all_tables()
            changes_made = self._perform_initial_setup(state) or changes_made
            
            if changes_made:
                state = self._scan_form_for_all_tables()

            Logger.info("Checking for missing EB.EXTRACTOR rows...")
            missing_tables = [t for t in table_names_from_file if t not in state["main_tables"].keys()]

            if missing_tables:
                changes_made = True
                Logger.info(f"Adding {len(missing_tables)} missing EB.EXTRACTOR job(s)...")
                
                all_main_indices = list(state["main_tables"].values())
                
                # Mengubah 'idx' menjadi 'job' untuk menyimpan nomor baris (integer), bukan nama tabel (string).
                extractor_indices = [job for idx, job in state["main_tables"].items() 
                                     if self.driver.find_element(By.NAME, f"fieldName:JOB.NAME:{job}").get_attribute("value") == "EB.EXTRACTOR"]
                
                last_row_index = max(extractor_indices) if extractor_indices else (max(all_main_indices) if all_main_indices else 0)
                Logger.info(f"Adding new jobs after row: {last_row_index}")
                
                for i, table_to_add in enumerate(missing_tables):
                    Logger.info(f"Adding job for: {table_to_add}")
                    if not self._click_expand_on_row(last_row_index): return False
                    new_row_index = last_row_index + 1
                    if not self.utils.wait_for_element(By.NAME, f"fieldName:JOB.NAME:{new_row_index}", 10): return False
                    self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "EB.EXTRACTOR")
                    
                    verification_value = None
                    if i == 0 and not extractor_indices: # First extractor to be added on a form without any existing extractors
                        verification_value = self._get_first_extractor_verification()
                    else: # Subsequent extractors
                        verification_value = "EB.EXTRACTOR"
                    
                    if verification_value:
                        self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", verification_value)

                    self.driver.execute_script(f"document.getElementsByName('fieldName:FREQUENCY:{new_row_index}')[0].value = 'D';")
                    self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", table_to_add)
                    
                    last_row_index = new_row_index
                    # Tidak perlu menambahkan ke extractor_indices lagi di dalam loop

            Logger.info("Processing CONCAT row...")
            final_state = self._scan_form_for_all_tables()
            concat_row_index = final_state["concat_row_index"]

            if concat_row_index == 0:
                if not final_state["main_tables"]:
                    Logger.error("Cannot create CONCAT row without main jobs")
                    return False
                changes_made = True
                Logger.info("Creating new CONCAT row")
                # Menggunakan final_state untuk mendapatkan baris terakhir yang akurat
                last_main_row = max(final_state["main_tables"].values())
                if not self._click_expand_on_row(last_main_row): return False
                concat_row_index = last_main_row + 1
                if not self.utils.wait_for_element(By.NAME, f"fieldName:JOB.NAME:{concat_row_index}", 10): return False
                self._fill_field_by_name(f"fieldName:JOB.NAME:{concat_row_index}", "FDS.CBR.CONCAT.FILE.MT")
                self._fill_field_by_name(f"fieldName:VERIFICATION:{concat_row_index}:1", "EB.EXTRACTOR")
                self.driver.execute_script(f"document.getElementsByName('fieldName:FREQUENCY:{concat_row_index}')[0].value = 'D';")
                final_state = self._scan_form_for_all_tables()

            missing_in_concat_list = [t for t in table_names_from_file if t not in final_state["concat_tables"].keys()]
            if missing_in_concat_list:
                changes_made = True
                Logger.info(f"Adding {len(missing_in_concat_list)} missing CONCAT entries...")
                first_data_field_name = f"fieldName:DATA:{final_state['concat_row_index']}:1"
                first_data_field = self.utils.find_element_recursive(By.NAME, first_data_field_name)
                if first_data_field and not first_data_field.get_attribute("value"):
                    table_to_fill_first = missing_in_concat_list.pop(0)
                    Logger.info(f"Filling first data field with: {table_to_fill_first}")
                    self._fill_field_by_name(first_data_field_name, table_to_fill_first)
                    final_state = self._scan_form_for_all_tables()

                if missing_in_concat_list:
                    Logger.info(f"Adding {len(missing_in_concat_list)} remaining CONCAT entries...")
                    current_sub_index = final_state["last_sub_value_index"]
                    for table_name in missing_in_concat_list:
                        if not self._click_sub_value_expand_button(final_state["concat_row_index"], current_sub_index): return False
                        next_index = current_sub_index + 1
                        new_field = self.utils.wait_for_element(By.NAME, f"fieldName:DATA:{final_state['concat_row_index']}:{next_index}", 5)
                        if not new_field: new_field = self.utils.wait_for_element(By.NAME, f"fieldName:DATA:{final_state['concat_row_index'] + 1}:{next_index}", 5)
                        if not new_field: return False
                        self._fill_field_by_name(new_field.get_attribute("name"), table_name)
                        current_sub_index = next_index
            
            changes_made = self._add_final_mandatory_rows(self._scan_form_for_all_tables()) or changes_made
            
            if not changes_made:
                Logger.plain("All batch data already exist")
            Logger.success("Form filling completed")
            return True

        except Exception as e:
            Logger.error(f"Form processing error: {e}")
            self.utils.take_screenshot(f"{self.config.screenshot_dir}/form_error.png")
            return False

    # def execute_filling_process(self) -> bool:
    #     """Main batch form filling workflow"""
    #     try:
    #         Logger.info(f"Starting form filling process for version: {self.config.batch_version.upper()}")
    #         changes_made = False
    #         table_names_from_file = DataManager.load_batch_tables(self.batch_file_path)

    #         state = self._scan_form_for_all_tables()
    #         changes_made = self._perform_initial_setup(state) or changes_made
            
    #         # Re-scan state if initial setup was performed
    #         if changes_made:
    #             state = self._scan_form_for_all_tables()

    #         Logger.info("Checking for missing EB.EXTRACTOR rows...")
    #         missing_tables = [t for t in table_names_from_file if t not in state["main_tables"].keys()]

    #         if missing_tables:
    #             changes_made = True
    #             Logger.info(f"Adding {len(missing_tables)} missing EB.EXTRACTOR job(s)...")
                
    #             all_main_indices = list(state["main_tables"].values())
    #             extractor_indices = [idx for idx, job in state["main_tables"].items() 
    #                                  if self.driver.find_element(By.NAME, f"fieldName:JOB.NAME:{job}").get_attribute("value") == "EB.EXTRACTOR"]
    #             last_row_index = max(extractor_indices) if extractor_indices else (max(all_main_indices) if all_main_indices else 0)
    #             Logger.info(f"Adding new jobs after row: {last_row_index}")
                
    #             for i, table_to_add in enumerate(missing_tables):
    #                 Logger.info(f"Adding job for: {table_to_add}")
    #                 if not self._click_expand_on_row(last_row_index): return False
    #                 new_row_index = last_row_index + 1
    #                 if not self.utils.wait_for_element(By.NAME, f"fieldName:JOB.NAME:{new_row_index}", 10): return False
    #                 self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "EB.EXTRACTOR")
                    
    #                 verification_value = None
    #                 if i == 0: # First extractor to be added
    #                     verification_value = self._get_first_extractor_verification()
    #                 else: # Subsequent extractors
    #                     verification_value = "EB.EXTRACTOR"
                    
    #                 if verification_value:
    #                     self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", verification_value)

    #                 self.driver.execute_script(f"document.getElementsByName('fieldName:FREQUENCY:{new_row_index}')[0].value = 'D';")
    #                 self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", table_to_add)
                    
    #                 last_row_index = new_row_index
    #                 extractor_indices.append(new_row_index)

    #         Logger.info("Processing CONCAT row...")
    #         final_state = self._scan_form_for_all_tables()
    #         concat_row_index = final_state["concat_row_index"]

    #         if concat_row_index == 0:
    #             if not final_state["main_tables"]:
    #                 Logger.error("Cannot create CONCAT row without main jobs")
    #                 return False
    #             changes_made = True
    #             Logger.info("Creating new CONCAT row")
    #             last_main_row = max(final_state["main_tables"].values())
    #             if not self._click_expand_on_row(last_main_row): return False
    #             concat_row_index = last_main_row + 1
    #             if not self.utils.wait_for_element(By.NAME, f"fieldName:JOB.NAME:{concat_row_index}", 10): return False
    #             self._fill_field_by_name(f"fieldName:JOB.NAME:{concat_row_index}", "FDS.CBR.CONCAT.FILE.MT")
    #             self._fill_field_by_name(f"fieldName:VERIFICATION:{concat_row_index}:1", "EB.EXTRACTOR")
    #             self.driver.execute_script(f"document.getElementsByName('fieldName:FREQUENCY:{concat_row_index}')[0].value = 'D';")
    #             final_state = self._scan_form_for_all_tables()

    #         missing_in_concat_list = [t for t in table_names_from_file if t not in final_state["concat_tables"].keys()]
    #         if missing_in_concat_list:
    #             changes_made = True
    #             Logger.info(f"Adding {len(missing_in_concat_list)} missing CONCAT entries...")
    #             first_data_field_name = f"fieldName:DATA:{final_state['concat_row_index']}:1"
    #             first_data_field = self.utils.find_element_recursive(By.NAME, first_data_field_name)
    #             if first_data_field and not first_data_field.get_attribute("value"):
    #                 table_to_fill_first = missing_in_concat_list.pop(0)
    #                 Logger.info(f"Filling first data field with: {table_to_fill_first}")
    #                 self._fill_field_by_name(first_data_field_name, table_to_fill_first)
    #                 final_state = self._scan_form_for_all_tables()

    #             if missing_in_concat_list:
    #                 Logger.info(f"Adding {len(missing_in_concat_list)} remaining CONCAT entries...")
    #                 current_sub_index = final_state["last_sub_value_index"]
    #                 for table_name in missing_in_concat_list:
    #                     if not self._click_sub_value_expand_button(final_state["concat_row_index"], current_sub_index): return False
    #                     next_index = current_sub_index + 1
    #                     new_field = self.utils.wait_for_element(By.NAME, f"fieldName:DATA:{final_state['concat_row_index']}:{next_index}", 5)
    #                     if not new_field: new_field = self.utils.wait_for_element(By.NAME, f"fieldName:DATA:{final_state['concat_row_index'] + 1}:{next_index}", 5)
    #                     if not new_field: return False
    #                     self._fill_field_by_name(new_field.get_attribute("name"), table_name)
    #                     current_sub_index = next_index
            
    #         # Add version-specific mandatory final rows
    #         changes_made = self._add_final_mandatory_rows(self._scan_form_for_all_tables()) or changes_made
            
    #         if not changes_made:
    #             Logger.plain("All batch data already exist")
    #         Logger.success("Form filling completed")
    #         return True

    #     except Exception as e:
    #         Logger.error(f"Form processing error: {e}")
    #         self.utils.take_screenshot(f"{self.config.screenshot_dir}/form_error.png")
    #         return False

# ===================================================================
# CLASS: BATCH Form Handler - SBII Version
# ===================================================================
class BatchFormFiller_SBII(BaseBatchFormFiller):
    """Implements the batch form filling logic for the SBII version."""
    
    def _get_initial_data_value(self) -> str:
        return "JEACS"

    def _get_first_extractor_verification(self) -> Optional[str]:
        return "FDS.COB.FLAG"
    
    def _add_final_mandatory_rows(self, state: dict) -> bool:
        Logger.info("Adding final mandatory rows for SBII version...")
        changes_made = False
        
        last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})

        # --- [LOGIKA PENGECEKAN DIPERBAIKI] ---
        # --- Row 1: FDS.COB.FLAG after CONCAT ---
        job_flag_fields = self.utils.find_elements_recursive(By.XPATH, "//input[@value='FDS.COB.FLAG']")
        
        job1_found = False
        for job_field in job_flag_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                if (verification_field and verification_field.get_attribute("value") == "FDS.CBR.CONCAT.FILE.MT"):
                    job1_found = True
                    Logger.info("Found existing row: FDS.COB.FLAG verified by CONCAT")
                    break
            except (ValueError, IndexError):
                continue

        if not job1_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "JEACE")
            Logger.success("Added FDS.COB.FLAG verified by CONCAT")
            last_row_index = new_row_index
            changes_made = True

        # --- [LOGIKA PENGECEKAN DIPERBAIKI] ---
        # --- Row 2: CREATE.FILE.DONE.2 ---
        job2_field = self.utils.find_element_recursive(By.XPATH, "//input[@value='CREATE.FILE.DONE.2']")
        job2_found = job2_field is not None
        if job2_found:
            Logger.info("Found existing row: CREATE.FILE.DONE.2")

        if not job2_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "CREATE.FILE.DONE.2")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            Logger.success("Added CREATE.FILE.DONE.2")
            last_row_index = new_row_index
            changes_made = True

        # --- [LOGIKA PENGECEKAN DIPERBAIKI] ---
        # --- Row 3: FDS.COB.FLAG after CREATE.FILE.DONE.2 ---
        job3_found = False
        # Gunakan lagi hasil pencarian job_flag_fields dari atas
        for job_field in job_flag_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                if (verification_field and verification_field.get_attribute("value") == "CREATE.FILE.DONE.2"):
                    job3_found = True
                    Logger.info("Found existing row: FDS.COB.FLAG verified by CREATE.FILE.DONE.2")
                    break
            except (ValueError, IndexError):
                continue
        
        if not job3_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "CREATE.FILE.DONE.2")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            Logger.success("Added FDS.COB.FLAG verified by CREATE.FILE.DONE.2")
            changes_made = True
        return changes_made

    # def _add_final_mandatory_rows(self, state: dict) -> bool:
    #     Logger.info("Adding final mandatory rows for SBII version...")
    #     changes_made = False
        
    #     # Determine the last row index to expand from
    #     # last_row_index = max(state["main_tables"].values() | {state["concat_row_index"]})
    #     last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})

    #     # --- Row 1: FDS.COB.FLAG after CONCAT ---
    #     job1_exists = any(v == "FDS.COB.FLAG" and self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{k}:1").get_attribute("value") == "FDS.CBR.CONCAT.FILE.MT"
    #                       for k, v in state["main_tables"].items())
    #     if not job1_exists:
    #         if not self._click_expand_on_row(last_row_index): return False
    #         new_row_index = last_row_index + 1
    #         self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
    #         self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
    #         self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
    #         self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "JEACE")
    #         Logger.success("Added FDS.COB.FLAG verified by CONCAT")
    #         last_row_index = new_row_index
    #         changes_made = True

    #     # --- Row 2: CREATE.FILE.DONE.2 ---
    #     job2_exists = any(v == "CREATE.FILE.DONE.2" for v in state["main_tables"].values())
    #     if not job2_exists:
    #         if not self._click_expand_on_row(last_row_index): return False
    #         new_row_index = last_row_index + 1
    #         self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "CREATE.FILE.DONE.2")
    #         self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
    #         self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
    #         Logger.success("Added CREATE.FILE.DONE.2")
    #         last_row_index = new_row_index
    #         changes_made = True

    #     # --- Row 3: FDS.COB.FLAG after CREATE.FILE.DONE.2 ---
    #     job3_exists = any(v == "FDS.COB.FLAG" and self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{k}:1").get_attribute("value") == "CREATE.FILE.DONE.2"
    #                       for k, v in state["main_tables"].items())
    #     if not job3_exists:
    #         if not self._click_expand_on_row(last_row_index): return False
    #         new_row_index = last_row_index + 1
    #         self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
    #         self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "CREATE.FILE.DONE.2")
    #         self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
    #         Logger.success("Added FDS.COB.FLAG verified by CREATE.FILE.DONE.2")
    #         changes_made = True
    #     return changes_made

# ===================================================================
# CLASS: BATCH Form Handler - KALSEL Version
# ===================================================================
class BatchFormFiller_KALSEL(BaseBatchFormFiller):
    """Implements the batch form filling logic for the KALSEL version."""

    def _get_initial_data_value(self) -> str:
        return "SEACS"

    def _get_first_extractor_verification(self) -> Optional[str]:
        return None # KALSEL does not have verification on the first EB.EXTRACTOR

    def _add_final_mandatory_rows(self, state: dict) -> bool:
        Logger.info("Adding final mandatory rows for KALSEL version...")
        changes_made = False

        last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})

        # --- [LOGIKA PENGECEKAN DIPERBAIKI] ---
        # --- Row 1: CREATE.FILE.DONE ---
        job1_field = self.utils.find_element_recursive(By.XPATH, "//input[@value='CREATE.FILE.DONE']")
        job1_found = job1_field is not None
        if job1_found:
            Logger.info("Found existing row: CREATE.FILE.DONE")

        if not job1_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "CREATE.FILE.DONE")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            Logger.success("Added CREATE.FILE.DONE")
            last_row_index = new_row_index
            changes_made = True

        # --- [LOGIKA PENGECEKAN DIPERBAIKI] ---
        # --- Row 2: FDS.COB.FLAG after CREATE.FILE.DONE ---
        job_flag_fields = self.utils.find_elements_recursive(By.XPATH, "//input[@value='FDS.COB.FLAG']")

        job2_found = False
        for job_field in job_flag_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                if (verification_field and verification_field.get_attribute("value") == "CREATE.FILE.DONE"):
                    job2_found = True
                    Logger.info("Found existing row: FDS.COB.FLAG verified by CREATE.FILE.DONE")
                    break
            except (ValueError, IndexError):
                continue
        
        if not job2_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "CREATE.FILE.DONE")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "SEACE")
            Logger.success("Added FDS.COB.FLAG verified by CREATE.FILE.DONE")
            changes_made = True
            
        return changes_made

    # def _add_final_mandatory_rows(self, state: dict) -> bool:
    #     Logger.info("Adding final mandatory rows for KALSEL version...")
    #     changes_made = False

    #     # last_row_index = max(state["main_tables"].values() | {state["concat_row_index"]})
    #     last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})

    #     # --- Row 1: CREATE.FILE.DONE ---
    #     job1_exists = any(v == "CREATE.FILE.DONE" for v in state["main_tables"].values())
    #     if not job1_exists:
    #         if not self._click_expand_on_row(last_row_index): return False
    #         new_row_index = last_row_index + 1
    #         self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "CREATE.FILE.DONE")
    #         self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
    #         self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
    #         Logger.success("Added CREATE.FILE.DONE")
    #         last_row_index = new_row_index
    #         changes_made = True

    #     # --- Row 2: FDS.COB.FLAG after CREATE.FILE.DONE ---
    #     job2_exists = any(v == "FDS.COB.FLAG" and self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{k}:1").get_attribute("value") == "CREATE.FILE.DONE"
    #                       for k, v in state["main_tables"].items())
    #     if not job2_exists:
    #         if not self._click_expand_on_row(last_row_index): return False
    #         new_row_index = last_row_index + 1
    #         self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
    #         self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "CREATE.FILE.DONE")
    #         self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
    #         self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "SEACE")
    #         Logger.success("Added FDS.COB.FLAG verified by CREATE.FILE.DONE")
    #         changes_made = True
    #     return changes_made

# ===================================================================
# CLASS: BATCH Form Handler - BJI Version
# ===================================================================
class BatchFormFiller_BJI(BaseBatchFormFiller):
    """Implements the batch form filling logic for the BJI version."""

    def _get_initial_data_value(self) -> str:
        return "JEACS"

    def _get_first_extractor_verification(self) -> Optional[str]:
        return "FDS.COB.FLAG"
    
    def _add_final_mandatory_rows(self, state: dict) -> bool:
        Logger.info("Adding final mandatory rows for BJI version...")
        changes_made = False

        last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})

        # --- [LOGIKA PENGECEKAN DIPERBAIKI] ---
        # --- Row 1: FDS.COB.FLAG with JEACE ---
        
        # Cari semua field yang memiliki JOB.NAME = FDS.COB.FLAG
        job_flag_fields = self.utils.find_elements_recursive(By.XPATH, "//input[@value='FDS.COB.FLAG']")
        
        # Cek kondisi untuk baris pertama (dengan DATA = JEACE)
        job1_found = False
        for job_field in job_flag_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])

                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                data_field = self.utils.find_element_recursive(By.NAME, f"fieldName:DATA:{row_index}:1")

                if (verification_field and verification_field.get_attribute("value") == "FDS.CBR.CONCAT.FILE.MT" and
                    data_field and data_field.get_attribute("value") == "JEACE"):
                    job1_found = True
                    Logger.info("Found existing row: FDS.COB.FLAG with DATA=JEACE")
                    break
            except (ValueError, IndexError):
                continue

        if not job1_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "JEACE")
            Logger.success("Added FDS.COB.FLAG verified by CONCAT with DATA=JEACE")
            last_row_index = new_row_index
            changes_made = True
        
        # --- [LOGIKA PENGECEKAN DIPERBAIKI] ---
        # --- Row 2: FDS.COB.FLAG without DATA ---

        # Cek kondisi untuk baris kedua (dengan DATA = kosong)
        job2_found = False
        for job_field in job_flag_fields: # Gunakan hasil pencarian yang sama
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])

                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                data_field = self.utils.find_element_recursive(By.NAME, f"fieldName:DATA:{row_index}:1")
                
                # Kondisi data_field.get_attribute("value") == "" akan mencari field DATA yang kosong
                if (verification_field and verification_field.get_attribute("value") == "FDS.CBR.CONCAT.FILE.MT" and
                    data_field and data_field.get_attribute("value") == ""):
                    job2_found = True
                    Logger.info("Found existing row: FDS.COB.FLAG with empty DATA")
                    break
            except (ValueError, IndexError):
                continue

        if not job2_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            # Field DATA tidak diisi untuk baris ini
            Logger.success("Added FDS.COB.FLAG verified by CONCAT without DATA")
            changes_made = True
            
        return changes_made

    # def _add_final_mandatory_rows(self, state: dict) -> bool:
    #     Logger.info("Adding final mandatory rows for BJI version...")
    #     changes_made = False

    #     # last_row_index = max(state["main_tables"].values() | {state["concat_row_index"]})
    #     last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})

    #     # --- Row 1: FDS.COB.FLAG with JEACE ---
    #     job1_exists = any(v == "FDS.COB.FLAG" and self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{k}:1").get_attribute("value") == "FDS.CBR.CONCAT.FILE.MT" 
    #                                           and self.utils.find_element_recursive(By.NAME, f"fieldName:DATA:{k}:1").get_attribute("value") == "JEACE"
    #                       for k, v in state["main_tables"].items())
    #     if not job1_exists:
    #         if not self._click_expand_on_row(last_row_index): return False
    #         new_row_index = last_row_index + 1
    #         self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
    #         self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
    #         self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
    #         self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "JEACE")
    #         Logger.success("Added FDS.COB.FLAG verified by CONCAT with DATA=JEACE")
    #         last_row_index = new_row_index
    #         changes_made = True
        
    #     # --- Row 2: FDS.COB.FLAG without DATA ---
    #     job2_exists = any(v == "FDS.COB.FLAG" and self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{k}:1").get_attribute("value") == "FDS.CBR.CONCAT.FILE.MT" 
    #                                           and self.utils.find_element_recursive(By.NAME, f"fieldName:DATA:{k}:1").get_attribute("value") == ""
    #                       for k, v in state["main_tables"].items())
    #     if not job2_exists:
    #         if not self._click_expand_on_row(last_row_index): return False
    #         new_row_index = last_row_index + 1
    #         self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
    #         self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
    #         self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
    #         Logger.success("Added FDS.COB.FLAG verified by CONCAT without DATA")
    #         changes_made = True
    #     return changes_made
    

# ===================================================================
# CLASS: BATCH Form Handler - JAMBI Version (FINAL FIX)
# ===================================================================
class BatchFormFiller_JAMBI:
    """
    Implements the batch form filling logic for the JAMBI version.
    NOTE: This class has a completely different logic from the others and does not inherit from BaseBatchFormFiller.
    """
    def __init__(self, driver, wait, utils: PageUtils, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.utils = utils
        self.config = config
        self.batch_file_path = config.file_path

    def _click_expand_on_row(self, row_index: int) -> bool:
        """Expand multi-value row using JavaScript click."""
        try:
            xpath = f"//input[contains(@name, 'JOB.NAME:{row_index}')]/ancestor::tr[1]//a[contains(@href, 'javascript:mvExpandClient')]/img"
            
            Logger.debug(f"Waiting for expand button to be clickable on row {row_index}...")
            expand_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            
            self.driver.execute_script("arguments[0].click();", expand_button)
            
            new_row_index = row_index + 1
            self.wait.until(EC.presence_of_element_located((By.NAME, f"fieldName:JOB.NAME:{new_row_index}")))
            return True
        except Exception as e:
            Logger.error(f"Expand click failed on row {row_index}. The button may not be active or visible.")
            self.utils.save_page_source(f"{self.config.inspect_dir}/expand_fail_row_{row_index}.html")
            self.utils.take_screenshot(f"{self.config.screenshot_dir}/expand_fail_row_{row_index}.png")
            Logger.error(f"Full error: {e}")
            return False

    def _fill_field_by_name(self, field_name: str, value: str) -> bool:
        """Fill form field by its name attribute."""
        try:
            field = self.utils.wait_for_element(By.NAME, field_name, timeout=10)
            if not field:
                Logger.error(f"Field not found: {field_name}")
                return False
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", field)
            field.clear()
            field.send_keys(value)
            return True
        except Exception as e:
            Logger.error(f"Field fill failed for {field_name}: {e}")
            return False
            
    def _scan_for_existing_jambi_tables(self) -> Set[str]:
        """Scans the form to find which tables have already been added for the Jambi version."""
        Logger.info("Scanning form for existing JAMBI tables...")
        existing_tables = set()
        
        job_name_fields = self.utils.find_elements_recursive(
            By.XPATH,
            "//input[@value='GENERATE.EXT.REPORT']"
        )
        
        for job_field in job_name_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                data_field_name = f"fieldName:DATA:{row_index}:1"
                data_field = self.utils.find_element_recursive(By.NAME, data_field_name)
                
                if data_field:
                    table_name = data_field.get_attribute("value")
                    if table_name:
                        existing_tables.add(table_name)
            except (ValueError, IndexError) as e:
                Logger.warning(f"Could not parse row index from field name '{name_attr}': {e}")
                continue
                
        Logger.info(f"Found {len(existing_tables)} existing JAMBI tables on the form.")
        return existing_tables

    def execute_filling_process(self) -> bool:
        """Main batch form filling workflow for the JAMBI version."""
        try:
            Logger.info("Starting form filling process for version: JAMBI")
            
            if not self.utils.select_radio_value_recursive("radio:tab1:BATCH.ENVIRONMENT", "F"):
                Logger.error("Failed to set mandatory BATCH.ENVIRONMENT radio button.")
                return False

            tables_from_file = DataManager.load_batch_tables(self.batch_file_path)
            if not tables_from_file:
                Logger.warning("No tables to process from file.")
                return True

            existing_tables = self._scan_for_existing_jambi_tables()
            missing_tables = [tbl for tbl in tables_from_file if tbl not in existing_tables]

            if not missing_tables:
                Logger.plain("All JAMBI batch data already exist on the form.")
                return True

            Logger.info(f"Adding {len(missing_tables)} new table pairs for JAMBI version...")

            all_job_name_fields = self.utils.find_elements_recursive(By.XPATH, "//input[starts-with(@name, 'fieldName:JOB.NAME:')]")
            last_row_index = 0
            if all_job_name_fields:
                indices = [int(field.get_attribute("name").split(":")[-1]) for field in all_job_name_fields]
                last_row_index = max(indices) if indices else 0

            is_form_pristine = False
            if last_row_index == 1:
                job_name_field_1 = self.utils.find_element_recursive(By.NAME, "fieldName:JOB.NAME:1")
                if job_name_field_1 and job_name_field_1.get_attribute("value") == "":
                    is_form_pristine = True
                    Logger.info("Form is pristine. Will start filling from row 1 directly.")

            is_first_addition = True
            for table_to_add in missing_tables:
                Logger.info(f"--- Adding pair for table: {table_to_add} ---")
                
                current_row_for_generate: int
                
                if is_first_addition and is_form_pristine:
                    current_row_for_generate = 1
                else:
                    if not self._click_expand_on_row(last_row_index): return False
                    current_row_for_generate = last_row_index + 1

                Logger.plain(f"Adding GENERATE.EXT.REPORT on row {current_row_for_generate}")
                self._fill_field_by_name(f"fieldName:JOB.NAME:{current_row_for_generate}", "GENERATE.EXT.REPORT")
                self._fill_field_by_name(f"fieldName:FREQUENCY:{current_row_for_generate}", "D")
                self._fill_field_by_name(f"fieldName:DATA:{current_row_for_generate}:1", table_to_add)

                if not self._click_expand_on_row(current_row_for_generate): return False
                current_row_for_concat = current_row_for_generate + 1
                
                Logger.plain(f"Adding FDS.CBR.CONCAT.FILE on row {current_row_for_concat}")
                self._fill_field_by_name(f"fieldName:JOB.NAME:{current_row_for_concat}", "FDS.CBR.CONCAT.FILE")
                self._fill_field_by_name(f"fieldName:VERIFICATION:{current_row_for_concat}:1", "GENERATE.EXT.REPORT")
                self._fill_field_by_name(f"fieldName:FREQUENCY:{current_row_for_concat}", "D")
                self._fill_field_by_name(f"fieldName:DATA:{current_row_for_concat}:1", table_to_add)

                last_row_index = current_row_for_concat
                is_first_addition = False

            Logger.success("Form filling for JAMBI version completed.")
            return True

        except Exception as e:
            Logger.error(f"Form processing error in JAMBI version: {e}")
            self.utils.take_screenshot(f"{self.config.screenshot_dir}/form_error_jambi.png")
            return False

# ?    
# ! New Form Filler for Batch
# ?    


# ===================================================================
# CLASS: REPORT Form Handler
# ===================================================================
class ReportFormFiller:
    """Fills report configuration forms"""
    
    def __init__(self, driver, wait, utils: PageUtils, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.utils = utils
        self.config = config
        self.reset_extractor_cache()

    def reset_extractor_cache(self):
        """Reset field detection cache"""
        self.existing_extractors_cache = None
        self.last_filled_index_cache = None

    def get_existing_extractors(self) -> list:
        """Get existing extractors with caching"""
        if self.existing_extractors_cache is not None:
            return self.existing_extractors_cache
            
        # Find all label fields
        all_label_fields = self.utils.find_elements_recursive(
            By.CSS_SELECTOR, 
            "input[name^='fieldName:REP.FLD.LABEL:']"
        )
        
        # Normalize values (lowercase + trim)
        existing = []
        for field in all_label_fields:
            value = field.get_attribute("value")
            if value:
                normalized = value.strip().lower()
                existing.append(normalized)
                
        self.existing_extractors_cache = existing
        return existing
    
    def fill_mandatory_fields(self, table_name: str) -> bool:
        """Fill required fields for report configuration"""
        # Generate field values based on table name
        short_name = table_name.replace("ST.","",1) if table_name.startswith("ST.") else table_name
        test_last_name = (
            table_name.replace("ST.", "", 1).replace(".TEST", "")
            if ".TEST" in table_name else table_name.replace("ST.","",1)
        )
        mandatory_fields = {
            "fieldName:DESCRIPTION": f"TABLE {short_name} SIMIAN",
            "fieldName:APPLICATION": test_last_name, # ! Gunakan short_name
            "fieldName:TARGET.FILE": f"ST.{short_name}.csv",
            "fieldName:OUTPUT.DIR": "CBR.BP",
            "fieldName:SEPARATOR": ";"
        }
        
        try:
            Logger.info("Filling mandatory fields...")
            # Handle radio button selection
            radio_button_locator = (By.NAME, "radio:tab1:EXT.APP")
            try:
                # Wait until ALL elements with that name are in the DOM
                self.wait.until(EC.presence_of_all_elements_located(radio_button_locator))
                Logger.debug("Radio buttons found by NAME.")
            except Exception:
                # Fallback if search by NAME fails, try by CSS
                Logger.debug("Radio buttons not found by NAME, trying CSS selector.")
                radio_button_locator_css = (By.CSS_SELECTOR, "input[type='radio'][name='radio:tab1:EXT.APP']")
                self.wait.until(EC.presence_of_all_elements_located(radio_button_locator_css))
                Logger.debug("Radio buttons found by CSS.")
            
            if not self.utils.select_radio_value_recursive("radio:tab1:EXT.APP", "N"): 
                return False
            
            # Fill each mandatory field
            for field_name, value in mandatory_fields.items():
                field = self.utils.wait_for_element(By.NAME, field_name)
                if field:
                    current_value = field.get_attribute("value")
                    if not current_value or current_value.strip() == "":
                        if not self._fill_field(field_name, value): 
                            return False
                    else:
                        Logger.plain(f'Field {field_name} already contains: {current_value}')
                else:
                    Logger.error(f"Field {field_name} not found")
                    return False
            return True
        except Exception as e:
            Logger.error(f"Mandatory field error: {e}")
            return False

    def _fill_field(self, name: str, value: str) -> bool:
        """Generic field filling method"""
        try:
            field = self.utils.find_element_recursive(By.NAME, name)
            if not field:
                Logger.error(f"Field '{name}' not found")
                return False
            self.wait.until(EC.visibility_of(field))
            field.clear()
            field.send_keys(value)
            return True
        except Exception as e:
            Logger.error(f"Field fill error '{name}': {e}")
            return False

    def fill_dynamic_fields(self, extractor_fields: list) -> bool:
        """Fill dynamic extractor fields"""
        self._has_logged_new_extractors = False

        try:
            if not extractor_fields: 
                return True
                
            existing_extractors = self.get_existing_extractors()
            
            # Normalize extractor names for comparison
            normalized_extractors = [f.strip().lower() for f in extractor_fields]
            
            # Identify new extractors
            new_extractors = [
                orig for orig, norm in zip(extractor_fields, normalized_extractors)
                if norm not in existing_extractors
            ]
            
            if not new_extractors:
                Logger.plain("All extractors already exist")
                return True
                
            if not self._has_logged_new_extractors:
                Logger.plain(f"Adding {len(new_extractors)} new extractors")
                self._has_logged_new_extractors = True

            # Determine starting index
            last_filled = self._get_last_filled_index()
            start_index = last_filled + 1
            
            # Fill new extractors
            for i, field_val in enumerate(new_extractors, start=start_index):
                if not self._fill_field_set(i, field_val): 
                    return False
                    
            return True
        except Exception as e:
            Logger.error(f"Dynamic field error: {e}")
            return False
        
    def _get_last_filled_index(self) -> int:
        """Get highest filled index in form"""
        if self.last_filled_index_cache is not None: 
            return self.last_filled_index_cache
            
        last_index = 0
        all_label_fields = self.utils.find_elements_recursive(
            By.CSS_SELECTOR, "input[name^='fieldName:REP.FLD.LABEL:']")
        
        for field in all_label_fields:
            if field.get_attribute("value").strip():
                try:
                    name_attr = field.get_attribute("name")
                    current_index = int(name_attr.split(':')[-1])
                    if current_index > last_index: 
                        last_index = current_index
                except: 
                    continue
                    
        self.last_filled_index_cache = last_index
        return last_index
    
    def _fill_field_set(self, index: int, value: str) -> bool:
        """Fill complete field set for one extractor"""
        if not self._handle_label_field(index, value): 
            return False
        if not self._handle_dropdown(index): 
            return False
        if not self._handle_value_field(index, value): 
            return False
        return True
    
    def _handle_label_field(self, index: int, value: str) -> bool:
        """Fill label field with expand handling"""
        try:
            label_field_name = f"fieldName:REP.FLD.LABEL:{index}"
            label_field = self.utils.find_element_recursive(By.NAME, label_field_name)
            
            # Expand form if field not found
            if not label_field:
                if not self._expand_form(index): 
                    return False
                label_field = self.utils.wait_for_element(By.NAME, label_field_name)
                if not label_field: 
                    raise TimeoutError(f"Field {label_field_name} missing after expand")
            
            self.wait.until(EC.visibility_of(label_field))
            if not label_field.get_attribute("value").strip():
                label_field.send_keys(value)
                label_field.send_keys(Keys.TAB)
                Logger.plain(f"Filled LABEL.{index}")
            return True
        except Exception as e:
            Logger.error(f"LABEL field error {index}: {e}")
            return False
    
    def _expand_form(self, index: int) -> bool:
        """Expand form section for new fields"""
        try:
            self.driver.switch_to.default_content()
            expand_xpath = f"//tr[contains(@mvlist, 'M_13.{index}_23.{index}')]//a[contains(@href, 'mvExpandClient')]/img"
            expand_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, expand_xpath)))
            expand_btn.click()
            self.wait.until(lambda d: self.utils.find_element_recursive(By.NAME, f"fieldName:REP.FLD.LABEL:{index}"))
            return True
        except Exception as e:
            Logger.error(f"Expand error {index}: {type(e).__name__}: {e}")
            self.utils.save_page_source(f"{self.config.inspect_dir}/expand_fail_index_{index}.html")
            self.utils.take_screenshot(f"{self.config.screenshot_dir}/expand_fail_index_{index}.png")
            return False
    
    def _handle_dropdown(self, index: int) -> bool:
        """Set default value in dropdown"""
        try:
            dropdown_name = f"fieldName:REP.FLD.EXT:{index}:1"
            dropdown = self.utils.wait_for_element(By.NAME, dropdown_name, timeout=5)
            if not dropdown:
                 Logger.error(f"Dropdown {dropdown_name} not found")
                 return False
            select = Select(dropdown)
            if not select.first_selected_option.text.strip():
                select.select_by_visible_text("Fld")
            return True
        except Exception as e:
            Logger.error(f"Dropdown error {index}: {e}")
            return False
    
    def _handle_value_field(self, index: int, value: str) -> bool:
        """Fill value field"""
        try:
            val_field_name = f"fieldName:REP.FLD.VAL1:{index}:1"
            val_field = self.utils.wait_for_element(By.NAME, val_field_name, timeout=5)
            if not val_field:
                Logger.error(f"Value field {val_field_name} not found")
                return False
            if not val_field.get_attribute("value").strip():
                val_field.send_keys(value)
                val_field.send_keys(Keys.TAB)
            return True
        except Exception as e:
            Logger.error(f"VALUE field error {index}: {e}")
            return False

# ===================================================================
# CLASS: DFE PARAMETER Form Handler
# ===================================================================
class DfeParamFormFiller:
    """Fills DFE.PARAMETER configuration forms"""
    
    def __init__(self, driver, wait, utils: PageUtils):
        self.driver = driver
        self.wait = wait
        self.utils = utils

    def fill_form(self, table_name: str) -> bool:
        """Fill all required fields for DFE configuration with improved logging."""
        Logger.info(f"Checking/Filling DFE form for table: {table_name}")
        try:
            # Flag to track if any changes were made
            changes_made = False

            # Wait for the form element to be ready
            Logger.info("Waiting for DFE form elements to be present...")
            radio_button_locator = (By.NAME, "radio:tab1:IN.OUT.TYPE")
            try:
                self.wait.until(EC.presence_of_all_elements_located(radio_button_locator))
                Logger.debug("Radio buttons found.")
            except Exception as e:
                Logger.error(f"Timed out waiting for radio buttons: {e}")
                self.utils.take_screenshot("screenshots/radio_button_wait_failed.png")
                return False

            # Field and value definitions
            description = (
                table_name.replace("ST.", "", 1).strip() + " EXTRACTION"
            )
            out_file_name = f"{table_name}.csv"
            
            radio_buttons = {
                "radio:tab1:IN.OUT.TYPE": "Out",
                "radio:tab1:MODE.OF.TXN": "Offline",
            }
            text_fields = {
                "fieldName:DESCRIPTION:1:1": description,
                "fieldName:DFE.MAPPING.ID": table_name.replace(".TEST", "").strip(), # ! change to table_name in prod
                "fieldName:OUTPUT.DIR": "../DFE",
                "fieldName:ARCHIVE.DIR": "../DFE",
                "fieldName:OUT.FILE.NAME": out_file_name,
            }

            # Radio Button charging logic
            for name, value in radio_buttons.items():
                success, changed = self.utils.select_radio_value_recursive(name, value)
                if not success:
                    Logger.error(f"Failed to handle radio button '{name}'")
                    return False
                if changed:
                    changes_made = True

            # Fill Text Field 
            for name, value in text_fields.items():
                field = self.utils.wait_for_element(By.NAME, name)
                if field:
                    # Fill only if field is empty
                    if field.get_attribute("value") == "":
                        self.driver.execute_script("arguments[0].value = arguments[1];", field, value)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", field)
                        Logger.plain(f"Filled '{name}' with '{value}'")
                        changes_made = True
                else:
                    Logger.error(f"Field '{name}' not found")
                    return False
            
            if not changes_made:
                Logger.plain("All fields already exist.")
            
            Logger.success(f"DFE form for '{table_name}' check/fill process completed.")
            return True
            
        except Exception as e:
            Logger.error(f"An error occurred while filling the DFE form: {e}")
            return False

# ===================================================================
# CLASS: DFE Mapping Form Handler (Inherits from ReportFormFiller)
# ===================================================================
class DfeMappingFormFiller(ReportFormFiller):
    """
    Fills DFE.MAPPING forms. Inherits from ReportFormFiller
    and overrides methods for mandatory and dynamic fields.
    """

    def _scan_existing_appl_fields(self) -> list:
        """Scans and returns a list of existing APPL.FIELD.NAME values."""
        if self.existing_extractors_cache is not None:
            return self.existing_extractors_cache
            
        all_label_fields = self.utils.find_elements_recursive(
            By.CSS_SELECTOR, 
            "input[name^='fieldName:APPL.FIELD.NAME:']"
        )
        
        existing = [field.get_attribute("value") for field in all_label_fields if field.get_attribute("value")]
        self.existing_extractors_cache = existing
        Logger.info(f"Found {len(existing)} existing mapping fields.")
        return existing
    
    def fill_mandatory_fields(self, table_name: str) -> bool:
        """Overrides parent method to fill DFE.MAPPING mandatory fields."""
        Logger.info("Filling DFE.MAPPING mandatory fields...")
        try:
            # Wait for the stable form element to appear, indicating that the form is ready.
            Logger.debug("Waiting for DFE Mapping form to be ready...")
            self.wait.until(EC.presence_of_element_located((By.NAME, "fieldName:FILE.NAME")))
            Logger.debug("DFE Mapping form is ready.")

            # Generate dynamic values
            file_name_val = table_name.replace("ST.", "", 1).replace(".TEST", "")
            description_val = table_name.replace("ST.", "", 1) + " EXTRACTOR"

            # Define fields and values
            text_fields = {
                "fieldName:FILE.NAME": file_name_val,
                "fieldName:DESCRIPTION:1:1": description_val,
                "fieldName:FIELD.DELIM": ";",
                "fieldName:VM.DELIM": "]",
                "fieldName:SM.DELIM": "!",
                "fieldName:ID.POSITION": "1",
            }

            # Handle radio button
            success, _ = self.utils.select_radio_value_recursive("radio:tab1:ID.GEN.TYPE", "Data")
            if not success: return False

            # Handle text fields
            for name, value in text_fields.items():
                field = self.utils.wait_for_element(By.NAME, name, timeout=5)
                if field and not field.get_attribute("value"):
                    if not self._fill_field(name, value):
                        return False
            return True
        except Exception as e:
            Logger.error(f"Failed to fill DFE.MAPPING mandatory fields: {e}")
            return False

    def _fill_field_set(self, index: int, value: str) -> bool:
        """Overrides parent method to fill a single row of mapping fields."""
        try:
            # 1. Fill APPL.FIELD.NAME
            if not self._fill_field(f"fieldName:APPL.FIELD.NAME:{index}", value): return False
            # 2. Fill APPL.FIELD.TEXT
            if not self._fill_field(f"fieldName:APPL.FIELD.TEXT:{index}", value): return False
            # 3. Fill FIELD.POSITION
            if not self._fill_field(f"fieldName:FIELD.POSITION:{index}", str(index)): return False
            Logger.plain(f"Filled mapping row {index} for field '{value}'")
            return True
        except Exception as e:
            Logger.error(f"Failed to fill mapping field set for index {index}: {e}")
            return False

    def fill_dynamic_fields(self, extractor_fields: list) -> bool:
        """
        Overrides parent method to orchestrate filling the dynamic mapping list.
        """
        self._has_logged_new_extractors = False
        try:
            if not extractor_fields: return True
                
            existing_fields = self._scan_existing_appl_fields()
            new_fields = [f for f in extractor_fields if f not in existing_fields]
            
            if not new_fields:
                Logger.plain("All mapping fields already exist.")
                return True
            
            Logger.plain(f"New mapping fields to add: {len(new_fields)}")
            
            last_filled_index = len(existing_fields)
            
            for i, field_val in enumerate(new_fields, start=1):
                current_index_to_fill = last_filled_index + i
                
                # Check whether the field to be filled in already exists or not
                label_field = self.utils.find_element_recursive(By.NAME, f"fieldName:APPL.FIELD.NAME:{current_index_to_fill}")
                if not label_field:
                    # If none, click expand from the previous row
                    index_to_expand_from = current_index_to_fill - 1
                    if index_to_expand_from == 0:
                        Logger.error("Cannot expand from index 0. First row should exist.")
                        return False
                    if not self._expand_form(index_to_expand_from): return False

                # Fill the field set for the current row
                if not self._fill_field_set(current_index_to_fill, field_val): return False
                    
            return True
        except Exception as e:
            Logger.error(f"Failed to fill dynamic mapping fields: {e}")
            return False
        
    def _expand_form(self, index_to_expand_from: int) -> bool:
        """
        Overrides the parent method with a locator specific to DFE.MAPPING.
        Clicks the expand button on the last known row to create a new row.
        """
        Logger.info(f"Expanding form from row {index_to_expand_from} to create a new row...")
        try:
            # This XPath looks for input from the last line, and then looks for the ‘Expand’ image on the same line.
            expand_xpath = f"//input[@name='fieldName:APPL.FIELD.NAME:{index_to_expand_from}']/ancestor::tr[1]//img[@title='Expand Multi Value']"
            
            expand_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, expand_xpath)))
            
            # Use Javascript for clicking
            self.driver.execute_script("arguments[0].click();", expand_btn)
            
            # Wait for the field in the new row to appear as confirmation
            new_index = index_to_expand_from + 1
            self.wait.until(EC.presence_of_element_located((By.NAME, f"fieldName:APPL.FIELD.NAME:{new_index}")))
            Logger.debug(f"Successfully expanded form, new row {new_index} is present.")
            return True
        except Exception as e:
            Logger.error(f"Expand error at row {index_to_expand_from}: {type(e).__name__}: {e}")
            self.utils.save_page_source(f"{self.config.inspect_dir}/expand_fail_index_{index_to_expand_from}.html")
            self.utils.take_screenshot(f"{self.config.screenshot_dir}/expand_fail_index_{index_to_expand_from}.png")
            return False