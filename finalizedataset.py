import pandas as pd
import numpy as np
import os
import random
import glob

# Set random seeds for reproducibility
np.random.seed(42)
random.seed(42)

# --- CONFIGURATION ---
# IMPORTANT: Update these paths to point to your specific data files (JSON for Devign/Juliet, CSV for Draper/LVDAndro)
TARGET_DIR = 'C:\\Users\\Abdullah\\Downloads\\LVDAndro_APKs_Combined_Processed'
os.makedirs(TARGET_DIR, exist_ok=True)
FINAL_OUTPUT_FILE = os.path.join(TARGET_DIR, 'final_dataset.json')

# Define sample counts and column mappings for each source
# NOTE: The keys 'project' and 'id' are placeholders for generating 'filename' and 'method_name'
DATA_CONFIG = {
    # DEVIGN (12.5k POS / 12.5k NEG)
    'Devign':   {'path': 'devign_dataset.json', 'loader': 'json', 'code_col': 'code', 'label_col': 'label', 'pos': 12500, 'neg': 12500},
    # DRAPER (37.5k POS / 37.5k NEG)
    'Draper':   {'path': 'draper_dataset.json', 'loader': 'json', 'code_col': 'code', 'label_col': 'label', 'pos': 37500, 'neg': 37500},
    # JULIET (12.5k POS / 12.5k NEG)
    'Juliet':   {'path': 'juliet_dataset.json', 'loader': 'json', 'code_col': 'func', 'label_col': 'label', 'pos': 12500, 'neg': 12500},
    # LVDAndro (37.5k POS / 37.5k NEG)
    'LVDAndro': {'path': 'lvdandro_dataset.json', 'loader': 'json', 'code_col': 'code', 'label_col': 'label', 'pos': 37500, 'neg': 37500},
}
# --- END CONFIGURATION ---

def load_and_sample_dataset(name, config):
    print(f"--- Processing {name} ---")
    file_path = config['path']
    code_col = config['code_col']
    label_col = config['label_col']
    
    # 1. Load Data (handling JSON Lines/Array and CSV)
    try:
        if config['loader'] == 'json':
            try:
                # Try reading JSON Lines first (efficient)
                df = pd.read_json(file_path, lines=True)
            except ValueError:
                # Fallback to single JSON Array
                df = pd.read_json(file_path, lines=False)
        elif config['loader'] == 'csv':
            # Load CSV (using low_memory=False to better handle mixed types, avoiding previous MemoryErrors)
            df = pd.read_csv(file_path, low_memory=False)
    except FileNotFoundError:
        print(f"ERROR: File not found for {name} at {file_path}. Skipping.")
        return pd.DataFrame()
    except Exception as e:
        print(f"ERROR: Could not load {name} data: {e}. Skipping.")
        return pd.DataFrame()

    # 2. Standardize Columns & Clean
    # Rename code and label columns to generic names
    df = df.rename(columns={code_col: 'code', label_col: 'label'})
    df = df.dropna(subset=['code', 'label'])
    df['label'] = df['label'].astype(int)
    
    # --- CRITICAL MODIFICATION: ADD IDENTIFIER COLUMNS ---
    # We must generate the 'filename' and 'method_name' columns requested by the user.
    # Since the raw input structure is unknown, we use placeholders:
    df['filename'] = df.apply(lambda row: f"{name}_{row.name}_file", axis=1) # row.name is the original index
    df['method_name'] = df.apply(lambda row: f"func_{row.name}", axis=1)
    # --------------------------------------------------------
    
    # 3. Split by Class
    df_pos = df[df['label'] == 1]
    df_neg = df[df['label'] == 0]
    
    print(f"Original {name} count: POS={len(df_pos)}, NEG={len(df_neg)}")
    
    # 4. Sample and Standardize for Final Output (Random Sampling)
    
    # Define columns to keep for the final output
    final_cols = ['filename', 'method_name', 'label', 'code']
    
    # Sample Positive Class (Vulnerable)
    final_df_pos = df_pos.sample(n=min(config['pos'], len(df_pos)), random_state=42).copy()
    
    # Sample Negative Class (Non-Vulnerable)
    final_df_neg = df_neg.sample(n=min(config['neg'], len(df_neg)), random_state=42).copy()
    
    # 5. Prepare for Concatenation
    final_df_pos = final_df_pos[final_cols]
    final_df_neg = final_df_neg[final_cols]
    
    print(f"Sampled {name} count: POS={len(final_df_pos)}, NEG={len(final_df_neg)}. Total={len(final_df_pos) + len(final_df_neg)}")
    
    return pd.concat([final_df_pos, final_df_neg], ignore_index=True)


def combine_and_finalize_datasets():
    all_sampled_data = []
    
    # Process each dataset individually
    for name, config in DATA_CONFIG.items():
        sampled_df = load_and_sample_dataset(name, config)
        if not sampled_df.empty:
            all_sampled_data.append(sampled_df)
            
    if not all_sampled_data:
        print("FATAL ERROR: No datasets were loaded successfully.")
        return
        
    # 1. Concatenate all sampled data into one DataFrame
    final_combined_df = pd.concat(all_sampled_data, ignore_index=True)
    
    # 2. Shuffle the entire combined dataset
    final_combined_df = final_combined_df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    # 3. Save as JSON
    print("\n--- Finalizing and Saving Combined Dataset ---")
    print(f"Final Total Samples: {len(final_combined_df)}")
    
    # --- CRITICAL MODIFICATION: Save as Standard JSON Array ---
    # Remove lines=True to output the requested format: [{"f":...}, {"f":...}]
    final_combined_df.to_json(FINAL_OUTPUT_FILE, orient='records', lines=False, indent=2) 
    # --------------------------------------------------------
    
    print(f"Successfully created final balanced dataset at: {FINAL_OUTPUT_FILE}")
    
# Run the main function
if __name__ == "__main__":
    combine_and_finalize_datasets()