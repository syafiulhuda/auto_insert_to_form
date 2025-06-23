from core.logger import Logger
from config.config_manager import AppConfig
from core.page_utils import PageUtils
from core.banner_handler import BannerFrameHandler
from core.commit_handler import CommitHandler
from core.transaction_handler import TransactionInputHandler

from core.form_filler import BatchFormFiller_SBII, BatchFormFiller_KALSEL, BatchFormFiller_BJI, BatchFormFiller_JAMBI
from core.form_filler import ReportFormFiller
from core.form_filler import DfeParamFormFiller
from core.form_filler import DfeMappingFormFiller

from typing import Dict

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC


class BatchProcessor:
    """Orchestrates batch processing workflow"""
    
    def __init__(self, driver, wait, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.config = config
        self.utils = PageUtils(driver, wait)
        self.banner_handler = BannerFrameHandler(driver, wait)
        self.commit_handler = CommitHandler(driver, wait)

        # --- New: Select the correct FormFiller based on batch_version ---
        filler_map = {
            "sbii": BatchFormFiller_SBII,
            "bji": BatchFormFiller_BJI,
            "kalsel": BatchFormFiller_KALSEL,
            "jambi": BatchFormFiller_JAMBI,
        }
        # ? FillerClass = filler_map.get(config.batch_version, BatchFormFiller_SBII) # Default to SBII
        FillerClass = filler_map.get(config.batch_version)
        if not FillerClass:
            # Jika versi tidak valid atau None, hentikan program dengan error yang jelas
            raise ValueError(f"Versi batch '{config.batch_version} 'tidak valid atau tidak diatur dalam config. Program tidak dapat melanjutkan.")
        
        self.form_filler = FillerClass(driver, wait, self.utils, config)
        Logger.info(f"BatchProcessor initialized with {FillerClass.__name__}")

    # ! FUNC WITHOUT CLICK COMMIT BUTTON
    def process(self) -> bool:
        """Execute batch processing without commit (for testing)"""
        Logger.info("Starting Batch Mode (Commit disabled)")
        try:
            # command = f"BATCH, BNK/JIARSI.EXT.AFTER.COB"
            command = f"BATCH, BNK/BATCH.TEST.AUTO.NEW"
            if not self.banner_handler.execute_command(command):
                Logger.error("Command execution failed")
                return False

            # Wait for form elements
            try:
                self.wait.until(EC.visibility_of_element_located((By.ID, "datagrid_JOB.NAME")))
            except Exception:
                Logger.warning("Using fallback form container detection")
                self.wait.until(EC.visibility_of_element_located((By.ID, "contract_screen_div")))
            
            # Execute form filling
            success = self.form_filler.execute_filling_process()
            if success:
                Logger.success("Form filling completed (Commit disabled)")
            return success
        except Exception as e:
            Logger.error(f"Batch processing failed: {e}")
            return False

    # ! FUNC WITH CLICK COMMIT BUTTON
    # def process(self) -> bool:
    #     """Execute batch processing with commit (for production)"""
    #     Logger.info("Starting Batch Mode (Commit Enabled)")
    #     try:
    #         command = f"BATCH, BNK/BATCH.TEST.AUTO"
    #         if not self.banner_handler.execute_command(command):
    #             Logger.error("Command execution failed")
    #             return False

    #         # Wait for form elements
    #         try:
    #             self.wait.until(EC.visibility_of_element_located((By.ID, "datagrid_JOB.NAME")))
    #         except Exception:
    #             Logger.warning("Using fallback form container detection")
    #             self.wait.until(EC.visibility_of_element_located((By.ID, "contract_screen_div")))
            
    #         # Execute form filling
    #         success = self.form_filler.execute_filling_process()
    #         if success:
    #             if not self.commit_handler.execute_commit():
    #                 return False
    #             Logger.success("Batch processing completed")
    #         return success
    #     except Exception as e:
    #         Logger.error(f"Batch processing failed: {e}")
    #         return False

# ===================================================================
# CLASS: Report Processor
# ===================================================================
class ReportProcessor:
    """Orchestrates report processing workflow"""
    
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
        """Execute report processing without commit"""
        Logger.info("Starting Report Mode Processing")
        results = {}

        for i, table_name in enumerate(self.config.tables):
            self.form_filler.reset_extractor_cache()

            # Initial command for first table
            if i == 0:
                command = f"EXT.REPORT,INP {table_name}"
                if not self.banner_handler.execute_command(command):
                    results[table_name] = False
                    continue
                
            # Process current table
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
    #     """Execute report processing with commit"""
    #     Logger.info("Starting Report Mode Processing")
    #     results = {}
    #     for i, table_name in enumerate(self.config.tables):
    #         self.form_filler.reset_extractor_cache()

    #         # Initial command for first table
    #         if i == 0:
    #             command = f"EXT.REPORT,INP {table_name}"
    #             if not self.banner_handler.execute_command(command):
    #                 results[table_name] = False
    #                 continue
                
    #         # Process current table
    #         extractor_fields = self.config.extractors.get(table_name, [])
    #         if not self.form_filler.fill_mandatory_fields(table_name):
    #             results[table_name] = False
    #             continue
                
    #         if extractor_fields and not self.form_filler.fill_dynamic_fields(extractor_fields):
    #             results[table_name] = False
    #             continue
            
    #         # Commit current form
    #         if not self.commit_handler.execute_commit():
    #             results[table_name] = False
    #             continue

    #         results[table_name] = True
    #         Logger.success(f"Processed table: {table_name}\n")
            
    #         # Prepare next transaction if applicable
    #         if i < len(self.config.tables) - 1:
    #             next_table = self.config.tables[i + 1]
    #             if not self.transaction_handler.input_transaction(next_table):
    #                 break    
    #     return results

# ===================================================================
# CLASS: DFE Param Processor
# ===================================================================
class DfeParamProcessor:
    """Orchestrates DFE.MAPPING processing workflow"""
    
    def __init__(self, driver, wait, config: AppConfig):
        self.driver = driver
        self.wait = wait
        self.config = config
        self.banner_handler = BannerFrameHandler(driver, wait)
        self.form_filler = DfeParamFormFiller(driver, wait, PageUtils(driver, wait))
        self.transaction_handler = TransactionInputHandler(driver, wait)
        self.commit_handler = CommitHandler(driver, wait)

    # ! FUNC WITHOUT CLICK COMMIT BUTTON (use in PROD ENV)
    def process(self) -> Dict[str, bool]:
        """Execute DFE processing WITHOUT commit for testing"""
        Logger.info("Starting DFE Mode Processing (NO COMMIT)")
        results = {}
        total_tables = len(self.config.tables)

        for i, table_name in enumerate(self.config.tables):
            Logger.plain("-" * 50)
            Logger.info(f"Processing DFE table {i+1}/{total_tables}: {table_name}")

            # Only run the initial command for the first item
            if i == 0:
                command = f"DFE.PARAMETER, {table_name}"
                if not self.banner_handler.execute_command(command):
                    results[table_name] = False
                    Logger.error("Initial command failed. Aborting process.")
                    break 
            
            # Filling Mandatory field
            if not self.form_filler.fill_form(table_name):
                results[table_name] = False
                Logger.error(f"Form filling failed for {table_name}.")
                continue

            # Skip commit step
            Logger.info("[SKIP] Commit button skipped for testing.")
            results[table_name] = True
            Logger.success(f"Successfully filled DFE form for table: {table_name}")
            
            # Stopped after the first item because the commit was skipped
            Logger.plain("Process will stop after this table because commit is skipped.")
            break      
        return results

    # ! FUNC WITH CLICK COMMIT BUTTON (use in PROD)
    # def process(self) -> Dict[str, bool]:
    #     """Execute DFE processing WITH commit"""
    #     Logger.info("Starting DFE Mode Processing")
    #     results = {}
    #     total_tables = len(self.config.tables)

    #     for i, table_name in enumerate(self.config.tables):
    #         Logger.plain("-" * 50)
    #         Logger.info(f"Processing DFE table {i+1}/{total_tables}: {table_name}")

    #         # For the first table, execute the initial command to open the form
    #         if i == 0:
    #             # Command format is "DFE.PARAMETER, TABLE.NAME"
    #             command = f"DFE.PARAMETER, {table_name}"
    #             if not self.banner_handler.execute_command(command):
    #                 results[table_name] = False
    #                 # If the first command fails, no point in continuing
    #                 Logger.error("Initial command failed. Aborting process.")
    #                 break 
            
    #         # Fill the main DFE form
    #         if not self.form_filler.fill_form(table_name):
    #             results[table_name] = False
    #             # If filling fails, we might not be able to continue reliably
    #             Logger.error(f"Form filling failed for {table_name}. Attempting to continue...")
    #             continue

    #         # Commit the current form
    #         if not self.commit_handler.execute_commit():
    #             results[table_name] = False
    #             Logger.error(f"Commit failed for {table_name}. Aborting process.")
    #             break # If commit fails, subsequent operations will likely fail too

    #         results[table_name] = True
    #         Logger.success(f"Successfully processed DFE table: {table_name}\n")
            
    #         # If there is a next table, input its name to load the next record
    #         if i < total_tables - 1:
    #             next_table = self.config.tables[i + 1]
    #             if not self.transaction_handler.input_transaction(next_table):
    #                 Logger.error(f"Failed to input next transaction ID: {next_table}. Aborting.")
    #                 break      
    #     return results

# ===================================================================
# CLASS: DFE Mapping Processor (Inherits from ReportProcessor)
# ===================================================================
class DfeMappingProcessor(ReportProcessor):
    """
    Orchestrates DFE.MAPPING workflow. Inherits from ReportProcessor.
    """
    def __init__(self, driver, wait, config: AppConfig):
        super().__init__(driver, wait, config)
        self.form_filler = DfeMappingFormFiller(driver, wait, self.utils, config)

    # ! # ! FUNC WITHOUT CLICK COMMIT BUTTON
    def process(self) -> Dict[str, bool]:
        Logger.info("Starting DFE Mapping Mode (NO COMMIT)")
        results = {}
        for i, table_name in enumerate(self.config.tables):
            self.form_filler.reset_extractor_cache()

            command = f"DFE.MAPPING, {table_name}"
            # Gunakan flag untuk melacak status
            is_successful = True

            if not self.banner_handler.execute_command(command):
                is_successful = False
            
            if is_successful and not self.form_filler.fill_mandatory_fields(table_name):
                is_successful = False

            extractor_fields = self.config.extractors.get(table_name, [])
            if is_successful and extractor_fields and not self.form_filler.fill_dynamic_fields(extractor_fields):
                is_successful = False
            
            # Catat hasil akhir berdasarkan flag
            if is_successful:
                results[table_name] = True
                Logger.info("[SKIP] Commit button skipped during testing")
                Logger.success(f"Table {table_name} processed successfully (simulation).")
            else:
                results[table_name] = False
                Logger.error(f"Processing failed for table {table_name}.")

            Logger.plain("Process will stop after this table because commit is skipped.")
            break 
        return results
    
    # ! FUNC WITH CLICK COMMIT BUTTON
    # def process(self) -> Dict[str, bool]:
    #     """Execute DFE Mapping processing with commit"""
    #     Logger.info("Starting DFE Map Mode Processing")
    #     results = {}
    #     for i, table_name in enumerate(self.config.tables):
    #         self.form_filler.reset_extractor_cache()

    #         # Initial command for first table
    #         if i == 0:
    #             command = f"DFE.MAPPING, {table_name}"
    #             if not self.banner_handler.execute_command(command):
    #                 results[table_name] = False
    #                 continue
                
    #         # Process current table
    #         extractor_fields = self.config.extractors.get(table_name, [])
    #         if not self.form_filler.fill_mandatory_fields(table_name):
    #             results[table_name] = False
    #             continue
                
    #         if extractor_fields and not self.form_filler.fill_dynamic_fields(extractor_fields):
    #             results[table_name] = False
    #             continue
            
    #         # Commit current form
    #         if not self.commit_handler.execute_commit():
    #             results[table_name] = False
    #             continue

    #         results[table_name] = True
    #         Logger.success(f"Processed table: {table_name}\n")
            
    #         # Prepare next transaction if applicable
    #         if i < len(self.config.tables) - 1:
    #             next_table = self.config.tables[i + 1]
    #             if not self.transaction_handler.input_transaction(next_table):
    #                 break
    #     return results