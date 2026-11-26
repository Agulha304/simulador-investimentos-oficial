"""Carreira de artista (ator, músico, pintor, influenciador) e horas de trabalho PJ."""
from decimal import Decimal

from backend.services import artist_rules as AR
from backend.services import career_hub_rules as H
from tests.test_companies import close, rich  # noqa: F401

A = "/api/artist"
D = Decimal


# ------------------------------------------------------------------ PJ com horas reais
def test_pj_hours_are_realistic_varied_and_bounded():
    vals = {(f, lv): H.pj_hours(f, lv, 7, f"{f}:{lv}") for f in ("tecnologia", "saude", "artes", "comercio") for lv in range(4)}
    assert all(H.PJ_MIN_HOURS <= v <= H.PJ_MAX_HOURS for v in vals.values())
    assert min(vals.values()) >= 48 and max(vals.values()) <= 140 and len(set(vals.values())) >= 6              # varia de contrato para contrato
    assert H.pj_hours("tecnologia", 3, 7, "k") > H.pj_hours("tecnologia", 0, 7, "k")                              # mais nível, mais horas
    assert H.PJ_EXTRA_HOURS >= 48


def test_pj_offers_show_hours(client, rich):
    r = client.get("/api/career/offers?field=tecnologia", headers=rich)
    assert r.status_code == 200, r.text
    assert all(o["pj"]["hours"] >= 48 for o in r.json()["offers"])


# ------------------------------------------------------------------ regras puras
def test_artist_rules_math():
    assert AR.hire_chance(70, 30, 40, 0) > AR.hire_chance(30, 0, 40, 0) and 0.03 <= AR.hire_chance(0, 0, 90, 90) <= 0.92
    assert AR.INSTRUMENTS["vocal"][1] > AR.INSTRUMENTS["trompete"][1]
    assert AR.label_accepts(85, 60, 1.4, 0.2) and not AR.label_accepts(20, 0, 0.7, 0.9)
    g0, g5 = {k: 0 for k in AR.GEAR}, {k: 5 for k in AR.GEAR}
    assert AR.channel_quality(30, g5, True) > AR.channel_quality(30, g0, False) + 40
    assert AR.channel_revenue(100000, 100, "youtube", "games", False, 20) == (0, 0)                              # abaixo da meta de monetização
    ads, shop = AR.channel_revenue(100000, 5000, "youtube", "financas", True, 60)
    assert ads > 0 and shop > 0
    assert AR.month_views(5000, 60, 0, "games", "youtube", 1.0, False, False, 0.5) < AR.month_views(5000, 60, 8, "games", "youtube", 1.0, False, False, 0.5)
    assert AR.sponsorship(500, "games", False, 1, 1, __import__("datetime").date(2026, 11, 1)) == 0


def test_gear_prices_increase_with_level():
    for k, (_, prices) in AR.GEAR.items():
        assert prices == sorted(prices) and len(prices) == 5


# ------------------------------------------------------------------ API
def test_overview_and_catalogs(client, rich):
    r = client.get(A, headers=rich)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["instrument"] is None and set(j["skills"]) == set(AR.DISCIPLINES)
    assert len(j["offers"]["acting"]) >= 3 and j["offers"]["music"] == [] and len(j["offers"]["painting"]) >= 3
    assert {x["key"] for x in j["catalog"]["instruments"]} == set(AR.INSTRUMENTS) and len(j["catalog"]["niches"]) == len(AR.NICHES)


def test_actor_and_painter_hiring_flow(client, rich):
    ov = client.get(A, headers=rich).json()
    for disc in ("acting", "painting"):
        offer = ov["offers"][disc][0]
        r = client.post(f"{A}/apply", headers=rich, json={"discipline": disc, "offer_key": offer["key"]})
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["result"]["hired"], bool)
        again = client.post(f"{A}/apply", headers=rich, json={"discipline": disc, "offer_key": offer["key"]})
        assert again.status_code == 409                                                       # não repete a mesma candidatura
    t = client.post(f"{A}/train", headers=rich, json={"discipline": "acting"})
    assert t.status_code == 200 and t.json()["result"]["gain"] > 0
    assert client.post(f"{A}/train", headers=rich, json={"discipline": "acting"}).status_code == 409


