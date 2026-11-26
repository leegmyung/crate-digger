"""Last.fm에서 아티스트 태그를 가져와 data/ext_artist_tags.csv 를 만듭니다.

좋아요 CSV(data/likes/*.csv)에 나오는 아티스트마다 Last.fm `artist.getTopTags`를 호출하고,
태그 점수(0~100)를 가중치(0~1)로 바꿔 저장합니다. build_reco.py 가 이 파일을 그대로 읽습니다.

준비
  1) https://www.last.fm/api/account/create 에서 API 키 발급 (무료)
  2) export LASTFM_API_KEY=발급받은키

실행
  python3 scripts/fetch_lastfm_tags.py                 # 좋아요 CSV의 모든 아티스트
  python3 scripts/fetch_lastfm_tags.py --refresh       # 캐시 무시하고 다시 받기
  python3 scripts/fetch_lastfm_tags.py --min-count 15 --max-tags 6

출력
  data/ext_artist_tags.csv         artist_name, tag, weight        (build_reco.py 입력)
  data/lastfm_report.csv           아티스트별 결과 (found / not_found / no_tags / error, Last.fm 표기명)
  data/lastfm_unmapped_tags.csv    tag_family에 없는 태그 빈도 → schema_reco.sql 매핑 보강용
  data/cache/lastfm/*.json         원본 응답 캐시 (다시 실행하면 API를 부르지 않음)

이름 보정
  data/artist_aliases.csv (선택): artist_name,lastfm_name
  예) 혁오,HYUKOH   검정치마,The Black Skirts
  Last.fm 자동 보정(autocorrect=1)으로 못 찾는 한글·현지어 표기를 직접 이어줍니다.

이용 규칙: Last.fm API 약관상 과도한 호출을 피해야 하므로 기본 초당 4회 이하로 호출하고,
결과를 캐시합니다. API 키는 코드나 저장소에 넣지 말고 환경변수로만 전달하세요.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://ws.audioscrobbler.com/2.0/"
UA = "bandcamp-taste-match/0.1 (prototype)"

# 의미 없는 태그 (취향 신호가 아닌 것)
JUNK = {
    "seen live", "favorite", "favorites", "favourite", "favourites", "my favorite", "love", "loved",
    "awesome", "beautiful", "cool", "amazing", "best", "good", "great", "albums i own", "under 2000 listeners",
    "spotify", "check out", "all", "music", "fip", "male vocalists", "female vocalists", "male vocalist",
    "female vocalist", "british", "american", "usa", "uk", "japanese", "korean", "canadian", "german",
    "french", "swedish", "australian", "icelandic", "scottish", "english", "irish",
}
# Last.fm 표기 → 프로젝트 태그 어휘 (tag_family / Bandcamp 태그와 맞춤)
ALIAS = {
    "hip hop": "hip-hop", "hiphop": "hip-hop", "rap": "hip-hop", "hip-hop/rap": "hip-hop",
    "underground hip hop": "underground hip-hop", "conscious hip hop": "conscious hip-hop",
    "instrumental hip hop": "instrumental hip-hop", "uk hip hop": "uk hip-hop", "jazz hop": "instrumental hip-hop",
    "rnb": "r&b/soul", "r&b": "r&b/soul", "rhythm and blues": "r&b/soul", "contemporary r&b": "r&b/soul",
    "alternative rnb": "alternative r&b", "neo soul": "neo-soul", "neosoul": "neo-soul",
    "kpop": "k-pop", "k pop": "k-pop", "korean pop": "k-pop", "k-indie": "korean indie", "korean rock": "korean indie",
    "citypop": "city pop", "city-pop": "city pop", "シティポップ": "city pop",
    "synthpop": "synth-pop", "synth pop": "synth-pop", "dreampop": "dream pop", "dream-pop": "dream pop",
    "post rock": "post-rock", "postrock": "post-rock", "post punk": "post-punk", "indie": "indie rock",
    "alternative rock": "alternative", "alt-rock": "alternative", "electronica": "electronic",
    "electro": "electronic", "intelligent dance music": "idm", "deep house": "house", "lofi": "lo-fi",
    "lo fi": "lo-fi", "chillhop": "lo-fi", "soundtracks": "soundtrack", "score": "film score", "ost": "soundtrack",
    "singer songwriter": "singer-songwriter", "acoustic": "folk", "spiritual-jazz": "spiritual jazz",
    "fusion": "jazz fusion", "avantgarde": "avant-garde", "avant garde": "avant-garde",
}
YEAR = re.compile(r"^(\d{2,4}s?|\d{4})$")

# load_likes.sql 와 같은 규칙으로 주 아티스트 추출
SPLIT = re.compile(r",\s|\s&\s|\sfeat\.|\sft\.\s|\sx\s", re.I)


def primary_artist(name, keep_whole):
    n = (name or "").strip()
    if n.lower() in keep_whole:
        return n
    return SPLIT.split(n + " ", maxsplit=1)[0].strip()


def norm_tag(t):
    t = re.sub(r"\s+", " ", t.strip().lower())
    return ALIAS.get(t, t)


class LastFM:
    def __init__(self, key, base, cache_dir, rps, refresh):
        self.key, self.base, self.cache_dir, self.refresh = key, base, cache_dir, refresh
        self.min_gap = 1.0 / rps
        self.last = 0.0
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, method, artist):
        h = hashlib.sha1(f"{method}|{artist.lower()}".encode()).hexdigest()[:16]
        return self.cache_dir / f"{method}_{h}.json"

    def call(self, method, artist):
        path = self._cache_path(method, artist)
        if path.exists() and not self.refresh:
            return json.loads(path.read_text(encoding="utf-8")), True
        params = {"method": method, "artist": artist, "autocorrect": 1, "api_key": self.key, "format": "json"}
        url = self.base + "?" + urllib.parse.urlencode(params)
        for attempt in range(5):
            wait = self.min_gap - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                try:
                    data = json.loads(body)
                except ValueError:
                    data = {"error": e.code, "message": body[:200]}
                if e.code >= 500 or data.get("error") in (11, 16, 29):
                    time.sleep(2 ** attempt)
                    continue
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == 4:
                    return {"error": -1, "message": str(e)}, False
                time.sleep(2 ** attempt)
                continue
            err = data.get("error")
            if err in (11, 16, 29):              # 서비스 일시 장애 / 호출 한도 초과 → 대기 후 재시도
                time.sleep(2 ** attempt * 2)
                continue
            if err in (10, 26):                  # 잘못된 키 / 정지된 키 → 즉시 중단
                sys.exit(f"Last.fm API 키 오류 ({err}): {data.get('message')}  LASTFM_API_KEY를 확인하세요.")
            if err is None or err == 6:          # 정상 또는 '아티스트 없음'은 캐시
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data, False
        return {"error": -2, "message": "재시도 한도 초과"}, False


def load_artists(aliases):
    # 이름에 쉼표가 들어간 아티스트('Tyler, The Creator')는 별칭 파일이나 기존 태그 파일에 있으면 통째로 유지
    keep_whole = {a.lower() for a in aliases}
    tags_csv = ROOT / "data/ext_artist_tags.csv"
    if tags_csv.exists():
        with open(tags_csv, newline="", encoding="utf-8") as f:
            keep_whole |= {r["artist_name"].strip().lower() for r in csv.DictReader(f)}
    counts = Counter()
    for p in sorted((ROOT / "data/likes").glob("*.csv")):
        with open(p, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                low = {k.strip().lower(): v for k, v in row.items() if k}
                name = low.get("artist name") or low.get("artist") or low.get("artists")
                if name and name.strip():
                    counts[primary_artist(name, keep_whole)] += 1
    return counts


def load_aliases():
    p = ROOT / "data/artist_aliases.csv"
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as f:
        return {r["artist_name"].strip(): r["lastfm_name"].strip() for r in csv.DictReader(f) if r.get("lastfm_name")}


def known_families():
    """schema_reco.sql 의 tag_family 에 들어 있는 태그 목록."""
    sql = (ROOT / "sql/reco/schema_reco.sql").read_text(encoding="utf-8")
    con = sqlite3.connect(":memory:")
    con.executescript(sql)
    return {t for (t,) in con.execute("SELECT tag FROM tag_family")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-count", type=int, default=10, help="Last.fm 태그 점수 하한 (0~100, 기본 10)")
    ap.add_argument("--max-tags", type=int, default=8, help="아티스트당 최대 태그 수 (기본 8)")
    ap.add_argument("--rps", type=float, default=4.0, help="초당 최대 호출 수 (기본 4)")
    ap.add_argument("--refresh", action="store_true", help="캐시 무시")
    ap.add_argument("--out", default=str(ROOT / "data/ext_artist_tags.csv"))
    ap.add_argument("--base-url", default=os.environ.get("LASTFM_BASE_URL", API), help=argparse.SUPPRESS)
    args = ap.parse_args()

    key = os.environ.get("LASTFM_API_KEY")
    if not key:
        sys.exit("LASTFM_API_KEY 환경변수가 없습니다. https://www.last.fm/api/account/create 에서 키를 발급한 뒤\n"
                 "  export LASTFM_API_KEY=발급받은키\n로 설정하고 다시 실행하세요.")

    aliases = load_aliases()
    artists = load_artists(aliases)
    if not artists:
        sys.exit("data/likes/*.csv 에서 아티스트를 찾지 못했습니다.")
    families = known_families()
    fm = LastFM(key, args.base_url, ROOT / "data/cache/lastfm", args.rps, args.refresh)

    out_rows, report, unmapped = [], [], Counter()
    for i, (name, likes) in enumerate(artists.most_common(), 1):
        query = aliases.get(name, name)
        data, cached = fm.call("artist.gettoptags", query)
        status, lf_name, kept = "found", "", 0
        if data.get("error") == 6:
            status = "not_found"
        elif "error" in data:
            status = f"error:{data.get('error')}"
        else:
            tt = data.get("toptags", {})
            lf_name = tt.get("@attr", {}).get("artist", "")
            tags = tt.get("tag", [])
            if isinstance(tags, dict):           # 태그가 1개면 객체로 옴
                tags = [tags]
            seen = {}
            for t in tags:
                cnt = int(t.get("count", 0) or 0)
                tag = norm_tag(t.get("name", ""))
                if (cnt < args.min_count or not tag or tag in JUNK or YEAR.match(tag)
                        or tag == name.lower() or tag == lf_name.lower()):
                    continue
                seen[tag] = max(seen.get(tag, 0), cnt)   # 별칭으로 합쳐진 태그는 큰 값
            top = sorted(seen.items(), key=lambda x: -x[1])[: args.max_tags]
            mx = top[0][1] if top else 1
            for tag, cnt in top:
                out_rows.append((name, tag, round(cnt / mx, 3)))
                if tag not in families:
                    unmapped[tag] += likes
            kept = len(top)
            if not top:
                status = "no_tags"
        report.append((name, query, lf_name, status, kept, likes, "cache" if cached else "api"))
        print(f"[{i:>3}/{len(artists)}] {name:<28} → {status:<10} {kept} tags {'(cache)' if cached else ''}")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["artist_name", "tag", "weight"])
        w.writerows(out_rows)
    with open(ROOT / "data/lastfm_report.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["artist_name", "query", "lastfm_name", "status", "tags_kept", "liked_tracks", "source"])
        w.writerows(report)
    with open(ROOT / "data/lastfm_unmapped_tags.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tag", "weighted_likes"])
        w.writerows(unmapped.most_common())

    found = sum(1 for r in report if r[3] == "found")
    print(f"\n{found}/{len(report)} 아티스트 태그 확보 → {args.out}")
    miss = [r[0] for r in report if r[3] != "found"]
    if miss:
        print("못 찾은 아티스트 (data/artist_aliases.csv 에 Last.fm 표기를 추가하세요): " + ", ".join(miss))
    if unmapped:
        print("취향군 매핑이 없는 태그 상위: " + ", ".join(t for t, _ in unmapped.most_common(10))
              + "  → sql/reco/schema_reco.sql 의 tag_family 에 추가하면 세분화에 반영됩니다.")


if __name__ == "__main__":
    main()
