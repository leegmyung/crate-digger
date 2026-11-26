"""추천 프로토타입용 샘플 데이터 생성 (실제 사용자 데이터 아님).

만드는 파일
  data/likes/u_spotify.csv   TuneMyMusic 'Spotify → 파일' 형식을 흉내 낸 좋아요 목록
  data/likes/u_apple.csv     'Apple Music → 파일'
  data/likes/u_ytmusic.csv   'YouTube Music → 파일'
  data/ext_artist_tags.csv   Last.fm/MusicBrainz 태그 대신 손으로 지정한 아티스트 태그 (샘플)
  data/fan_collections.csv   Bandcamp 팬 컬렉션 (가상 팬 3,000명, bandcamp.db의 가상 카탈로그 기준)

좋아요 목록의 아티스트·곡은 실제 존재하는 음악이지만, 이 세 사람은 가상의 사용자입니다.
ISRC는 지어내지 않고 비워 둡니다.

    python3 scripts/generate_reco_sample.py [bandcamp.db]
"""
import csv
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
rng = np.random.default_rng(7)

# TuneMyMusic 파일 내보내기 컬럼 (제3자 리뷰 기준 추정 — 실제 파일로 확인 필요)
COLS = ["Track name", "Artist name", "Album", "Playlist name", "Type", "ISRC"]

USERS = {
    "u_spotify": ("Spotify", "Liked Songs", [
        ("When the Sun Hits", "Slowdive", "Souvlaki"), ("Alison", "Slowdive", "Souvlaki"),
        ("Sugar for the Pill", "Slowdive", "Slowdive"), ("Only Shallow", "My Bloody Valentine", "Loveless"),
        ("When You Sleep", "My Bloody Valentine", "Loveless"), ("Space Song", "Beach House", "Depression Cherry"),
        ("Myth", "Beach House", "Bloom"), ("Zebra", "Beach House", "Teen Dream"),
        ("Heaven or Las Vegas", "Cocteau Twins", "Heaven or Las Vegas"),
        ("Weird Fishes/Arpeggi", "Radiohead", "In Rainbows"), ("Reckoner", "Radiohead", "In Rainbows"),
        ("Everything In Its Right Place", "Radiohead", "Kid A"),
        ("Your Hand in Mine", "Explosions in the Sky", "The Earth Is Not a Cold Dead Place"),
        ("Take Me Somewhere Nice", "Mogwai", "Rock Action"), ("Hoppípolla", "Sigur Rós", "Takk..."),
        ("Nobody", "Mitski", "Be the Cowboy"), ("Washing Machine Heart", "Mitski", "Be the Cowboy"),
        ("Be Sweet", "Japanese Breakfast", "Jubilee"), ("Motion Sickness", "Phoebe Bridgers", "Stranger in the Alps"),
        ("Kyoto", "Phoebe Bridgers", "Punisher"), ("Not", "Big Thief", "Two Hands"),
        ("Super Natural", "Turnover", "Peripheral Vision"),
        ("Roygbiv", "Boards of Canada", "Music Has the Right to Children"),
        ("Dayvan Cowboy", "Boards of Canada", "The Campfire Headphase"),
        ("Baby", "Four Tet", "Sixteen Oceans"), ("Two Thousand and Seventeen", "Four Tet", "New Energy"),
        ("Kerala", "Bonobo", "Migration"),
    ]),
    "u_apple": ("Apple Music", "Favorite Songs", [
        ("Alright", "Kendrick Lamar", "To Pimp a Butterfly"), ("DNA.", "Kendrick Lamar", "DAMN."),
        ("Pink + White", "Frank Ocean", "Blonde"), ("Nights", "Frank Ocean", "Blonde"),
        ("Thinking Bout You", "Frank Ocean", "channel ORANGE"), ("Good Days", "SZA", "SOS"),
        ("Snooze", "SZA", "SOS"), ("Come Down", "Anderson .Paak", "Malibu"),
        ("Am I Wrong", "Anderson .Paak", "Malibu"), ("Untitled (How Does It Feel)", "D'Angelo", "Voodoo"),
        ("On & On", "Erykah Badu", "Baduizm"), ("EARFQUAKE", "Tyler, The Creator", "IGOR"),
        ("See You Again", "Tyler, The Creator", "Flower Boy"), ("Feather", "Nujabes", "Modal Soul"),
        ("Aruarian Dance", "Nujabes", "Samurai Champloo Music Record: Departure"),
        ("Don't Cry", "J Dilla", "Donuts"), ("Accordion", "Madvillain", "Madvillainy"),
        ("Truth", "Kamasi Washington", "Harmony of Difference"), ("Afro Blue", "Robert Glasper", "Black Radio"),
        ("Them Changes", "Thundercat", "Drunk"), ("Cranes in the Sky", "Solange", "A Seat at the Table"),
        ("Nakamarra", "Hiatus Kaiyote", "Tawk Tomahawk"), ("Venom", "Little Simz", "Grey Area"),
        ("Time Moves Slow", "BADBADNOTGOOD", "IV"),
        ("Journey in Satchidananda", "Alice Coltrane", "Journey in Satchidananda"),
    ]),
    "u_ytmusic": ("YouTube Music", "Liked Music", [
        ("Ditto", "NewJeans", "OMG"), ("Hype Boy", "NewJeans", "New Jeans"), ("Super Shy", "NewJeans", "Get Up"),
        ("Blueming", "IU", "Love poem"), ("Love wins all", "IU", "The Winning"),
        ("Supernova", "aespa", "Armageddon"), ("ANTIFRAGILE", "LE SSERAFIM", "ANTIFRAGILE"),
        ("Dynamite", "BTS", "Dynamite"), ("와리가리", "혁오", "22"), ("TOMBOY", "혁오", "23"),
        ("EVERYTHING", "검정치마", "TEAM BABY"), ("주저하는 연인들을 위해", "잔나비", "전설"),
        ("Square (2017)", "백예린", "Every letter I sent you."),
        ("Plastic Love", "Mariya Takeuchi", "Variety"), ("Ride on Time", "Tatsuro Yamashita", "Ride on Time"),
        ("Mayonaka no Door", "Miki Matsubara", "Pocket Park"),
        ("An Ending (Ascent)", "Brian Eno", "Apollo: Atmospheres and Soundtracks"),
        ("Merry Christmas Mr. Lawrence", "Ryuichi Sakamoto", "Merry Christmas Mr. Lawrence"),
        ("Glimpse of Us", "Joji", "Smithereens"), ("(It Goes Like) Nanana", "Peggy Gou", "I Hear You"),
        ("Starry Night", "Peggy Gou", "Moment"), ("Kerala", "Bonobo", "Migration"),
    ]),
}