def test_musician_instrument_jobs_band_song_and_promotion(client, rich):
    assert client.post(f"{A}/apply", headers=rich, json={"discipline": "music", "offer_key": "x"}).status_code == 400    # sem instrumento
    assert client.post(f"{A}/band", headers=rich, json={"name": "Os Testes", "style": "rock"}).status_code == 400
    r = client.post(f"{A}/instrument", headers=rich, json={"instrument": "guitarra"})
    assert r.status_code == 200 and r.json()["instrument"] == "guitarra" and r.json()["offers"]["music"]
    assert client.post(f"{A}/instrument", headers=rich, json={"instrument": "pandeiro"}).status_code == 400
    b = client.post(f"{A}/band", headers=rich, json={"name": "Os Testes", "style": "rock"})
    assert b.status_code == 200 and b.json()["band"]["name"] == "Os Testes" and len(b.json()["band"]["members"]) == 1
    assert client.post(f"{A}/band", headers=rich, json={"name": "Outra", "style": "pop"}).status_code == 409
    pool = b.json()["market_musicians"] + b.json()["friend_musicians"]
    joined = False
    for c in pool:
        rr = client.post(f"{A}/band/recruit", headers=rich, json={"key": c["key"]})
        if rr.status_code == 409:                                                           # banda cheia (6 integrantes)
            assert "integrantes" in rr.json()["detail"]
            break
        assert rr.status_code == 200 and "joined" in rr.json()["result"]
        joined = joined or rr.json()["result"]["joined"]
    ov = client.get(A, headers=rich).json()
    assert (len(ov["band"]["members"]) > 1) == joined
    made = None
    for theme in ("amor", "saudade", "festa", "superacao", "cotidiano", "liberdade", "tristeza", "natureza"):
        s = client.post(f"{A}/song", headers=rich, json={"scope": "BAND", "style": "rock", "theme": theme})
        assert s.status_code in (200, 409), s.text
        if s.status_code == 200 and s.json()["result"]["created"]:
            made = s.json()
            break
    if made is None:                                                                        # banda de um só fraca: tenta em carreira solo
        for theme in ("amor", "saudade", "festa", "superacao", "cotidiano", "liberdade", "tristeza", "natureza", "politica", "fe", "viagem"):
            s = client.post(f"{A}/song", headers=rich, json={"scope": "SOLO", "style": "pop", "theme": theme})
            if s.status_code == 200 and s.json()["result"]["created"]:
                made = s.json()
                break
    if made is not None:
        dec = made["decisions"][0]                                                          # a decisão de divulgação aparece logo depois da música
        assert {o["key"] for o in dec["options"]} == set(AR.SONG_PROMO)
        r = client.post(f"{A}/decisions/{dec['id']}", headers=rich, json={"option": "boca"})
        assert r.status_code == 200 and r.json()["decisions"] == []
        assert client.post(f"{A}/decisions/{dec['id']}", headers=rich, json={"option": "boca"}).status_code == 409
        assert any(w["work"] == "SONG" and w["status"] in ("PUBLISHED", "UNPROMOTED") for w in r.json()["works"])
    g = client.post(f"{A}/gig", headers=rich, json={"tier": "bar", "scope": "BAND"})
    assert g.status_code == 200 and isinstance(g.json()["result"]["booked"], bool)
    assert client.post(f"{A}/gig", headers=rich, json={"tier": "bar", "scope": "BAND"}).status_code == 409
    assert client.post(f"{A}/album", headers=rich, json={"scope": "SOLO", "mode": "INDIE"}).status_code == 409        # falta repertório


def test_painting_flow_and_promotion_decision(client, rich):
    p = client.post(f"{A}/painting", headers=rich, json={"theme": "paisagem", "style": "realismo", "size": "pequeno"})
    assert p.status_code == 200, p.text
    dec = p.json()["decisions"][0]
    assert {o["key"] for o in dec["options"]} == set(AR.PAINT_PROMO)
    r = client.post(f"{A}/decisions/{dec['id']}", headers=rich, json={"option": "doacao"})
    assert r.status_code == 200 and r.json()["fame"]["painting"] > 0
    assert client.post(f"{A}/painting", headers=rich, json={"theme": "x", "style": "realismo", "size": "pequeno"}).status_code == 400


def test_platform_monetization_goals_follow_real_rules():
    yt = AR.PLATFORM_RULES["youtube"]
    assert (yt[0]["subs"], yt[0]["watch_12m"], yt[0]["uploads_90d"]) == (500, 3000, 3) and (yt[1]["subs"], yt[1]["watch_12m"]) == (1000, 4000)
    assert AR.PLATFORM_RULES["tiktok"][0]["subs"] == 10000 and AR.PLATFORM_RULES["twitch"][0]["subs"] == 50
    assert [t["subs"] for t in AR.PLATFORM_RULES["instagram"]] == [1000, 5000, 10000]
    assert AR.tier_status("youtube", 1500, watch_12m=4500)["tier"]["key"] == "FULL"
    assert AR.tier_status("youtube", 700, watch_12m=3500, uploads_90d=4)["tier"]["key"] == "EXPANDED"
    st = AR.tier_status("youtube", 900, watch_12m=1000)
    assert st["tier"] is None and st["next"]["key"] == "EXPANDED" and {m["goal"] for m in st["next"]["missing"]} == {3000, 3}
    assert AR.channel_money("youtube", None, 100000, 5000, "games", 50, False) == (0, 0, 0)
    ads, fan, shop = AR.channel_money("youtube", yt[1], 100000, 5000, "financas", 60, True)
    assert ads > 0 and fan > 0 and shop > 0
    ig = AR.channel_money("instagram", AR.PLATFORM_RULES["instagram"][2], 100000, 12000, "beleza", 60, False)
    assert ig[0] == 0 and ig[1] > 0                                                              # Instagram não divide anúncios


