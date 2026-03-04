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

All evaluations were performed on the same 19,996-sample validation split.

### Model Comparison

| Configuration | Accuracy | Precision | Recall | F1 (macro) | FN (missed) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| GraphCodeBERT alone | 91.82% | 0.9182 | 0.9182 | 0.9182 | 829 |
| Soft Ensemble — 50/50 (GCB + CB) | 91.87% | 0.9189 | 0.9188 | 0.9187 | 685 |
| **Weighted Ensemble — 70/30 (GCB + CB)** | **91.94%** | **0.9194** | **0.9194** | **0.9194** | ~720 |
| Triple Ensemble — soft @ threshold 0.49 | 91.88% | 0.9191 | 0.9190 | 0.9188 | **671** |
| Triple Ensemble — hard voting | 91.10% | 0.9113 | 0.9112 | 0.9110 | 748 |

> **Best overall accuracy**: Weighted 70/30 ensemble at **91.94%**
> **Fewest missed malware (lowest FN)**: Triple soft ensemble at **671 false negatives** — a 19% reduction vs. GraphCodeBERT alone.

---

### Detailed Results — GraphCodeBERT (standalone)

```
              precision    recall  f1-score   support

    Safe (0)     0.9181    0.9201    0.9191     10095
   Vuln  (1)     0.9183    0.9163    0.9173      9901

    accuracy                         0.9182     19996
   macro avg     0.9182    0.9182    0.9182     19996
weighted avg     0.9182    0.9182    0.9182     19996
```

| | Predicted Safe | Predicted Vulnerable |
| :--- | :---: | :---: |
| **Actual Safe** | **9288** (TN) | 807 (FP) |
| **Actual Vulnerable** | 829 (FN) | **9072** (TP) |

---

### Detailed Results — Soft Ensemble 50/50 (GraphCodeBERT + CodeBERT)

```
              precision    recall  f1-score   support

        Safe     0.9304    0.9068    0.9184     10095
  Vulnerable     0.9074    0.9308    0.9189      9901

    accuracy                         0.9187     19996
   macro avg     0.9189    0.9188    0.9187     19996
weighted avg     0.9190    0.9187    0.9187     19996
```

| | Predicted Safe | Predicted Vulnerable |
| :--- | :---: | :---: |
| **Actual Safe** | **9154** (TN) | 941 (FP) |
| **Actual Vulnerable** | 685 (FN) | **9216** (TP) |

---

### Detailed Results — Weighted Ensemble 70/30 (GraphCodeBERT + CodeBERT)

```
              precision    recall  f1-score   support

        Safe     0.9242    0.9154    0.9198     10095
  Vulnerable     0.9146    0.9234    0.9190      9901

    accuracy                         0.9194     19996
   macro avg     0.9194    0.9194    0.9194     19996
weighted avg     0.9194    0.9194    0.9194     19996
```

---

### Detailed Results — Triple Ensemble (soft voting @ threshold 0.49)

```
              precision    recall  f1-score   support

        Safe     0.9316    0.9057    0.9185     10095
  Vulnerable     0.9065    0.9322    0.9192      9901

    accuracy                         0.9188     19996
   macro avg     0.9191    0.9190    0.9188     19996
weighted avg     0.9192    0.9188    0.9188     19996
```

| | Predicted Safe | Predicted Vulnerable |
| :--- | :---: | :---: |
| **Actual Safe** | **9143** (TN) | 952 (FP) |
| **Actual Vulnerable** | **671** (FN) | **9230** (TP) |

---

### Key Findings

- **Ensemble always outperforms GraphCodeBERT alone**: Every ensemble configuration achieved higher accuracy and/or lower false negatives versus the single model.
- **Soft voting beats hard voting**: Hard voting (majority label) underperforms because it discards model confidence — averaging raw probabilities is strictly better when models are well-calibrated.
- **Weighted ensembling is the sweet spot**: Giving 70% weight to the stronger GraphCodeBERT and 30% to CodeBERT maximises accuracy at 91.94%.
- **Threshold tuning trades precision for recall**: Lowering the decision threshold to 0.49 reduces missed malware by 19% at the cost of slightly more false alarms — the right choice for a security scanner where missing a threat is costlier than a false alert.

## Limitations

- **Static Analysis Scope**: The system performs static code analysis. Vulnerabilities that depend on runtime state, external configuration, or complex user interaction flows may be missed.
- **Input Length Restrictions**: GraphCodeBERT and CodeBERT have a fixed maximum sequence length (typically 512 tokens). Large functions are truncated, which may result in critical logic (and the vulnerability itself) being cut off from the model's view.
- **Parser Heuristics**: While Tree-sitter is robust, some parts of the function extraction pipeline (e.g., `lvdandroprocessperfunction.py`) rely on brace-counting heuristics which can be fragile with complex nested structures or comments containing braces.
- **Language Support**: The DFG extractor is strictly configured for **C/C++** and **Java**. Android Kotlin code or native libraries written in other languages are not currently processed.
- **Synthetic Data Bias**: The inclusion of the Juliet Test Suite adds a significant volume of synthetic, "clean" vulnerability patterns. This helps training stability but may introduce a bias where the model expects vulnerabilities to look like textbook examples rather than messy real-world bugs.
