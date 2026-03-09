import pandas as pd
import os
import numpy as np
import random 

# --- HELPER FUNCTION TO FIND FUNCTION BOUNDARIES ---
def find_function_boundaries(df, file_id):
    """
    Finds function boundaries within a file segment using curly brace matching.
    It returns a list of dictionaries, where each dict describes a unique 
    function/scope found in the file:
    {'start': index, 'end': index, 'code_lines': [list of code]}
    """
    file_df = df[df['file_id'] == file_id].copy()
    code_lines = file_df['Code'].tolist()
    start_index = file_df.index[0]
    
    function_scopes = []
    
    # Simple state machine for brace balancing
    brace_balance = 0
    function_start_idx = -1
    
    # Iterate over the lines of the file segment
    for relative_idx, line in enumerate(code_lines):
        global_idx = start_index + relative_idx
        
        # Check for function definition keywords (Java/Android context)
        # We look for common function headers: public/private/protected/static/void, etc.
        is_function_header = (
            any(keyword in line for keyword in ['public', 'private', 'protected', 'static']) and 
            '(' in line and ')' in line and 
            not any(ignore in line for ignore in ['class', 'interface', 'enum', 'if', 'for', 'while'])
        )
        
        # Start a new scope/function if we see a header or if a new brace scope opens
        if is_function_header and function_start_idx == -1:
             function_start_idx = global_idx
        
        # Update brace balance
        brace_balance += line.count('{')
        brace_balance -= line.count('}')

        if brace_balance > 0 and function_start_idx == -1:
            # If we enter a brace block without an identified function header, 
            # assume the block start is the function start (e.g., constructors, lambdas)
            function_start_idx = global_idx
        
        # If the balance returns to 0 after being positive, a scope has closed
        if brace_balance == 0 and function_start_idx != -1:
            function_end_idx = global_idx
            
            # Extract the code for this function
            func_code_chunk = '\n'.join(df.loc[function_start_idx:function_end_idx, 'Code'].tolist())
            
            # Store the function scope
            function_scopes.append({
                'start': function_start_idx,
                'end': function_end_idx,
                'code': func_code_chunk
            })
            
            # Reset for the next function
            function_start_idx = -1
            
    return function_scopes

# --- NEW EXTRACTOR FUNCTION ---
def extract_function_sample(df, flaw_index, function_map):
    """ Extracts the full function code given a vulnerable line index. """
    
    for func_scope in function_map:
        if func_scope['start'] <= flaw_index <= func_scope['end']:
            # The flaw is contained in this function scope
            
            # Flaw line index relative to the start of the function code block
            relative_flaw_index = flaw_index - func_scope['start']
            
            return func_scope['code'], relative_flaw_index, func_scope
            
    return None, None, None # Flaw line was outside any recognized function (e.g., file-level fields)