def test_topic_fit_and_sponsor_catalog():
    assert AR.topic_fit("tecnologia", "painting") < 0.3 < AR.topic_fit("beleza", "painting")
    assert AR.topic_fit("musica", "song") > 1 > AR.topic_fit("financas", "song") and AR.topic_fit("negocios", "company") > 1
    bet = next(x for x in AR.SPONSORS if "bet" in x[1].lower())
    assert bet[4] >= 0.8 and bet[3] >= 3 * min(x[3] for x in AR.SPONSORS)                         # bet paga muito e é arriscada


def test_events_data_is_consistent():
    discs = {e["disc"] for e in AR.EVENTS.values()}
    assert discs == {"influencer", "music", "acting", "painting"}
    assert {"bet_publi", "fa_na_rua", "tocar_na_rua"} <= set(AR.EVENTS)
    for k, e in AR.EVENTS.items():
        for o in e["options"]:
            assert abs(sum(x[0] for x in o["outcomes"]) - 1) < 1e-6, (k, o["key"])


def test_music_lessons_general_or_specific_instrument(client, rich):
    client.post(f"{A}/instrument", headers=rich, json={"instrument": "guitarra"})
    base = client.get(A, headers=rich).json()
    g = client.post(f"{A}/train", headers=rich, json={"discipline": "music", "instrument": "geral"})
    assert g.status_code == 200 and g.json()["result"]["instrument"] is None
    sp = client.post(f"{A}/train", headers=rich, json={"discipline": "music", "instrument": "guitarra"})
    assert sp.status_code == 200 and sp.json()["result"]["instrument"] == "guitarra"
    ov = sp.json()
    assert ov["inst_skills"]["guitarra"] > 0 and ov["effective_music"] > base["effective_music"]
    assert client.post(f"{A}/train", headers=rich, json={"discipline": "music", "instrument": "guitarra"}).status_code == 409
    assert client.post(f"{A}/train", headers=rich, json={"discipline": "music", "instrument": "pandeiro"}).status_code == 400
    other = client.post(f"{A}/instrument", headers=rich, json={"instrument": "violino"}).json()
    assert other["effective_music"] < ov["effective_music"]                                          # o treino específico fica no instrumento


def test_influencer_accounts_multi_platform_and_selective_videos(client, rich):
    r = client.post(f"{A}/accounts", headers=rich, json={"name": "Games do Zé", "niche": "games", "platforms": ["youtube", "tiktok", "twitch"]})
    assert r.status_code == 200, r.text
    aid = r.json()["result"]["account_id"]
    assert len(r.json()["influencer"]["accounts"][0]["channels"]) == 3
    t = client.post(f"{A}/accounts", headers=rich, json={"name": "Tech do Zé", "niche": "tecnologia", "platforms": ["youtube", "instagram"]})
    assert t.status_code == 200 and len(t.json()["influencer"]["accounts"]) == 2                    # duas contas (nichos), cada uma com canais próprios
    assert client.post(f"{A}/accounts/{aid}/channels", headers=rich, json={"platform": "youtube"}).status_code == 409
    assert client.post(f"{A}/accounts/{aid}/channels", headers=rich, json={"platform": "podcast"}).status_code == 200
    assert client.post(f"{A}/accounts/{aid}/gear", headers=rich, json={"category": "camera"}).status_code == 200
    assert client.post(f"{A}/accounts/{aid}/gear", headers=rich, json={"category": "xx"}).status_code == 400
    ov = client.post(f"{A}/accounts/{aid}/invest", headers=rich, json={"kind": "editor"}).json()
    acc = next(a for a in ov["influencer"]["accounts"] if a["id"] == aid)
    assert acc["gear"]["camera"] == 1 and acc["flags"]["editor"] and acc["quality"] > 0
    assert client.post(f"{A}/accounts/{aid}/invest", headers=rich, json={"kind": "agencia"}).status_code == 409           # exige 10 mil inscritos
    # vídeo só em algumas plataformas
    v = client.post(f"{A}/accounts/{aid}/video", headers=rich, json={"platforms": ["youtube", "tiktok"]})
    assert v.status_code == 200, v.text
    ch = {c["platform"]: c for c in next(a for a in v.json()["influencer"]["accounts"] if a["id"] == aid)["channels"]}
    assert ch["youtube"]["posted"] == 1 and ch["tiktok"]["posted"] == 1 and ch["twitch"]["posted"] == 0 and ch["podcast"]["posted"] == 0
    assert client.post(f"{A}/accounts/{aid}/video", headers=rich, json={"platforms": ["instagram"]}).status_code == 400       # a conta de games não tem Instagram
    allv = client.post(f"{A}/accounts/{aid}/video", headers=rich, json={"platforms": ["youtube", "tiktok", "twitch", "podcast"]})
    assert allv.status_code == 200
    assert close(client, rich).status_code == 200
    after = client.get(A, headers=rich).json()["influencer"]["accounts"]
    g = next(a for a in after if a["id"] == aid)
    yt = next(c for c in g["channels"] if c["platform"] == "youtube")
    assert yt["views"] > 0 and len(yt["history"]) == 1 and yt["posted"] == 0 and yt["next"] is not None and yt["next"]["missing"]
    assert next(c for c in g["channels"] if c["platform"] == "podcast")["history"][0]["posted"] == 1
    assert client.delete(f"{A}/accounts/{aid}/invest/editor", headers=rich).status_code == 200
    assert client.delete(f"{A}/accounts/{aid}", headers=rich).status_code == 200
    assert len(client.get(A, headers=rich).json()["influencer"]["accounts"]) == 1


