"""스포티파이 협업(피처링) 수집기 → data/raw/raw_collab_<날짜>.csv, raw_collab_partner_<날짜>.csv

    python3 scripts/collect_spotify_collabs.py                    # 이어서 수집 (요청 약 3,000번까지)
    python3 scripts/collect_spotify_collabs.py --max-requests 500 --partner-cap 100

- 왜: "신인이 이미 자리 잡은 팀과 협업했다"가 나중 수상을 미리 알려 주는지 보려고, 날짜가 붙은 협업 관계(엣지)를 모은다.
- 대상(우리 팀): spotify_match.json 에서 id 가 있고 동명 팀(namesakes)이 1 이하인 팀
  + 최신 점수 스냅숏 상위 300팀 + 정답(outcomes.csv, counted=true) 팀 중 아직 짝이 없는 팀.
  짝이 없는 팀은 collect_spotify.find_artist 로 찾고 data/raw/state/spotify_collab_match.json 에 따로 저장한다
  (spotify_match.json 은 건드리지 않는다).
- 방법: 팀마다 앨범 목록(include_groups=album,single,appears_on — appears_on 은 다른 팀 곡에 우리 팀이 참여한 것)
  → 앨범마다 수록곡(/albums/{id}/tracks) → 우리 팀이 다른 팀과 같이 이름이 올라간 곡이면 상대(partner)마다 한 행.
  컴필레이션(album_type=compilation)과 'Various Artists' 앨범은 건너뛴다. 같은 앨범은 한 번만 읽고,
  그 앨범에 나오는 우리 팀 전부의 행을 한꺼번에 만든다.
- role: co_lead(둘 다 앨범 아티스트) / feat_on_own(우리 팀이 곡의 첫 아티스트) / guest_on_partner(상대가 첫 아티스트)
  / co_guest(둘 다 다른 팀 곡의 게스트).
- 상대 프로필: 많이 나온 상대부터 --partner-cap 명까지 collect_spotify 의 발매 요약(첫 발매일·발매 수)을 받는다.
- 한도: 한 번 실행에 요청 --max-requests 번까지. 넘거나 429 로 오래 기다리라고 하면 멈추고, 끝낸 팀·앨범·상대를
  data/raw/state/spotify_collabs_state.json 에 저장해 다음 실행에서 이어 간다.
- 인증·HTTP·429 처리는 collect_spotify 를 그대로 쓴다.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import collect_spotify as cs
from normalize import artist_key

LAB_DIR = cs.ROOT / "docs" / "lab" / "data"
STATE_FILE = "spotify_collabs_state.json"
MATCH_FILE = "spotify_collab_match.json"
MAX_REQUESTS = 3000
PARTNER_CAP = 400
SNAPSHOT_TOP = 300
TRACK_LIMIT = 50               # 수록곡은 50개까지 시도, 400이면 cs.PAGE_LIMIT(10)으로 낮춘다
MAX_ALBUM_PAGES = 20           # 팀 하나당 앨범 목록 최대 20쪽(200장)
VARIOUS_ARTISTS = {"various artists", "varios artistas", "verschiedene interpreten"}

COLLAB_COLUMNS = ["collected_at", "artist_name", "artist_spotify_id", "partner_spotify_id", "partner_name",
                  "track_id", "track_name", "album_id", "album_name", "release_date", "release_date_precision",
                  "role", "album_group"]
PARTNER_COLUMNS = ["collected_at", "partner_spotify_id", "partner_name", "first_release_date", "album_count",
                   "edge_count"]


class BudgetExhausted(RuntimeError):
    pass


class CountingHttp:
    """http 함수를 감싸 요청 수를 센다. 한도에 닿으면 보내기 전에 멈춘다."""

    def __init__(self, http, max_requests):
        self._http = http
        self.max_requests = max_requests
        self.count = 0

    def __call__(self, method, url, headers=None, data=None):
        if self.count >= self.max_requests:
            raise BudgetExhausted(f"요청 {self.max_requests}번 한도")
        self.count += 1
        return self._http(method, url, headers, data)


# ---------- 대상 ----------

def _csv_rows(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def lab_names(lab_dir, top=SNAPSHOT_TOP):
    """최신 스냅숏 상위 top 팀 + 정답(counted=true) 팀의 표시 이름 (순서 유지, 중복 없음)."""
    display = {r["team_key"]: r.get("display_name") or r["team_key"] for r in _csv_rows(lab_dir / "teams.csv")}
    snaps = sorted((lab_dir / "snapshots").glob("*.csv"))
    snap_rows = _csv_rows(snaps[-1])[:top] if snaps else []
    keys = [r["team_key"] for r in snap_rows]
    keys += [r["team_key"] for r in _csv_rows(lab_dir / "outcomes.csv") if r.get("counted") == "true"]
    return list(dict.fromkeys(display.get(k, k) for k in keys if k))


def _usable(match):
    return bool(match and match.get("id") and int(match.get("namesakes") or 1) <= 1)


def base_targets(spotify_match, collab_match, names):
    """→ (대상 [{name, id, spotify_name}], 아직 찾아야 할 이름). 우선순위: 스냅숏·정답 이름 → 나머지 짝."""
    by_key = {}
    for name, m in list(spotify_match.items()) + list(collab_match.items()):
        by_key.setdefault(artist_key(name), (name, m))
    targets, to_search, seen = [], [], set()

    def add(name, m):
        if _usable(m) and m["id"] not in seen:
            seen.add(m["id"])
            targets.append({"name": name, "id": m["id"], "spotify_name": m.get("name", name)})

    for name in names:
        key = artist_key(name)
        if key in by_key and (by_key[key][1] or by_key[key][0] in collab_match):
            add(name, by_key[key][1])
        elif name not in collab_match:
            to_search.append(name)
    for name, m in spotify_match.items():
        add(name, m)
    return targets, to_search


# ---------- 앨범·곡 ----------

def skip_album(album):
    if (album.get("album_type") or "").lower() == "compilation":
        return True
    return any((a.get("name") or "").strip().lower() in VARIOUS_ARTISTS for a in album.get("artists") or [])


def classify_role(our_id, partner_id, track, album):
    album_ids = {a.get("id") for a in album.get("artists") or []}
    if our_id in album_ids and partner_id in album_ids:
        return "co_lead"
    first = ((track.get("artists") or [{}])[0]).get("id")
    if first == our_id:
        return "feat_on_own"
    if first == partner_id:
        return "guest_on_partner"
    return "co_guest"


def _album_group(our_id, album):
    if our_id == album.get("_listed_for") and album.get("album_group"):
        return album["album_group"]
    if our_id in {a.get("id") for a in album.get("artists") or []}:
        return album.get("album_type") or ""
    return "appears_on"


def edges_from_album(album, tracks, targets_by_id, collected_at):
    """곡마다 우리 팀 × 같이 이름이 오른 다른 팀 → 행. (우리 id, 상대 id, 곡 id)가 같으면 한 번만."""
    rows, seen = [], set()
    for track in tracks:
        people = [a for a in track.get("artists") or [] if a.get("id")]
        if len(people) < 2:
            continue
        for our in people:
            target = targets_by_id.get(our["id"])
            if not target:
                continue
            for partner in people:
                key = (our["id"], partner["id"], track.get("id"))
                if partner["id"] == our["id"] or key in seen \
                        or (partner.get("name") or "").strip().lower() in VARIOUS_ARTISTS:
                    continue
                seen.add(key)
                rows.append({
                    "collected_at": collected_at, "artist_name": target["name"], "artist_spotify_id": our["id"],
                    "partner_spotify_id": partner["id"], "partner_name": partner.get("name", ""),
                    "track_id": track.get("id", ""), "track_name": track.get("name", ""),
                    "album_id": album.get("id", ""), "album_name": album.get("name", ""),
                    "release_date": album.get("release_date", ""),
                    "release_date_precision": album.get("release_date_precision", ""),
                    "role": classify_role(our["id"], partner["id"], track, album),
                    "album_group": _album_group(our["id"], album),
                })
    return rows


class Fetcher:
    """collect_spotify.SpotifyClient.get 위에 앨범 목록·수록곡 페이지 넘기기."""

    def __init__(self, client):
        self.client = client
        self.track_limit = TRACK_LIMIT

    def albums(self, artist_id):
        items, offset = [], 0
        for _ in range(MAX_ALBUM_PAGES):
            page = self.client.get(f"/artists/{artist_id}/albums",
                                   {"include_groups": "album,single,appears_on", "market": cs.MARKET,
                                    "limit": cs.PAGE_LIMIT, "offset": offset})
            got = page.get("items") or []
            items += [{**a, "_listed_for": artist_id} for a in got if a]
            offset += cs.PAGE_LIMIT
            if not page.get("next") or not got:
                break
        return items

    def tracks(self, album_id):
        items, offset = [], 0
        while True:
            try:
                page = self.client.get(f"/albums/{album_id}/tracks",
                                       {"market": cs.MARKET, "limit": self.track_limit, "offset": offset})
            except cs.SpotifyError as e:
                if "HTTP 400" in str(e) and self.track_limit > cs.PAGE_LIMIT:
                    self.track_limit = cs.PAGE_LIMIT
                    continue
                raise
            got = page.get("items") or []
            items += got
            offset += self.track_limit
            if not page.get("next") or not got:
                return items


# ---------- 저장 ----------

def load_state(path):
    s = cs._load_json(path, {})
    return {"done_artists": set(s.get("done_artists", [])), "done_albums": set(s.get("done_albums", [])),
            "partners": dict(s.get("partners", {})), "partner_counts": Counter(s.get("partner_counts", {})),
            "partner_names": dict(s.get("partner_names", {}))}


def save_state(path, state):
    cs._save_json(path, {"done_artists": sorted(state["done_artists"]), "done_albums": sorted(state["done_albums"]),
                         "partners": state["partners"], "partner_counts": dict(state["partner_counts"]),
                         "partner_names": state["partner_names"]})


def _append_csv(path, columns, rows, key_cols):
    """오늘 파일이 있으면 이어 붙인다 (같은 키 행은 건너뜀)."""
    existing = {tuple(r.get(c, "") for c in key_cols) for r in _csv_rows(path)} if path.exists() else set()
    new = []
    for r in rows:
        k = tuple(r.get(c, "") for c in key_cols)
        if k not in existing:
            existing.add(k)
            new.append(r)
    if not new:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        if fresh:
            w.writeheader()
        w.writerows([{c: r.get(c, "") for c in columns} for r in new])
    return len(new)


# ---------- 실행 ----------

def _match_names(client, to_search, collab_match, match_path, failures):
    for i, name in enumerate(to_search, 1):
        try:
            collab_match[name] = cs.find_artist(client, name)
        except cs.SpotifyError as e:
            failures.append(f"검색 {name}: {e}")
        if i % cs.SAVE_EVERY == 0:
            cs._save_json(match_path, collab_match)


def _collect_artist(fetcher, target, targets_by_id, state, edges, collected_at, failures):
    complete = True
    for album in fetcher.albums(target["id"]):
        aid = album.get("id")
        if not aid or aid in state["done_albums"]:
            continue
        if skip_album(album):
            state["done_albums"].add(aid)
            continue
        try:
            tracks = fetcher.tracks(aid)
        except cs.SpotifyError as e:
            failures.append(f"수록곡 {album.get('name')}({aid}): {e}")
            complete = False  # 못 읽은 앨범은 끝낸 것으로 치지 않는다 → 다음 실행에서 다시
            continue
        new = edges_from_album(album, tracks, targets_by_id, collected_at)
        edges += new
        for r in new:
            state["partner_counts"][r["partner_spotify_id"]] += 1
            state["partner_names"][r["partner_spotify_id"]] = r["partner_name"]
        state["done_albums"].add(aid)
    if complete:
        state["done_artists"].add(target["id"])


def _collect_partners(client, state, partner_cap, collected_at, profiles, failures):
    todo = [p for p, _ in state["partner_counts"].most_common() if p not in state["partners"]][:partner_cap]
    for pid in todo:
        try:
            summary = client.release_summary(pid)
        except cs.SpotifyError as e:
            failures.append(f"상대 {pid}: {e}")
            continue
        state["partners"][pid] = summary
        profiles.append({"collected_at": collected_at, "partner_spotify_id": pid,
                         "partner_name": state["partner_names"].get(pid, ""), **summary,
                         "edge_count": str(state["partner_counts"][pid])})


def run(client, names, raw_dir, day, collected_at, partner_cap=PARTNER_CAP, counter=None):
    state_dir = raw_dir / "state"
    state_path, match_path = state_dir / STATE_FILE, state_dir / MATCH_FILE
    state = load_state(state_path)
    collab_match = cs._load_json(match_path, {})
    spotify_match = cs._load_json(state_dir / "spotify_match.json", {})
    edges, profiles, failures, stopped = [], [], [], ""
    targets = []
    try:
        targets, to_search = base_targets(spotify_match, collab_match, names)
        _match_names(client, to_search, collab_match, match_path, failures)
        targets, _ = base_targets(spotify_match, collab_match, names)
        targets_by_id = {t["id"]: t for t in targets}
        fetcher = Fetcher(client)
        for t in targets:
            if t["id"] not in state["done_artists"]:
                _collect_artist(fetcher, t, targets_by_id, state, edges, collected_at, failures)
        _collect_partners(client, state, partner_cap, collected_at, profiles, failures)
    except (BudgetExhausted, cs.RateLimited) as e:
        stopped = str(e)
    finally:
        cs._save_json(match_path, collab_match)
        save_state(state_path, state)
        n_edges = _append_csv(raw_dir / f"raw_collab_{day}.csv", COLLAB_COLUMNS, edges,
                              ["artist_spotify_id", "partner_spotify_id", "track_id"])
        n_prof = _append_csv(raw_dir / f"raw_collab_partner_{day}.csv", PARTNER_COLUMNS, profiles,
                             ["partner_spotify_id"])
    return {"targets": len(targets), "done_artists": len(state["done_artists"] & {t["id"] for t in targets}),
            "edges": n_edges, "profiles": n_prof, "partners_total": len(state["partner_counts"]),
            "partners_done": len(state["partners"]), "requests": counter.count if counter else None,
            "failures": failures, "stopped": stopped}


def main(argv):
    ap = argparse.ArgumentParser(description="스포티파이 협업(피처링) 엣지 수집")
    ap.add_argument("--max-requests", type=int, default=MAX_REQUESTS, help="이번 실행 요청 수 상한")
    ap.add_argument("--partner-cap", type=int, default=PARTNER_CAP, help="이번 실행에서 프로필 받을 상대 수 상한")
    args = ap.parse_args(argv)
    env = cs.load_env(cs.ENV_FILE)
    counter = CountingHttp(cs.urllib_http, args.max_requests)
    try:
        client = cs.SpotifyClient(env.get("SPOTIFY_CLIENT_ID"), env.get("SPOTIFY_CLIENT_SECRET"), http=counter)
        now = datetime.now(cs.KST).replace(microsecond=0)
        res = run(client, lab_names(LAB_DIR), cs.RAW_DIR, f"{now:%Y-%m-%d}", now.isoformat(),
                  partner_cap=args.partner_cap, counter=counter)
    except (cs.SpotifyError, OSError) as e:
        print(f"⚠️ 스포티파이 협업 수집 실패: {e}")
        return 1
    print(f"✅ 스포티파이 협업: 대상 {res['targets']}팀 중 끝낸 팀 {res['done_artists']} → 새 엣지 {res['edges']}행, "
          f"상대 프로필 {res['profiles']}명 (상대 누적 {res['partners_total']}명, 프로필 {res['partners_done']}명), "
          f"요청 {res['requests']}번")
    for f in res["failures"][:20]:
        print("  - 실패:", f)
    if res["stopped"]:
        print("⚠️ 중간에 멈춤 (다음 실행에서 이어감):", res["stopped"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
