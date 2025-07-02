from core.logger import Logger
from core.page_utils import PageUtils
from core.data_manager import DataManager
from config.config_manager import AppConfig

import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from typing import List, Optional, Set

class BaseBatchFormFiller:
    """Base class for filling batch processing forms with common logic."""

    def __init__(self, driver, wait, utils: PageUtils, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.utils = utils
        self.config = config
        self.batch_file_path = config.file_path
        self._form_cache = None # Caches the form structure to avoid re-scanning.

    def _get_initial_data_value(self) -> str:
        """Returns the specific data value for the first, static job (e.g., 'JEACS')."""
        raise NotImplementedError

    def _get_first_extractor_verification(self) -> Optional[str]:
        """Returns the verification value for the first dynamically added EB.EXTRACTOR job."""
        raise NotImplementedError
    
    def _add_final_mandatory_rows(self, state: dict) -> bool:
        """Adds the specific sequence of mandatory jobs at the end of the form."""
        raise NotImplementedError

    def _fill_field_direct(self, name: str, value: str) -> bool:
        """A faster, non-recursive method to fill a field by its name."""
        try:
            field = self.driver.find_element(By.NAME, name)
            field.clear()
            field.send_keys(value)
            return True
        except Exception as e:
            Logger.error(f"Direct field fill error '{name}': {e}")
            return False

    def _scan_form_for_all_tables(self, use_cache=True) -> dict:
        """Scans the form to detect existing job configurations."""
        if use_cache and self._form_cache is not None:
            Logger.debug("[CACHE] Using cached form structure.")
            return self._form_cache

        Logger.info("Scanning form structure...")
        state = {
            "main_tables": {},
            "concat_tables": {},
            "concat_row_index": 0,
            "last_sub_value_index": 0,
            "all_tables": set(),
        }
        
        try:
            concat_input_xpath = "//span[normalize-space(text())='FDS.CBR.CONCAT.FILE.MT']/ancestor::tr[1]//input[starts-with(@name, 'fieldName:JOB.NAME:')]"
            concat_input_element = self.utils.find_element_recursive(By.XPATH, concat_input_xpath)
            if concat_input_element:
                name_attr = concat_input_element.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                state["concat_row_index"] = row_index
                Logger.debug(f"CONCAT row explicitly found at index: {row_index} via its text label.")
        except Exception:
            Logger.debug("Could not find CONCAT row via text label, will rely on input value scan.")

        all_job_fields = self.driver.find_elements(By.XPATH, "//input[starts-with(@name, 'fieldName:JOB.NAME:')]")
        all_data_fields = self.driver.find_elements(By.XPATH, "//input[starts-with(@name, 'fieldName:DATA:')]")
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
                if state["concat_row_index"] == 0:
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

        Logger.info(f"Scan complete: Found {len(state['main_tables'])} main jobs, {len(state['concat_tables'])} concat tables.")
        self._form_cache = state
        return state

    def _click_expand_on_row(self, row_index: int) -> bool:
        """Clicks the 'Expand Multi Value' button for a given row."""
        try:
            xpath = f"//input[@name='fieldName:JOB.NAME:{row_index}']/ancestor::tr[1]//img[contains(@title, 'Expand Multi Value')]"
            expand_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            self.driver.execute_script("arguments[0].click();", expand_button)
            
            new_row_index = row_index + 1
            self.wait.until(EC.presence_of_element_located((By.NAME, f"fieldName:JOB.NAME:{new_row_index}")))
            return True
        except Exception as e:
            Logger.error(f"Expand click failed on row {row_index}: {e}")
            return False

    def _click_sub_value_expand_button(self, row_index: int, last_sub_value_index: int) -> bool:
        """Expand sub-values in concat rows using a faster JS click."""
        try:
            xpath = f"//input[@name='fieldName:DATA:{row_index}:{last_sub_value_index}']/ancestor::tr[1]//img[@title='Expand Sub Value']"
            
            expand_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            self.driver.execute_script("arguments[0].click();", expand_button)
            
            new_sub_index = last_sub_value_index + 1
            self.wait.until(EC.presence_of_element_located((By.NAME, f"fieldName:DATA:{row_index}:{new_sub_index}")))
            return True
        except Exception as e:
            Logger.error(f"Expand sub-value failed at row {row_index}, sub-index {last_sub_value_index}: {e}")
            self.utils.save_page_source(f"{self.config.inspect_dir}/expand_sub_value_failed.html")
            return False

    def _fill_field_by_name(self, field_name: str, value: str) -> bool:
        """A wrapper for finding and filling a field by its name attribute."""
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
            Logger.error(f"Field fill failed for '{field_name}': {e}")
            return False
            
    def _perform_initial_setup(self, table_names_from_file: List[str]) -> bool:
        """Performs the initial setup if the form is completely empty."""
        initial_state = self._scan_form_for_all_tables(use_cache=False)
        is_form_truly_empty = not initial_state["main_tables"] and not initial_state["concat_tables"]
        
        if not is_form_truly_empty:
            return False

        Logger.info("Form is empty. Performing initial setup...")
        initial_data_value = self._get_initial_data_value()
        
        if not self.utils.select_radio_value_recursive("radio:tab1:BATCH.ENVIRONMENT", "F"): return False
        if not self._fill_field_by_name("fieldName:JOB.NAME:1", "FDS.COB.FLAG"): return False
        if not self._fill_field_by_name("fieldName:FREQUENCY:1", "D"): return False
        if not self._fill_field_by_name("fieldName:DATA:1:1", initial_data_value): return False
        
        Logger.success(f"Initial setup complete with data: {initial_data_value}")
        return True

    def _invalidate_form_cache(self):
        """Clears the cached form structure to force a re-scan."""
        self._form_cache = None
    
    def _update_concat_cache(self, table_name: str, concat_row_index: int):
        """Updates the local cache after adding a table to the CONCAT row without a full re-scan."""
        if self._form_cache:
            self._form_cache["concat_tables"][table_name] = concat_row_index
            self._form_cache["all_tables"].add(table_name)
            self._form_cache["last_sub_value_index"] += 1

    def execute_filling_process(self, table_names_from_file: List[str]) -> bool:
        """The main, generic workflow for filling a batch form."""
        try:
            Logger.info(f"Starting standard batch filling for version: {self.config.batch_version.upper()}")
            changes_made = False

            # Initial setup is now more complex and version-dependent, handled by subclasses
            if self._perform_initial_setup(table_names_from_file):
                self._invalidate_form_cache()
                changes_made = True

            initial_state = self._scan_form_for_all_tables(use_cache=False)
            missing_tables = [t for t in table_names_from_file if t not in initial_state.get("all_tables", set())]

            if missing_tables:
                Logger.info(f"Found {len(missing_tables)} new jobs to add.")
                
                all_job_inputs = self.utils.find_elements_recursive(By.XPATH, "//input[starts-with(@name, 'fieldName:JOB.NAME:')]")
                last_row_index = 0
                for job_input in all_job_inputs:
                    job_name = job_input.get_attribute("value")
                    current_row_index = int(job_input.get_attribute("name").split(":")[-1])
                    if job_name in ("EB.EXTRACTOR", "FDS.COB.FLAG", ""):
                        last_row_index = current_row_index
                    else:
                        break

                has_existing_extractors = any(
                    "EB.EXTRACTOR" in job_name for job_name in initial_state.get("main_tables", {}).keys()
                )

                for i, table_to_add in enumerate(missing_tables):
                    if not self._click_expand_on_row(last_row_index): return False
                    new_row_index = last_row_index + 1
                    self.wait.until(EC.presence_of_element_located((By.NAME, f"fieldName:JOB.NAME:{new_row_index}")))

                    self._fill_field_direct(f"fieldName:JOB.NAME:{new_row_index}", "EB.EXTRACTOR")
                    
                    verification_value = "EB.EXTRACTOR"
                    if i == 0 and not has_existing_extractors:
                        v = self._get_first_extractor_verification()
                        verification_value = v if v else verification_value
                    self._fill_field_direct(f"fieldName:VERIFICATION:{new_row_index}:1", verification_value)
                    
                    self.driver.execute_script(f"document.getElementsByName('fieldName:FREQUENCY:{new_row_index}')[0].value = 'D';")
                    self._fill_field_direct(f"fieldName:DATA:{new_row_index}:1", table_to_add)
                    last_row_index = new_row_index
                    changes_made = True

            self._invalidate_form_cache()
            final_state = self._scan_form_for_all_tables(use_cache=False)
            concat_row_index = final_state.get("concat_row_index", 0)

            if concat_row_index == 0 and final_state.get("main_tables"):
                last_main_row = max(final_state["main_tables"].values())
                if not self._click_expand_on_row(last_main_row): return False
                concat_row_index = last_main_row + 1
                self._fill_field_direct(f"fieldName:JOB.NAME:{concat_row_index}", "FDS.CBR.CONCAT.FILE.MT")
                self._fill_field_direct(f"fieldName:VERIFICATION:{concat_row_index}:1", "EB.EXTRACTOR")
                self.driver.execute_script(f"document.getElementsByName('fieldName:FREQUENCY:{concat_row_index}')[0].value = 'D';")
                self._invalidate_form_cache()
                final_state = self._scan_form_for_all_tables(use_cache=False)
                changes_made = True

            existing_tables_in_concat = final_state.get("concat_tables", {}).keys()
            tables_to_add_to_concat = [t for t in table_names_from_file if t not in existing_tables_in_concat]

            if tables_to_add_to_concat:
                Logger.info(f"Adding {len(tables_to_add_to_concat)} tables to CONCAT job...")
                current_sub_index = final_state.get("last_sub_value_index", 0)

                first_field = self.driver.find_element(By.NAME, f"fieldName:DATA:{concat_row_index}:1")
                if first_field and not first_field.get_attribute("value") and tables_to_add_to_concat:
                    first_table = tables_to_add_to_concat.pop(0)
                    self._fill_field_direct(f"fieldName:DATA:{concat_row_index}:1", first_table)
                    self._update_concat_cache(first_table, concat_row_index)
                    current_sub_index = 1
                
                for table_name in tables_to_add_to_concat:
                    if not self._click_sub_value_expand_button(concat_row_index, current_sub_index): return False
                    current_sub_index += 1
                    field_name = f"fieldName:DATA:{concat_row_index}:{current_sub_index}"
                    self.wait.until(EC.presence_of_element_located((By.NAME, field_name)))
                    self._fill_field_direct(field_name, table_name)
                    self._update_concat_cache(table_name, concat_row_index)
                changes_made = True

            self._invalidate_form_cache()
            if self._add_final_mandatory_rows(self._scan_form_for_all_tables(use_cache=False)):
                changes_made = True

            if not changes_made:
                Logger.plain("No changes needed; all jobs already exist.")
            else:
                Logger.success("Form filling completed successfully.")
            return True

        except Exception as e:
            Logger.error(f"Batch form processing error: {e}", exc_info=True)
            self.utils.take_screenshot(f"{self.config.screenshot_dir}/form_error.png")
            return False

class BatchFormFiller_SBII(BaseBatchFormFiller):
    """Implements the batch form filling logic for the SBII version."""
    
    def _get_initial_data_value(self) -> str:
        return "JEACS"

    def _get_first_extractor_verification(self) -> Optional[str]:
        return "FDS.COB.FLAG"
    
    def _add_final_mandatory_rows(self, state: dict) -> bool:
        """Adds SBII-specific jobs: FDS.COB.FLAG and CREATE.FILE.DONE.2."""
        Logger.info("Adding final mandatory rows for SBII version...")
        changes_made = False
        
        last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})
        job_flag_fields = self.utils.find_elements_recursive(By.XPATH, "//input[@value='FDS.COB.FLAG']")
        
        # Check for and add the first FDS.COB.FLAG job.
        job1_found = False
        for job_field in job_flag_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                if (verification_field and verification_field.get_attribute("value") == "FDS.CBR.CONCAT.FILE.MT"):
                    job1_found = True
                    break
            except (ValueError, IndexError): continue
        if not job1_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "JEACE")
            last_row_index = new_row_index
            changes_made = True

        # Check for and add the CREATE.FILE.DONE.2 job.
        job2_field = self.utils.find_element_recursive(By.XPATH, "//input[@value='CREATE.FILE.DONE.2']")
        if not job2_field:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "CREATE.FILE.DONE.2")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            last_row_index = new_row_index
            changes_made = True

        # Check for and add the final FDS.COB.FLAG job.
        job3_found = False
        for job_field in job_flag_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                if (verification_field and verification_field.get_attribute("value") == "CREATE.FILE.DONE.2"):
                    job3_found = True
                    break
            except (ValueError, IndexError): continue
        if not job3_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "CREATE.FILE.DONE.2")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            changes_made = True
            
        return changes_made