def create_balanced_function_dataset(input_csv, output_json):
    """
    Converts a line-by-line CSV into a balanced function-level dataset (1:1).
    """
    print(f"Reading {input_csv} with memory optimization...")
    
    # 1. Define Dtypes and Columns to Load
    dtype_spec = {
        'Vulnerability_status': 'int8', 
        'Code': str, 
        'CWE_ID': str,
        'Description': str
    }
    cols_to_use = list(dtype_spec.keys())
    
    try:
        df = pd.read_csv(
            input_csv, 
            dtype=dtype_spec, 
            usecols=cols_to_use, 
            low_memory=False
        )
    except Exception as e:
        print(f"FATAL: Error loading CSV: {e}")
        return

    # 2. Initial Cleaning and File Boundary Detection
    df['Code'] = df['Code'].fillna('')
    df = df.dropna(subset=['Vulnerability_status']) 
    df['Vulnerability_status'] = df['Vulnerability_status'].astype(int)
    
    df['is_new_file'] = df['Code'].str.strip().str.startswith('package ')
    df['file_id'] = df['is_new_file'].cumsum()
    
    print(f"Detected {df['file_id'].max() + 1} distinct files/segments.")

    # 3. Pre-calculate all Function Boundaries and create a flat list
    all_function_scopes = []
    for file_id in df['file_id'].unique():
        all_function_scopes.extend(find_function_boundaries(df, file_id))
    
    print(f"Calculated {len(all_function_scopes)} unique function scopes.")
    
    # Store unique vulnerable functions to avoid duplication in positive samples
    vulnerable_functions_set = {} # Key: (start_index, end_index)

    # --- PASS 1: COLLECT ALL POSITIVE FUNCTION SAMPLES AND DEFINE EXCLUSION ZONES ---
    pos_samples = []
    vulnerable_indices = df[df['Vulnerability_status'] == 1].index.tolist()
    
    for vuln_idx in vulnerable_indices:
        
        code_chunk, relative_index, func_scope = extract_function_sample(df, vuln_idx, all_function_scopes)
        
        if func_scope:
            func_key = (func_scope['start'], func_scope['end'])
            
            if func_key not in vulnerable_functions_set:
                # This is the first time we found a flaw in this specific function
                vulnerable_functions_set[func_key] = {
                    'vuln_idx': vuln_idx,
                    'code': code_chunk,
                    'relative_index': relative_index
                }

    # Now convert the unique vulnerable functions into final samples
    for func_key, data in vulnerable_functions_set.items():
        row = df.loc[data['vuln_idx']]
        sample = {
            'code': data['code'],
            'label': 1,
            'project': 'LVDAndro_Function',
            'flaw_line_index': int(data['relative_index']), # Relative line of the FIRST flaw found
            'CWE_ID': row.get('CWE_ID', 'N/A'),
            'Description': row.get('Description', 'Vulnerable function snippet.')
        }
        pos_samples.append(sample)
        
    print(f"\nCollected {len(pos_samples)} final positive function samples.")
    
    # --- PASS 2: COLLECT NEGATIVE SAMPLES (BALANCED 1:1) ---
    num_positives = len(pos_samples)
    
    # 4. Define Exclusion Zones (all lines covered by vulnerable functions)
    vulnerable_exclusion_indices = set()
    for start, end in vulnerable_functions_set.keys():
        for idx in range(start, end + 1):
            vulnerable_exclusion_indices.add(idx)

    # 5. Identify all clean function scopes
    clean_function_scopes = []
    for func_scope in all_function_scopes:
        start, end = func_scope['start'], func_scope['end']
        
        # Check if *any* line in this function is part of an exclusion zone
        is_clean = True
        for idx in range(start, end + 1):
            if idx in vulnerable_exclusion_indices:
                is_clean = False
                break
        
        if is_clean:
            clean_function_scopes.append(func_scope)
            
    print(f"Found {len(clean_function_scopes)} unique, fully clean function scopes.")
    
    # 6. Sample the required number of clean functions
    if len(clean_function_scopes) < num_positives:
        print(f"Warning: Only {len(clean_function_scopes)} fully clean negative candidates available.")
        num_negatives = len(clean_function_scopes)
    else:
        num_negatives = num_positives

    random.seed(42) 
    sampled_negative_scopes = random.sample(clean_function_scopes, num_negatives)
    
    neg_samples = []
    for func_scope in sampled_negative_scopes:
        # Create a clean negative sample entry
        sample = {
            'code': func_scope['code'],
            'label': 0, 
            'project': 'LVDAndro_Clean_Function',
            'flaw_line_index': -1, 
            'CWE_ID': 'N/A',
            'Description': 'Non-vulnerable clean function snippet.'
        }
        neg_samples.append(sample)

    print(f"Collected {len(neg_samples)} unique negative function samples for balance.")
    
    # --- 7. Combine and Save ---
    
    result_df = pd.DataFrame(pos_samples + neg_samples)
    
    result_df = result_df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    # Save as JSON Lines (orient='records', lines=True)
    output_json_path = os.path.join("C:\\Users\\Abdullah\\Downloads\\LVDAndro_APKs_Combined_Processed", output_json)
    output_dir = os.path.dirname(output_json_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    result_df.to_json(output_json_path, orient='records', lines=True, indent=2)
    
    print("\n--- Processing Complete ---")
    print(f"Total Final Samples: {len(result_df)}")
    print(f"Positive Samples: {len(pos_samples)}, Negative Samples: {len(neg_samples)}")
    print(f"Saved balanced dataset to: {output_json_path}")

# --- Execution ---
csv_path = "C:\\Users\\Abdullah\\Downloads\\LVDAndro_APKs_Combined_Processed\\LVDAndro_APKs_Combined_Processed.csv"
create_balanced_function_dataset(csv_path,"lvdandro_function_dataset.json")