"""Import Apify JSON exports as a deduplicated REVIEW-ONLY seller CSV (offline)."""
import argparse, csv, json, re
from pathlib import Path
from urllib.parse import urlparse, unquote

FIELDS=("username","instagram_url","instagram_id","business_name","biography","category","followers","source_files","city_status","phones","whatsapp_urls","other_urls","contact_status","review_status")
PHONE=re.compile(r"(?<!\d)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s()\-]*\d{2}[\s()\-]*\d{2}(?!\d)")
CITY=re.compile(r"алмат|almaty|almati",re.I)
OTHER=re.compile(r"жаркент|семей|астана|караганда|шымкент|усть.камен",re.I)

def phone(value):
    d=re.sub(r"\D","",value)
    if len(d)==11 and d[0]=="8":d="7"+d[1:]
    return "+"+d if len(d)==11 and d[0]=="7" else ""

def adapt(x,source):
    user=str(x.get("username") or x.get("requestedUsername") or "").strip().lower()
    if not user:return None
    bio=x.get("biography") or ""
    name=x.get("full_name") or x.get("fullName") or ""
    links=[a.get("url","") for a in (x.get("bio_links") or []) if isinstance(a,dict)]
    if x.get("external_url"): links.append(x["external_url"])
    links=sorted(set(link for link in links if link))
    whats=[u for u in links if "wa.me/" in u.lower() or "api.whatsapp.com" in u.lower()]
    numbers=set()
    for item in [bio,*whats]:
        numbers.update(filter(None,(phone(m.group()) for m in PHONE.finditer(unquote(item)))))
    for link in whats:
        p=phone(urlparse(link).path.strip("/").split("/")[0])
        if p:numbers.add(p)
    text=" ".join((user,name,bio))
    is_city=bool(CITY.search(text));is_other=bool(OTHER.search(text))
    city=("REVIEW_CONFLICT" if is_city and is_other else "OTHER_CITY_REVIEW" if is_other else "ALMATY_CLAIMED" if is_city else "UNVERIFIED")
    return dict(username=user,instagram_url=x.get("url") or x.get("profileUrl") or f"https://www.instagram.com/{user}/",instagram_id=x.get("pk") or x.get("userId") or x.get("id") or "",business_name=name,biography=bio,category=x.get("category") or "",followers=x.get("followers") if x.get("followers") is not None else x.get("followersCount",""),source_files=source,city_status=city,phones="; ".join(sorted(numbers)),whatsapp_urls="; ".join(whats),other_urls="; ".join(v for v in links if v not in whats),contact_status="PUBLIC_CONTACT" if links or numbers else "INSTAGRAM_ONLY",review_status="PENDING")

def import_files(paths):
    found={}
    for path in paths:
        data=json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(data,list):raise ValueError(f"Expected JSON array: {path}")
        for raw in data:
            if not isinstance(raw,dict):continue
            row=adapt(raw,Path(path).name)
            if not row:continue
            key=row["username"];old=found.get(key)
            if old:
                row["source_files"]="; ".join(sorted(set(old["source_files"].split("; ")+[Path(path).name])))
                for field in ("instagram_id","business_name","biography","category","followers"):
                    if not row[field] and old[field]:row[field]=old[field]
                # Merge all publicly available contacts across observations.
                # An empty or shorter new scrape must not discard old details.
                for field in ("phones","whatsapp_urls","other_urls"):
                    items=set(filter(None,old[field].split("; "))) | set(filter(None,row[field].split("; ")))
                    row[field]="; ".join(sorted(items))
                if row["city_status"]=="UNVERIFIED" and old["city_status"]!="UNVERIFIED":row["city_status"]=old["city_status"]
                row["contact_status"]="PUBLIC_CONTACT" if any(row[f] for f in ("phones","whatsapp_urls","other_urls")) else "INSTAGRAM_ONLY"
            found[key]=row
    return found

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files",nargs="+",type=Path)
    parser.add_argument("--output",type=Path,default=Path("data/extracted/instagram_seller_candidates.csv"))
    args=parser.parse_args()
    found=import_files(args.files)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(found[k] for k in sorted(found))
    print(f"Unique candidates: {len(found)}, with WhatsApp: {sum(bool(x['whatsapp_urls']) for x in found.values())}, output: {args.output}")
    print("All rows require manual review; nothing imported into KAIDA.")
if __name__=="__main__":main()
