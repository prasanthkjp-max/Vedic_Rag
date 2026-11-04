"""Personal calendar overlay: Tara Bala, Chandrashtama and star-birthday flags for
one native across a month of panchangam days. Pure computation, no HTTP or DB."""
from src.engines.astro_engine import NAKSHATRAS

TARA_NAMES = (
    "Janma", "Sampat", "Vipat", "Kshema", "Pratyak",
    "Sadhaka", "Naidhana", "Mitra", "Paramamitra",
)
HIGHLIGHTED_TARAS = frozenset({"Sampat", "Kshema", "Sadhaka", "Mitra", "Paramamitra"})


def janma_details(chart: dict) -> dict:
    """Birth star, Moon sign and solar month from a chart computed at the birth moment."""
    panchangam = chart["panchangam"]
    return {
        "nakshatra": panchangam["nakshatra"],
        "nakshatra_index": NAKSHATRAS.index(panchangam["nakshatra"]),
        "rasi_index": chart["placements"]["Moon"]["rasi_index"],
        "solar_month": panchangam["tamil_month"],
    }


def tara_bala(janma_nakshatra_index: int, day_nakshatra_index: int) -> tuple[int, str]:
    """(1-9, name) of the day's star, counted inclusively from the birth star."""
    position = ((day_nakshatra_index - janma_nakshatra_index) % 27) % 9
    return position + 1, TARA_NAMES[position]


def is_chandrashtama(janma_rasi_index: int, moon_rasi_index: int) -> bool:
    """True when the transiting Moon is in the 8th rasi from the birth Moon sign."""
    return (moon_rasi_index - janma_rasi_index) % 12 == 7


def build_day_overlay(janma: dict, day: dict) -> dict:
    """Flags for one day of `_compute_month_panchangam` output.

    The Moon can change rasi during the day, so Chandrashtama is flagged if the Moon
    is in the 8th at sunrise or at the following midnight. The star comes from
    sunrise, matching the star the calendar shows. A solar month that holds the star
    twice flags both dates as the annual star birthday.
    """
    day_star = day.get("nakshatra_index", -1)
    if day_star < 0:
        tara_num, tara_name = None, None
    else:
        tara_num, tara_name = tara_bala(janma["nakshatra_index"], day_star)

    moon_positions = (day.get("moon_rasi_index"), day.get("moon_rasi_index_end"))
    star_day = day_star == janma["nakshatra_index"]
    return {
        "tara_num": tara_num,
        "tara_name": tara_name,
        "tara_good": tara_name in HIGHLIGHTED_TARAS,
        "chandrashtama": any(
            position is not None and is_chandrashtama(janma["rasi_index"], position)
            for position in moon_positions
        ),
        "star_day": star_day,
        "star_birthday": star_day and day.get("solar_month") == janma["solar_month"],
    }
