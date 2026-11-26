"""가상 Bandcamp 판매 피드 데이터 생성기 (실제 데이터 아님).

크롤러가 만들 CSV와 같은 컬럼(stg_salesfeed)으로 28일치 판매 이벤트를 만듭니다.
아티스트/앨범명은 무작위 조합한 가상의 이름입니다.

    python3 scripts/generate_sample.py data/sample_salesfeed.csv
"""
import csv
import sys
from datetime import date, datetime, timedelta

import numpy as np

rng = np.random.default_rng(20261123)
START = date(2026, 10, 26)
DAYS = 28
BASE_PER_DAY = 650
SPIKE_DAY = date(2026, 11, 6)       # 가정: 수수료 면제 이벤트일 (판매 급증)

# 구매자 국가 (가중치)
COUNTRIES = [
    ("US", "United States", 36), ("GB", "United Kingdom", 14), ("DE", "Germany", 9),
    ("CA", "Canada", 5.5), ("JP", "Japan", 4.5), ("FR", "France", 4), ("AU", "Australia", 3.5),
    ("NL", "Netherlands", 2.6), ("IT", "Italy", 1.8), ("ES", "Spain", 1.6), ("SE", "Sweden", 1.6),
    ("BE", "Belgium", 1.2), ("KR", "South Korea", 1.3), ("BR", "Brazil", 1.2), ("MX", "Mexico", 1.0),
    ("PL", "Poland", 0.9), ("IE", "Ireland", 0.9), ("CH", "Switzerland", 0.9), ("NO", "Norway", 0.8),
    ("DK", "Denmark", 0.7), ("FI", "Finland", 0.7), ("NZ", "New Zealand", 0.7), ("AT", "Austria", 0.6),
    ("SG", "Singapore", 0.4), ("ID", "Indonesia", 0.4), ("CL", "Chile", 0.4), ("AR", "Argentina", 0.3),
    ("TW", "Taiwan", 0.3), ("PH", "Philippines", 0.3), ("ZA", "South Africa", 0.3),
]
# 국가별 현지 시간대 오프셋(UTC 기준, 대략) — 구매가 현지 저녁에 몰리도록
TZ = {"US": -6, "CA": -5, "MX": -6, "BR": -3, "AR": -3, "CL": -3, "JP": 9, "KR": 9, "TW": 8,
      "SG": 8, "ID": 7, "PH": 8, "AU": 10, "NZ": 13, "GB": 0, "IE": 0, "ZA": 2}
LOCAL_HOUR_W = np.array([3, 2, 1.2, .7, .5, .5, .8, 1.5, 2.5, 3.5, 4.2, 4.8,
                         5.2, 5.4, 5.5, 5.7, 6, 6.4, 6.8, 7.2, 7.5, 7.2, 6, 4.5])
LOCAL_HOUR_W = LOCAL_HOUR_W / LOCAL_HOUR_W.sum()

# 판매자 통화 (Bandcamp 결제 통화 = 아티스트가 정한 통화)
CURRENCIES = [("USD", 1.0, 52), ("GBP", 1.27, 18), ("EUR", 1.08, 20),
              ("JPY", 0.0066, 3), ("CAD", 0.73, 4), ("AUD", 0.65, 3)]

GENRES = {  # 장르: (아티스트 비중, 실물 판매 비중, 대표 서브 태그)
    "electronic": (17, .22, ["techno", "house", "idm"]),
    "ambient": (10, .20, ["drone", "new age", "field recordings"]),
    "hip-hop": (9, .18, ["boom bap", "instrumental hip-hop", "lo-fi"]),
    "rock": (10, .40, ["indie rock", "shoegaze", "post-rock"]),
    "punk": (8, .55, ["hardcore", "post-punk", "diy"]),
    "metal": (9, .60, ["black metal", "doom", "death metal"]),
    "experimental": (8, .30, ["noise", "avant-garde", "improvisation"]),
    "jazz": (6, .38, ["spiritual jazz", "free jazz", "jazz fusion"]),
    "folk": (6, .33, ["singer-songwriter", "americana", "psych folk"]),
    "pop": (6, .28, ["synth-pop", "bedroom pop", "dream pop"]),
    "soundtrack": (5, .30, ["video game music", "film score", "library music"]),
    "r&b/soul": (6, .25, ["neo-soul", "funk", "soul"]),
}

ADJ = ["Velvet", "Hollow", "Paper", "Neon", "Quiet", "Glass", "Static", "Copper", "Lunar", "Feral",
       "Sunken", "Golden", "Distant", "Rusted", "Electric", "Pale", "Wild", "Silent", "Crooked", "Amber",
       "Northern", "Tidal", "Faded", "Burning", "Soft", "Midnight", "Iron", "Plastic", "Secret", "Broken"]
NOUN = ["Harbor", "Moth", "Signal", "Choir", "Orchard", "Engine", "Garden", "Tapes", "Wolves", "Lanterns",
        "Archive", "Season", "Machine", "Rivers", "Ghosts", "Satellite", "Parade", "Hymns", "Atlas", "Fever",
        "Room", "Weather", "Tower", "Mirrors", "Static", "Bloom", "Coast", "Ritual", "Circuit", "Cathedral"]
TITLE_W = ["Afterglow", "Low Light", "Night Bus", "Tidal Memory", "Small Hours", "Field Notes", "Cold Open",
           "Ritual Sky", "Last Ferry", "Blue Room", "Soft Machines", "Northbound", "Ash & Honey", "Endless Loop",
           "Paper Moon", "Static Bloom", "Half Asleep", "Deep Water", "Fever Dream", "Long Shadow"]

