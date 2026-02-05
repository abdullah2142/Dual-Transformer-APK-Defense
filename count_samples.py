import pandas as pd
import os
import glob

def count_items_in_json_dataset(json_file_path):
    """
    Attempts to count the number of records in a JSON dataset file.
    It tries reading the file as JSON Lines first (efficient) and falls back
    to reading as a single JSON array if the first attempt fails.

    Args:
        json_file_path (str): The path to the JSON file.

    Returns:
        int: The number of rows (records) found, or -1 if the file is invalid or not found.
    """
    if not os.path.exists(json_file_path):
        print(f"Error: File not found at {json_file_path}")
        return -1

    try:
        # --- Attempt 1: Read as JSON Lines (most common for large datasets) ---
        df = pd.read_json(json_file_path, lines=True)
        print("Success! File read as JSON Lines (one record per line).")
        return len(df)
        
    except ValueError:
        # If JSON Lines fails (e.g., file is a single array)
        try:
            # --- Attempt 2: Read as a single JSON Array/Object ---
            df = pd.read_json(json_file_path, lines=False)
            print("Success! File read as a single JSON Array/Object.")
            return len(df)
            
        except Exception as e:
            print(f"Error: File could not be parsed as JSON Lines or single JSON Array.")
            print(f"Details: {e}")
            return -1
            
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return -1


# --- Configuration ---
# Replace with the actual path to your unified JSON dataset file
dataset_path = 'C:\\Users\\Abdullah\\Downloads\\LVDAndro_APKs_Combined_Processed\\lvdandro_windowed.json' 
# --- End Configuration ---

# --- Run Count ---
num_rows = count_items_in_json_dataset(dataset_path)

if num_rows > 0:
    print(f"\nTotal number of items (rows) in the dataset: {num_rows}")
elif num_rows == 0:
    print("\nDataset loaded successfully, but it contains 0 items.")