class BatchFormFiller_KALSEL(BaseBatchFormFiller):
    """Implements the batch form filling logic for the KALSEL version."""

    def _get_initial_data_value(self) -> str:
        return "SEACS"

    def _get_first_extractor_verification(self) -> Optional[str]:
        return None

    def _add_final_mandatory_rows(self, state: dict) -> bool:
        """Adds KALSEL-specific jobs: CREATE.FILE.DONE and FDS.COB.FLAG."""
        Logger.info("Adding final mandatory rows for KALSEL version...")
        changes_made = False

        last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})

        # Check for and add CREATE.FILE.DONE job.
        job1_field = self.utils.find_element_recursive(By.XPATH, "//input[@value='CREATE.FILE.DONE']")
        if not job1_field:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "CREATE.FILE.DONE")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            last_row_index = new_row_index
            changes_made = True

        # Check for and add final FDS.COB.FLAG job.
        job_flag_fields = self.utils.find_elements_recursive(By.XPATH, "//input[@value='FDS.COB.FLAG']")
        job2_found = False
        for job_field in job_flag_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                if (verification_field and verification_field.get_attribute("value") == "CREATE.FILE.DONE"):
                    job2_found = True
                    break
            except (ValueError, IndexError): continue
        if not job2_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "CREATE.FILE.DONE")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "SEACE")
            changes_made = True
            
        return changes_made

