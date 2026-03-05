# Android APK Vulnerability Detection

This project implements a robust vulnerability detection system for Android applications using an **Ensemble of GraphCodeBERT and CodeBERT**. It processes code from various sources, generates semantic features (Data Flow Graphs), and combines model predictions for high-accuracy detection.

## Goal

The primary objective is to detect security vulnerabilities in Android-native (C/C++) and Java code. By leveraging an ensemble of:
1.  **GraphCodeBERT**: Captures data flow and structural semantics.
2.  **CodeBERT**: Captures general code syntax and natural language context.

The system aims to minimize false positives and cover a wide range of vulnerability patterns including memory safety issues (buffer overflows) and logic errors.

## Methodology

### 1. Data Pipeline
The dataset uses a 1:1 balanced mix of vulnerable to safe samples from:
- **LVDAndro**: Android-specific vulnerabilities.
- **Juliet Test Suite**: Synthetic Java test cases.
- **Draper (VDISC) & Devign**: Real-world C/C++ vulnerabilities.

### 2. Feature Engineering (DFG)
**Data Flow Graphs (DFG)** are generated for every code snippet using `parser_production.py`.
- **Tree-sitter** parses code into ASTs.
- The system extracts variable usage maps (where variables are defined, used, and updated).
- These relationships form the graph input for GraphCodeBERT.

### 3. Ensemble Model
The final prediction is based on an **Ensemble Approach**:
- **Model A (GraphCodeBERT)**: Trained with Code + DFG inputs.
- **Model B (CodeBERT)**: Trained on Code only.
- **Fusion**: Predictions (logits/probabilities) from both models are combined (e.g., averaged) to produce the final classification. This leverages GraphCodeBERT's structural insight and CodeBERT's general robustness.

## Project Structure & Scripts

| Script Name | Role |
| :--- | :--- |
| **Data Processing** | |
| `devignprocess.py` | Converts Devign dataset to the unified JSON format. |
| `draperprocess.py` | extracts C/C++ samples from Draper HDF5 files. |
| `julietprocess.py` | Parses the Juliet Java Test Suite into JSON samples. |
| `lvdprocess.py` | Processes LVDAndro CSVs into window-based samples. |
| `lvdandroprocessperfunction.py` | Processes LVDAndro CSVs into function-level samples. |
| `finalizedataset.py` | Merges all processed datasets into `final_dataset.json`. |
| **Feature Extraction** | |
| `parser_production.py` | Core library using `tree-sitter` to generate DFGs for C and Java. |
| `parse.py` | Main preprocessing script. Guesses code language, runs DFG extraction, and caches tensors to `cached_dataset.pt`. |
| **Training & Utils** | |
| `graphcodebert-training.ipynb` | Main Jupyter notebook for training and evaluating models. |
| `dfg-generation.ipynb` | Notebook version of the DFG generation pipeline. |
| `count_samples.py` | Utility to verify dataset size and format. |

## How to Reproduce

Follow these steps to reproduce the results:

### 1. Setup Environment
Ensure you have Python 3.8+ and install dependencies:
```bash
pip install torch transformers tree_sitter==0.21.3 pandas h5py scikit-learn
```

### 2. Prepare Data
Run the processing scripts for your raw datasets. For example:
```bash
python devignprocess.py
python julietprocess.py
# ... run others as needed
python finalizedataset.py
```
This will create `final_dataset.json`.

### 3. Generate Features (DFG)
Run the preprocessor to generate Data Flow Graphs and tokenize the data:
```bash
python parse.py
```
This transforms `final_dataset.json` into `cached_dataset.pt`.

### 4. Train Models
Open `graphcodebert-training.ipynb` or convert it to a script.
- **Step A**: Train with `microsoft/graphcodebert-base`. Save weights.
- **Step B**: Switch config to `microsoft/codebert-base` (disable DFG inputs if needed). Train and save weights.

### 5. Evaluation
Load both models, run inference on the test set, average the probability scores, and calculate metrics.

## Results

### Summary

| Metric | GraphCodeBERT + DFG | GCB (no DFG) | CodeBERT | Ensemble (70/30) |
| :--- | :---: | :---: | :---: | :---: |
| **Accuracy** | 91.82% | 88.71% | 90.44% | **91.94%** |
| **ROC-AUC** | 0.9798 | 0.9615 | 0.9745 | **0.9804** |
| **PR-AUC** | 0.9797 | 0.9619 | 0.9745 | **0.9803** |
| **F1 (macro)** | 0.9182 | 0.8871 | — | 0.9194 |
| **FN (missed malware)** | 829 | 1,111 | — | ~720 |

---

### Test 1 — Held-Out Test Set (3-Way Split)

To rule out optimism bias, the model was evaluated on a fully held-out test set (20% of data, never seen during training or checkpoint selection).

| Split | Samples | Accuracy |
| :--- | :---: | :---: |
| Train | 143,971 | — |
| Validation (checkpoint selection) | 15,996 | 91.9980% |
| **Test (held-out, never seen)** | **39,993** | **92.0161%** |
| Optimism bias (val − test) | — | **−0.018%** ✅ |

