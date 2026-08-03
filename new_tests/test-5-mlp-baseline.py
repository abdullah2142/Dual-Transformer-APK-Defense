!pip install scikit-learn matplotlib -q

import os, json, random, math, hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score, roc_auc_score,
    average_precision_score, f1_score,
    classification_report, confusion_matrix
)
from collections import defaultdict

random.seed(42)
np.random.seed(42)
print('Imports OK')

# Configuration
DATA_FILE    = '/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl'
TEST2_OUT    = '/kaggle/working/test2_auc_results.txt'
OUT_DIR      = '/kaggle/working'
TEST_RATIO   = 0.10
VAL_RATIO    = 0.08
SEED         = 42
MAX_FEATURES = 50_000
NGRAM_RANGE  = (1, 3)
ANALYZER     = 'char_wb'  # character n-grams perform best on code
print(f'Data: {DATA_FILE}')
print('Split: 82/8/10 (stratified)')

# ─── STRATIFIED SPLIT ─────────────────────────────────────────────────────────
def infer_source(entry):
    for key in ("source", "dataset", "origin", "project"):
        value = entry.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return "unknown"

def allocate_counts(total_needed, groups, fraction):
    raw = {g: len(v) * fraction for g, v in groups.items()}
    base = {g: int(math.floor(v)) for g, v in raw.items()}
    remainder = total_needed - sum(base.values())
    order = sorted(groups.keys(), key=lambda g: (raw[g] - base[g], len(groups[g])), reverse=True)
    for g in order[:remainder]:
        base[g] += 1
    return base

def get_stratified_indices(filepath, test_ratio=0.10, val_ratio=0.08, seed=42):
    """Returns (train, val, test, code_hashes).

    Streams the file rather than materialising all 199,960 entries: each record
    carries a large `dfg` array that is irrelevant here, and holding them all is
    a needless multi-GB spike on top of the TF-IDF matrices built later. The
    code hashes are collected in the same pass for the duplicate filter below.
    """
    srcs, hashes = [], []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            entry = json.loads(line)
            srcs.append(infer_source(entry))
            hashes.append(hashlib.md5(
                str(entry.get('code', '')).encode('utf-8', 'ignore')).hexdigest())
            del entry

    rng = random.Random(seed)
    source_to_indices = defaultdict(list)
    for idx, s in enumerate(srcs):
        source_to_indices[s].append(idx)

    for indices in source_to_indices.values():
        rng.shuffle(indices)

    total = len(srcs)
    target_test = int(round(total * test_ratio))
    target_val = int(round(total * val_ratio))
    target_train = total - target_test - target_val

    test_alloc = allocate_counts(target_test, source_to_indices, test_ratio)
    trainval_groups = {}
    test_indices = []
    for source, indices in source_to_indices.items():
        take = min(test_alloc[source], len(indices))
        test_indices.extend(indices[:take])
        trainval_groups[source] = indices[take:]

    adjusted_val_ratio = val_ratio / (1.0 - test_ratio)
    val_alloc = allocate_counts(target_val, trainval_groups, adjusted_val_ratio)

    val_indices, train_indices = [], []
    for source, indices in trainval_groups.items():
        take = min(val_alloc[source], len(indices))
        val_indices.extend(indices[:take])
        train_indices.extend(indices[take:])

    return sorted(train_indices), sorted(val_indices), sorted(test_indices), hashes

print("Building split (matches training partition) with fixed seed=42...")
train_indices, val_indices, test_indices, code_hashes = get_stratified_indices(
    DATA_FILE, TEST_RATIO, VAL_RATIO, SEED)
print(f"Train: {len(train_indices):,}, Val: {len(val_indices):,}, Test: {len(test_indices):,}")

# ─── LOAD DATASET ─────────────────────────────────────────────────────────────
print('Loading dataset...')
texts, labels = [], []
with open(DATA_FILE, encoding='utf-8', errors='replace') as f:
    all_lines = f.readlines()

for line in all_lines:
    line = line.strip()
    if not line: continue
    try:
        entry = json.loads(line)
        texts.append(entry.get('code', ''))
        labels.append(int(entry.get('label', 0)))
    except Exception:
        texts.append('')
        labels.append(0)

texts  = np.array(texts,  dtype=object)
labels = np.array(labels, dtype=int)

# Combine train and val for TF-IDF training (so we evaluate only on the 10% test)
train_val_idx = train_indices + val_indices

