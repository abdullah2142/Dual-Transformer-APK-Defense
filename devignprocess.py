import pandas as pd
import json
import os

# --- CONFIGURATION ---
INPUT_FILE = "dataset.json" # Assuming the user's uploaded Devign file is named this
OUTPUT_FILE = "devign_dataset.json"
PROJECT_NAME = "Devign"
CWE_PLACEHOLDER_VULN = "CWE999" # Placeholder for general vulnerability (target=1)
CWE_PLACEHOLDER_SAFE = "CWE000" # Placeholder for safe code (target=0)

def process_devign_dataset(input_path: str):
    """
    Reads the Devign JSON dataset, transforms its columns to match the 
    Juliet/Draper structure, and outputs a list of dictionaries.

    Args:
        input_path (str): Path to the original Devign JSON file.

    Returns:
        list: A list of dictionary samples in the target JSON structure.
    """
    print(f"Reading Devign dataset from: {input_path}")
    
    try:
        # Devign is usually a large JSON array of objects
        df = pd.read_json(input_path, orient='records')
    except Exception as e:
        print(f"CRITICAL ERROR: Could not read Devign JSON file. Ensure it is a valid JSON array of objects. Error: {e}")
        return []

    print(f"Successfully loaded {len(df)} original samples.")
    
    # --- Data Transformation ---
    
    # Map the columns to the new names/format
    transformed_data = []
    
    for index, row in df.iterrows():
        # Devign only provides a binary label (0 or 1)
        label = int(row['target'])
        
        # 1. Create a unique filename/identifier
        # We combine project, commit_id, and index for uniqueness
        filename = f"{PROJECT_NAME}_{row['project']}_{row['commit_id']}_{index}.c"
        
        # 2. Determine CWE ID based on the binary label
        cwe_id = CWE_PLACEHOLDER_VULN if label == 1 else CWE_PLACEHOLDER_SAFE
        
        # 3. Construct the final entry dictionary
        entry = {
            # Note: Devign's 'func' is the raw source code, which maps to 'code'
            "filename": filename,
            "method_name": f"func_{index}",
            "label": label,  # 1 (Vulnerable) or 0 (Safe)
            "CWE_ID": cwe_id, 
            "code": row['func'] 
        }
        
        transformed_data.append(entry)

    print(f"Transformation complete. {len(transformed_data)} samples generated.")
    return transformed_data


def save_to_json(data_list, output_path):
    """
    Saves the list of dictionaries as a single JSON array, matching the requested format.
    """
    print(f"Saving combined dataset to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as outfile:
        # Writes the entire list as a single JSON array with indentation
        json.dump(data_list, outfile, indent=2)
    print(f"Save complete. File saved to {output_path}")


if __name__ == '__main__':
    # Execute the transformation pipeline
    transformed_data = process_devign_dataset(INPUT_FILE)
    
    if transformed_data:
        save_to_json(transformed_data, OUTPUT_FILE)