def test_themed_videos_sell_or_hurt_depending_on_niche_fit(client, rich):
    p = client.post(f"{A}/painting", headers=rich, json={"theme": "paisagem", "style": "realismo", "size": "pequeno"})
    assert p.status_code == 200
    wid = p.json()["result"].get("work_id")
    assert wid and p.json()["influencer"]["promotable"]["painting"]
    aid = client.post(f"{A}/accounts", headers=rich, json={"name": "Canal Tech", "niche": "tecnologia", "platforms": ["youtube"]}).json()["result"]["account_id"]
    r = client.post(f"{A}/accounts/{aid}/video", headers=rich, json={"platforms": ["youtube"], "topic": "painting", "ref_id": wid})
    assert r.status_code == 200 and "não combina" in r.json()["result"]["message"]                    # quadro num canal de tecnologia: mal encaixado
    assert client.post(f"{A}/accounts/{aid}/video", headers=rich, json={"platforms": ["youtube"], "topic": "painting"}).status_code == 400   # falta escolher o quadro
    assert client.post(f"{A}/accounts/{aid}/video", headers=rich, json={"platforms": ["youtube"], "topic": "xx"}).status_code == 400
    aid2 = client.post(f"{A}/accounts", headers=rich, json={"name": "Arte e Vida", "niche": "vlog", "platforms": ["instagram"]}).json()["result"]["account_id"]
    r2 = client.post(f"{A}/accounts/{aid2}/video", headers=rich, json={"platforms": ["instagram"], "topic": "company", "ref_id": 999999})
    assert r2.status_code == 404


def test_artist_event_decision_resolves_with_effects(client, rich):
    from sqlalchemy import select

    from backend.database import SessionLocal
    from backend.models import ArtistItem, SimMonth
    uid = client.get("/api/auth/me", headers=rich).json()["id"]
    client.post(f"{A}/instrument", headers=rich, json={"instrument": "violao"})
    with SessionLocal() as s:
        month = s.scalar(select(SimMonth).where(SimMonth.user_id == uid, SimMonth.status == "OPEN"))
        e = AR.EVENTS["tocar_na_rua"]
        s.add(ArtistItem(user_id=uid, kind="DECISION", status="OPEN", name=e["title"], created_month=month.ref_month,
                         data={"work": "EVENT", "event_key": "tocar_na_rua", "desc": e["desc"], "work_id": 0,
                               "options": [{"key": o["key"], "label": o["label"], "cost": o["cost"], "desc": ""} for o in e["options"]]}))
        s.commit()
    ov = client.get(A, headers=rich).json()
    dec = ov["decisions"][0]
    assert dec["work"] == "EVENT" and dec["desc"] and {o["key"] for o in dec["options"]} == {"tocar", "recusar"}
    r = client.post(f"{A}/decisions/{dec['id']}", headers=rich, json={"option": "tocar"})
    assert r.status_code == 200 and r.json()["decisions"] == [] and r.json()["result"]["message"]
    assert client.post(f"{A}/decisions/{dec['id']}", headers=rich, json={"option": "tocar"}).status_code == 409
