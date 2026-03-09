import torch
import json
from transformers import RobertaTokenizer
# This imports the updated, production-grade logic for DFG extraction
from parser_production import extract_dataflow 
from torch.utils.data import Dataset # Keep this if you plan to define your Dataset class here

# --- 1. NEW: Language Heuristic Function ---
def guess_language(code):
    """
    Heuristically determines if the code snippet is C/C++ or Java.
    """
    code_lower = code.lower()
    
    # Java indicators are more specific for Android/general Java source
    java_keywords = ['import ', 'class ', 'package ', 'public static void main']
    if any(k in code_lower for k in java_keywords):
        return 'java'
    
    # C/C++ indicators (common in native APK libraries)
    c_keywords = ['include <', '.h>', 'struct ', 'union ', 'malloc', 'free', '#define']
    if any(k in code_lower for k in c_keywords):
        return 'c'
    
    # Fallback: Check for generic function structure
    if code_lower.count('(') > 0 and code_lower.count(')') > 0 and code_lower.count('{') > 0:
        # If it looks like a function but lacks strong Java keywords, assume C/C++ 
        # as it is the most common alternative in systems programming/native code.
        return 'c'
        
    return 'c' # Default fallback


# --- 2. UPDATED: Preprocessing Function ---
def preprocess_and_save(input_file, output_file, tokenizer, max_len=512):
    print(f"Processing {input_file}...")
    processed_data = []
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        print("Successfully loaded file as a single JSON array.")
    except json.JSONDecodeError as e:
        print(f"Failed to load as standard JSON ({e}). Attempting JSON Lines format...")
        raw_data = []
        # Fallback to reading line-by-line (JSON Lines format)
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f):
                    line = line.strip()
                    if line: # Skip empty lines which caused the previous error
                        raw_data.append(json.loads(line))
        except json.JSONDecodeError as e_line:
            # If reading line-by-line still fails, something is fundamentally wrong
            print(f"FATAL ERROR: Failed to decode JSON Line at Line {line_num + 1}. Check file integrity.")
            print(f"Error: {e_line}")
            return # Stop execution if data is unreadable

    # Process
    count = 0
    skipped = 0
    for item in raw_data:
        try:
            code = item['code']
            label = int(item['label'])
            
            # --- CRITICAL STEP: GUESS LANGUAGE ---
            lang = guess_language(code)
            
            # --- EXPENSIVE STEP: DFG Extraction ---
            # Now correctly passes the detected language to the extractor
            code_tokens, dfg_vars = extract_dataflow(code, lang) 
            
            # Tokenize Code and DFG
            code_subtokens = sum([tokenizer.tokenize(token) for token in code_tokens], [])
            dfg_subtokens = sum([tokenizer.tokenize(var) for var in dfg_vars], [])
            
            # Truncate
            total_len = len(code_subtokens) + len(dfg_subtokens) + 3
            if total_len > max_len:
                available = max_len - 3 - len(dfg_subtokens)
                if available < 0:
                     dfg_subtokens = dfg_subtokens[:max_len - 3 - len(code_subtokens)]
                else:
                    code_subtokens = code_subtokens[:available]

            # Convert to IDs: [CLS] + Code + [SEP] + DFG + [SEP]
            source_ids = [tokenizer.cls_token_id] + \
                         tokenizer.convert_tokens_to_ids(code_subtokens) + \
                         [tokenizer.sep_token_id] + \
                         tokenizer.convert_tokens_to_ids(dfg_subtokens) + \
                         [tokenizer.sep_token_id]
            
            padding_length = max_len - len(source_ids)
            source_ids += [tokenizer.pad_token_id] * padding_length
            attention_mask = [1] * (max_len - padding_length) + [0] * padding_length
            
            processed_data.append({
                'input_ids': torch.tensor(source_ids, dtype=torch.uint8),
                'attention_mask': torch.tensor(attention_mask, dtype=torch.uint8),
                'labels': torch.tensor(label, dtype=torch.long),
                'func_name': f"{item.get('project', 'p')}_{count}"
            })
            
            count += 1
            if count % 1000 == 0:
                print(f"Processed {count} samples...", end='\r')
                
        except Exception as e:
            print(f"\nFATAL ERROR encountered at sample index {count}. Stopping execution.")
            print(f"Error details: {e}")
        
            # Stop the loop and exit the preprocess_and_save function immediately
            return
            
    print(f"\nFinished. Processed: {count}, Skipped: {skipped}")
    print(f"Saving {len(processed_data)} tensors to {output_file}...")
    torch.save(processed_data, output_file)
    print("Pre-processing Complete.")

# --- EXECUTION BLOCK ---
if __name__ == "__main__":
    # Ensure you replace "final_dataset.json" if you are using a different name
    DATASET_NAME = "final_dataset.json" 
    OUTPUT_CACHE_NAME = "cached_dataset.pt"

    print("Starting DFG preprocessing...")
    tokenizer = RobertaTokenizer.from_pretrained("microsoft/graphcodebert-base")
    preprocess_and_save(DATASET_NAME, OUTPUT_CACHE_NAME, tokenizer)