class BatchFormFiller_BJI(BaseBatchFormFiller):
    """Implements the batch form filling logic for the BJI version."""

    def _get_initial_data_value(self) -> str:
        return "JEACS"

    def _get_first_extractor_verification(self) -> Optional[str]:
        return "FDS.COB.FLAG"
    
    def _add_final_mandatory_rows(self, state: dict) -> bool:
        """Adds BJI-specific jobs: two FDS.COB.FLAG jobs with different data."""
        Logger.info("Adding final mandatory rows for BJI version...")
        changes_made = False

        last_row_index = max(set(state["main_tables"].values()) | {state["concat_row_index"]})
        job_flag_fields = self.utils.find_elements_recursive(By.XPATH, "//input[@value='FDS.COB.FLAG']")
        
        # Check for and add the first FDS.COB.FLAG job (with data).
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
                    break
            except (ValueError, IndexError): continue
        if not job1_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            self._fill_field_by_name(f"fieldName:DATA:{new_row_index}:1", "JEACE")
            last_row_index = new_row_index
            changes_made = True
        
        # Check for and add the second FDS.COB.FLAG job (without data).
        job2_found = False
        for job_field in job_flag_fields:
            try:
                name_attr = job_field.get_attribute("name")
                row_index = int(name_attr.split(':')[-1])
                verification_field = self.utils.find_element_recursive(By.NAME, f"fieldName:VERIFICATION:{row_index}:1")
                data_field = self.utils.find_element_recursive(By.NAME, f"fieldName:DATA:{row_index}:1")
                if (verification_field and verification_field.get_attribute("value") == "FDS.CBR.CONCAT.FILE.MT" and
                    data_field and data_field.get_attribute("value") == ""):
                    job2_found = True
                    break
            except (ValueError, IndexError): continue
        if not job2_found:
            if not self._click_expand_on_row(last_row_index): return False
            new_row_index = last_row_index + 1
            self._fill_field_by_name(f"fieldName:JOB.NAME:{new_row_index}", "FDS.COB.FLAG")
            self._fill_field_by_name(f"fieldName:VERIFICATION:{new_row_index}:1", "FDS.CBR.CONCAT.FILE.MT")
            self._fill_field_by_name(f"fieldName:FREQUENCY:{new_row_index}", "D")
            changes_made = True
            
        return changes_made