# ─── DUPLICATE FILTER ─────────────────────────────────────────────────────────
# Drops test entries whose code is byte-identical to a train/val entry. Without
# this the TF-IDF baselines are credited for samples they were fitted on, which
# would flatter them relative to the transformers. Hashes come from the split
# pass above, so there is no extra read. See REMEDIATION_PLAN.md 5.1.
_seen = {code_hashes[i] for i in train_val_idx}
_before = len(test_indices)
test_indices = [i for i in test_indices if code_hashes[i] not in _seen]
_dropped = _before - len(test_indices)
print(f'Duplicate filter: dropped {_dropped:,} ({_dropped/_before:.2%}) test entries '
      f'byte-identical to a train/val sample -> {len(test_indices):,} clean')

X_train, y_train = texts[train_val_idx], labels[train_val_idx]
X_test,  y_test  = texts[test_indices],  labels[test_indices]

print(f'Total samples  : {len(texts):,}')
print(f'Train+Val      : {len(X_train):,}  |  Test: {len(X_test):,}')
print(f'Test class balance: {y_test.mean():.4f}')

# ─── BASELINE 1: Logistic Regression + TF-IDF ─────────────────────────────────
print('Training LR + TF-IDF  (vectorizer fit ~5-10 min)...')
pipeline_lr = Pipeline([
    ('tfidf', TfidfVectorizer(
        analyzer=ANALYZER,
        ngram_range=NGRAM_RANGE,
        max_features=MAX_FEATURES,
        sublinear_tf=True,
        min_df=5,
        strip_accents='unicode',
    )),
    ('clf', LogisticRegression(
        C=1.0, max_iter=1000, solver='saga',
        n_jobs=-1, random_state=SEED,
    ))
])
pipeline_lr.fit(X_train, y_train)
print('  ✓ LR done')

# ─── EVALUATE LR ──────────────────────────────────────────────────────────────
y_pred_lr = pipeline_lr.predict(X_test)
y_prob_lr = pipeline_lr.predict_proba(X_test)[:, 1]
acc_lr    = accuracy_score(y_test, y_pred_lr)
auc_lr    = roc_auc_score(y_test, y_prob_lr)
pr_lr     = average_precision_score(y_test, y_prob_lr)
f1_lr     = f1_score(y_test, y_pred_lr)
fn_lr     = confusion_matrix(y_test, y_pred_lr)[1, 0]
print(f'\nLogistic Regression + TF-IDF')
print(f'  Accuracy : {acc_lr:.4%}')
print(f'  ROC-AUC  : {auc_lr:.4f}')
print(f'  PR-AUC   : {pr_lr:.4f}')
print(f'  F1       : {f1_lr:.4f}')
print(f'  FN (missed malware): {fn_lr:,}')
print()
print(classification_report(y_test, y_pred_lr, target_names=['safe','malicious']))

# ─── BASELINE 2: MLP + TF-IDF ─────────────────────────────────────────────────
print('Transforming features (reusing fitted TF-IDF)...')
vectorizer    = pipeline_lr.named_steps['tfidf']
X_train_vec   = vectorizer.transform(X_train)
X_test_vec    = vectorizer.transform(X_test)
print(f'  Feature matrix: {X_train_vec.shape}')

print('Training MLP 512->256  (~10-15 min on CPU)...')
mlp = MLPClassifier(
    hidden_layer_sizes=(512, 256),
    activation='relu',
    max_iter=30,
    batch_size=256,
    learning_rate_init=1e-3,
    early_stopping=True,
    validation_fraction=0.05,
    n_iter_no_change=5,
    verbose=True,
    random_state=SEED,
)
mlp.fit(X_train_vec, y_train)
print('  ✓ MLP done')

# ─── EVALUATE MLP ─────────────────────────────────────────────────────────────
y_pred_mlp = mlp.predict(X_test_vec)
y_prob_mlp = mlp.predict_proba(X_test_vec)[:, 1]
acc_mlp    = accuracy_score(y_test, y_pred_mlp)
auc_mlp    = roc_auc_score(y_test, y_prob_mlp)
pr_mlp     = average_precision_score(y_test, y_prob_mlp)
f1_mlp     = f1_score(y_test, y_pred_mlp)
fn_mlp     = confusion_matrix(y_test, y_pred_mlp)[1, 0]

print(f'\nMLP (512-256) + TF-IDF')
print(f'  Accuracy : {acc_mlp:.4%}')
print(f'  ROC-AUC  : {auc_mlp:.4f}')
print(f'  PR-AUC   : {pr_mlp:.4f}')
print(f'  F1       : {f1_mlp:.4f}')
print(f'  FN (missed malware): {fn_mlp:,}')
print()
print(classification_report(y_test, y_pred_mlp, target_names=['safe','malicious']))

