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

from typing import Dict

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

class ReportProcessor:
    """Orchestrates the report generation workflow."""
    
    def __init__(self, driver, wait, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.config = config
        self.utils = PageUtils(driver, wait)
        self.banner_handler = BannerFrameHandler(driver, wait)
        self.form_filler = ReportFormFiller(driver, wait, self.utils, config)
        self.transaction_handler = TransactionInputHandler(driver, wait)
        self.commit_handler = CommitHandler(driver, wait)
        
    # ! FUNC WITHOUT CLICK COMMIT BUTTON
    def process(self) -> Dict[str, bool]:
        """Execute report processing without commit."""
        Logger.info("Starting Report Mode Processing")
        results = {}

        for i, table_name in enumerate(self.config.tables):
            self.form_filler.reset_extractor_cache()

            if i == 0:
                command = f"EXT.REPORT,INP {table_name}"
                if not self.banner_handler.execute_command(command):
                    results[table_name] = False
                    continue
                
            extractor_fields = self.config.extractors.get(table_name, [])
            if not self.form_filler.fill_mandatory_fields(table_name):
                results[table_name] = False
                continue

            if extractor_fields and not self.form_filler.fill_dynamic_fields(extractor_fields):
                results[table_name] = False
                continue
            
            Logger.info("[SKIP] Commit button skipped during testing")
                
            results[table_name] = True
            Logger.success(f"Table {table_name} processed")
            
            Logger.plain("Process will stop after this table because commit is skipped.")
            break 
        return results
    
    # ! FUNC WITH CLICK COMMIT BUTTON
    # def process(self) -> Dict[str, bool]:
    #     """Execute report processing with commit."""
    #     Logger.info("Starting Report Mode Processing")
    #     results = {}
    #     for i, table_name in enumerate(self.config.tables):
    #         self.form_filler.reset_extractor_cache()
    #         if i == 0:
    #             command = f"EXT.REPORT,INP {table_name}"
    #             if not self.banner_handler.execute_command(command):
    #                 results[table_name] = False
    #                 continue
    #         extractor_fields = self.config.extractors.get(table_name, [])
            
    #         if not self.form_filler.fill_mandatory_fields(table_name):
    #             results[table_name] = False
    #             continue
            
    #         if extractor_fields and not self.form_filler.fill_dynamic_fields(extractor_fields):
    #             results[table_name] = False
    #             continue
            
    #         if not self.commit_handler.execute_commit():
    #             results[table_name] = False
    #             continue
            
    #         results[table_name] = True
    #         Logger.success(f"Processed table: {table_name}\n")
    #         if i < len(self.config.tables) - 1:
    #             next_table = self.config.tables[i + 1]
    #             if not self.transaction_handler.input_transaction(next_table):
    #                 break    
    #     return results

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

class DfeMappingProcessor:
    """Orchestrates the DFE.MAPPING workflow using a high-performance filler."""
    
    def __init__(self, driver, wait, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.config = config
        self.utils = PageUtils(driver, wait)
        self.banner_handler = BannerFrameHandler(driver, wait)
        self.form_filler = DfeMappingFormFiller(driver, wait, self.utils, config)
        self.transaction_handler = TransactionInputHandler(driver, wait)
        self.commit_handler = CommitHandler(driver, wait)

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
        Executes a test run for DFE Mapping on the first table without committing.
        Utilizes the batched method for a fast and accurate test.
        """
        Logger.info("Starting DFE Mapping Mode (NO COMMIT / TEST RUN)")
        results = {}
        if not self.config.tables:
            Logger.warning("No tables configured for DFE Mapping.")
            return {}

        table_name = self.config.tables[0]
        self.form_filler.reset_cache()
        
        command = f"DFE.MAPPING, {table_name}"
        if not self.banner_handler.execute_command(command):
            results[table_name] = False
            return results

        if not self._switch_to_main_frame():
            results[table_name] = False
            return results

        is_successful = True
        if not self.form_filler.fill_mandatory_fields(table_name):
            is_successful = False

        extractor_fields = self.config.extractors.get(table_name, [])
        if is_successful and extractor_fields:
            if not self.form_filler.fill_dynamic_fields_batched(extractor_fields):
                is_successful = False
        
        results[table_name] = is_successful
        if is_successful:
            Logger.info("[SKIP] Commit button skipped during test run.")
            Logger.success(f"Table '{table_name}' processed successfully (simulation).")
        else:
            Logger.error(f"Processing failed for table '{table_name}'.")
        return results
    
    # ! FUNC WITH CLICK COMMIT BUTTON
    # def process(self) -> Dict[str, bool]:
    #     """
    #     Execute DFE Mapping processing with commit, utilizing the batched
    #     method for optimal performance on all browsers.
    #     """
    #     Logger.info("Starting DFE Map Mode Processing (Commit Enabled)")
    #     results = {}
    #     total_tables = len(self.config.tables)
    #     for i, table_name in enumerate(self.config.tables):
    #         self.form_filler.reset_cache()
    #         Logger.plain("-" * 50)
    #         Logger.info(f"Processing table {i+1}/{total_tables}: {table_name}")
    #         if i == 0:
    #             command = f"DFE.MAPPING, {table_name}"
    #             if not self.banner_handler.execute_command(command):
    #                 results[table_name] = False
    #                 Logger.error(f"Initial command failed for {table_name}. Aborting process.")
    #                 break
    #         if not self._switch_to_main_frame():
    #             results[table_name] = False
    #             Logger.error(f"Failed to find form frame for {table_name}. Aborting.")
    #             break
    #         extractor_fields = self.config.extractors.get(table_name, [])
    #         if not self.form_filler.fill_mandatory_fields(table_name):
    #             results[table_name] = False
    #             continue
    #         if extractor_fields and not self.form_filler.fill_dynamic_fields_batched(extractor_fields):
    #             results[table_name] = False
    #             continue
    #         if not self.commit_handler.execute_commit():
    #             results[table_name] = False
    #             Logger.error(f"Commit failed for {table_name}. Aborting process.")
    #             break
    #         results[table_name] = True
    #         Logger.success(f"Successfully processed table: {table_name}\n")
    #         if i < len(self.config.tables) - 1:
    #             next_table = self.config.tables[i + 1]
    #             if not self.transaction_handler.input_transaction(next_table):
    #                 Logger.error(f"Failed to load next table: {next_table}. Aborting.")
    #                 break
    #     return results