PHYSICAL = [  # (설명, USD 정가, 가중치)
    ("Vinyl LP", 28, 42), ("Limited Edition Vinyl LP", 34, 10), ('7" Vinyl', 10, 5),
    ("Compact Disc (CD)", 12, 18), ("Cassette", 10, 14),
    ("T-Shirt/Shirt", 25, 7), ("Hoodie/Sweater", 45, 1.5), ("Poster/Print", 15, 1.5), ("Tote Bag", 18, 1),
]


def pick(items, weights, n=None):
    w = np.array(weights, float)
    return rng.choice(len(items), size=n, p=w / w.sum())


def build_catalog(n_artists=650):
    genre_names = list(GENRES)
    used, artists = set(), []
    while len(artists) < n_artists:
        name = f"{rng.choice(ADJ)} {rng.choice(NOUN)}"
        if rng.random() < .25:
            name = "The " + name
        if name in used:
            continue
        used.add(name)
        g = genre_names[pick(genre_names, [GENRES[x][0] for x in genre_names])]
        cur = CURRENCIES[pick(CURRENCIES, [c[2] for c in CURRENCIES])]
        sub = name.lower().replace("the ", "").replace(" ", "")
        artists.append({"name": name, "genre": g, "cur": cur, "sub": sub})
    # 인기도: 롱테일(Zipf)
    pop = 1 / np.arange(1, n_artists + 1) ** 0.72
    rng.shuffle(pop)
    for a, p in zip(artists, pop):
        a["pop"] = p
        n_alb = 1 + rng.poisson(1.2)
        a["albums"] = []
        for _ in range(n_alb):
            title = str(rng.choice(TITLE_W)) + ("" if rng.random() < .6 else f" {rng.choice(['EP', 'Vol. 2', 'II', 'Sessions'])}")
            slug = title.lower().replace(" ", "-").replace("&", "and").replace(".", "")
            a["albums"].append({"title": title, "slug": slug,
                                "price_usd": float(rng.choice([5, 7, 8, 9, 10, 12])),
                                "tracks": int(rng.integers(4, 13))})
    return artists


def local_price(usd, cur):
    code, rate, _ = cur
    v = usd / rate
    return float(round(v, -1)) if code == "JPY" else float(round(v))


def main(out_path):
    artists = build_catalog()
    a_w = np.array([a["pop"] for a in artists])
    c_idx_w = [c[2] for c in COUNTRIES]
    rows = []
    for d in range(DAYS):
        day = START + timedelta(days=d)
        mult = 1.0 + (0.18 if day.weekday() >= 4 else 0) + 0.004 * d
        if day == SPIKE_DAY:
            mult *= 3.6
        n = rng.poisson(BASE_PER_DAY * mult)
        a_ids = pick(artists, a_w, n)
        c_ids = pick(COUNTRIES, c_idx_w, n)
        for ai, ci in zip(a_ids, c_ids):
            a = artists[ai]
            cc, cname, _ = COUNTRIES[ci]
            alb = a["albums"][rng.integers(len(a["albums"]))]
            phys_share = GENRES[a["genre"]][1] * (1.15 if day == SPIKE_DAY else 1)
            r = rng.random()
            base = f"https://{a['sub']}.bandcamp.com"
            if r < phys_share:
                k = pick(PHYSICAL, [p[2] for p in PHYSICAL])
                desc, usd, _ = PHYSICAL[k]
                item_type = "p"
                url = f"{base}/album/{alb['slug']}" if k < 5 else f"{base}/merch/{desc.split('/')[0].lower().replace(' ', '-')}"
                list_usd = usd * rng.choice([0.9, 1, 1, 1.1])
                tip = rng.random() < .07
            elif r < phys_share + (1 - phys_share) * .7:
                item_type, desc, url, list_usd = "a", "digital album", f"{base}/album/{alb['slug']}", alb["price_usd"]
                tip = rng.random() < .34
            else:
                item_type, desc = "t", "digital track"
                url = f"{base}/track/{alb['slug']}-{rng.integers(1, alb['tracks'] + 1)}"
                list_usd = 1.0
                tip = rng.random() < .27
            price = local_price(list_usd, a["cur"])
            if price <= 0:
                price = local_price(1.0, a["cur"])
            paid = price
            if tip:
                ratio = 1 + min(rng.lognormal(-1.0, 0.8), 6)
                paid = price * ratio
                paid = float(round(paid, -1)) if a["cur"][0] == "JPY" else float(np.ceil(paid))
                if paid <= price:
                    paid = price + (10 if a["cur"][0] == "JPY" else 1)
            # 시각: 구매자 현지 저녁 시간대에 몰림
            lh = rng.choice(24, p=LOCAL_HOUR_W)
            off = TZ.get(cc, 1)
            ts = datetime(day.year, day.month, day.day) + timedelta(hours=int((lh - off) % 24),
                                                                    minutes=int(rng.integers(60)),
                                                                    seconds=int(rng.integers(60)))
            rows.append({
                "utc_date": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "artist_name": a["name"],
                "album_title": alb["title"],
                "item_description": desc,
                "item_type": item_type,
                "url": url,
                "item_price": price,
                "amount_paid": paid,
                "amount_paid_usd": round(paid * a["cur"][1], 2),
                "currency": a["cur"][0],
                "country": cname,
                "country_code": cc.lower(),
                "tags": "|".join([a["genre"]] + list(rng.choice(GENRES[a["genre"]][2], 2, replace=False))),
            })
    rows.sort(key=lambda x: x["utc_date"])
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows):,} sample sales → {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/sample_salesfeed.csv")