# ─── EXTRACT TRANSFORMER RESULTS ──────────────────────────────────────────────
# We try to extract results from Test 2. If it hasn't run, we use placeholders.
transformer_results = []
if os.path.exists(TEST2_OUT):
    print(f"Loading transformer results from {TEST2_OUT}")
    with open(TEST2_OUT, 'r') as f:
        lines = f.readlines()
        for line in lines:
            if ":" in line and "Acc=" in line:
                name = line.split(":")[0].strip()
                parts = line.split(",")
                acc = float(parts[0].split("=")[1])
                roc = float(parts[1].split("=")[1])
                pr = float(parts[2].split("=")[1])
                # We don't have F1 and FN from Test 2's summary txt directly, use 0 or dummy
                transformer_results.append((name, acc, roc, pr, 0.0, 0))
else:
    print(f"{TEST2_OUT} not found. Using placeholders.")
    transformer_results = [
        ('GraphCodeBERT (DFG)',  0.0, 0.0, 0.0, 0.0, 0),
        ('GraphCodeBERT (Text)', 0.0, 0.0, 0.0, 0.0, 0),
        ('CodeBERT (DFG)',       0.0, 0.0, 0.0, 0.0, 0),
        ('CodeBERT (Text)',      0.0, 0.0, 0.0, 0.0, 0),
        ('UniXcoder (DFG)',      0.0, 0.0, 0.0, 0.0, 0),
        ('UniXcoder (Text)',     0.0, 0.0, 0.0, 0.0, 0),
    ]

REF = [
    ('LR + TF-IDF',  acc_lr,  auc_lr,  pr_lr,  f1_lr,  fn_lr),
    ('MLP + TF-IDF', acc_mlp, auc_mlp, pr_mlp, f1_mlp, fn_mlp),
] + transformer_results

print(f'\n{"Method":<30} {"Acc":>8} {"ROC-AUC":>9} {"PR-AUC":>8} {"F1":>7} {"FN":>6}')
print('-'*75)
for nm, acc, auc_, pr, f1, fn in REF:
    fn_s = f'{int(fn):,}' if fn else '    -'
    print(f'{nm:<30} {acc:>8.4%} {auc_:>9.4f} {pr:>8.4f} {f1:>7.4f} {fn_s:>6}')

# ─── BAR CHART ────────────────────────────────────────────────────────────────
labels_plot = [r[0].replace(' (','\n(').replace(' + ','+\n') for r in REF]
vals_acc    = [r[1] for r in REF]
vals_auc    = [r[2] for r in REF]

x = np.arange(len(labels_plot))
w = 0.35
fig, ax = plt.subplots(figsize=(14, 6))

b1 = ax.bar(x - w/2, vals_acc, w, label='Accuracy', color='#4C72B0', alpha=0.88)
b2 = ax.bar(x + w/2, vals_auc, w, label='ROC-AUC', color='#55A868', alpha=0.88)

for bar in list(b1) + list(b2):
    ax.annotate(f'{bar.get_height():.3f}',
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 4), textcoords='offset points',
                ha='center', va='bottom', fontsize=8)

ax.set_ylim(0.0, 1.1)
ax.set_xticks(x)
ax.set_xticklabels(labels_plot, fontsize=9, rotation=15, ha='right')
ax.set_ylabel('Score', fontsize=12)
ax.set_title('Accuracy & ROC-AUC: TF-IDF Baselines vs All 6 Transformer Models', fontsize=14)
ax.legend(fontsize=11, loc='lower right')
ax.yaxis.grid(True, alpha=0.3)
ax.set_axisbelow(True)

ax.axvspan(-0.5, 1.5, alpha=0.07, color='red')
ax.text(0.5, 1.05, 'Baselines', ha='center', fontsize=10, color='#880000',
        transform=ax.get_xaxis_transform())

plt.tight_layout()
out_img = '/kaggle/working/test6_baseline_bar.png'
fig.savefig(out_img, dpi=150)
plt.close()
print(f'Saved -> {out_img}')

# ─── SAVE RESULTS TXT ─────────────────────────────────────────────────────────
out_txt = '/kaggle/working/test6_baseline_results.txt'
with open(out_txt, 'w') as fh:
    fh.write('Test 6: MLP / TF-IDF Baseline Results\n')
    fh.write('=' * 60 + '\n')
    for nm, acc, auc_, pr, f1, fn in REF:
        fn_s = f'{int(fn):,}' if fn else '-'
        fh.write(f'\n{nm}\n')
        fh.write(f'  Accuracy : {acc:.4%}\n')
        fh.write(f'  ROC-AUC  : {auc_:.4f}\n')
        fh.write(f'  PR-AUC   : {pr:.4f}\n')
        fh.write(f'  F1       : {f1:.4f}\n')
        fh.write(f'  FN       : {fn_s}\n')

print(f'Saved -> {out_txt}')
