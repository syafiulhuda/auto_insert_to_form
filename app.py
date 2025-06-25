from core.logger import Logger
from config.config_manager import AppConfig
from core.webdriver_manager import WebDriverManager
from core.authentication import AuthenticationService
from core.page_utils import PageUtils
from core.data_manager import DataManager

from processing.table_processor import BatchProcessor
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
            }

            processor_class = processor_map.get(self.config.mode)
            if not processor_class:
                Logger.error(f"Unknown mode: {self.config.mode}")
            else:
                # Instantiate and run the chosen processor.
                processor = processor_class(driver, wait, self.config)
                result = processor.process()
                key = self.config.mode.upper()
                results[key] = result if isinstance(result, bool) else all(result.values())

        except Exception as e:
            Logger.error(f"A fatal error occurred: {e}")
            if self.driver_manager.driver:
                filename = f"{self.config.screenshot_dir}/error_{int(time.time())}.png"
                PageUtils(self.driver_manager.driver, self.driver_manager.wait).take_screenshot(filename)

        finally:
            self._log_summary(results, start_time)
            input("\nPress ENTER to close browser...")
            self.driver_manager.quit()

    def _log_summary(self, results: dict, start_time: float):
        """Logs a summary of the execution results."""
        success_count = sum(1 for success in results.values() if success)
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
    
    # Map user's numeric choice to a mode string.
    mode_map = {
        "1": "batch",
        "2": "report",
        "3": "parameter",
        "4": "mapping",
    }

    print("\nSelect execution mode:")
    print("1. Batch Mode\n2. Report Mode\n3. DFE Parameter Mode\n4. DFE Map Mode")
    mode_choice = input("Choice: ").strip()
    mode = mode_map.get(mode_choice)
    if not mode:
        Logger.error("Invalid mode selected. Exiting.")
        return
    
    # Get the batch version only if batch mode is selected.
    batch_version = None
    if mode == "batch":
        batch_version_map = {
            "1": "sbii", "2": "bji", "3": "kalsel", "4": "jamkrindo", "5": "jambi"
        }
        print("\nSelect Batch Version:")
        print("1. SBII\n2. BJI\n3. KALSEL\n4. JAMKRINDO\n5. JAMBI")
        version_choice = input(f"Choice [{'/'.join(batch_version_map.keys())}]: ").strip()
        batch_version = batch_version_map.get(version_choice)
        if not batch_version:
            Logger.error(f"Invalid batch version '{version_choice}'. Exiting.")
            return

    # Determine the correct configuration file for the selected mode.
    config_files = {
        "batch": "batch_config.ini",
        "report": "ext_report_config.ini",
        "parameter": "dfe_parameter_config.ini",
        "mapping": "dfe_mapping_config.ini",
    }
    config_file = config_files[mode]

    # If the config file doesn't exist, create a default one and instruct the user.
    if not os.path.exists(config_file):
        Logger.info(f"Config file not found. Creating default: {config_file}")
        config = configparser.ConfigParser()
        config['WEB'] = {'url': 'T24 Url', 'username': 'YourUsername', 'password': 'YourPassword'}
        config['PATHS'] = {'file_path': 'path/to/your/datafile.txt', 'screenshot_dir': 'screenshots', 'inspect_dir': 'inspect'}
        config['SETTINGS'] = {'timeout': '600', 'headless': 'False'}
        with open(config_file, 'w') as f: config.write(f)

        print("-" * 60)
        print(f"ACTION REQUIRED: Please edit the new '{config_file}' with your details and restart.")
        print("-" * 60)
        input("Press ENTER to exit.")
        return

    # Get user input for browser choice.
    print("\nSelect browser:\n1. Chrome (default)\n2. Firefox")
    browser = "firefox" if input("Choice [1/2]: ").strip() == "2" else "chrome"

    # Load the application configuration from the file.
    config = AppConfig.from_config_file(config_file, mode)
    config.browser_choice = browser
    config.batch_version = batch_version

    # Validate that the file_path is configured.
    if not config.file_path:
        Logger.error(f"The 'file_path' is missing in the config file: {config_file}")
        return

    # Load the required data into the config object based on the selected mode.
    if mode == "batch":
        config.batch_jobs = DataManager.load_batch_tables(config.file_path)
        if not config.batch_jobs:
            Logger.error(f"No batch jobs loaded from {config.file_path}.")
            return
    else:
        # Logika pemuatan data untuk mode lain
        data_loaders = {
            "report": lambda: (lambda x: (setattr(config, 'tables', x[0]), setattr(config, 'extractors', x[1])))(DataManager.load_extractor_data(config.file_path)),
            "parameter": lambda: setattr(config, 'tables', DataManager.load_dfe_params_data(config.file_path)),
            "mapping": lambda: (lambda x: (setattr(config, 'tables', x[0]), setattr(config, 'extractors', x[1])))(DataManager.load_dfe_map_data(config.file_path)),
        }
        data_loaders[mode]()
        if not config.tables:
            Logger.error(f"No data loaded from {config.file_path} for mode: {mode}")
            return

    # Create output directories if they don't exist.
    os.makedirs(config.screenshot_dir, exist_ok=True)
    os.makedirs(config.inspect_dir, exist_ok=True)

    # Validate that the password has been filled in the config file.
    if not config.password or config.password == 'YourPassword':
        Logger.error(f"Password not found or not filled in {config_file}.")
        Logger.error("Please fill in the password under the [WEB] section and restart.")
        input("Press ENTER to exit.")
        return

    # Create and run the main application instance.
    app = AutomatApp(config)
    app.run()

if __name__ == "__main__":
    main()