# Last.fm 상위 태그 대신 손으로 지정 (태그, 가중치). 실제 서비스는 API로 받아옴
EXT_TAGS = {
    "Slowdive": [("shoegaze", 1), ("dream pop", .8), ("indie rock", .4)],
    "My Bloody Valentine": [("shoegaze", 1), ("noise", .5), ("indie rock", .4)],
    "Beach House": [("dream pop", 1), ("indie rock", .4), ("synth-pop", .3)],
    "Cocteau Twins": [("dream pop", 1), ("shoegaze", .5)],
    "Radiohead": [("alternative", 1), ("indie rock", .6), ("electronic", .4), ("experimental", .4)],
    "Explosions in the Sky": [("post-rock", 1), ("ambient", .3)],
    "Mogwai": [("post-rock", 1), ("indie rock", .3)],
    "Sigur Rós": [("post-rock", 1), ("ambient", .6), ("dream pop", .3)],
    "Mitski": [("indie rock", 1), ("singer-songwriter", .7), ("bedroom pop", .4)],
    "Japanese Breakfast": [("indie rock", .8), ("dream pop", .7), ("synth-pop", .4)],
    "Phoebe Bridgers": [("singer-songwriter", 1), ("indie rock", .6), ("folk", .5)],
    "Big Thief": [("indie rock", .9), ("folk", .8), ("singer-songwriter", .6)],
    "Turnover": [("dream pop", .9), ("indie rock", .8), ("shoegaze", .3)],
    "Boards of Canada": [("idm", 1), ("electronic", .8), ("ambient", .7)],
    "Four Tet": [("electronic", 1), ("idm", .7), ("house", .6)],
    "Bonobo": [("electronic", 1), ("downtempo", .8), ("house", .4)],
    "Kendrick Lamar": [("hip-hop", 1), ("conscious hip-hop", .8), ("jazz fusion", .2)],
    "Frank Ocean": [("r&b/soul", 1), ("neo-soul", .7), ("alternative r&b", .9)],
    "SZA": [("r&b/soul", 1), ("neo-soul", .6), ("alternative r&b", .7)],
    "Anderson .Paak": [("funk", 1), ("r&b/soul", .8), ("hip-hop", .6), ("soul", .5)],
    "D'Angelo": [("neo-soul", 1), ("r&b/soul", .9), ("funk", .5)],
    "Erykah Badu": [("neo-soul", 1), ("r&b/soul", .8), ("soul", .5)],
    "Tyler, The Creator": [("hip-hop", 1), ("neo-soul", .4), ("funk", .3)],
    "Nujabes": [("instrumental hip-hop", 1), ("lo-fi", .8), ("jazz", .5), ("boom bap", .4)],
    "J Dilla": [("instrumental hip-hop", 1), ("boom bap", .8), ("hip-hop", .6)],
    "Madvillain": [("hip-hop", 1), ("boom bap", .8), ("underground hip-hop", .8)],
    "Kamasi Washington": [("spiritual jazz", 1), ("jazz", .9), ("jazz fusion", .6)],
    "Robert Glasper": [("jazz", 1), ("jazz fusion", .8), ("neo-soul", .6)],
    "Thundercat": [("funk", 1), ("jazz fusion", .8), ("soul", .4)],
    "Solange": [("r&b/soul", 1), ("neo-soul", .8), ("soul", .5)],
    "Hiatus Kaiyote": [("neo-soul", 1), ("jazz fusion", .7), ("funk", .5)],
    "Little Simz": [("hip-hop", 1), ("uk hip-hop", .8), ("boom bap", .3)],
    "BADBADNOTGOOD": [("jazz", 1), ("jazz fusion", .8), ("instrumental hip-hop", .6)],
    "Alice Coltrane": [("spiritual jazz", 1), ("jazz", .8), ("free jazz", .5)],
    "NewJeans": [("k-pop", 1), ("pop", .7), ("synth-pop", .4)],
    "IU": [("k-pop", 1), ("pop", .7), ("singer-songwriter", .4)],
    "aespa": [("k-pop", 1), ("pop", .6), ("electronic", .4)],
    "LE SSERAFIM": [("k-pop", 1), ("pop", .7), ("house", .2)],
    "BTS": [("k-pop", 1), ("pop", .8)],
    "혁오": [("korean indie", 1), ("indie rock", .8), ("alternative", .4)],
    "검정치마": [("korean indie", 1), ("indie rock", .8), ("dream pop", .3)],
    "잔나비": [("korean indie", 1), ("indie rock", .6), ("soul", .3)],
    "백예린": [("korean indie", .8), ("r&b/soul", .6), ("bedroom pop", .6), ("dream pop", .4)],
    "Mariya Takeuchi": [("city pop", 1), ("pop", .6), ("funk", .4)],
    "Tatsuro Yamashita": [("city pop", 1), ("funk", .6), ("soul", .4)],
    "Miki Matsubara": [("city pop", 1), ("pop", .5)],
    "Brian Eno": [("ambient", 1), ("new age", .5), ("drone", .4), ("experimental", .4)],
    "Ryuichi Sakamoto": [("film score", 1), ("ambient", .7), ("soundtrack", .6), ("electronic", .4)],
    "Joji": [("bedroom pop", .9), ("lo-fi", .7), ("r&b/soul", .5)],
    "Peggy Gou": [("house", 1), ("electronic", .9), ("techno", .4)],
}


