from core.logger import Logger
from typing import Dict, List, Tuple, Union

class DataManager:
    """Handles data loading operations from external files."""

    @staticmethod
    def load_batch_commands_and_tables(file_path: str) -> List[Tuple[str, List[str]]]:
        """
        Loads a sequence of batch commands and their corresponding table lists from a file.
        The file format uses [Command] as a header for each section.
        """
        batch_jobs = []
        current_command = None
        current_tables = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    stripped_line = line.strip()
                    # Ignore empty lines or lines that are comments.
                    if not stripped_line or stripped_line.startswith(';'):
                        continue

                    # Detect a new command section (e.g., [BATCH, ...])
                    if stripped_line.startswith("[") and stripped_line.endswith("]"):
                        # If we were already processing a command, save it before starting a new one.
                        if current_command and current_tables:
                            batch_jobs.append((current_command, current_tables))
                        
                        # Start the new command section.
                        current_command = f"BATCH, {stripped_line[1:-1].strip()}"
                        current_tables = []
                    # Add the line as a table only if a command section is active.
                    elif current_command is not None:
                        current_tables.append(stripped_line)
                    else:
                        # This occurs if there is table data before the first [COMMAND] header.
                        Logger.warning(f"Ignoring line {line_num} ('{stripped_line}') because it appears before any active [Command] header.")
        
            # Add the last processed command and its tables after the loop finishes.
            if current_command and current_tables:
                batch_jobs.append((current_command, current_tables))

            Logger.info(f"Loaded {len(batch_jobs)} batch jobs from {file_path}")
            return batch_jobs

        except FileNotFoundError:
            Logger.error(f"batch source file not found: {file_path}")
            return []
        except Exception as e:
            Logger.error(f"Failed to load batch data: {e}")
            return []

    @staticmethod
    def load_extractor_data(file_path: str) -> Tuple[List[str], Dict[str, List[str]]]:
        """Loads extractor configuration (table-to-field mapping) from an INI-like format."""
        ordered_tables = []
        extractors_dict = {}
        current_table = None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';') or line.startswith('#'):
                        continue

                    if line.startswith("[") and line.endswith("]"):
                        current_table = line[1:-1].strip()
                        if current_table and current_table not in extractors_dict:
                            ordered_tables.append(current_table)
                            extractors_dict[current_table] = []
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
        """Loads DFE parameter data (a simple list of tables)."""
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
        """Loads DFE mapping data, which follows an INI-like format."""
        ordered_tables = []
        extractors_dict = {}
        current_table = None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';') or line.startswith('#'):
                        continue

                    if line.startswith("[") and line.endswith("]"):
                        current_table = line[1:-1].strip()
                        if current_table and current_table not in extractors_dict:
                            ordered_tables.append(current_table)
                            extractors_dict[current_table] = []
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