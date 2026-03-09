from tree_sitter import Language, Parser
import tree_sitter_c
import tree_sitter_java

# --- 1. Language Setup (Crucial for modern Tree-Sitter) ---
# This assumes tree-sitter-c and tree-sitter-java packages were installed successfully.
C_LANGUAGE = tree_sitter_c.language()
JAVA_LANGUAGE = tree_sitter_java.language() 

def get_parser(lang):
    parser = Parser()
    if lang == 'c':
        parser.set_language(C_LANGUAGE)
    elif lang == 'java':
        parser.set_language(JAVA_LANGUAGE)
    return parser

def tree_to_token_index(node):
    """Recursively traverses the AST to collect all leaf node (token) positions."""
    def traverse(node):
        if len(node.children) == 0:
            return [(node.start_point, node.end_point, node.start_byte, node.end_byte)]
        res = []
        for child in node.children:
            res += traverse(child)
        return res
    return traverse(node)

# --- 2. OFFICIAL DFG Extraction Logic for C/C++ ---
# This tracks variable assignment (definition) and subsequent use.
def DFG_c(root_node, index_to_code, states):
    DFG = []
    # Node types relevant to variable definition/assignment in C/C++
    def_statement = ['init_declarator', 'parameter_declaration']
    
    # Base case: Leaf node (token)
    if (len(root_node.children) == 0 or root_node.type == 'string_literal') and root_node.type != 'comment':
        idx = (root_node.start_point, root_node.end_point)
        # Check if this token is a variable or identifier
        if idx in index_to_code:
            return [idx], states
        else:
            return [], states
            
    # DFG Logic for C/C++
    if root_node.type in def_statement:
        name_node = root_node.child_by_field_name('declarator')
        value_node = root_node.child_by_field_name('value')
        
        if name_node is None: # Should not happen often
            return [], states
            
        name_indexs = tree_to_token_index(name_node)
        
        if value_node is None:
            # Simple declaration (e.g., int x;)
            for idx in name_indexs:
                if idx in states:
                    DFG.append((states[idx][-1], idx, 'computedFrom'))
                states[idx] = [idx]
        else:
            # Declaration with assignment (e.g., int x = 10;)
            value_indexs, states = DFG_c(value_node, index_to_code, states)
            for name_idx in name_indexs:
                states[name_idx] = [name_idx]
                for value_idx in value_indexs:
                    DFG.append((value_idx, name_idx, 'computedFrom'))
        return DFG, states

    # Logic for update expressions (e.g., x++ or x = y + 1)
    if root_node.type == 'update_expression' or root_node.type == 'assignment_expression':
        left_node = root_node.child_by_field_name('left')
        right_node = root_node.child_by_field_name('right')
        
        if left_node and right_node:
            left_indexs = tree_to_token_index(left_node)
            right_indexs, states = DFG_c(right_node, index_to_code, states)
            
            for left_idx in left_indexs:
                old_state = states.get(left_idx, [])
                if old_state:
                    DFG.append((old_state[-1], left_idx, 'computedFrom'))
                
                states[left_idx] = [left_idx]
                for right_idx in right_indexs:
                    DFG.append((right_idx, left_idx, 'computedFrom'))
            return DFG, states

    # Recursive traversal for other nodes
    children = root_node.children
    for child in children:
        temp, states = DFG_c(child, index_to_code, states)
        DFG += temp
        
    return DFG, states

# --- 3. OFFICIAL DFG Extraction Logic for Java ---
def DFG_java(root_node, index_to_code, states):
    DFG = []
    # Java node types relevant to variable definition/assignment
    def_statement = ['variable_declarator', 'formal_parameter']
    
    # Base case: Leaf node (token)
    if (len(root_node.children) == 0 or root_node.type == 'string_literal') and root_node.type != 'comment':
        idx = (root_node.start_point, root_node.end_point)
        if idx in index_to_code:
            return [idx], states
        else:
            return [], states
            
    # DFG Logic for Java
    if root_node.type in def_statement:
        name_node = root_node.child_by_field_name('name')
        value_node = root_node.child_by_field_name('value')
        
        if name_node is None:
            return [], states
            
        name_indexs = tree_to_token_index(name_node)
        
        if value_node is None:
            # Simple declaration (e.g., int x;)
            for idx in name_indexs:
                if idx in states:
                    DFG.append((states[idx][-1], idx, 'computedFrom'))
                states[idx] = [idx]
        else:
            # Declaration with assignment (e.g., int x = 10;)
            value_indexs, states = DFG_java(value_node, index_to_code, states)
            for name_idx in name_indexs:
                states[name_idx] = [name_idx]
                for value_idx in value_indexs:
                    DFG.append((value_idx, name_idx, 'computedFrom'))
        return DFG, states

    # Logic for assignment expressions
    if root_node.type == 'assignment_expression':
        left_node = root_node.child_by_field_name('left')
        right_node = root_node.child_by_field_name('right')
        
        if left_node and right_node:
            left_indexs = tree_to_token_index(left_node)
            right_indexs, states = DFG_java(right_node, index_to_code, states)
            
            for left_idx in left_indexs:
                old_state = states.get(left_idx, [])
                if old_state:
                    DFG.append((old_state[-1], left_idx, 'computedFrom'))
                
                states[left_idx] = [left_idx]
                for right_idx in right_indexs:
                    DFG.append((right_idx, left_idx, 'computedFrom'))
            return DFG, states

    # Recursive traversal for other nodes
    children = root_node.children
    for child in children:
        temp, states = DFG_java(child, index_to_code, states)
        DFG += temp
        
    return DFG, states
    
# --- 4. Main Extractor Function ---
def extract_dataflow(code, lang): 
    parser = get_parser(lang)
    tree = parser.parse(bytes(code, 'utf8'))
    root_node = tree.root_node
    
    # Map tokens to their indices/text
    tokens_index = tree_to_token_index(root_node)
    
    index_to_code = {}
    code_tokens = []
    
    code_bytes = bytes(code, 'utf8')
    for (start_point, end_point, start_byte, end_byte) in tokens_index:
        token_str = code_bytes[start_byte:end_byte].decode('utf8', errors='ignore')
        index_to_code[(start_point, end_point)] = token_str
        code_tokens.append(token_str)

    # --- Language Specific DFG Call ---
    if lang == 'c':
        DFG, _ = DFG_c(root_node, index_to_code, {})
    elif lang == 'java':
        DFG, _ = DFG_java(root_node, index_to_code, {})
    else:
        DFG = [] 
        
    # Extract unique variables from DFG for model input: 
    # The GraphCodeBERT input format requires the list of variables involved in the flow.
    dfg_vars = set()
    for (src, tgt, rel) in DFG:
        # src and tgt are tuples of (start_point, end_point)
        if src in index_to_code:
            dfg_vars.add(index_to_code[src])
        if tgt in index_to_code:
            dfg_vars.add(index_to_code[tgt])
            
    return code_tokens, list(dfg_vars)