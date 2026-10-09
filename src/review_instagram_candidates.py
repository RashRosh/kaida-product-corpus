"""Create offline provisional quality review; never certify a seller automatically."""
import argparse
import csv
import re
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/"data"/"extracted"/"instagram_seller_candidates.csv"
OUTPUT=ROOT/"data"/"extracted"/"instagram_seller_review.csv"

PATTERNS={
 "producer":r"леплю|лепим|готовлю|готовим|печ[еёкм]|выпека|производ|сыровар|ручной леп|домашн|собственн|крафт",
 "reseller_store":r"магазин|супермаркет|оптом|дистрибьют|перепрода|маркетплейс",
 "food":r"пельмен|манты|сыр|колбас|мяс|торт|десерт|выпеч|хлеб|рыб|солен|солён|полуфабрикат|ягод|овощ|фрукт|орех|джерки|самса|вареник|пирог|продукт|еда|кухн",
}
FIELDS=("username","business_name","instagram_url","city_status","food_relevance","seller_type","contact_route","priority","manual_check","biography","phones","whatsapp_urls","other_urls","followers","review_status")

def classify(row):
    text=" ".join([row.get("username",""),row.get("business_name",""),row.get("biography",""),row.get("category","")]).lower()
    food="FOOD_LIKELY" if re.search(PATTERNS["food"],text) else "REVIEW"
    if re.search(PATTERNS["reseller_store"],text):
        kind="STORE_OR_RESELLER_REVIEW"
    elif re.search(PATTERNS["producer"],text):
        kind="PRODUCER_LIKELY"
    else:
        kind="SELLER_TYPE_UNKNOWN"
    contacts="WHATSAPP" if row.get("whatsapp_urls","").strip() else "PHONE" if row.get("phones","").strip() else "OTHER_LINK" if row.get("other_urls","").strip() else "INSTAGRAM_DIRECT"
    city=row.get("city_status","UNVERIFIED")
    if city in ("OTHER_CITY_REVIEW","REVIEW_CONFLICT"): priority="CHECK_GEO"
    elif city=="ALMATY_CLAIMED" and food=="FOOD_LIKELY" and kind=="PRODUCER_LIKELY":
        priority="HIGH" if contacts in ("WHATSAPP","PHONE") else "MEDIUM"
    else:priority="REVIEW"
    checks=[]
    if city!="ALMATY_CLAIMED":checks.append("location")
    if food!="FOOD_LIKELY":checks.append("food_product")
    if kind!="PRODUCER_LIKELY":checks.append("seller_type")
    checks+=["recent_activity","real_orders"]
    return {
        "username":row.get("username",""),"business_name":row.get("business_name",""),
        "instagram_url":row.get("instagram_url",""),"city_status":city,
        "food_relevance":food,"seller_type":kind,"contact_route":contacts,
        "priority":priority,"manual_check":"; ".join(checks),
        "biography":row.get("biography",""),"phones":row.get("phones",""),
        "whatsapp_urls":row.get("whatsapp_urls",""),"other_urls":row.get("other_urls",""),
        "followers":row.get("followers",""),"review_status":row.get("review_status","PENDING")
    }

def analyze(input_path=INPUT,output_path=OUTPUT):
    with input_path.open("r",encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows:raise ValueError("No candidates; refusing to overwrite review")
    if not {"username","city_status","whatsapp_urls","biography"}.issubset(rows[0]):
        raise ValueError("Unexpected input schema")
    ranked=[classify(r) for r in rows]
    order={"HIGH":0,"MEDIUM":1,"REVIEW":2,"CHECK_GEO":3}
    ranked.sort(key=lambda r:(order[r["priority"]],r["username"]))
    output_path.parent.mkdir(parents=True,exist_ok=True)
    with output_path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(ranked)
    print("Candidates:",len(ranked))
    print("Geography:",dict(Counter(r["city_status"] for r in ranked)))
    print("Priority:",dict(Counter(r["priority"] for r in ranked)))
    print("Contact:",dict(Counter(r["contact_route"] for r in ranked)))
    print("Saved:",output_path)
    print("All labels are heuristic; no account is considered verified or active.")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=INPUT)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    a=parser.parse_args()
    analyze(a.input,a.output)
