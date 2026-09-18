import pandas as pd
import re
import os
from pathlib import Path
from collections import Counter

# ============================================================
# QUESTION 2 - SETUBID NOTICE DEDUPLICATION
# Initial corpus and labelled-pair analysis
# ============================================================

BASE = Path(__file__).resolve().parent.parent

# labelled_pairs.csv is in the project root
LABEL_FILE = BASE / "labelled_pairs.csv"

print("=" * 65)
print("SETUBID - QUESTION 2 ANALYSIS")
print("=" * 65)

# ------------------------------------------------------------
# 1. LOAD LABELLED PAIRS
# ------------------------------------------------------------

if not LABEL_FILE.exists():
    raise FileNotFoundError(
        f"Cannot find: {LABEL_FILE}\n"
        "Make sure labelled_pairs.csv is in the project root."
    )

df = pd.read_csv(LABEL_FILE)

print("\nLABELLED PAIRS")
print("-" * 65)
print("Rows:", len(df))
print("Columns:", list(df.columns))

# ------------------------------------------------------------
# 2. IDENTIFY LABEL COLUMN
# ------------------------------------------------------------

possible_labels = [
    c for c in df.columns
    if c.lower() in ["label", "match", "same", "decision", "is_same"]
]

if possible_labels:
    label_col = possible_labels[0]
else:
    # Exam dataset places the label in the final column
    label_col = df.columns[-1]

print("Label column:", label_col)

# ------------------------------------------------------------
# 3. LABEL DISTRIBUTION
# ------------------------------------------------------------

counts = df[label_col].value_counts(dropna=False)
percentages = df[label_col].value_counts(
    normalize=True,
    dropna=False
).mul(100).round(2)

print("\nLABEL DISTRIBUTION")
print("-" * 65)

for label in counts.index:
    print(
        f"{label}: {counts[label]} "
        f"({percentages[label]}%)"
    )

# ------------------------------------------------------------
# 4. BASIC NOTICE TEXT NORMALISATION
# ------------------------------------------------------------

def normalize_text(text):
    if pd.isna(text):
        return ""

    text = str(text).lower()

    # remove URLs
    text = re.sub(r"https?://\S+", " ", text)

    # remove reference numbers
    text = re.sub(
        r"\b(?:ref|reference|tender|nit|bid|notice)[\s:/#-]*"
        r"[a-z0-9/-]*\d[a-z0-9/-]*\b",
        " ",
        text,
    )

    # remove dates
    text = re.sub(
        r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b",
        " ",
        text,
    )

    # remove monetary values
    text = re.sub(
        r"(?:₹|rs\.?|inr|\$)\s*[\d,]+(?:\.\d+)?",
        " ",
        text,
    )

    # keep words
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ------------------------------------------------------------
# 5. TOKEN / SHINGLE REPRESENTATIONS
# ------------------------------------------------------------

def word_tokens(text):
    return normalize_text(text).split()


def word_shingles(text, k=3):
    tokens = word_tokens(text)

    if len(tokens) < k:
        return set(tokens)

    return {
        " ".join(tokens[i:i+k])
        for i in range(len(tokens) - k + 1)
    }


def jaccard(a, b):
    if not a and not b:
        return 1.0

    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


# ------------------------------------------------------------
# 6. REPORT REPRESENTATION CHOICES
# ------------------------------------------------------------

print("\nREPRESENTATION DESIGN")
print("-" * 65)
print("Choice 1: word-level 3-shingles")
print("Choice 2: character-level 5-grams")
print("Noise removed: portal URLs, reference numbers, dates,")
print("and monetary formatting.")
print("Signal retained: procurement wording and descriptive terms.")

# ------------------------------------------------------------
# 7. FIND POSSIBLE TEXT COLUMNS
# ------------------------------------------------------------

text_columns = [
    c for c in df.columns
    if any(x in c.lower() for x in ["title", "body", "text", "notice"])
]

print("\nTEXT COLUMNS FOUND:", text_columns)

# ------------------------------------------------------------
# 8. IF PAIRS CONTAIN NOTICE TEXT, MEASURE SAMPLE PAIRS
# ------------------------------------------------------------

if len(text_columns) >= 2:

    c1, c2 = text_columns[:2]

    scores = []

    for _, row in df.iterrows():

        a = word_shingles(row[c1], 3)
        b = word_shingles(row[c2], 3)

        score = jaccard(a, b)

        scores.append(score)

    df["similarity_3gram"] = scores

    print("\nSIMILARITY MEASUREMENT")
    print("-" * 65)

    print(
        df.groupby(label_col)["similarity_3gram"]
        .agg(["count", "mean", "min", "max"])
        .round(4)
    )

else:
    print("\nNotice text is not contained directly in labelled_pairs.csv.")
    print("The labelled file will be used as the evaluation source.")

# ------------------------------------------------------------
# 9. SAVE ANALYSIS
# ------------------------------------------------------------

OUTPUT = BASE / "output"
OUTPUT.mkdir(exist_ok=True)

summary = pd.DataFrame({
    "label": counts.index.astype(str),
    "count": counts.values,
    "percentage": [
        percentages[x] for x in counts.index
    ]
})

summary.to_csv(
    OUTPUT / "q2_label_distribution.csv",
    index=False
)

print("\nSaved:")
print(OUTPUT / "q2_label_distribution.csv")

print("\n" + "=" * 65)
print("Q2 INITIAL ANALYSIS COMPLETE")
print("=" * 65)