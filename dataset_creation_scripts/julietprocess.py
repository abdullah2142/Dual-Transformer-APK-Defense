import os
import json
import javalang
import re

# CONFIGURATION
# Update this to point to your specific Juliet 'testcases' directory
JULIET_DIR = "C:\\Users\\Abdullah\\Downloads\\\juliet-java-test-suite-master" 
OUTPUT_FILE = "juliet_dataset.json" # Output will be a single JSON array, matching your requested format

def remove_comments(string):
    """
    Removes Java-style comments (// and /* */) from code string.
    """
    # Pattern to match:
    # 1. Strings (to avoid removing comments inside strings)
    # 2. Block comments /* ... */
    # 3. Line comments // ...
    pattern = r"(\".*?\"|\'.*?\')|(/\*.*?\*/|//[^\r\n]*$)"
    
    regex = re.compile(pattern, re.MULTILINE|re.DOTALL)
    
    def _replacer(match):
        # If the 2nd group (comment) is matched, replace with empty space
        if match.group(2) is not None:
            return "" 
        # Otherwise (it was a string), return the string as is
        else: 
            return match.group(1)
            
    return regex.sub(_replacer, string)

def extract_method_body(file_content, method_node):
    """
    Extracts the raw string of the method body using brace counting.
    """
    lines = file_content.splitlines()
    start_line = method_node.position.line - 1
    
    open_braces = 0
    found_start = False
    body_lines = []
    
    for i in range(start_line, len(lines)):
        line = lines[i]
        
        # Count braces to find the matching closing brace
        open_braces += line.count('{')
        open_braces -= line.count('}')
        
        body_lines.append(line)
        
        if open_braces > 0:
            found_start = True
        
        # If we started and went back to 0, the method is closed
        if found_start and open_braces == 0:
            break
            
    return "\n".join(body_lines)

def process_juliet_suite():
    all_data = [] # List to hold all samples before writing
    count = 0
    
    print(f"Scanning {JULIET_DIR}...")
    
    for root, dirs, files in os.walk(JULIET_DIR):
        for file in files:
            if file.endswith(".java"):
                file_path = os.path.join(root, file)
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                    # Parse the Java file
                    tree = javalang.parse.parse(content)
                    
                    for _, node in tree.filter(javalang.tree.MethodDeclaration):
                        label = None
                        
                        # --- LABELING LOGIC ---
                        # 1. Vulnerable (Method name is exactly "bad")
                        if node.name == 'bad':
                            label = 1 
                        
                        # 2. Safe (Method name starts with "good", e.g., goodG2B, goodB2G)
                        elif node.name.startswith('good'):
                            label = 0 
                            
                        if label is not None:
                            raw_code = extract_method_body(content, node)
                            clean_code = remove_comments(raw_code).strip()
                            
                            if clean_code:
                                # Create the data object using the format from your check.py for reference
                                entry = {
                                    "filename": file,
                                    "method_name": node.name,
                                    "label": label,  # 1 = Vulnerable, 0 = Safe
                                    "code": clean_code
                                }
                                
                                all_data.append(entry)
                                count += 1
                                
                                if count % 1000 == 0:
                                    print(f"Processed {count} samples...")

                except Exception as e:
                    # Skip files that javalang cannot parse
                    continue

    # --- FINAL WRITE TO JSON ARRAY ---
    if all_data:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
            # Writes the entire list as a single JSON array with indentation for readability
            json.dump(all_data, outfile, indent=2)
            
        print(f"\nDone! Successfully wrote {len(all_data)} samples as a single JSON array to {OUTPUT_FILE}")
    else:
        print("No samples were processed.")


if __name__ == "__main__":
    # Ensure javalang is installed: pip install javalang
    process_juliet_suite()