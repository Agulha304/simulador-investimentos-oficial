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


def test_influencer_channel_gear_invest_and_month_close(client, rich):
    c = client.post(f"{A}/channels", headers=rich, json={"platform": "youtube", "niche": "tecnologia", "name": "Canal Teste"})
    assert c.status_code == 200, c.text
    cid = c.json()["result"]["channel_id"]
    assert client.post(f"{A}/channels", headers=rich, json={"platform": "youtube", "niche": "games", "name": "Outro"}).status_code == 409
    assert client.post(f"{A}/channels/{cid}/gear", headers=rich, json={"category": "camera"}).status_code == 200
    assert client.post(f"{A}/channels/{cid}/gear", headers=rich, json={"category": "xx"}).status_code == 400
    ov = client.post(f"{A}/channels/{cid}/invest", headers=rich, json={"kind": "editor"}).json()
    ch = ov["channels"][0]
    assert ch["gear"]["camera"] == 1 and ch["flags"]["editor"] and ch["quality"] > 0 and ov["committed_hours"] > 0
    assert client.post(f"{A}/channels/{cid}/invest", headers=rich, json={"kind": "editor"}).status_code == 409
    assert client.post(f"{A}/channels/{cid}/invest", headers=rich, json={"kind": "agencia"}).status_code == 409        # exige 10 mil inscritos
    assert client.put(f"{A}/channels/{cid}/cadence", headers=rich, json={"cadence": 8}).status_code == 200
    assert client.put(f"{A}/channels/{cid}/cadence", headers=rich, json={"cadence": 7}).status_code == 400
    assert close(client, rich).status_code == 200
    after = client.get(A, headers=rich).json()["channels"][0]
    assert after["views"] > 0 and len(after["history"]) == 1 and after["last"]["quality"] > 0
    assert client.delete(f"{A}/channels/{cid}/invest/editor", headers=rich).status_code == 200
    assert client.delete(f"{A}/channels/{cid}", headers=rich).status_code == 200
    assert client.get(A, headers=rich).json()["channels"] == []
