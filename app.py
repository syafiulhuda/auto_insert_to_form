import traceback
from core.logger import Logger
from config.config_manager import AppConfig
from core.webdriver_manager import WebDriverManager
from core.authentication import AuthenticationService
from core.page_utils import PageUtils
from core.data_manager import DataManager

from processing.table_processor import BatchProcessor, PipelineProcessor
from processing.table_processor import ReportProcessor
from processing.table_processor import DfeParamProcessor
from processing.table_processor import DfeMappingProcessor

import os
import time
import configparser
import getpass


class AutomatApp:
    """The main application class that orchestrates the entire process."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.driver_manager = WebDriverManager(config)

    def run(self):
        """The main execution flow: initialize, login, process, and cleanup."""
        start_time = time.time()
        results = {}

        try:
            self.driver_manager.initialize()
            driver, wait = self.driver_manager.get_driver_and_wait()
            
            if not AuthenticationService(driver, wait, self.config).login():
                raise Exception("Login aborted.")

            # Map the selected mode string to its corresponding Processor class.
            processor_map = {
                "batch": BatchProcessor,
                "report": ReportProcessor,
                "parameter": DfeParamProcessor,
                "mapping": DfeMappingProcessor,
                "pipeline": PipelineProcessor,
            }

            processor_class = processor_map.get(self.config.mode)
            if not processor_class:
                Logger.error(f"Unknown mode: {self.config.mode}")
            else:
                # Instantiate the chosen processor.
                processor = processor_class(driver, wait, self.config)
                
                # Determine which process method to call based on user's commit choice.
                result = None
                commit_is_enabled = getattr(self.config, 'commit_enabled', False)

                if commit_is_enabled and hasattr(processor, 'process_with_commit'):
                    Logger.info(f"Executing {self.config.mode.title()} Mode WITH COMMIT.")
                    result = processor.process_with_commit()
                else:
                    Logger.info(f"Executing {self.config.mode.title()} Mode WITHOUT COMMIT (Test Mode).")
                    result = processor.process()

                key = self.config.mode.upper()
                if isinstance(result, bool):
                    results[key] = result
                elif isinstance(result, dict) and result:
                    results[key] = all(result.values())
                else:
                    # If the process fails midway and returns nothing, consider it a failure.
                    results[key] = False

        except Exception as e:
            Logger.error(f"A fatal error occurred: {e}")
            if self.driver_manager.driver:
                filename = f"{self.config.screenshot_dir}/error_{int(time.time())}.png"
                PageUtils(self.driver_manager.driver, self.driver_manager.wait).take_screenshot(filename)
                traceback.print_exc()

        finally:
            self._log_summary(results, start_time)
            input("\nPress ENTER to close browser...")
            self.driver_manager.quit()

    def _log_summary(self, results: dict, start_time: float):
        """Logs a summary of the execution results."""
        success_count = sum(1 for v in results.values() if v)
        failure_count = len(results) - success_count
        duration = time.time() - start_time

        Logger.plain("\n" + "=" * 50)
        Logger.plain("EXECUTION SUMMARY".center(50))
        Logger.plain("=" * 50)
        Logger.info(f"Total tasks processed: {len(results)}")
        Logger.success(f"Successful tasks: {success_count}")
        Logger.error(f"Failed tasks: {failure_count}")
        Logger.info(f"Total duration: {int(duration // 60)}m {int(duration % 60)}s")
        Logger.plain("=" * 50)

def main():
    """The main entry point of the script with user interaction."""
    
    # --- 1. Pemilihan Mode Eksekusi ---
    mode_map = {
        "1": "batch",
        "2": "report",
        "3": "parameter",
        "4": "mapping",
        "5": "pipeline"
    }
    print("\nSelect execution mode:")
    print("1. Batch Mode")
    print("2. EXT Report Mode")
    print("3. DFE Parameter Mode")
    print("4. DFE Map Mode")
    print("5. Full Cycle (Dynamic Pipeline)")
    
    mode_choice = input("Choice: ").strip()
    mode = mode_map.get(mode_choice)
    if not mode:
        Logger.error("Invalid mode selected. Exiting.")
        return
    
    # --- 2. Inisialisasi Variabel ---
    config = None
    batch_version = None

    print("\nSelect browser:\n1. Chrome (default)\n2. Firefox")
    browser = "firefox" if input("Choice [1/2]: ").strip() == "2" else "chrome"

    # --- 3. Logika Pemuatan Konfigurasi Sesuai Mode ---
    if mode == 'pipeline':
        Logger.info("Pipeline mode selected.")
        
        batch_version_map = {"1": "sbii", "2": "bji", "3": "kalsel", "4": "jamkrindo", "5": "jambi"}
        print("\nSelect target Batch Version for the pipeline:")
        print("1. SBII\n2. BJI\n3. KALSEL\n4. JAMKRINDO\n5. JAMBI")
        version_choice = input(f"Choice [{'/'.join(batch_version_map.keys())}]: ").strip()
        batch_version = batch_version_map.get(version_choice)
        if not batch_version:
            Logger.error(f"Invalid batch version '{version_choice}'. Exiting.")
            return
        
        try:
            if batch_version == 'jambi':
                Logger.info("JAMBI version selected. Loading Report and Batch configurations...")
                report_config = AppConfig.from_config_file("ext_report_config.ini", "report")
                batch_config_for_jambi = AppConfig.from_config_file("batch_config.ini", "batch")
                
                config = report_config
                config.mode = 'pipeline'
                config.report_config = report_config
                config.batch_config = batch_config_for_jambi
                
                config.report_config.tables, config.report_config.extractors = DataManager.load_extractor_data(report_config.file_path)
                config.batch_config.batch_jobs = DataManager.load_batch_commands_and_tables(batch_config_for_jambi.file_path)
                
            else: 
                Logger.info("Standard pipeline selected. Loading all related configurations...")
                param_config = AppConfig.from_config_file("dfe_parameter_config.ini", "parameter")
                mapping_config = AppConfig.from_config_file("dfe_mapping_config.ini", "mapping")
                batch_config_std = AppConfig.from_config_file("batch_config.ini", "batch")
                
                config = param_config
                config.mode = 'pipeline'
                config.param_config = param_config
                config.mapping_config = mapping_config
                config.batch_config = batch_config_std
                
                config.param_config.tables = DataManager.load_dfe_params_data(param_config.file_path)
                config.mapping_config.tables, config.mapping_config.extractors = DataManager.load_dfe_map_data(mapping_config.file_path)
                config.batch_config.batch_jobs = DataManager.load_batch_commands_and_tables(batch_config_std.file_path)

            if hasattr(config, 'batch_config'):
                config.batch_config.batch_version = batch_version
            
            print("\nEnable Commit Mode for the ENTIRE pipeline?")
            commit_choice = input("Enter 'yes' to enable commit for all stages: ").strip().lower()
            if commit_choice == 'yes':
                config.commit_enabled = True

        except Exception as e:
            Logger.error(f"Failed to load one or more configuration files for the pipeline: {e}")
            return
            
    else:  # Logika untuk mode individual
        config_files = {
            "batch": "batch_config.ini",
            "report": "ext_report_config.ini",
            "parameter": "dfe_parameter_config.ini",
            "mapping": "dfe_mapping_config.ini",
        }
        config_file = config_files[mode]
        
        if not os.path.exists(config_file):
            Logger.info(f"Config file not found. Creating default: {config_file}")
            default_config = configparser.ConfigParser()
            default_password_placeholder = "MASUKKAN_PASSWORD_DISINI"
            default_config['WEB'] = {'url': 'http://enter.your.url/here', 'username': 'YourUsername', 'password': default_password_placeholder}
            default_config['PATHS'] = {'file_path': 'path/to/your/datafile.txt', 'screenshot_dir': 'screenshots', 'inspect_dir': 'inspect'}
            default_config['SETTINGS'] = {'timeout': '15', 'headless': 'False'}
            with open(config_file, 'w') as f:
                default_config.write(f)

            print("-" * 60)
            print(f"ACTION REQUIRED: Please edit the new '{config_file}' with your details and restart.")
            print("-" * 60)
            input("Press ENTER to exit.")
            return
            
        config = AppConfig.from_config_file(config_file, mode)

        if mode == "batch":
            batch_version_map = {"1": "sbii", "2": "bji", "3": "kalsel", "4": "jamkrindo", "5": "jambi"}
            print("\nSelect Batch Version:")
            print("1. SBII\n2. BJI\n3. KALSEL\n4. JAMKRINDO\n5. JAMBI")
            version_choice = input(f"Choice [{'/'.join(batch_version_map.keys())}]: ").strip()
            batch_version = batch_version_map.get(version_choice)
            if not batch_version:
                Logger.error(f"Invalid batch version '{version_choice}'. Exiting.")
                return
        
        print(f"\nEnable Commit Mode for {mode.replace('_', ' ').title()} Mode?")
        commit_choice = input("Enter 'yes' to enable commit, otherwise it will run in test mode: ").strip().lower()
        if commit_choice == 'yes':
            config.commit_enabled = True

        if mode == "batch":
            config.batch_jobs = DataManager.load_batch_commands_and_tables(config.file_path)
            if not config.batch_jobs:
                Logger.error(f"No batch jobs loaded from {config.file_path}.")
                return
        else:
            if mode in ["report", "mapping"]:
                config.tables, config.extractors = DataManager.load_extractor_data(config.file_path)
            else: # parameter
                config.tables = DataManager.load_dfe_params_data(config.file_path)

            if not config.tables:
                Logger.error(f"No data loaded from {config.file_path} for mode: {mode}")
                return

    # --- 4. Validasi & Persiapan Akhir ---
    config.browser_choice = browser
    if batch_version:
        config.batch_version = batch_version

    os.makedirs(config.screenshot_dir, exist_ok=True)
    os.makedirs(config.inspect_dir, exist_ok=True)
    
    default_password_placeholder = "MASUKKAN_PASSWORD_DISINI"
    if config.password == default_password_placeholder:
        Logger.error(f"Password not configured in the corresponding .ini file.")
        Logger.error("Please edit the password field under the [WEB] section and restart.")
        input("Press ENTER to exit.")
        return

    # --- 5. Menjalankan Aplikasi Utama ---
    app = AutomatApp(config)
    app.run()

if __name__ == "__main__":
    main()