class BatchFormFiller_JAMKRINDO(BaseBatchFormFiller):
    """
    Implements a modified batch form filling logic for JAMKRINDO.
    It overrides the main execution process to handle unique verification rules,
    sets a specific Batch Environment, and eliminates final mandatory rows.
    """

    def _add_final_mandatory_rows(self, state: dict) -> bool:
        """
        Overrides the base method to do nothing.
        No fields will be added after the CONCAT job for this version.
        """
        Logger.info("No final mandatory rows will be added for JAMKRINDO version.")
        return False

    def execute_filling_process(self, table_names_from_file: List[str]) -> bool:
        """
        A completely overridden execution process to implement the custom logic
        for adding EB.EXTRACTOR jobs with specific verification rules.
        """
        try:
            Logger.info("[JAMKRINDO] Starting custom batch filling process.")
            changes_made = False

            # Set the mandatory Batch Environment to 'F'.
            Logger.info("Setting mandatory Batch Environment to 'F'...")
            success, changed = self.utils.select_radio_value_recursive("radio:tab1:BATCH.ENVIRONMENT", "F")
            if not success:
                Logger.error("Failed to set mandatory Batch Environment radio button.")
                return False
            if changed:
                changes_made = True

            # The list of tables is now passed as a parameter.
            if not table_names_from_file:
                Logger.warning("No tables were provided to process for this batch.")
                return True

            initial_state = self._scan_form_for_all_tables(use_cache=False)
            existing_tables = initial_state.get("all_tables", set())
            
            missing_tables = [t for t in table_names_from_file if t not in existing_tables]

            if not missing_tables:
                Logger.plain("No new jobs to add. All tables already exist in the form.")
                changes_made = False
            else:
                Logger.info(f"Found {len(missing_tables)} new jobs to add.")
                changes_made = True
                
                # Find the correct insertion point before adding new jobs.
                insertion_point = 0
                concat_row_index = initial_state.get("concat_row_index", 0)

                if concat_row_index > 0:
                    insertion_point = concat_row_index - 1
                    Logger.info(f"CONCAT job found at row {concat_row_index}. New jobs will be inserted after row {insertion_point}.")
                else:
                    all_job_inputs = self.utils.find_elements_recursive(By.XPATH, "//input[starts-with(@name, 'fieldName:JOB.NAME:')]")
                    if all_job_inputs:
                        if len(all_job_inputs) == 1 and not all_job_inputs[0].get_attribute("value"):
                            insertion_point = 0
                            Logger.info("Form is empty. Starting from row 1.")
                        else:
                            insertion_point = max([int(f.get_attribute("name").split(":")[-1]) for f in all_job_inputs])
                            Logger.info(f"CONCAT job not found. Inserting after last known row: {insertion_point}.")
                
                last_row_index = insertion_point
                
                has_existing_extractors = any(
                    "EB.EXTRACTOR" in val for val in initial_state.get("main_tables", {}).keys()
                )
                
                # Loop through missing tables and add them one by one.
                for table_to_add in missing_tables:
                    if last_row_index > 0:
                        if not self._click_expand_on_row(last_row_index): return False
                    
                    current_row_num = last_row_index + 1
                    Logger.info(f"Adding Job {current_row_num}: {table_to_add}")

                    self._fill_field_direct(f"fieldName:JOB.NAME:{current_row_num}", "EB.EXTRACTOR")
                    self.driver.execute_script(f"document.getElementsByName('fieldName:FREQUENCY:{current_row_num}')[0].value = 'D';")
                    self._fill_field_direct(f"fieldName:DATA:{current_row_num}:1", table_to_add)

                    # Apply custom logic for the Verification field.
                    if not has_existing_extractors and last_row_index == 0:
                        Logger.plain("First extractor job, verification is left empty.")
                    else:
                        self._fill_field_direct(f"fieldName:VERIFICATION:{current_row_num}:1", "EB.EXTRACTOR")

                    last_row_index = current_row_num
            
            # Re-check the form state before creating the CONCAT job.
            self._invalidate_form_cache()
            final_state = self._scan_form_for_all_tables(use_cache=False)
            concat_row_index = final_state.get("concat_row_index", 0)
            all_main_jobs = final_state.get("main_tables", {})
            last_job_index = max(all_main_jobs.values()) if all_main_jobs else 0
            
            if concat_row_index == 0 and last_job_index > 0:
                if not self._click_expand_on_row(last_job_index): return False
                concat_row_index = last_job_index + 1
                self._fill_field_direct(f"fieldName:JOB.NAME:{concat_row_index}", "FDS.CBR.CONCAT.FILE.MT")
                self._fill_field_direct(f"fieldName:VERIFICATION:{concat_row_index}:1", "EB.EXTRACTOR")
                self.driver.execute_script(f"document.getElementsByName('fieldName:FREQUENCY:{concat_row_index}')[0].value = 'D';")
                changes_made = True
            
            # Fill the data fields for the CONCAT job.
            if concat_row_index > 0:
                existing_concat_tables = final_state.get("concat_tables", {}).keys()
                tables_to_add_to_concat = [t for t in table_names_from_file if t not in existing_concat_tables]

                if tables_to_add_to_concat:
                    Logger.info(f"Adding {len(tables_to_add_to_concat)} tables to CONCAT job...")
                    current_sub_index = final_state.get("last_sub_value_index", 0)

                    first_field = self.driver.find_element(By.NAME, f"fieldName:DATA:{concat_row_index}:1")
                    if first_field and not first_field.get_attribute("value") and tables_to_add_to_concat:
                        self._fill_field_direct(f"fieldName:DATA:{concat_row_index}:1", tables_to_add_to_concat.pop(0))
                        current_sub_index = 1
                    
                    for table_name in tables_to_add_to_concat:
                        if not self._click_sub_value_expand_button(concat_row_index, current_sub_index): return False
                        current_sub_index += 1
                        field_name = f"fieldName:DATA:{concat_row_index}:{current_sub_index}"
                        self._fill_field_direct(field_name, table_name)
                    changes_made = True

            # Call the (empty) final rows method to adhere to the pattern.
            self._add_final_mandatory_rows(final_state)
            
            if changes_made:
                Logger.success("[JAMKRINDO] Form filling completed successfully.")
            else:
                Logger.plain("No changes were made to the form.")

            return True

        except Exception as e:
            Logger.error(f"[JAMKRINDO] Form processing error: {e}", exc_info=True)
            self.utils.take_screenshot(f"{self.config.screenshot_dir}/jamkrindo_batch_error.png")
            return False