def main(db_path):
    for uid, (platform, playlist, songs) in USERS.items():
        with open(ROOT / f"data/likes/{uid}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(COLS)
            for t, a, al in songs:
                w.writerow([t, a, al, playlist, "Favorite", ""])
        print(f"{uid}: {len(songs)} likes ({platform})")

    with open(ROOT / "data/ext_artist_tags.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["artist_name", "tag", "weight"])
        for a, tags in EXT_TAGS.items():
            for t, wt in tags:
                w.writerow([a, t, wt])

    # Bandcamp 팬 컬렉션: 가상 팬이 1~2개 장르 위주로 앨범을 모음
    con = sqlite3.connect(db_path)
    items = con.execute("""
        SELECT i.item_id, i.url, t.tag AS genre, COALESCE(s.n, 0) AS sales
        FROM dim_item i
        JOIN item_tags t ON t.item_id = i.item_id AND t.is_genre = 1
        LEFT JOIN (SELECT item_id, COUNT(*) n FROM fact_sales GROUP BY item_id) s ON s.item_id = i.item_id
        WHERE i.item_type IN ('a', 'p')""").fetchall()
    by_genre = {}
    for iid, url, g, n in items:
        by_genre.setdefault(g, []).append((url, n))
    genres = sorted(by_genre)
    rows = set()
    for fan in range(3000):
        k = 1 if rng.random() < .55 else 2
        favs = rng.choice(genres, size=k, replace=False)
        for _ in range(int(rng.integers(4, 30))):
            g = favs[0] if (k == 1 or rng.random() < .65) else favs[1]
            if rng.random() < .12:                          # 가끔 다른 장르도 삼
                g = genres[rng.integers(len(genres))]
            pool = by_genre[g]
            wts = np.array([n + 2 for _, n in pool], float)
            url = pool[rng.choice(len(pool), p=wts / wts.sum())][0]
            rows.add((f"fan{fan:04d}", url))
    with open(ROOT / "data/fan_collections.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fan_id", "item_url"])
        w.writerows(sorted(rows))
    print(f"fan_collections: {len(rows):,} rows")
    write_album_details(con)


CITIES = {"USD": ["Portland, Oregon", "Brooklyn, New York", "Chicago, Illinois", "Austin, Texas", "Los Angeles, California",
                  "Philadelphia, Pennsylvania", "Seattle, Washington", "Detroit, Michigan"],
          "GBP": ["London, UK", "Glasgow, UK", "Manchester, UK", "Bristol, UK", "Leeds, UK"],
          "EUR": ["Berlin, Germany", "Paris, France", "Amsterdam, Netherlands", "Brussels, Belgium", "Lisbon, Portugal",
                  "Milan, Italy", "Helsinki, Finland"],
          "JPY": ["Tokyo, Japan", "Osaka, Japan", "Kyoto, Japan"],
          "CAD": ["Montréal, Québec", "Toronto, Ontario", "Vancouver, British Columbia"],
          "AUD": ["Melbourne, Australia", "Sydney, Australia", "Brisbane, Australia"]}
LABELS = ["Hollow Pine Records", "Night Ferry Tapes", "Glasshouse Editions", "Copper Field", "Low Orbit Recordings",
          "Paper Lantern Music", "Tidepool", "Static Garden", "Moth & Signal", "Grey Harbour"]
ABOUT = {
    "rock": "기타 노이즈와 리버브 사이로 멜로디가 떠오르는 {n}곡짜리 앨범.",
    "pop": "아날로그 신스와 속삭이는 보컬로 만든 {n}곡의 침실 팝.",
    "electronic": "새벽 클럽과 헤드폰 사이 어딘가를 겨냥한 {n}곡의 전자음악.",
    "ambient": "느리게 번지는 드론과 필드 레코딩으로 채운 {n}개의 장면.",
    "hip-hop": "먼지 낀 샘플과 둔탁한 드럼으로 쌓은 {n}곡의 비트 테이프.",
    "r&b/soul": "따뜻한 키보드와 그루브 위에 얹은 {n}곡의 소울.",
    "jazz": "즉흥과 작곡의 경계를 오가는 {n}곡의 라이브 세션.",
    "punk": "3분을 넘기지 않는 {n}곡, 지하실에서 원테이크로 녹음.",
    "metal": "저음 튜닝과 긴 호흡으로 밀어붙이는 {n}곡.",
    "folk": "어쿠스틱 기타와 목소리만으로 남긴 {n}곡의 기록.",
    "experimental": "소리의 질감 자체를 탐구하는 {n}개의 실험.",
    "soundtrack": "가상의 영화와 게임을 위해 쓴 {n}곡의 스코어.",
}
FAMILY_OF = {"electronic": "electronic", "ambient": "ambient", "hip-hop": "hip-hop", "rock": "rock", "punk": "punk",
             "metal": "metal", "experimental": "experimental", "jazz": "jazz", "folk": "folk", "pop": "pop",
             "soundtrack": "soundtrack", "r&b/soul": "r&b/soul"}


def write_album_details(con):
    """디지털 앨범마다 앨범 페이지에서 크롤했을 법한 상세 정보를 만듦 (가상)."""
    rows = con.execute("""
        SELECT i.url, i.currency, MAX(CASE WHEN t.is_genre = 1 THEN t.tag END) AS genre
        FROM dim_item i LEFT JOIN item_tags t ON t.item_id = i.item_id
        WHERE i.item_type = 'a' GROUP BY i.url, i.currency""").fetchall()
    out = []
    for url, cur, genre in rows:
        n = int(rng.integers(4, 15))
        dur = int(sum(rng.integers(150, 420) for _ in range(n)))
        y = int(rng.choice([2016, 2018, 2020, 2021, 2022, 2023, 2024, 2025, 2025, 2026, 2026, 2026]))
        m = int(rng.integers(1, 12 if y == 2026 else 13))
        d = int(rng.integers(1, 29))
        label = None if rng.random() < .45 else str(rng.choice(LABELS))
        loc = str(rng.choice(CITIES.get(cur, CITIES["USD"])))
        about = ABOUT.get(FAMILY_OF.get(genre or "", ""), "{n}곡이 담긴 앨범.").format(n=n)
        out.append((url, "", "", f"{y}-{m:02d}-{d:02d}", n, dur, label or "", loc, about))
    with open(ROOT / "data/album_details.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "art_id", "art_url", "release_date", "track_count", "duration_sec", "label", "location", "about"])
        w.writerows(out)
    print(f"album_details: {len(out):,} albums (커버 없음: 대시보드가 생성형 커버를 그림)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "bandcamp.db"))