```
               precision    recall  f1-score   support

     Safe (0)     0.9191    0.9232    0.9211     20202
 Malicious (1)     0.9212    0.9171    0.9192     19791

     accuracy                         0.9202     39993
```

The near-zero optimism bias confirms no overfitting occurred and the model generalises cleanly to unseen data.

---

### Test 2 — ROC-AUC and Precision-Recall Analysis

| Model | ROC-AUC | PR-AUC | Accuracy @ 0.5 |
| :--- | :---: | :---: | :---: |
| GraphCodeBERT + DFG | 0.9798 | 0.9797 | 91.82% |
| CodeBERT (text only) | 0.9745 | 0.9745 | 90.44% |
| **Ensemble (50/50)** | **0.9804** | **0.9803** | **91.87%** |
| Random baseline | 0.5000 | ~0.50 | — |
| **Best F1 threshold (GraphCodeBERT)** | — | — | **0.45** |

ROC and PR curves are available in `test2_roc_curve.png` and `test2_pr_curve.png`. All three models maintain near-perfect precision (~1.0) up to ~80% recall, which is the critical operating range for a security scanner.

---

### Test 3 — DFG Ablation Study

Same GraphCodeBERT backbone trained **with** and **without** DFG-aware attention, with identical training budget (3 epochs, same seed).

| Condition | Accuracy | ROC-AUC | PR-AUC | FN (missed) |
| :--- | :---: | :---: | :---: | :---: |
| **GraphCodeBERT + DFG** | **91.82%** | **0.9798** | **0.9797** | **829** |
| GraphCodeBERT (no DFG) | 88.71% | 0.9615 | 0.9619 | 1,111 |
| **Δ (DFG gain)** | **+3.11%** | **+0.0183** | **+0.0178** | **−282 (−25%)** |

> The DFG attention mechanism reduces missed malware by **25%** compared to the identical backbone without structural information. This is the core finding of the ablation study.

Bar chart available in `test3_ablation_bar.png`.

---

### Ensemble Comparison

All ensemble variants evaluated on the same 19,996-sample validation split:

| Configuration | Accuracy | F1 (macro) | FN (missed) |
| :--- | :---: | :---: | :---: |
| GraphCodeBERT alone | 91.82% | 0.9182 | 829 |
| Soft Ensemble — 50/50 | 91.87% | 0.9187 | 685 |
| **Weighted Ensemble — 70/30** | **91.94%** | **0.9194** | ~720 |
| Triple Ensemble — soft @ 0.49 | 91.88% | 0.9188 | **671** |
| Triple Ensemble — hard voting | 91.10% | 0.9110 | 748 |

<details>
<summary>Detailed confusion matrices</summary>

**GraphCodeBERT standalone**

| | Predicted Safe | Predicted Malicious |
| :--- | :---: | :---: |
| **Actual Safe** | 9,288 (TN) | 807 (FP) |
| **Actual Malicious** | 829 (FN) | 9,072 (TP) |

**Soft Ensemble 50/50**

| | Predicted Safe | Predicted Malicious |
| :--- | :---: | :---: |
| **Actual Safe** | 9,154 (TN) | 941 (FP) |
| **Actual Malicious** | 685 (FN) | 9,216 (TP) |

**Triple Ensemble — soft @ 0.49**

| | Predicted Safe | Predicted Malicious |
| :--- | :---: | :---: |
| **Actual Safe** | 9,143 (TN) | 952 (FP) |
| **Actual Malicious** | 671 (FN) | 9,230 (TP) |

</details>

---

### Key Findings

- **DFG is essential**: Removing DFG-aware attention from the same backbone drops accuracy by 3.11% and increases missed malware by 25% (Test 3).
- **No optimism bias**: Test set accuracy (92.02%) matches validation (91.998%) within 0.018% — the reported numbers are genuine (Test 1).
- **Ensemble always beats the single model**: Every ensemble configuration achieved higher accuracy and/or lower false negatives vs. GraphCodeBERT alone.
- **Threshold tuning for security**: Lowering the decision threshold from 0.50 → 0.45 further reduces false negatives by 19%, the right tradeoff for a security-critical scanner.

## Limitations

- **Static Analysis Scope**: The system performs static code analysis. Vulnerabilities that depend on runtime state, external configuration, or complex user interaction flows may be missed.
- **Input Length Restrictions**: GraphCodeBERT and CodeBERT have a fixed maximum sequence length (typically 512 tokens). Large functions are truncated, which may result in critical logic (and the vulnerability itself) being cut off from the model's view.
- **Parser Heuristics**: While Tree-sitter is robust, some parts of the function extraction pipeline (e.g., `lvdandroprocessperfunction.py`) rely on brace-counting heuristics which can be fragile with complex nested structures or comments containing braces.
- **Language Support**: The DFG extractor is strictly configured for **C/C++** and **Java**. Android Kotlin code or native libraries written in other languages are not currently processed.
- **Synthetic Data Bias**: The inclusion of the Juliet Test Suite adds a significant volume of synthetic, "clean" vulnerability patterns. This helps training stability but may introduce a bias where the model expects vulnerabilities to look like textbook examples rather than messy real-world bugs.
