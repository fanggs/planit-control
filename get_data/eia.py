"""EIA-860M discovery, workbook parsing and conservative plant deduplication."""
from collections import Counter, defaultdict
import csv
from datetime import date
from html.parser import HTMLParser
import io
import math
import re
import unicodedata
from urllib.parse import urljoin, urlparse
from zipfile import ZipFile

from openpyxl import load_workbook

EIA_INDEX = "https://www.eia.gov/electricity/data/eia860m/index.php"
COUNTY_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/2026_Gaz_counties_national.zip"
MONTHS = {name: i for i, name in enumerate((
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december"), 1)}
REQUIRED = {"Plant ID", "Plant Name", "Plant State", "County", "Entity Name",
            "Generator ID", "Technology", "Status", "Latitude", "Longitude"}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def discover_latest(html, *, as_of=None):
    """Choose the newest linked workbook month, never the calendar's current month."""
    parser = Links()
    parser.feed(html)
    available = []
    for link in parser.links:
        url = urljoin(EIA_INDEX, link)
        if urlparse(url).hostname != "www.eia.gov":
            continue
        match = re.search(r"/([a-z]+)_generator(\d{4})\.xlsx$", url, re.I)
        if match and match[1].lower() in MONTHS:
            vintage = date(int(match[2]), MONTHS[match[1].lower()], 1)
            if vintage <= (as_of or date.today()):
                available.append((vintage, url))
    if not available:
        raise ValueError("No supported EIA-860M workbook links found")
    vintage, url = max(available)
    return url, vintage.strftime("%Y-%m")


def read_operating(path, vintage):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook["Operating"]
        rows = sheet.iter_rows(values_only=True)
        title = str(next(rows)[0])
        year, month = map(int, vintage.split("-"))
        month_name = next(name for name, number in MONTHS.items() if number == month)
        if f"{month_name} {year}" not in title.lower():
            raise ValueError("Workbook title and requested source vintage disagree")
        for _ in range(15):
            header = tuple(str(v).strip() if v is not None else "" for v in next(rows))
            if REQUIRED.issubset(header):
                if len([h for h in header if h]) != len(set(h for h in header if h)):
                    raise ValueError("Duplicate workbook headers")
                break
        else:
            raise ValueError("EIA workbook headers changed or required columns disappeared")
        return [dict(zip(header, row)) for row in rows
                if row[header.index("Plant ID")] is not None]
    finally:
        workbook.close()


def county_key(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    name = re.sub(r"\bsaint\b", "st", name)
    name = re.sub(r"\s+(county|parish|borough|census area|municipality)$", "", name)
    return re.sub(r"[^a-z0-9]", "", name)


def read_counties(path):
    with ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".txt")]
        if len(names) != 1:
            raise ValueError("Unexpected Census archive contents")
        text = archive.read(names[0]).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter="|" if "|" in text.splitlines()[0] else "\t")
    if not {"USPS", "GEOID", "NAME"}.issubset(reader.fieldnames or []):
        raise ValueError("Census county headers changed")
    lookup = {}
    for row in reader:
        key = (row["USPS"].strip(), county_key(row["NAME"].strip()))
        code = row["GEOID"].strip()
        if not re.fullmatch(r"\d{5}", code) or (key in lookup and lookup[key] != code):
            raise ValueError("Invalid or ambiguous Census county code")
        lookup[key] = code
    return lookup


def positive_id(value):
    if isinstance(value, bool):
        raise ValueError("Invalid plant ID")
    number = float(value)
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise ValueError("Invalid plant ID")
    return int(number)


def clean(value):
    return str(value).strip() if value is not None else ""


def group_plants(rows):
    """Keep OP generators only; reject conflicts rather than pick arbitrary values."""
    grouped, counts, rejected = defaultdict(list), Counter(), []
    for row in rows:
        counts["generator_rows"] += 1
        if clean(row["Status"]) not in {"OP", "(OP) Operating"}:
            counts["non_operating_generator_rows"] += 1
            continue
        try:
            site_id = positive_id(row["Plant ID"])
        except (TypeError, ValueError):
            counts["invalid_id_rows"] += 1
            continue
        grouped[site_id].append(row)
    plants = []
    for site_id, generators in sorted(grouped.items()):
        try:
            ids = [clean(g["Generator ID"]) for g in generators]
            if not all(ids) or len(ids) != len(set(ids)):
                raise ValueError("duplicate_or_missing_generator_id")
            fields = {}
            for source, target in (("Plant Name", "name"), ("Plant State", "state"), ("County", "county")):
                values = {clean(g[source]) for g in generators}
                if len(values) != 1 or not all(values):
                    raise ValueError(f"conflicting_or_missing_{target}")
                fields[target] = values.pop()
            coordinates = []
            for g in generators:
                lat, lon = float(g["Latitude"]), float(g["Longitude"])
                if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
                    raise ValueError("invalid_coordinates")
                coordinates.append((lat, lon))
            # A plant has one source location. Do not average inconsistent locations.
            if len(set(coordinates)) != 1:
                raise ValueError("conflicting_coordinates")
            utilities = sorted({clean(g["Entity Name"]) for g in generators if clean(g["Entity Name"])})
            technologies = sorted({clean(g["Technology"]) for g in generators if clean(g["Technology"])})
            if not utilities or not technologies:
                raise ValueError("missing_utility_or_technology")
            lat, lon = coordinates[0]
            plants.append(dict(fields, site_id=site_id, latitude=lat, longitude=lon,
                               utility="; ".join(utilities), plant_type="; ".join(technologies),
                               operating_status="OP"))
        except (TypeError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "invalid_coordinates"
            counts["rejected_plants"] += 1
            rejected.append({"site_id": site_id, "reason": reason})
    counts["operating_plants_before_validation"] = len(grouped)
    counts["grouped_plants"] = len(plants)
    return plants, dict(counts), rejected
