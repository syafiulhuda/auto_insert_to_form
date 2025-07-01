import os
from core.extractor_validator import ExtractorValidator
from core.logger import Logger
from config.config_manager import AppConfig
from core.page_utils import PageUtils
from core.banner_handler import BannerFrameHandler
from core.commit_handler import CommitHandler
from core.transaction_handler import TransactionInputHandler

from core.form_filler import BatchFormFiller_JAMKRINDO, BatchFormFiller_SBII, BatchFormFiller_KALSEL, BatchFormFiller_BJI, BatchFormFiller_JAMBI
from core.form_filler import ReportFormFiller
from core.form_filler import DfeParamFormFiller
from core.form_filler import DfeMappingFormFiller

from typing import Dict, List

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC


class BatchProcessor:
    """Orchestrates the entire batch processing workflow."""
    
    def __init__(self, driver, wait, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.config = config
        self.utils = PageUtils(driver, wait)
        self.banner_handler = BannerFrameHandler(driver, wait)
        self.commit_handler = CommitHandler(driver, wait)

        # Use a dictionary to map the version string to the correct form filler class.
        filler_map = {
            "sbii": BatchFormFiller_SBII,
            "bji": BatchFormFiller_BJI,
            "kalsel": BatchFormFiller_KALSEL,
            "jamkrindo": BatchFormFiller_JAMKRINDO,
            "jambi": BatchFormFiller_JAMBI,
        }
        FillerClass = filler_map.get(config.batch_version)
        if not FillerClass:
            raise ValueError(f"Batch version '{config.batch_version}' is invalid or not configured.")
        
        self.form_filler = FillerClass(driver, wait, self.utils, config)
        Logger.info(f"BatchProcessor initialized with {FillerClass.__name__}")

    # ! FUNC WITHOUT CLICK COMMIT BUTTON
    def process(self) -> bool:
        """
        Execute a sequence of batch jobs defined in the source file without committing.
        The process will stop on the form of the FIRST job for inspection.
        """
        Logger.info("Starting Batch Mode (Commit disabled)")
        
        # Hanya proses job pertama karena tidak ada commit/cleanup
        if not self.config.batch_jobs:
            Logger.warning("No batch jobs were loaded from the source file.")
            return True

        # Ambil hanya command dan tabel untuk job pertama
        command, tables = self.config.batch_jobs[0]
        
        Logger.plain("\n" + "="*60)
        Logger.info(f"Processing FIRST Batch Job | Command: {command}")
        Logger.plain("="*60)

        # Jalankan command
        if not self.banner_handler.execute_command(command):
            Logger.error("Command execution failed.")
            return False

        # Tunggu form siap
        try:
            self.wait.until(EC.presence_of_element_located((By.NAME, "fieldName:JOB.NAME:1")))
        except Exception:
            Logger.warning("Form not ready, using fallback wait.")
            self.wait.until(EC.presence_of_element_located((By.ID, "contract_screen_div")))

        # Jalankan proses pengisian
        success = self.form_filler.execute_filling_process(tables)
        
        if success:
            Logger.success("Form filling simulation completed successfully.")
            Logger.info("Process stopped for inspection. No commit or cleanup will be performed.")
        else:
            Logger.error("Form filling simulation failed.")
        return success

    # ! FUNC WITH CLICK COMMIT BUTTON  
    # def process(self) -> bool:
    #     """Execute a sequence of batch jobs with commit for each."""
    #     Logger.info("Starting Batch Mode (Commit Enabled)")
        
    #     all_batches_successful = True
    #     total_batches = len(self.config.batch_jobs)

    #     if total_batches == 0:
    #         Logger.warning("No batch jobs were loaded from the source file.")
    #         return True

    #     main_window_handle = self.driver.current_window_handle

    #     for i, (command, tables) in enumerate(self.config.batch_jobs):
    #         Logger.plain("\n" + "="*60)
    #         Logger.info(f"Processing Batch Job {i+1}/{total_batches} | Command: {command}")
    #         Logger.plain("="*60)

    #         self.driver.switch_to.window(main_window_handle)

    #         if not self.banner_handler.execute_command(command):
    #             Logger.error(f"Command execution failed for job {i+1}. Skipping to next job.")
    #             all_batches_successful = False
    #             continue

    #         try:
    #             self.wait.until(EC.presence_of_element_located((By.NAME, "fieldName:JOB.NAME:1")))
    #         except Exception:
    #             Logger.warning("Form not ready, using fallback wait.")
    #             self.wait.until(EC.presence_of_element_located((By.ID, "contract_screen_div")))

    #         # Execute form filling
    #         success = self.form_filler.execute_filling_process(tables)
            
    #         # Commit if filling was successful
    #         if success:
    #             if self.commit_handler.execute_commit():
    #                 Logger.success(f"Job {i+1} processed and committed successfully.")
    #             else:
    #                 Logger.error(f"Commit failed for job {i+1}.")
    #                 all_batches_successful = False
    #         else:
    #             Logger.error(f"Form filling for job {i+1} failed.")
    #             all_batches_successful = False
            
    #         # Close the form window/tab to return to the main window
    #         current_handles = self.driver.window_handles
    #         if len(current_handles) > 1:
    #             # The form window is assumed to be the active one, so close it.
    #             self.driver.close()
            
    #         # Switch focus back to the main window for the next iteration
    #         self.driver.switch_to.window(main_window_handle)
    #         Logger.info(f"Finished job {i+1}. Returning to main window.")

    #     Logger.plain("\n" + "="*60)
    #     Logger.info("All batch jobs have been processed.")
    #     return all_batches_successful

# ! NEW CLASS
class ReportProcessor:
    """
    Orchestrates the report processing workflow, including a pre-check
    and correct window management for multi-table processing.
    """
    
    def __init__(self, driver, wait, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.config = config
        self.utils = PageUtils(driver, wait)
        self.banner_handler = BannerFrameHandler(driver, wait)
        self.commit_handler = CommitHandler(driver, wait)
        self.validator = ExtractorValidator(driver, wait, self.banner_handler)
        self.form_filler = ReportFormFiller(driver, wait, self.utils, config)
        self.unidentified_log_path = os.path.join(config.inspect_dir, "extractor_unidentify.txt")

        # Clear the log file at the start of the process
        with open(self.unidentified_log_path, "w") as f:
            f.write("--- Unidentified Extractor Fields Log ---\n")

    def _log_unidentified_extractors(self, table_name: str, invalid_extractors: List[str]):
        """Appends a list of unidentified extractors for a table to the log file."""
        if not invalid_extractors:
            return
        
        with open(self.unidentified_log_path, "a") as f:
            f.write(f"\nTable: {table_name}\n")
            f.write("  Fields not found in STANDARD.SELECTION:\n")
            for extractor in invalid_extractors:
                f.write(f"  - {extractor}\n")
        Logger.warning(f"{len(invalid_extractors)} fields for '{table_name}' were not found. See log for details.")

    # ! FUNC WITHOUT CLICK COMMIT BUTTON
    # def process(self) -> Dict[str, bool]:
    #     """
    #     Executes report processing with pre-validation but without committing.
    #     Stops after filling the form for the first table for inspection.
    #     """
    #     Logger.info("Starting Report Mode (NO COMMIT / TEST RUN)")
    #     results = {}
        
    #     if not self.config.tables:
    #         Logger.warning("No tables configured for Report Mode.")
    #         return {}
        
    #     table_name = self.config.tables[0]
    #     self.form_filler.reset_extractor_cache()
        
    #     # --- VALIDATION STEP ---
    #     required_extractors = self.config.extractors.get(table_name, [])
    #     if not required_extractors:
    #         valid_extractors = []
    #     else:
    #         valid_extractors, invalid_extractors = self.validator.validate_extractors_for_table(table_name, required_extractors)
    #         self._log_unidentified_extractors(table_name, invalid_extractors)

    #     if required_extractors and not valid_extractors:
    #         Logger.error(f"All required fields for '{table_name}' are invalid. Skipping form filling.")
    #         results[table_name] = False
    #         return results

    #     # --- FORM FILLING STEP ---
    #     Logger.plain("-" * 50)
    #     Logger.info(f"Proceeding to fill EXT.REPORT form for '{table_name}'.")
        
    #     command = f"EXT.REPORT,INP {table_name}"
    #     if not self.banner_handler.execute_command(command):
    #         results[table_name] = False
    #         return results
        
    #     if not self.form_filler.fill_mandatory_fields(table_name):
    #         results[table_name] = False
    #         return results
        
    #     if valid_extractors and not self.form_filler.fill_dynamic_fields(valid_extractors):
    #         results[table_name] = False
    #         return results
        
    #     results[table_name] = True
    #     Logger.success(f"Table '{table_name}' form filled successfully (simulation).")
    #     Logger.info("Process stopped for inspection. No commit will be performed.")
    #     return results

    # ! FUNC WITH CLICK COMMIT BUTTON
    def process(self) -> Dict[str, bool]:
        """Execute report processing with commit and pre-validation for multiple tables."""
        Logger.info("Starting Report Mode Processing (Commit Enabled)")
        results = {}
        
        main_window_handle = self.driver.current_window_handle
        
        for i, table_name in enumerate(self.config.tables):
            self.form_filler.reset_extractor_cache()
            
            # Ensure the driver context is on the main window before starting a new validation cycle.
            self.driver.switch_to.window(main_window_handle)
            
            # --- VALIDATION STEP ---
            required_extractors = self.config.extractors.get(table_name, [])
            if not required_extractors:
                valid_extractors = []
            else:
                valid_extractors, invalid_extractors = self.validator.validate_extractors_for_table(table_name, required_extractors)
                self._log_unidentified_extractors(table_name, invalid_extractors)
            
            if required_extractors and not valid_extractors:
                Logger.error(f"All required fields for '{table_name}' are invalid. Skipping.")
                results[table_name] = False
                continue
            
            # --- FORM FILLING STEP ---
            Logger.plain("-" * 50)
            Logger.info(f"Proceeding to fill EXT.REPORT form for '{table_name}'.")
            
            # Execute command from the main window. This opens a new window/tab.
            command = f"EXT.REPORT,INP {table_name}"
            if not self.banner_handler.execute_command(command):
                results[table_name] = False
                continue
            
            # The driver is now in the new EXT.REPORT window/tab.
            
            if not self.form_filler.fill_mandatory_fields(table_name):
                results[table_name] = False
                continue
            
            if valid_extractors and not self.form_filler.fill_dynamic_fields(valid_extractors):
                results[table_name] = False
                continue
            
            if not self.commit_handler.execute_commit():
                results[table_name] = False
                continue

            results[table_name] = True
            Logger.success(f"Successfully processed and committed table: {table_name}\n")
            
            # --- WINDOW MANAGEMENT FOR NEXT LOOP ---
            # After processing, close the current form window to return to the main one.
            if i < len(self.config.tables) - 1:
                Logger.info("Closing current form window to prepare for the next table.")
                if self.driver.current_window_handle != main_window_handle:
                    self.driver.close()
                self.driver.switch_to.window(main_window_handle)
            else:
                Logger.info("Last table processed. Finishing.")
        return results

# ! OLD CLASS
# class ReportProcessor:
#     """Orchestrates the report generation workflow."""
    
#     def __init__(self, driver, wait, config: AppConfig):
#         self.driver = driver
#         self.wait = wait
#         self.config = config
#         self.utils = PageUtils(driver, wait)
#         self.banner_handler = BannerFrameHandler(driver, wait)
#         self.form_filler = ReportFormFiller(driver, wait, self.utils, config)
#         self.transaction_handler = TransactionInputHandler(driver, wait)
#         self.commit_handler = CommitHandler(driver, wait)
        
#     # ! FUNC WITHOUT CLICK COMMIT BUTTON
#     # def process(self) -> Dict[str, bool]:
#     #     """Execute report processing without commit."""
#     #     Logger.info("Starting Report Mode Processing")
#     #     results = {}

#     #     for i, table_name in enumerate(self.config.tables):
#     #         self.form_filler.reset_extractor_cache()

#     #         if i == 0:
#     #             command = f"EXT.REPORT,INP {table_name}"
#     #             if not self.banner_handler.execute_command(command):
#     #                 results[table_name] = False
#     #                 continue
                
#     #         extractor_fields = self.config.extractors.get(table_name, [])
#     #         if not self.form_filler.fill_mandatory_fields(table_name):
#     #             results[table_name] = False
#     #             continue

#     #         if extractor_fields and not self.form_filler.fill_dynamic_fields(extractor_fields):
#     #             results[table_name] = False
#     #             continue
            
#     #         Logger.info("[SKIP] Commit button skipped during testing")
                
#     #         results[table_name] = True
#     #         Logger.success(f"Table {table_name} processed")
            
#     #         Logger.plain("Process will stop after this table because commit is skipped.")
#     #         break 
#     #     return results
    
#     # ! FUNC WITH CLICK COMMIT BUTTON
#     def process(self) -> Dict[str, bool]:
#         """Execute report processing with commit."""
#         Logger.info("Starting Report Mode Processing")
#         results = {}
#         for i, table_name in enumerate(self.config.tables):
#             self.form_filler.reset_extractor_cache()
#             if i == 0:
#                 command = f"EXT.REPORT,INP {table_name}"
#                 if not self.banner_handler.execute_command(command):
#                     results[table_name] = False
#                     continue
#             extractor_fields = self.config.extractors.get(table_name, [])
            
#             if not self.form_filler.fill_mandatory_fields(table_name):
#                 results[table_name] = False
#                 continue
            
#             if extractor_fields and not self.form_filler.fill_dynamic_fields(extractor_fields):
#                 results[table_name] = False
#                 continue
            
#             if not self.commit_handler.execute_commit():
#                 results[table_name] = False
#                 continue
            
#             results[table_name] = True
#             Logger.success(f"Processed table: {table_name}\n")
#             if i < len(self.config.tables) - 1:
#                 next_table = self.config.tables[i + 1]
#                 if not self.transaction_handler.input_transaction(next_table):
#                     break    
#         return results

class DfeParamProcessor:
    """Orchestrates the DFE.PARAMETER processing workflow."""
    
    def __init__(self, driver, wait, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.config = config
        self.banner_handler = BannerFrameHandler(driver, wait)
        self.form_filler = DfeParamFormFiller(driver, wait, PageUtils(driver, wait))
        self.transaction_handler = TransactionInputHandler(driver, wait)
        self.commit_handler = CommitHandler(driver, wait)

    # ! FUNC WITHOUT CLICK COMMIT BUTTON
    # def process(self) -> Dict[str, bool]:
    #     """Execute DFE.PARAMETER processing without commit for testing."""
    #     Logger.info("Starting DFE Parameter Mode (NO COMMIT)")
    #     results = {}
    #     total_tables = len(self.config.tables)

    #     for i, table_name in enumerate(self.config.tables):
    #         Logger.plain("-" * 50)
    #         Logger.info(f"Processing DFE table {i+1}/{total_tables}: {table_name}")

    #         if i == 0:
    #             command = f"DFE.PARAMETER, {table_name}"
    #             if not self.banner_handler.execute_command(command):
    #                 results[table_name] = False
    #                 Logger.error("Initial command failed. Aborting process.")
    #                 break 
            
    #         if not self.form_filler.fill_form(table_name):
    #             results[table_name] = False
    #             Logger.error(f"Form filling failed for {table_name}.")
    #             continue

    #         Logger.info("[SKIP] Commit button skipped for testing.")
    #         results[table_name] = True
    #         Logger.success(f"Successfully filled DFE form for table: {table_name}")
            
    #         Logger.plain("Process will stop after this table because commit is skipped.")
    #         break      
    #     return results

    # ! FUNC WITH CLICK COMMIT BUTTON
    def process(self) -> Dict[str, bool]:
        """Execute DFE.PARAMETER processing WITH commit."""
        Logger.info("Starting DFE Parameter Mode Processing")
        results = {}
        total_tables = len(self.config.tables)
        for i, table_name in enumerate(self.config.tables):
            Logger.plain("-" * 50)
            Logger.info(f"Processing DFE table {i+1}/{total_tables}: {table_name}")
            if i == 0:
                command = f"DFE.PARAMETER, {table_name}"
                if not self.banner_handler.execute_command(command):
                    results[table_name] = False
                    Logger.error("Initial command failed. Aborting process.")
                    break 
            if not self.form_filler.fill_form(table_name):
                results[table_name] = False
                Logger.error(f"Form filling failed for {table_name}. Attempting to continue...")
                continue
            if not self.commit_handler.execute_commit():
                results[table_name] = False
                Logger.error(f"Commit failed for {table_name}. Aborting process.")
                break
            results[table_name] = True
            Logger.success(f"Successfully processed DFE table: {table_name}\n")
            if i < total_tables - 1:
                next_table = self.config.tables[i + 1]
                if not self.transaction_handler.input_transaction(next_table):
                    Logger.error(f"Failed to input next transaction ID: {next_table}. Aborting.")
                    break      
        return results

# ! NEW CLASS
class DfeMappingProcessor:
    """
    Orchestrates the DFE.MAPPING workflow, including a pre-check
    to validate mapping fields against STANDARD.SELECTION and to halt
    if no valid extractor fields are found.
    """
    
    def __init__(self, driver, wait, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.config = config
        self.utils = PageUtils(driver, wait)
        self.banner_handler = BannerFrameHandler(driver, wait)
        self.commit_handler = CommitHandler(driver, wait)
        # Initialize the validator and the form filler
        self.validator = ExtractorValidator(driver, wait, self.banner_handler)
        self.form_filler = DfeMappingFormFiller(driver, wait, self.utils, config)
        self.unidentified_log_path = os.path.join(config.inspect_dir, "extractor_unidentify.txt")

        # Clear the log file at the start of the process
        with open(self.unidentified_log_path, "w") as f:
            f.write("--- Unidentified Extractor Fields Log ---\n")

    def _log_unidentified_extractors(self, table_name: str, invalid_extractors: List[str]):
        """Appends a list of unidentified extractors for a table to the log file."""
        if not invalid_extractors:
            return
        
        with open(self.unidentified_log_path, "a") as f:
            f.write(f"\nTable: {table_name}\n")
            f.write("  Fields not found in STANDARD.SELECTION:\n")
            for extractor in invalid_extractors:
                f.write(f"  - {extractor}\n")
        Logger.warning(f"{len(invalid_extractors)} fields for '{table_name}' were not found. See log for details.")
    
    def _switch_to_main_frame(self) -> bool:
        """Helper to reliably switch to the main form frame using a landmark element."""
        if not self.utils.find_and_switch_to_frame_containing(By.NAME, "fieldName:FILE.NAME"):
            Logger.error("Could not switch to the main form frame.")
            return False
        Logger.debug("Successfully switched to the main form frame.")
        return True

    # ! FUNC WITHOUT CLICK COMMIT BUTTON
    def process(self) -> Dict[str, bool]:
        """
        Executes a test run for DFE Mapping with pre-validation but no commit.
        """
        Logger.info("Starting DFE Mapping Mode (NO COMMIT / TEST RUN)")
        results = {}
        
        if not self.config.tables:
            Logger.warning("No tables configured for DFE Mapping.")
            return {}
        
        table_name = self.config.tables[0]
        self.form_filler.reset_cache()
        
        required_extractors = self.config.extractors.get(table_name, [])
        if not required_extractors:
            Logger.warning(f"No extractors listed for table '{table_name}'. Assuming only mandatory fields needed.")
            valid_extractors = []
        else:
            valid_extractors, invalid_extractors = self.validator.validate_extractors_for_table(table_name, required_extractors)
            self._log_unidentified_extractors(table_name, invalid_extractors)

        if required_extractors and not valid_extractors:
            Logger.error(f"All {len(required_extractors)} required fields for '{table_name}' are invalid. Skipping form filling for this table.")
            results[table_name] = False
            return results

        Logger.plain("-" * 50)
        if valid_extractors:
            Logger.info(f"Proceeding to fill DFE.MAPPING form for '{table_name}' with {len(valid_extractors)} valid fields.")
        else:
            Logger.info(f"Proceeding to fill DFE.MAPPING form for '{table_name}' with mandatory fields only.")
        
        command = f"DFE.MAPPING, {table_name}"
        if not self.banner_handler.execute_command(command):
            results[table_name] = False
            return results

        if not self._switch_to_main_frame():
            results[table_name] = False
            return results

        if not self.form_filler.fill_mandatory_fields(table_name):
            results[table_name] = False
            return results
        
        if valid_extractors:
            if not self.form_filler.fill_dynamic_fields_batched(valid_extractors):
                results[table_name] = False
                return results
        
        results[table_name] = True
        Logger.success(f"Table '{table_name}' form filled successfully (simulation).")
        Logger.info("Process stopped for inspection. No commit will be performed.")
        return results

    # ! FUNC WITH CLICK COMMIT BUTTON
    # def process(self) -> Dict[str, bool]:
    #     """Execute DFE Mapping processing with commit and pre-validation."""
    #     Logger.info("Starting DFE Map Mode Processing (Commit Enabled)")
    #     results = {}
    #     total_tables = len(self.config.tables)

    #     for i, table_name in enumerate(self.config.tables):
    #         self.form_filler.reset_cache()
            
    #         # --- VALIDATION STEP ---
    #         required_extractors = self.config.extractors.get(table_name, [])
    #         if not required_extractors:
    #             Logger.warning(f"No fields listed for table '{table_name}'. Proceeding with mandatory fields only.")
    #             valid_extractors = []
    #         else:
    #             valid_extractors, invalid_extractors = self.validator.validate_extractors_for_table(table_name, required_extractors)
    #             self._log_unidentified_extractors(table_name, invalid_extractors)

    #         # --- HALT IF NO VALID FIELDS ---
    #         if required_extractors and not valid_extractors:
    #             Logger.error(f"All {len(required_extractors)} required fields for '{table_name}' are invalid. Skipping processing for this table.")
    #             results[table_name] = False
    #             continue # Lanjut ke tabel berikutnya

    #         # --- FORM FILLING STEP ---
    #         Logger.plain("-" * 50)
    #         if valid_extractors:
    #             Logger.info(f"Proceeding to fill DFE.MAPPING form for '{table_name}' with {len(valid_extractors)} valid fields.")
    #         else:
    #             Logger.info(f"Proceeding to fill DFE.MAPPING form for '{table_name}' with mandatory fields only.")
            
    #         command = f"DFE.MAPPING, {table_name}"
    #         if not self.banner_handler.execute_command(command):
    #             results[table_name] = False
    #             continue

    #         if not self._switch_to_main_frame():
    #             results[table_name] = False
    #             continue
            
    #         if not self.form_filler.fill_mandatory_fields(table_name):
    #             results[table_name] = False
    #             continue
            
    #         if valid_extractors:
    #             if not self.form_filler.fill_dynamic_fields_batched(valid_extractors):
    #                 results[table_name] = False
    #                 continue
            
    #         if not self.commit_handler.execute_commit():
    #             results[table_name] = False
    #             continue

    #         results[table_name] = True
    #         Logger.success(f"Successfully processed and committed table: {table_name}\n")

    #         # Berhenti setelah satu tabel untuk mode DFE Mapping
    #         Logger.info("DFE Mapping processing for one table complete. Stopping as designed.")
    #         break
    #     return results

# ! OLD CLASS
# class DfeMappingProcessor:
#     """Orchestrates the DFE.MAPPING workflow using a high-performance filler."""
    
#     def __init__(self, driver, wait, config: AppConfig):
#         self.driver = driver
#         self.wait = wait
#         self.config = config
#         self.utils = PageUtils(driver, wait)
#         self.banner_handler = BannerFrameHandler(driver, wait)
#         self.form_filler = DfeMappingFormFiller(driver, wait, self.utils, config)
#         self.transaction_handler = TransactionInputHandler(driver, wait)
#         self.commit_handler = CommitHandler(driver, wait)

#     def _switch_to_main_frame(self) -> bool:
#         """Helper to reliably switch to the main form frame using a landmark element."""
#         if not self.utils.find_and_switch_to_frame_containing(By.NAME, "fieldName:FILE.NAME"):
#             Logger.error("Could not switch to the main form frame.")
#             return False
#         Logger.debug("Successfully switched to the main form frame.")
#         return True

#     # ! FUNC WITHOUT CLICK COMMIT BUTTON
#     def process(self) -> Dict[str, bool]:
#         """
#         Executes a test run for DFE Mapping on the first table without committing.
#         Utilizes the batched method for a fast and accurate test.
#         """
#         Logger.info("Starting DFE Mapping Mode (NO COMMIT / TEST RUN)")
#         results = {}
#         if not self.config.tables:
#             Logger.warning("No tables configured for DFE Mapping.")
#             return {}

#         table_name = self.config.tables[0]
#         self.form_filler.reset_cache()
        
#         command = f"DFE.MAPPING, {table_name}"
#         if not self.banner_handler.execute_command(command):
#             results[table_name] = False
#             return results

#         if not self._switch_to_main_frame():
#             results[table_name] = False
#             return results

#         is_successful = True
#         if not self.form_filler.fill_mandatory_fields(table_name):
#             is_successful = False

#         extractor_fields = self.config.extractors.get(table_name, [])
#         if is_successful and extractor_fields:
#             if not self.form_filler.fill_dynamic_fields_batched(extractor_fields):
#                 is_successful = False
        
#         results[table_name] = is_successful
#         if is_successful:
#             Logger.info("[SKIP] Commit button skipped during test run.")
#             Logger.success(f"Table '{table_name}' processed successfully (simulation).")
#         else:
#             Logger.error(f"Processing failed for table '{table_name}'.")
#         return results
    
#     # ! FUNC WITH CLICK COMMIT BUTTON
#     # def process(self) -> Dict[str, bool]:
#     #     """
#     #     Execute DFE Mapping processing with commit, utilizing the batched
#     #     method for optimal performance on all browsers.
#     #     """
#     #     Logger.info("Starting DFE Map Mode Processing (Commit Enabled)")
#     #     results = {}
#     #     total_tables = len(self.config.tables)
#     #     for i, table_name in enumerate(self.config.tables):
#     #         self.form_filler.reset_cache()
#     #         Logger.plain("-" * 50)
#     #         Logger.info(f"Processing table {i+1}/{total_tables}: {table_name}")
#     #         if i == 0:
#     #             command = f"DFE.MAPPING, {table_name}"
#     #             if not self.banner_handler.execute_command(command):
#     #                 results[table_name] = False
#     #                 Logger.error(f"Initial command failed for {table_name}. Aborting process.")
#     #                 break
#     #         if not self._switch_to_main_frame():
#     #             results[table_name] = False
#     #             Logger.error(f"Failed to find form frame for {table_name}. Aborting.")
#     #             break
#     #         extractor_fields = self.config.extractors.get(table_name, [])
#     #         if not self.form_filler.fill_mandatory_fields(table_name):
#     #             results[table_name] = False
#     #             continue
#     #         if extractor_fields and not self.form_filler.fill_dynamic_fields_batched(extractor_fields):
#     #             results[table_name] = False
#     #             continue
#     #         if not self.commit_handler.execute_commit():
#     #             results[table_name] = False
#     #             Logger.error(f"Commit failed for {table_name}. Aborting process.")
#     #             break
#     #         results[table_name] = True
#     #         Logger.success(f"Successfully processed table: {table_name}\n")
#     #         if i < len(self.config.tables) - 1:
#     #             next_table = self.config.tables[i + 1]
#     #             if not self.transaction_handler.input_transaction(next_table):
#     #                 Logger.error(f"Failed to load next table: {next_table}. Aborting.")
#     #                 break
#     #     return results