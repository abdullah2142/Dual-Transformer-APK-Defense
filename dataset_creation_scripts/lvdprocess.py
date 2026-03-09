import pandas as pd
import os
import sys
import numpy as np
import random 
import csv 
import json 

# Define the helper function (must be included or imported)
def extract_window_sample(df, index, current_file_id, window_radius):
    """ Helper function to extract a code window based on index and file boundary. """
    
    start_idx = max(0, index - window_radius)
    end_idx = min(len(df), index + window_radius + 1)
    
    window_df = df.iloc[start_idx:end_idx]
    window_df = window_df[window_df['file_id'] == current_file_id]
    
    code_chunk = '\n'.join(window_df['Code'].tolist())
    
    try:
        relative_flaw_index = window_df.index.get_loc(index)
    except KeyError:
        return None, None 

    return code_chunk, relative_flaw_index


def create_balanced_windowed_dataset_juliet_format(input_csv, output_json, window_radius=5):
    """
    Loads the LVDAndro data and processes it into a balanced dataset,
    saving the output in a simple JSON array format matching the Juliet dataset.
    """
    print(f"Applying final fix: Increasing CSV field limit for large code entries.")
    
    # Increase CSV field limit to handle large code strings (to prevent OSError: field larger than field limit)
    try:
        csv.field_size_limit(1000000) 
        print(f"CSV field size limit set to {csv.field_size_limit()} bytes.")
    except Exception as e:
        # sys.maxsize is sometimes needed for Python 3.6/3.7 to set a very large limit
        csv.field_size_limit(sys.maxsize)
        print("Warning: Failed to set explicit limit, setting to sys.maxsize.")

    print(f"Reading {input_csv} with Python engine and memory optimization...")
    
    # Define dtypes for ONLY the necessary columns
    dtype_spec = {
        'Vulnerability_status': 'int8', 
        'Code': str,  
    }
    required_cols = list(dtype_spec.keys())
    
    try:
        # Load the CSV
        df = pd.read_csv(
            input_csv, 
            usecols=required_cols, 
            dtype=dtype_spec, 
            engine='python', 
        )
        print(f"File loaded successfully. Total lines: {len(df)}")
        
    except Exception as e:
        print(f"FATAL: Error loading CSV. Original error: {e}")
        return

    # --- PROCESSING LOGIC ---
    df['Code'] = df['Code'].fillna('')
    df = df.dropna(subset=['Vulnerability_status']) 
    df['Vulnerability_status'] = df['Vulnerability_status'].astype(int)
    
    df['is_new_file'] = df['Code'].str.strip().str.startswith('package ')
    df['file_id'] = df['is_new_file'].cumsum()
    
    print(f"Detected {df['file_id'].max() + 1} distinct files/segments.")

    # PASS 1: COLLECT ALL POSITIVE SAMPLES AND DEFINE EXCLUSION ZONES
    pos_samples = []
    vulnerable_indices = df[df['Vulnerability_status'] == 1].index.tolist()
    vulnerable_window_indices = set() 
    
    for vuln_idx in vulnerable_indices:
        current_file_id = df.loc[vuln_idx, 'file_id']

        for offset in range(-window_radius, window_radius + 1):
            idx = vuln_idx + offset
            if 0 <= idx < len(df):
                if df.loc[idx, 'file_id'] == current_file_id:
                    vulnerable_window_indices.add(idx)

        code_chunk, relative_index = extract_window_sample(df, vuln_idx, current_file_id, window_radius)
        
        if code_chunk and relative_index is not None:
            # --- MODIFICATION: Create the Juliet-compatible entry ---
            sample = {
                # Use the file_id and index to simulate a unique identifier
                "filename": f"file_{current_file_id}.java", 
                "method_name": f"bad_{vuln_idx}",
                "label": 1,
                "code": code_chunk
            }
            pos_samples.append(sample)

    print(f"\nCollected {len(pos_samples)} final positive windows.")
    
    # PASS 2: COLLECT NEGATIVE SAMPLES (BALANCED 1:1)
    num_positives = len(pos_samples)
    safe_indices = df[df['Vulnerability_status'] == 0].index.tolist()
    valid_negative_indices = [i for i in safe_indices if i not in vulnerable_window_indices]

    if len(valid_negative_indices) < num_positives:
        num_negatives = len(valid_negative_indices)
    else:
        num_negatives = num_positives

    random.seed(42) 
    sampled_negative_indices = random.sample(valid_negative_indices, num_negatives)
    
    neg_samples = []
    for neg_idx in sampled_negative_indices:
        current_file_id = df.loc[neg_idx, 'file_id']
        code_chunk, _ = extract_window_sample(df, neg_idx, current_file_id, window_radius)
        
        if code_chunk:
            # --- MODIFICATION: Create the Juliet-compatible entry ---
            sample = {
                "filename": f"file_{current_file_id}.java", 
                "method_name": f"good_{neg_idx}",
                "label": 0,
                "code": code_chunk
            }
            neg_samples.append(sample)

    print(f"Collected {len(neg_samples)} negative windows for balance.")
    
    # --- 3. Combine and Save (Final Step Modified) ---
    
    all_data = pos_samples + neg_samples
    random.shuffle(all_data) # Equivalent to DataFrame.sample(frac=1)
    
    # Save as a single JSON array (list of dicts)
    output_json_path = os.path.join("C:\\Users\\Abdullah\\Downloads\\LVDAndro_APKs_Combined_Processed", output_json)
    output_dir = os.path.dirname(output_json_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Use json.dump to write the list as a single JSON array
    try:
        with open(output_json_path, 'w', encoding='utf-8') as outfile:
            json.dump(all_data, outfile, indent=2)
            
        print("\n--- Processing Complete ---")
        print(f"Total Final Samples: {len(all_data)}")
        print(f"Positive Samples: {len(pos_samples)}, Negative Samples: {len(neg_samples)}")
        print(f"Saved balanced dataset as a single JSON array to: {output_json_path}")
        
    except Exception as e:
         print(f"FATAL: Error during final JSON writing: {e}")
         print(f"Ensure the path {output_json_path} has enough disk space.")
         return


# --- EXECUTION ---

csv_path = "C:\\Users\\Abdullah\\Downloads\\LVDAndro_APKs_Combined_Processed\\LVDAndro_APKs_Combined_Processed.csv"
create_balanced_windowed_dataset_juliet_format(csv_path,"lvdandro_dataset.json", 5)