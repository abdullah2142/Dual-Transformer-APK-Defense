!pip install torch transformers tree_sitter==0.21.3 scikit-learn matplotlib -q

import torch
import json
import math
import random
import numpy as np
from transformers import AutoTokenizer, RobertaConfig, RobertaModel
from torch.utils.data import DataLoader, SequentialSampler, Dataset
from tqdm.auto import tqdm
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import CrossEntropyLoss
from collections import defaultdict

print("Imports complete.")

class Args:
    train_file = '/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl'
    gcb_dfg_weights = '' # TODO: /kaggle/input/.../model.bin
    code_length = 384
    data_flow_length = 128
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    eval_batch_size = 32
    seed = 42
    test_ratio = 0.10
    
args = Args()

def set_seed(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)
    if torch.cuda.device_count() > 0: torch.cuda.manual_seed_all(s)
set_seed(args.seed)

# ─── STRATIFIED SPLIT ─────────────────────────────────────────────────────────
def infer_source(entry):
    for key in ("source", "dataset", "origin", "project"):
        val = entry.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    fn = entry.get('filename', '')
    if fn:
        return fn.split('_')[0]
    return "unknown"

def allocate_counts(total_needed, groups, fraction):
    raw = {g: len(v) * fraction for g, v in groups.items()}
    base = {g: int(math.floor(v)) for g, v in raw.items()}
    remainder = total_needed - sum(base.values())
    order = sorted(groups.keys(), key=lambda g: (raw[g] - base[g], len(groups[g])), reverse=True)
    for g in order[:remainder]:
        base[g] += 1
    return base

def get_test_indices(filepath, test_ratio=0.10, seed=42):
    with open(filepath, 'r', encoding='utf-8') as f:
        entries = [json.loads(line) for line in f]
    
    rng = random.Random(seed)
    source_to_indices = defaultdict(list)
    for idx, entry in enumerate(entries):
        source_to_indices[infer_source(entry)].append(idx)

    for indices in source_to_indices.values():
        rng.shuffle(indices)

    total = len(entries)
    target_test = int(round(total * test_ratio))

    test_alloc = allocate_counts(target_test, source_to_indices, test_ratio)
    test_indices = []
    for source, indices in source_to_indices.items():
        take = min(test_alloc[source], len(indices))
        test_indices.extend(indices[:take])

    return sorted(test_indices)

print("Calculating stratified split (seed=42)...")
test_indices = get_test_indices(args.train_file, test_ratio=args.test_ratio, seed=args.seed)
print(f"Test samples: {len(test_indices):,}")

# ─── MODEL DEFINITIONS ───────────────────────
class DFGModel(nn.Module):
    def __init__(self, encoder, config):
        super().__init__()
        self.encoder = encoder
        self.config = config
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.classifier = nn.Linear(config.hidden_size, 2)

    def forward(self, input_ids=None, p_ids=None, attn_mask=None, labels=None):
        extended_attention_mask = (1.0 - attn_mask) * -10000.0
        extended_attention_mask = extended_attention_mask.unsqueeze(1)
        embedding_output = self.encoder.embeddings(input_ids=input_ids, position_ids=p_ids)
        encoder_outputs = self.encoder.encoder(
            embedding_output,
            attention_mask=extended_attention_mask,
            head_mask=[None] * self.config.num_hidden_layers
        )[0]
        logits = self.classifier(self.dropout(encoder_outputs[:, 0, :]))
        prob = F.softmax(logits, dim=-1)

        if labels is not None:
            loss_fct = CrossEntropyLoss()
            loss = loss_fct(logits, labels)
            return loss, prob
        return prob