class BatchFormFiller_JAMBI:
    """
    Implements the batch form filling logic for the JAMBI version.
    This version has a unique structure and does not inherit from the base filler.
    """
    def __init__(self, driver, wait, utils: PageUtils, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.utils = utils
        self.config = config
        self.batch_file_path = config.file_path

    def _click_expand_on_row(self, row_index: int) -> bool:
        """Helper to click the expand button for a given row."""
        try:
            xpath = f"//input[contains(@name, 'JOB.NAME:{row_index}')]/ancestor::tr[1]//a[contains(@href, 'javascript:mvExpandClient')]/img"
            
            expand_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            self.driver.execute_script("arguments[0].click();", expand_button)
            
            new_row_index = row_index + 1
            self.wait.until(EC.presence_of_element_located((By.NAME, f"fieldName:JOB.NAME:{new_row_index}")))
            return True
        except Exception as e:
            Logger.error(f"Expand click failed on row {row_index}: {e}")
            self.utils.save_page_source(f"{self.config.inspect_dir}/expand_fail_row_{row_index}.html")
            self.utils.take_screenshot(f"{self.config.screenshot_dir}/expand_fail_row_{row_index}.png")
            return False

    def _fill_field_by_name(self, field_name: str, value: str) -> bool:
        """Helper to find and fill a field by its name attribute."""
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
            Logger.error(f"Field fill failed for '{field_name}': {e}")
            return False
            
    def _scan_for_existing_jambi_tables(self) -> Set[str]:
        """Scans the form to find tables already added for the Jambi version."""
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
            except (ValueError, IndexError):
                continue
                
        Logger.info(f"Found {len(existing_tables)} existing JAMBI tables on the form.")
        return existing_tables

    def execute_filling_process(self, tables_from_file: List[str]) -> bool:
        """Main batch form filling workflow for the JAMBI version."""
        try:
            Logger.info("Starting form filling process for version: JAMBI")
            
            if not self.utils.select_radio_value_recursive("radio:tab1:BATCH.ENVIRONMENT", "F"):
                Logger.error("Failed to set mandatory BATCH.ENVIRONMENT radio button.")
                return False

            # tables_from_file = DataManager.load_batch_tables(self.batch_file_path)
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

                # Add the GENERATE.EXT.REPORT job.
                self._fill_field_by_name(f"fieldName:JOB.NAME:{current_row_for_generate}", "GENERATE.EXT.REPORT")
                self._fill_field_by_name(f"fieldName:FREQUENCY:{current_row_for_generate}", "D")
                self._fill_field_by_name(f"fieldName:DATA:{current_row_for_generate}:1", table_to_add)

                # Add the FDS.CBR.CONCAT.FILE job that verifies the previous one.
                if not self._click_expand_on_row(current_row_for_generate): return False
                current_row_for_concat = current_row_for_generate + 1
                
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

class ReportFormFiller:
    """Fills the EXT.REPORT configuration forms."""
    
    def __init__(self, driver, wait, utils: PageUtils, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.utils = utils
        self.config = config
        self.reset_extractor_cache()

    def reset_extractor_cache(self):
        """Reset the field detection cache for a new form."""
        self.existing_extractors_cache = None
        self.last_filled_index_cache = None

    def get_existing_extractors(self) -> list:
        """Get a list of existing extractors from the form, with caching."""
        if self.existing_extractors_cache is not None:
            return self.existing_extractors_cache
            
        all_label_fields = self.utils.find_elements_recursive(
            By.CSS_SELECTOR, 
            "input[name^='fieldName:REP.FLD.LABEL:']"
        )
        
        existing = []
        for field in all_label_fields:
            value = field.get_attribute("value")
            if value:
                normalized = value.strip().lower()
                existing.append(normalized)
                
        self.existing_extractors_cache = existing
        return existing
    
    def fill_mandatory_fields(self, table_name: str) -> bool:
        """Fill the main, required fields for the report configuration."""
        short_name = table_name.replace("ST.","",1) if table_name.startswith("ST.") else table_name
        test_last_name = (
            table_name.replace("ST.", "", 1).replace(".TEST", "")
            if ".TEST" in table_name else table_name.replace("ST.","",1)
        )
        mandatory_fields = {
            "fieldName:DESCRIPTION": f"TABLE {short_name} SIMIAN",
            "fieldName:APPLICATION": test_last_name,
            "fieldName:TARGET.FILE": f"ST.{short_name}.csv",
            "fieldName:OUTPUT.DIR": "CBR.BP",
            "fieldName:SEPARATOR": ";"
        }
        
        try:
            Logger.info("Filling mandatory fields...")
            
            # Select the 'N' option for the EXT.APP radio button.
            if not self.utils.select_radio_value_recursive("radio:tab1:EXT.APP", "N"): 
                return False
            
            # Fill each mandatory field if it is empty.
            for field_name, value in mandatory_fields.items():
                field = self.utils.wait_for_element(By.NAME, field_name)
                if field:
                    current_value = field.get_attribute("value")
                    if not current_value or current_value.strip() == "":
                        if not self._fill_field(field_name, value): 
                            return False
                else:
                    Logger.error(f"Mandatory field '{field_name}' not found.")
                    return False
            return True
        except Exception as e:
            Logger.error(f"Error filling mandatory fields: {e}")
            return False

    def _fill_field(self, name: str, value: str) -> bool:
        """Generic helper method to fill a single field."""
        try:
            field = self.utils.find_element_recursive(By.NAME, name)
            if not field:
                Logger.error(f"Field '{name}' not found.")
                return False
            self.wait.until(EC.visibility_of(field))
            field.clear()
            field.send_keys(value)
            return True
        except Exception as e:
            Logger.error(f"Field fill error for '{name}': {e}")
            return False

    def fill_dynamic_fields(self, extractor_fields: list) -> bool:
        """Fill the dynamic list of extractor fields at the bottom of the form."""
        try:
            if not extractor_fields: 
                return True
                
            existing_extractors = self.get_existing_extractors()
            normalized_extractors = [f.strip().lower() for f in extractor_fields]
            
            # Determine which fields from the input are new.
            new_extractors = [
                orig for orig, norm in zip(extractor_fields, normalized_extractors)
                if norm not in existing_extractors
            ]
            
            if not new_extractors:
                Logger.plain("All extractor fields already exist.")
                return True
                
            Logger.plain(f"Adding {len(new_extractors)} new extractor fields...")

            # Find the last filled row to start adding from.
            last_filled = self._get_last_filled_index()
            start_index = last_filled + 1
            
            # Loop and fill each new extractor.
            for i, field_val in enumerate(new_extractors, start=start_index):
                if not self._fill_field_set(i, field_val): 
                    return False
                    
            return True
        except Exception as e:
            Logger.error(f"Dynamic field filling error: {e}")
            return False
        
    def _get_last_filled_index(self) -> int:
        """Get the highest index of a filled row in the dynamic list."""
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
                except: continue
                    
        self.last_filled_index_cache = last_index
        return last_index
    
    def _fill_field_set(self, index: int, value: str) -> bool:
        """Fill a complete set of fields for one extractor row."""
        if not self._handle_label_field(index, value): return False
        if not self._handle_dropdown(index): return False
        if not self._handle_value_field(index, value): return False
        return True
    
    def _handle_label_field(self, index: int, value: str) -> bool:
        """Fill the label field, expanding the form if necessary."""
        try:
            label_field_name = f"fieldName:REP.FLD.LABEL:{index}"
            label_field = self.utils.find_element_recursive(By.NAME, label_field_name)
            
            if not label_field:
                if not self._expand_form(index): return False
                label_field = self.utils.wait_for_element(By.NAME, label_field_name)
                if not label_field: 
                    raise TimeoutError(f"Field {label_field_name} not found after expand.")
            
            self.wait.until(EC.visibility_of(label_field))
            if not label_field.get_attribute("value").strip():
                label_field.send_keys(value)
                label_field.send_keys(Keys.TAB) # Tab out to trigger potential JS.
            return True
        except Exception as e:
            Logger.error(f"LABEL field error at index {index}: {e}")
            return False
    
    def _expand_form(self, index: int) -> bool:
        """Expand the form to reveal a new row for dynamic fields."""
        try:
            self.driver.switch_to.default_content()
            expand_xpath = f"//tr[contains(@mvlist, 'M_13.{index}_23.{index}')]//a[contains(@href, 'mvExpandClient')]/img"
            expand_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, expand_xpath)))
            expand_btn.click()
            self.wait.until(lambda d: self.utils.find_element_recursive(By.NAME, f"fieldName:REP.FLD.LABEL:{index}"))
            return True
        except Exception as e:
            Logger.error(f"Expand form error at index {index}: {e}")
            self.utils.save_page_source(f"{self.config.inspect_dir}/expand_fail_index_{index}.html")
            return False
    
    def _handle_dropdown(self, index: int) -> bool:
        """Set the default 'Fld' value in the dropdown for an extractor row."""
        try:
            dropdown_name = f"fieldName:REP.FLD.EXT:{index}:1"
            dropdown = self.utils.wait_for_element(By.NAME, dropdown_name, timeout=5)
            if not dropdown:
                 Logger.error(f"Dropdown {dropdown_name} not found.")
                 return False
            select = Select(dropdown)
            if not select.first_selected_option.text.strip():
                select.select_by_visible_text("Fld")
            return True
        except Exception as e:
            Logger.error(f"Dropdown error at index {index}: {e}")
            return False
    
    def _handle_value_field(self, index: int, value: str) -> bool:
        """Fill the value field for an extractor row."""
        try:
            val_field_name = f"fieldName:REP.FLD.VAL1:{index}:1"
            val_field = self.utils.wait_for_element(By.NAME, val_field_name, timeout=5)
            if not val_field:
                Logger.error(f"Value field {val_field_name} not found.")
                return False
            if not val_field.get_attribute("value").strip():
                val_field.send_keys(value)
                val_field.send_keys(Keys.TAB)
            return True
        except Exception as e:
            Logger.error(f"VALUE field error at index {index}: {e}")
            return False
    
    def _fill_field_direct(self, name: str, value: str) -> bool:
        """A fast, non-recursive method to fill a field, assuming the driver is already in the correct frame."""
        try:
            field = self.driver.find_element(By.NAME, name)
            field.clear()
            field.send_keys(value)
            return True
        except Exception as e:
            Logger.error(f"Direct field fill error for '{name}': {e}")
            return False

