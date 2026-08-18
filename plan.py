"""คำนวณจำนวน batch จากจำนวน token จริงในชีต แล้วพ่น matrix ให้ GitHub Actions

หัวใจของ "ตั้งแล้วลืม": จำนวน batch ไม่ได้ฮาร์ดโค้ดไว้ใน YAML แต่คิดใหม่ทุกครั้ง
ที่รัน — เพิ่ม/ลบ token ในชีต subscribetokens แล้ว matrix ปรับตามเอง
ไม่ต้องแตะไฟล์ workflow อีกเลย

ENV:
  TOKENS_PER_BATCH  จำนวน token ต่อ 1 job (default 60 → ~22 นาที/job)
  MAX_BATCHES       เพดานจำนวน job ต่อรอบ (default 256 — ลิมิตของ GitHub)
"""
import json
import math
import os
import sys

from cluster import read_subscribe_tokens

TOKENS_PER_BATCH = int(os.getenv("TOKENS_PER_BATCH", "60"))
MAX_BATCHES = int(os.getenv("MAX_BATCHES", "256"))


def main():
    tokens = read_subscribe_tokens()
    count = len(tokens)

    if count == 0:
        print("❌ ไม่พบ token ในชีต subscribetokens", file=sys.stderr)
        # ไม่ล้มทั้ง workflow — พ่น matrix ว่างแล้วให้ job ถัดไป skip เอง
        emit(count=0, total=0, batches=[])
        return

    total = min(max(1, math.ceil(count / TOKENS_PER_BATCH)), MAX_BATCHES)
    batches = list(range(1, total + 1))

    per = math.ceil(count / total)
    print(f"📋 พบ {count} token → {total} batch (~{per} token/batch)", file=sys.stderr)
    if total == MAX_BATCHES and count / total > TOKENS_PER_BATCH:
        print(f"⚠️ ชน MAX_BATCHES ({MAX_BATCHES}) — แต่ละ batch จะได้ {per} token "
              f"(มากกว่า TOKENS_PER_BATCH={TOKENS_PER_BATCH})", file=sys.stderr)

    emit(count=count, total=total, batches=batches)


def emit(count, total, batches):
    """เขียน output ให้ GitHub Actions อ่านต่อผ่าน needs.plan.outputs.*"""
    out = {
        "token_count": str(count),
        "batch_total": str(total),
        "batches": json.dumps(batches),
        "has_work": "true" if batches else "false",
    }
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            for k, v in out.items():
                fh.write(f"{k}={v}\n")
    for k, v in out.items():
        print(f"{k}={v}")


if __name__ == "__main__":
    main()
