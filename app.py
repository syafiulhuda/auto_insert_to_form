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
    """Main application controller"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.driver_manager = WebDriverManager(config)

    def run(self):
        """Main execution flow"""
        start_time = time.time()
        results = {}

        try:
            self.driver_manager.initialize()
            driver, wait = self.driver_manager.get_driver_and_wait()
            if not AuthenticationService(driver, wait, self.config).login():
                raise Exception("Login aborted")

            # Map mode to processor class
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
                processor = processor_class(driver, wait, self.config)
                result = processor.process()
                key = self.config.mode.upper()
                results[key] = result if isinstance(result, bool) else all(result.values())

        except Exception as e:
            Logger.error(f"Fatal error: {e}")
            if self.driver_manager.driver:
                filename = f"{self.config.screenshot_dir}/error_{int(time.time())}.png"
                PageUtils(self.driver_manager.driver, self.driver_manager.wait).take_screenshot(filename)

        finally:
            self._log_summary(results, start_time)
            input("\nPress ENTER to close browser")
            self.driver_manager.quit()

    def _log_summary(self, results: dict, start_time: float):
        """Log execution summary"""
        success_count = sum(1 for success in results.values() if success)
        failure_count = len(results) - success_count
        duration = time.time() - start_time

        Logger.plain("\n" + "=" * 50)
        Logger.plain("EXECUTION SUMMARY".center(50))
        Logger.plain("=" * 50)
        Logger.info(f"Total processed: {len(results)}")
        Logger.success(f"Success: {success_count}")
        Logger.error(f"Failures: {failure_count}")
        Logger.info(f"Duration: {int(duration // 60)}m {int(duration % 60)}s")
        Logger.plain("=" * 50)

def main():
    """Entry point with user interaction"""
    mode_map = {
        "1": "batch",
        "2": "report",
        "3": "parameter",
        "4": "mapping",
    }

    print("\nSelect execution mode:")
    print("1. Batch Mode\n2. Report Mode\n3. DFE Parameter Mode\n4. DFE Map Mode")
    mode_choice = input("Choice: ").strip()
    mode = mode_map.get(mode_choice, "mapping")
    
    # ? batch_version = "sbii"
    batch_version = None
    if mode == "batch":
        batch_version_map = {
            "1": "sbii",
            "2": "bji",
            "3": "kalsel",
            "4": "jambi"
        }
        print("\nSelect Batch Version:")
        print("1. SBII\n2. BJI\n3. KALSEL\n4. JAMBI")
        version_choice = input("Choice [1/2/3/4]: ").strip()
        # ? batch_version = batch_version_map.get(version_choice, "sbii")
        if version_choice not in batch_version_map:
            Logger.error(f"Pilihan versi '{version_choice}' tidak valid. Program akan berhenti.")
            return
        batch_version = batch_version_map[version_choice]

    config_files = {
        "batch": "batch_config.ini",
        "report": "ext_report_config.ini",
        "parameter": "dfe_parameter_config.ini",
        "mapping": "dfe_mapping_config.ini",
    }
    config_file = config_files[mode]

    # Create default config if missing
    if not os.path.exists(config_file):
        Logger.info(f"Creating default config: {config_file}")
        config = configparser.ConfigParser()
        config.add_section('COMMENT')
        config.set('COMMENT', '; Edit this file for configuration changes', '')
        config['WEB'] = {'url': 'Masukkan URL', 'username': 'T24 Username', 'password': ''}
        config['PATHS'] = {'file_path': 'path/your_file', 'screenshot_dir': 'screenshots', 'inspect_dir': 'inspect'}
        config['SETTINGS'] = {'timeout': '15', 'headless': 'False'}
        with open(config_file, 'w') as f: config.write(f)

        print("-" * 60)
        print(f"ACTION: Edit '{config_file}' and restart application")
        print("-" * 60)
        input("Press ENTER to exit")
        return

    # Browser selection
    print("\nSelect browser:\n1. Chrome (default)\n2. Firefox")
    browser = "firefox" if input("Choice [1/2]: ").strip() == "2" else "chrome"

    config = AppConfig.from_config_file(config_file, mode)
    config.browser_choice = browser
    config.batch_version = batch_version # Set the chosen batch version

    if not config.file_path:
        Logger.error(f"Missing 'file_path' in config: {config_file}")
        return

    # Load data per mode
    data_loaders = {
        "batch": lambda: setattr(config, 'tables', DataManager.load_batch_tables(config.file_path)),
        "report": lambda: (lambda x: (setattr(config, 'tables', x[0]), setattr(config, 'extractors', x[1])))(DataManager.load_extractor_data(config.file_path)),
        "parameter": lambda: setattr(config, 'tables', DataManager.load_dfe_params_data(config.file_path)),
        "mapping": lambda: (lambda x: (setattr(config, 'tables', x[0]), setattr(config, 'extractors', x[1])))(DataManager.load_dfe_map_data(config.file_path)),
    }
    data_loaders[mode]()

    if not config.tables:
        Logger.error(f"No data loaded from {config.file_path} for mode: {mode}")
        return

    os.makedirs(config.screenshot_dir, exist_ok=True)
    os.makedirs(config.inspect_dir, exist_ok=True)

    if not config.password:
        config.password = getpass.getpass("T24 Password: ")

    app = AutomatApp(config)
    app.run()

if __name__ == "__main__":
    main()