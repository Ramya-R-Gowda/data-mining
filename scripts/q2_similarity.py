import pandas as pd
import re
from pathlib import Path
from itertools import combinations

BASE = Path(__file__).resolve().parent.parent

LABEL_FILE = BASE / "labelled_pairs.csv"
NOTICE_DIR = BASE / "notices"

print("=" * 70)
print("SETUBID Q2-A - SIMILARITY COMPARISON")
print("=" * 70)

# ------------------------------------------------------------
# LOAD LABELLED PAIRS
# ------------------------------------------------------------
pairs = pd.read_csv(LABEL_FILE)

# ------------------------------------------------------------
# LOAD ALL PARQUET NOTICE FILES
# ------------------------------------------------------------
files = list(NOTICE_DIR.glob("*.parquet"))

if not files:
    raise FileNotFoundError(
        f"No parquet files found in {NOTICE_DIR}"
    )

notices = pd.concat(
    [pd.read_parquet(f) for f in files],
    ignore_index=True
)

print("\nNotices loaded:", len(notices))
print("Notice columns:", list(notices.columns))

# ------------------------------------------------------------
# PREPARE NOTICE TEXT
# ------------------------------------------------------------
notices["notice_id"] = notices["notice_id"].astype(str)

notices["text"] = (
    notices["title"].fillna("").astype(str)
    + " "
    + notices["body"].fillna("").astype(str)
)

notice_map = notices.set_index("notice_id")["text"].to_dict()


# ------------------------------------------------------------
# NORMALISATION
# ------------------------------------------------------------
def normalize(text, remove_numbers=True):
    text = str(text).lower()

    # URLs
    text = re.sub(r"https?://\S+", " ", text)

    # Reference numbers
    text = re.sub(
        r"\b(?:ref|reference|tender|nit|bid|notice)[\s:/#-]*"
        r"[a-z0-9/-]*\d[a-z0-9/-]*\b",
        " ",
        text
    )

    # Dates
    text = re.sub(
        r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b",
        " ",
        text
    )

    # Money
    text = re.sub(
        r"(?:₹|rs\.?|inr|\$)\s*[\d,]+(?:\.\d+)?",
        " ",
        text
    )

    if remove_numbers:
        text = re.sub(r"\b\d+\b", " ", text)

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ------------------------------------------------------------
# WORD SHINGLES
# ------------------------------------------------------------
def word_shingles(text, k=3):
    words = normalize(text).split()

    if len(words) <= k:
        return set(words)

    return {
        " ".join(words[i:i+k])
        for i in range(len(words) - k + 1)
    }


# ------------------------------------------------------------
# CHARACTER N-GRAMS
# ------------------------------------------------------------
def char_ngrams(text, n=5):
    text = normalize(text)

    if len(text) <= n:
        return {text}

    return {
        text[i:i+n]
        for i in range(len(text) - n + 1)
    }


# ------------------------------------------------------------
# JACCARD SIMILARITY
# ------------------------------------------------------------
def jaccard(a, b):
    if not a and not b:
        return 1.0

    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


# ------------------------------------------------------------
# COMPARE LABELLED PAIRS
# ------------------------------------------------------------
results = []

for _, row in pairs.iterrows():

    a = notice_map.get(str(row["notice_id_a"]), "")
    b = notice_map.get(str(row["notice_id_b"]), "")

    word_score = jaccard(
        word_shingles(a, 3),
        word_shingles(b, 3)
    )

    char_score = jaccard(
        char_ngrams(a, 5),
        char_ngrams(b, 5)
    )

    results.append({
        "notice_id_a": row["notice_id_a"],
        "notice_id_b": row["notice_id_b"],
        "label": row["label"],
        "word_3gram": word_score,
        "char_5gram": char_score
    })

result = pd.DataFrame(results)

# ------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------
print("\nSIMILARITY BY LABEL")
print("-" * 70)

print(
    result.groupby("label")[["word_3gram", "char_5gram"]]
    .agg(["mean", "min", "max"])
    .round(4)
)

# ------------------------------------------------------------
# SHOW EXAMPLES
# ------------------------------------------------------------
print("\nEXAMPLE SAME PAIRS")
print("-" * 70)

print(
    result[result["label"].astype(str).str.lower() == "same"]
    .sort_values("word_3gram", ascending=False)
    [["notice_id_a", "notice_id_b", "label",
      "word_3gram", "char_5gram"]]
    .head(5)
    .to_string(index=False)
)

print("\nEXAMPLE DIFFERENT PAIRS")
print("-" * 70)

print(
    result[result["label"].astype(str).str.lower() == "different"]
    .sort_values("word_3gram")
    [["notice_id_a", "notice_id_b", "label",
      "word_3gram", "char_5gram"]]
    .head(5)
    .to_string(index=False)
)

# ------------------------------------------------------------
# SAVE
# ------------------------------------------------------------
out = BASE / "output"
out.mkdir(exist_ok=True)

result.to_csv(
    out / "q2_similarity_results.csv",
    index=False
)

print("\nSaved:")
print(out / "q2_similarity_results.csv")

print("\nQ2-A COMPLETE")