class DfeParamFormFiller:
    """Fills DFE.PARAMETER configuration forms."""
    
    def __init__(self, driver, wait, utils: PageUtils):
        self.driver = driver
        self.wait = wait
        self.utils = utils

    def fill_form(self, table_name: str) -> bool:
        """Fill all required fields for a DFE.PARAMETER record."""
        Logger.info(f"Checking/Filling DFE form for table: {table_name}")
        try:
            changes_made = False
            self.wait.until(EC.presence_of_all_elements_located((By.NAME, "radio:tab1:IN.OUT.TYPE")))

            description = table_name.replace("ST.", "", 1).strip() + " EXTRACTION"
            dfe_mapping_id = "ST." + table_name.replace("ST.", "", 1).replace(".TEST", "").strip()
            out_file_name = f"{table_name}.csv"
            
            radio_buttons = {
                "radio:tab1:IN.OUT.TYPE": "Out",
                "radio:tab1:MODE.OF.TXN": "Offline",
            }
            text_fields = {
                "fieldName:DESCRIPTION:1:1": description,
                "fieldName:DFE.MAPPING.ID": dfe_mapping_id,
                "fieldName:OUTPUT.DIR": "../DFE",
                "fieldName:ARCHIVE.DIR": "../DFE",
                "fieldName:OUT.FILE.NAME": out_file_name,
            }

            for name, value in radio_buttons.items():
                success, changed = self.utils.select_radio_value_recursive(name, value)
                if not success: return False
                if changed: changes_made = True

            # Check and fill text fields only if their current value is incorrect.
            for name, value in text_fields.items():
                field = self.utils.wait_for_element(By.NAME, name)
                if field:
                    current_value = field.get_attribute("value")
                    if current_value != value:
                        Logger.plain(f"Field '{name}' has incorrect value. Updating to '{value}'.")
                        self.driver.execute_script("arguments[0].value = arguments[1];", field, value)
                        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", field)
                        changes_made = True
                else:
                    Logger.error(f"Field '{name}' not found")
                    return False
            
            if not changes_made:
                Logger.plain("All fields already have the correct values.")
            
            Logger.success(f"DFE form for '{table_name}' check/fill process completed.")
            return True
            
        except Exception as e:
            Logger.error(f"An error occurred while filling the DFE form: {e}")
            return False

