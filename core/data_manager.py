from core.logger import Logger
from typing import Dict, List, Tuple, Union

class DataManager:
    """Handles data loading operations"""
    
    @staticmethod
    def load_batch_tables(file_path: str) -> List[str]:
        """Load batch table names from file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            Logger.error(f"Batch source file not found: {file_path}")
            return []
        except Exception as e:
            Logger.error(f"Failed to load batch data: {e}")
            return []

    @staticmethod
    def load_extractor_data(file_path: str) -> Tuple[List[str], Dict[str, List[str]]]:
        """Load extractor configuration with table/field mapping"""
        ordered_tables = []
        extractors_dict = {}
        current_table = None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith(';') or line.startswith('#'):
                        continue

                    # Table header detection
                    if line.startswith("[") and line.endswith("]"):
                        current_table = line[1:-1].strip()
                        if current_table and current_table not in extractors_dict:
                            ordered_tables.append(current_table)
                            extractors_dict[current_table] = []
                    # Field entry under current table
                    elif current_table:
                        extractors_dict[current_table].append(line)
            
            Logger.info(f"Loaded {len(ordered_tables)} tables from {file_path}")
            return ordered_tables, extractors_dict

        except FileNotFoundError:
            Logger.error(f"Extractor source file not found: {file_path}")
            return [], {}
        except Exception as e:
            Logger.error(f"Failed to load extractor data: {e}")
            return [], {}
        
    @staticmethod
    def load_dfe_params_data(file_path: str) -> List[str]:
        """Load DFE parameter data (simple list of tables)."""
        tables = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith(';') and not line.startswith('#'):
                        tables.append(line)
            Logger.info(f"Loaded {len(tables)} DFE tables from {file_path}")
            return tables
        except FileNotFoundError:
            Logger.error(f"DFE parameter file not found: {file_path}")
            return []
        except Exception as e:
            Logger.error(f"Failed to load DFE parameter data: {e}")
            return []

    @staticmethod
    def load_dfe_map_data(file_path: str) -> Tuple[List[str], Dict[str, List[str]]]:
        """Load extractor configuration with table/field mapping"""
        ordered_tables = []
        extractors_dict = {}
        current_table = None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith(';') or line.startswith('#'):
                        continue

                    # Table header detection
                    if line.startswith("[") and line.endswith("]"):
                        current_table = line[1:-1].strip()
                        if current_table and current_table not in extractors_dict:
                            ordered_tables.append(current_table)
                            extractors_dict[current_table] = []
                    # Field entry under current table
                    elif current_table:
                        extractors_dict[current_table].append(line)
            
            Logger.info(f"Loaded {len(ordered_tables)} tables from {file_path}")
            return ordered_tables, extractors_dict

        except FileNotFoundError:
            Logger.error(f"Extractor source file not found: {file_path}")
            return [], {}
        except Exception as e:
            Logger.error(f"Failed to load extractor data: {e}")
            return [], {}