# ─── DATASET CLASSES ─────────────────────────
class TextDataset(Dataset):
    def __init__(self, tokenizer, args, file_path, indices=None):
        self.args = args
        self.tokenizer = tokenizer
        self.total_len = args.code_length + args.data_flow_length
        with open(file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        self.lines = [all_lines[i] for i in indices] if indices is not None else all_lines
        self.original_indices = indices if indices is not None else list(range(len(all_lines)))
            
    def __len__(self): return len(self.lines)

    def _get_char_index(self, code_lines, coord):
        row, col = coord
        char_idx = 0
        for i in range(min(row, len(code_lines))):
            char_idx += len(code_lines[i]) 
        return char_idx + col

    def __getitem__(self, item):
        entry = json.loads(self.lines[item])
        code = entry.get('code', '')
        dfg = entry.get('dfg', [])[:self.args.data_flow_length]
        label = int(entry.get('label', 0)) if entry.get('label') is not None else 0

        tokens_obj = self.tokenizer(
            code, 
            max_length=self.args.code_length, 
            truncation=True, 
            padding='max_length',
            return_offsets_mapping=True
        )
        input_ids = tokens_obj['input_ids']
        offsets = tokens_obj['offset_mapping']
        code_lines = code.splitlines(keepends=True)

        dfg_ids = [self.tokenizer.unk_token_id] * len(dfg)
        pos_to_node_idx = {}
        node_to_token_map = {}

        for node_idx, item_node in enumerate(dfg):
            start_pos, end_pos = item_node[1][0], item_node[1][1]
            pos_key = (start_pos[0], start_pos[1], end_pos[0], end_pos[1])
            pos_to_node_idx[pos_key] = node_idx
            
            char_start = self._get_char_index(code_lines, start_pos)
            char_end = self._get_char_index(code_lines, end_pos)
            
            aligned_tokens = []
            for t_idx, (t_start, t_end) in enumerate(offsets):
                if t_start == t_end: continue
                if (t_start >= char_start and t_end <= char_end) or (char_start >= t_start and char_end <= t_end):
                    aligned_tokens.append(t_idx)
            node_to_token_map[node_idx] = aligned_tokens

        attn_mask = np.zeros((self.total_len, self.total_len), dtype=bool)
        c_len = self.args.code_length
        attn_mask[:c_len, :c_len] = True
        
        for node_idx, item_node in enumerate(dfg):
            abs_node_idx = c_len + node_idx
            for t_idx in node_to_token_map.get(node_idx, []):
                attn_mask[abs_node_idx, t_idx] = True
                attn_mask[t_idx, abs_node_idx] = True
            
            for p_pos in item_node[4]:
                p_key = (p_pos[0][0], p_pos[0][1], p_pos[1][0], p_pos[1][1])
                if p_key in pos_to_node_idx:
                    abs_parent_idx = c_len + pos_to_node_idx[p_key]
                    attn_mask[abs_node_idx, abs_parent_idx] = True
                    attn_mask[abs_parent_idx, abs_node_idx] = True
            attn_mask[abs_node_idx, abs_node_idx] = True

        full_input_ids = input_ids + dfg_ids
        p_ids = [i + 2 for i in range(c_len)] + [0] * len(dfg_ids)
        padding_len = self.total_len - len(full_input_ids)
        
        if padding_len > 0:
            full_input_ids += [self.tokenizer.pad_token_id] * padding_len
            p_ids += [1] * padding_len
        
        return {
            'input_ids': torch.tensor(full_input_ids, dtype=torch.long),
            'p_ids': torch.tensor(p_ids, dtype=torch.long),
            'attn_mask': torch.tensor(attn_mask, dtype=torch.float),
            'label': torch.tensor(label, dtype=torch.long),
            'index': item
        }

print("Loading dataset...")
tokenizer = AutoTokenizer.from_pretrained("microsoft/graphcodebert-base", use_fast=True)
test_ds = TextDataset(tokenizer, args, args.train_file, indices=test_indices)
print(f"Test samples isolated: {len(test_ds)}")

print("Loading GraphCodeBERT model...")
if not args.gcb_dfg_weights or not os.path.exists(args.gcb_dfg_weights):
    print("Please set args.gcb_dfg_weights")
    model = None
else:
    config = RobertaConfig.from_pretrained("microsoft/graphcodebert-base")
    config.num_labels = 2
    encoder = RobertaModel.from_pretrained("microsoft/graphcodebert-base", config=config)
    model = DFGModel(encoder, config)
    model.load_state_dict(torch.load(args.gcb_dfg_weights, map_location=args.device))
    model.to(args.device)
    model.eval()
    print("Model loaded successfully!")

if model:
    eval_sampler = SequentialSampler(test_ds)
    eval_dataloader = DataLoader(test_ds, sampler=eval_sampler, batch_size=args.eval_batch_size, num_workers=2)

    all_preds = []
    all_labels = []
    all_probs = []
    all_indices = []

    print("Running inference on test set...")
    with torch.no_grad():
        for batch in tqdm(eval_dataloader, desc="Evaluating"):
            input_ids = batch['input_ids'].to(args.device)
            p_ids = batch['p_ids'].to(args.device)
            attn_mask = batch['attn_mask'].to(args.device)
            labels = batch['label'].to(args.device)
            indices = batch['index']
            
            probs = model(input_ids=input_ids, p_ids=p_ids, attn_mask=attn_mask)
            preds = torch.argmax(probs, dim=-1)
            
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            all_probs.extend(probs[:, 1].cpu().numpy())
            all_indices.extend(indices.numpy())

if model:
    false_negatives = []

    for i, (pred, label, prob, raw_idx) in enumerate(zip(all_preds, all_labels, all_probs, all_indices)):
        if label == 1 and pred == 0:
            raw_line = test_ds.lines[raw_idx]
            raw_data = json.loads(raw_line)
            
            false_negatives.append({
                'index': raw_idx,
                'confidence_safe': 1.0 - prob,
                'code': raw_data.get('code', 'N/A'),
                'project': raw_data.get('filename', 'Unknown')
            })

    print(f"\nTotal False Negatives Found in Test Set: {len(false_negatives)}")

    false_negatives.sort(key=lambda x: x['confidence_safe'], reverse=True)

    print("\n======================================================")
    print("Analyzing the Top 20 Most Confident False Negatives:")
    print("======================================================\n")

    for i, fn in enumerate(false_negatives[:20]):
        print(f"[False Negative #{i+1}] - Originally from '{fn['project']}'")
        print(f"Model Confidence it was SAFE: {fn['confidence_safe'] * 100:.2f}%")
        print("-" * 40)
        lines = fn['code'].split('\n')
        
        max_lines = 35
        print('\n'.join(lines[:max_lines]))
        if len(lines) > max_lines:
            print(f"... [Truncated {len(lines) - max_lines} more lines]")
        print("=" * 60 + "\n")