class DfeMappingFormFiller:
    """
    Fills DFE.MAPPING forms with a high-performance, standalone approach.
    It assumes the driver is already in the correct frame context.
    """

    def __init__(self, driver, wait, utils: PageUtils, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.utils = utils
        self.config = config
        self.existing_fields_cache = None

    def reset_cache(self):
        """Resets the cache of existing fields for a new form."""
        self.existing_fields_cache = None
        
    def _fill_field_direct(self, name: str, value: str) -> bool:
        """A fast, non-recursive method to fill a field."""
        try:
            field = self.driver.find_element(By.NAME, name)
            field.clear()
            field.send_keys(value)
            return True
        except Exception as e:
            Logger.error(f"Direct field fill error for '{name}': {e}")
            return False

    def _scan_existing_appl_fields(self) -> list:
        """
        Scans for existing fields non-recursively, using iterative scrolling
        to handle potential lazy-loading of elements.
        """
        if self.existing_fields_cache is not None:
            return self.existing_fields_cache

        Logger.info("Scanning for existing fields with iterative scroll...")
        
        last_count = -1
        while True:
            all_label_fields = self.driver.find_elements(By.CSS_SELECTOR, "input[name^='fieldName:APPL.FIELD.NAME:']")
            current_count = len(all_label_fields)
            
            if current_count == last_count:
                break
            
            last_count = current_count
            
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", all_label_fields[-1])
                time.sleep(1.5) 
            except IndexError:
                break
        
        Logger.info(f"Scan complete. Total fields found: {last_count}")

        existing = [field.get_attribute("value") for field in all_label_fields if field.get_attribute("value")]
        self.existing_fields_cache = existing
        return existing

    def fill_mandatory_fields(self, table_name: str) -> bool:
        """Fills the main mandatory fields for a DFE.MAPPING record."""
        Logger.info("Filling DFE.MAPPING mandatory fields...")
        try:
            file_name_val = table_name.replace("ST.", "", 1).replace(".TEST", "") # ! Change this with your reqruitment
            description_val = table_name.replace("ST.", "", 1) + " EXTRACTOR"
            
            text_fields = {
                "fieldName:FILE.NAME": file_name_val,
                "fieldName:DESCRIPTION:1:1": description_val,
                "fieldName:FIELD.DELIM": ";",
                "fieldName:VM.DELIM": "]",
                "fieldName:SM.DELIM": "!",
                "fieldName:ID.POSITION": "1",
            }

            success, _ = self.utils.select_radio_value_recursive("radio:tab1:ID.GEN.TYPE", "Data")
            if not success: return False

            for name, value in text_fields.items():
                field = self.driver.find_element(By.NAME, name)
                if field and not field.get_attribute("value"):
                    self._fill_field_direct(name, value)

            # ? add mandatory fields specific to the STMT.ENTRY, CATEG.ENTRY, RE.CONSOL.SPEC.ENTRY table 
            selection_value = None
            if "STMT.ENTRY" in table_name:
                selection_value = "@DFE.SELECT.STMT.LWORK"
            elif "CATEG.ENTRY" in table_name:
                selection_value = "@DFE.SELECT.CATEG.LWORK"
            elif "RE.CONSOL.SPEC.ENTRY" in table_name:
                selection_value = "@DFE.SELECT.RE.SPEC.LWORK"
            
            if selection_value:
                Logger.info(f"Special table detected. Setting FILE.SELECTION to: {selection_value}")
                if not self._fill_field_direct("fieldName:FILE.SELECTION:1", selection_value):
                    return False # Gagal jika tidak bisa mengisi field

            return True
        except Exception as e:
            Logger.error(f"Failed to fill mandatory fields: {e}")
            return False

    def _get_last_filled_index(self) -> int:
        """Helper to get the last index of a filled field in the dynamic list."""
        last_index = 0
        all_label_fields = self.driver.find_elements(By.CSS_SELECTOR, "input[name^='fieldName:APPL.FIELD.NAME:']")
        for field in all_label_fields:
            if field.get_attribute("value").strip():
                try:
                    current_index = int(field.get_attribute("name").split(':')[-1])
                    if current_index > last_index:
                        last_index = current_index
                except (ValueError, IndexError):
                    continue
        return last_index

    def fill_dynamic_fields_batched(self, extractor_fields: list) -> bool:
        """
        Fills all dynamic fields using a single, large JavaScript command for maximum performance.
        """
        try:
            if not extractor_fields:
                return True

            existing_fields = self._scan_existing_appl_fields()
            new_fields = [f for f in extractor_fields if f not in existing_fields]

            if not new_fields:
                Logger.plain("All mapping fields already exist.")
                return True

            Logger.info(f"Adding {len(new_fields)} new mapping fields.")

            last_filled_index = self._get_last_filled_index()

            # This single JavaScript block performs the entire loop, which is much faster
            # than making separate calls from Python for each row.
            js_batch_script = """
            // Arguments received from Python: fieldsToAdd (array), startIndex (number)
            const fieldsToAdd = arguments[0];
            const startIndex = arguments[1];

            // The loop now happens inside the browser's fast JS engine.
            for (let i = 0; i < fieldsToAdd.length; i++) {
                const currentIndexToExpand = startIndex + i;
                const currentIndexToFill = currentIndexToExpand + 1;
                const valueToFill = fieldsToAdd[i];

                // Step 1: Expand a new row by calling the application's JS function.
                if (currentIndexToExpand > 0) {
                    try {
                        const row = document.querySelector("input[name='fieldName:APPL.FIELD.NAME:" + currentIndexToExpand + "']").closest('tr');
                        const mvlist = row.getAttribute('mvlist');
                        if (mvlist) {
                            mvExpandClient(mvlist, '0', '0');
                        }
                    } catch (e) {
                        return { success: false, error: "Expand failed at index " + currentIndexToExpand + ": " + e.message };
                    }
                }

                // Step 2: Fill the fields in the newly created row.
                try {
                    document.querySelector("input[name='fieldName:APPL.FIELD.NAME:" + currentIndexToFill + "']").value = valueToFill;
                    document.querySelector("input[name='fieldName:APPL.FIELD.TEXT:" + currentIndexToFill + "']").value = valueToFill;
                    document.querySelector("input[name='fieldName:FIELD.POSITION:" + currentIndexToFill + "']").value = currentIndexToFill;
                } catch (e) {
                    return { success: false, error: "Fill failed at index " + currentIndexToFill + ": " + e.message };
                }
            }
            // Return a success status if the entire loop completes.
            return { success: true };
            """

            result = self.driver.execute_script(js_batch_script, new_fields, last_filled_index)

            if result and result.get('success'):
                Logger.success(f"Completed filling all {len(new_fields)} new fields via batch.")
                return True
            else:
                error_message = result.get('error', 'Unknown JavaScript execution error.')
                Logger.error(f"Batched JavaScript execution failed: {error_message}")
                return False

        except Exception as e:
            Logger.error(f"Batched dynamic field filling failed with a Python error: {e}")
            return False