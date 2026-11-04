"""Check a finished reading's house and lordship statements against the chart.

A reading can be in any of six languages, so a model extracts the statements as
structured claims. The verdict is plain code comparing each claim with the
computed chart: the model never decides what is correct. A claim is reported only
when its quote really appears in the reading and it contradicts the chart.

Pure logic, no FastAPI or HTTP. The caller makes the LLM call.
"""
import json
import re

from src.core.translations import READING_CHECK_NOTE
from src.engines.prediction_engine import compute_houses, house_lords

GRAHAS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
MAX_NOTE_LINES = 5
_MAX_QUOTE_CHARS = 120


def chart_facts(chart):
    """Per-graha facts from a chart: occupied house, houses ruled, and combustion."""
    placements = chart["placements"]
    lagna_idx, houses = compute_houses(placements)
    lords = house_lords(lagna_idx)
    facts = {}
    for graha in GRAHAS:
        if graha in placements and graha in houses:
            facts[graha] = {
                "house": houses[graha],
                "lord_of": sorted(h for h, lord in lords.items() if lord == graha),
                "combust": bool(placements[graha].get("is_combust")),
            }
    return facts


def format_fact_sheet(facts_by_person):
    """Prompt block that states occupation and lordship separately for each graha."""
    lines = [
        "--- VERIFIED OCCUPATION & LORDSHIP FACTS ---",
        "Occupying a house does not make a graha that house's lord. Copy these facts exactly.",
        "A yoga formed by a combust graha must be described as weakened.",
    ]
    for person, facts in facts_by_person.items():
        lines.append(f"{person}:")
        for graha, fact in facts.items():
            ruled = ", ".join(str(h) for h in fact["lord_of"]) or "none"
            combust = "; combust" if fact["combust"] else ""
            lines.append(f"- {graha}: occupies house {fact['house']}; lord of houses: {ruled}{combust}")
    return "\n".join(lines)


def build_claim_prompt(reading, people):
    names = ", ".join(people)
    return f"""Extract statements from this Vedic astrology reading. It may be in any language.

List each statement that says a graha in a person's birth chart either occupies a numbered house or is the lord of a numbered house, with the house counted from that person's own Lagna.

Leave out transits, divisional charts, dasas, houses counted from the Moon, one person's graha falling in the other person's house, houses given only by name, and general rules that are not about these charts.

People in this reading: {names}
Grahas: {", ".join(GRAHAS)}

Reply with only a JSON array, and [] if there are none. Each item must have:
{{"person": "<name from the list>", "planet": "<graha in English>", "claim": "occupies" or "lord_of", "house": <1-12>, "quote": "<the exact words from the reading, copied character for character>"}}

READING:
{reading}
"""


def parse_claims(raw):
    """Parse the model's reply. Anything unusable yields no claims."""
    match = re.search(r"\[.*\]", raw or "", re.DOTALL)
    if not match:
        return []
    try:
        claims = json.loads(match.group(0))
    except ValueError:
        return []
    return [c for c in claims if isinstance(c, dict)] if isinstance(claims, list) else []


def _squash(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _resolve_person(person, facts_by_person):
    if len(facts_by_person) == 1:
        return next(iter(facts_by_person))
    wanted = _squash(str(person or "")).lower()
    if not wanted:
        return None
    matches = [name for name in facts_by_person if wanted in name.lower() or name.lower() in wanted]
    return matches[0] if len(matches) == 1 else None


def find_contradictions(claims, facts_by_person, reading):
    """Return the claims that contradict the computed chart, without duplicates."""
    text = _squash(reading)
    found, seen = [], set()
    for claim in claims:
        planet = claim.get("planet")
        kind = claim.get("claim")
        house = claim.get("house")
        quote = _squash(str(claim.get("quote") or ""))
        person = _resolve_person(claim.get("person"), facts_by_person)
        if (person is None or planet not in GRAHAS or kind not in ("occupies", "lord_of")
                or isinstance(house, bool) or not isinstance(house, int) or not 1 <= house <= 12
                or not quote or quote not in text):
            continue
        facts = facts_by_person[person].get(planet)
        if facts is None:
            continue
        if kind == "occupies":
            wrong = facts["house"] != house
        else:
            # Rahu and Ketu have no lordship here, and co-lordship traditions vary.
            wrong = bool(facts["lord_of"]) and house not in facts["lord_of"]
        key = (person, planet, kind, house)
        if wrong and key not in seen:
            seen.add(key)
            found.append({"person": person, "planet": planet, "quote": quote, **facts})
    return found


def render_note(contradictions, lang, planet_names=None, show_person=True):
    """Text appended to the reading, in its language. Empty when nothing is wrong."""
    if not contradictions:
        return ""
    labels = READING_CHECK_NOTE.get(lang) or READING_CHECK_NOTE["en"]
    names = planet_names or {}
    lines = [f"\n\n---\n**⚠️ {labels['heading']}**\n\n{labels['intro']}\n"]
    for item in contradictions[:MAX_NOTE_LINES]:
        quote = item["quote"]
        if len(quote) > _MAX_QUOTE_CHARS:
            quote = quote[:_MAX_QUOTE_CHARS] + "…"
        planet = names.get(item["planet"], item["planet"])
        who = f"{planet} ({item['person']})" if show_person else planet
        fact = labels["occupies"].format(house=item["house"])
        if item["lord_of"]:
            ruled = ", ".join(str(h) for h in item["lord_of"])
            fact += "; " + labels["lord_of"].format(lords=ruled)
        lines.append(f"- “{quote}” → **{who}:** {fact}")
    return "\n".join(lines) + "\n"
