import h5py
import pandas as pd
import json
import os
import numpy as np

# --- CONFIGURATION ---
# List all CWE columns present in your Draper HDF5 file
CWE_COLUMNS = ['CWE-120', 'CWE-119', 'CWE-469', 'CWE-476', 'CWE-other']
OUTPUT_FILE = "draper_dataset.json" # As requested by your query
PROJECT_NAME = "Draper"

def read_draper_hdf5(file_path):
    """
    Reads a single HDF5 file from the Draper dataset, extracts function code,
    and structures the data into the Juliet JSON array format.
    
    Args:
        file_path (str): Path to the HDF5 file.
        
    Returns:
        list: A list of dictionary samples in the target JSON structure.
    """
    if not os.path.exists(file_path):
        print(f"ERROR: HDF5 file not found at {file_path}. Skipping.")
        return []

    print(f"Reading HDF5 file: {file_path}")
    
    source_code = []
    cwe_data = {}
    
    try:
        with h5py.File(file_path, 'r') as hf:
            # 1. Decode the source code from bytes to UTF-8 string
            source_code = [func.decode('utf-8') for func in hf['functionSource'][:]]
            
            # 2. Read all specific CWE flags
            for cwe_id in CWE_COLUMNS:
                if cwe_id in hf:
                    # Store boolean/integer flags for each CWE
                    cwe_data[cwe_id] = hf[cwe_id][:].astype(int) 
                else:
                    print(f"Warning: CWE column '{cwe_id}' not found in {os.path.basename(file_path)}. Filling with 0s.")
                    cwe_data[cwe_id] = np.zeros(len(source_code), dtype=int)
    except OSError as e:
        print(f"CRITICAL ERROR: Unable to open HDF5 file {file_path}. Check permissions or file integrity.")
        print(f"Original System Error: {e}")
        return []


    # 3. Process and Expand Data into Juliet Format (JSON array items)
    juliet_samples = []
    
    for index, func_code in enumerate(source_code):
        is_vulnerable = False
        
        # --- Handle Vulnerable Code (Label=1) ---
        # A function may have multiple CWEs. We create an entry for EACH.
        for cwe_id in CWE_COLUMNS:
            if cwe_data[cwe_id][index] == 1:
                is_vulnerable = True
                
                # Create a unique entry for this specific CWE occurrence
                entry = {
                    # Uses the structure from the Juliet file: filename, method_name, label, CWE_ID, code
                    # The index must be globally unique if combining, but here it's local index
                    "filename": f"{PROJECT_NAME}_{cwe_id}_{os.path.basename(file_path).split('.')[0]}_{index}.c", 
                    "method_name": f"func_{index}",
                    "label": 1, 
                    "CWE_ID": cwe_id, 
                    "code": func_code
                }
                juliet_samples.append(entry)

        # --- Handle Safe Code (Label=0) ---
        # If the function is not marked by any specific CWE, it is safe.
        if not is_vulnerable:
            entry = {
                "filename": f"{PROJECT_NAME}_Safe_{os.path.basename(file_path).split('.')[0]}_{index}.c",
                "method_name": f"func_{index}",
                "label": 0,
                "CWE_ID": "CWE000", # Placeholder for non-vulnerable code
                "code": func_code
            }
            juliet_samples.append(entry)

    return juliet_samples

def save_to_json(data_list, output_path):
    """
    Saves the list of dictionaries as a single JSON array, matching the requested format.
    """
    print(f"\nTotal samples to save: {len(data_list)}")
    print(f"Saving combined dataset to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as outfile:
        # Writes the entire list as a single JSON array with indentation
        json.dump(data_list, outfile, indent=2)
    print("Save complete.")


# This helper function is not needed if you combine the results of read_draper_hdf5 directly.
# def read_and_combine_draper_splits(path_to_draper_folder):
#     """
#     Reads the train, validate, and test HDF5 files from Draper and combines them.
#     """
#     # ... logic removed as it's cleaner in the __main__ block

if __name__ == '__main__':
    # --- EXAMPLE USAGE ---
    # 1. Define the folder containing your three HDF5 files (VDISC_train.hdf5, etc.)
    path_to_draper_folder = 'C:\\Users\\Abdullah\\Downloads' 
    
    # 2. Define the file names for the splits
    train_file = os.path.join(path_to_draper_folder, 'VDISC_train.hdf5')
    validate_file = os.path.join(path_to_draper_folder, 'VDISC_validate.hdf5')
    test_file = os.path.join(path_to_draper_folder, 'VDISC_test.hdf5')

    all_juliet_data = []

    # 3. Process each split and combine the resulting list of JSON samples
    all_juliet_data.extend(read_draper_hdf5(train_file))
    all_juliet_data.extend(read_draper_hdf5(validate_file))
    all_juliet_data.extend(read_draper_hdf5(test_file))
    
    # 4. Save the combined list to the final JSON file
    save_to_json(all_juliet_data, OUTPUT_FILE)