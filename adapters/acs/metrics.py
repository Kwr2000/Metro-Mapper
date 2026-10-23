"""The task's Census cells and neutral display choices, shared by adapter and generator."""

VINTAGE = "ACS 2020–2024 5-year estimates"
ATTRIBUTION = "U.S. Census Bureau, ACS 2020–2024 5-year estimates; 2020 TIGER/Line via TIGERweb"
BLUE = ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"]
MISSING = "#bdbdbd"
SCALES = {"block_group": "Block group", "tract": "Tract"}
COUNTIES = ("453", "491", "209")


def cells(table, numbers):
    return tuple(f"{table}_{number:03d}" for number in numbers)


# metric -> (label, format, numerator cells, denominator, four fixed legend breaks)
METRICS = {
    "population": ("Population", "number", ("B01003_001",), None, (500, 1000, 2000, 4000)),
    "median_household_income": ("Median household income", "currency", ("B19013_001",), None,
                                (50000, 75000, 100000, 150000)),
    "median_home_value": ("Median home value", "currency", ("B25077_001",), None,
                         (200000, 350000, 500000, 750000)),
    "median_gross_rent": ("Median gross rent", "currency", ("B25064_001",), None, (1000, 1500, 2000, 2500)),
    "median_year_built": ("Median year built", "number", ("B25035_001",), None, (1960, 1980, 2000, 2010)),
    "median_age": ("Median age", "number", ("B01002_001",), None, (25, 35, 45, 55)),
    "owner_occupied_share": ("Owner-occupied share", "percent", ("B25003_002",), "B25003_001", (.2, .4, .6, .8)),
    "under_18_share": ("Under 18 share", "percent", cells("B01001", (*range(3, 7), *range(27, 31))),
                       "B01001_001", (.2, .4, .6, .8)),
    "age_18_34_share": ("Age 18–34 share", "percent", cells("B01001", (*range(7, 13), *range(31, 37))),
                        "B01001_001", (.2, .4, .6, .8)),
    "age_65_plus_share": ("Age 65+ share", "percent", cells("B01001", (*range(20, 26), *range(44, 50))),
                          "B01001_001", (.2, .4, .6, .8)),
    "family_children_share": ("Family households with children share", "percent",
                              cells("B11003", (3, 10, 16)), "B11003_001", (.2, .4, .6, .8)),
    "one_person_share": ("One-person household share", "percent", ("B11001_008",), "B11001_001", (.2, .4, .6, .8)),
    "bachelors_plus_share": ("Bachelor's degree or higher share (age 25+)", "percent",
                             cells("B15003", range(22, 26)), "B15003_001", (.2, .4, .6, .8)),
    "hispanic_latino_share": ("Hispanic or Latino share", "percent", ("B03002_012",), "B03002_001", (.2, .4, .6, .8)),
}
for metric, label, cell in (
    ("nh_white_share", "Non-Hispanic White share", 3),
    ("nh_black_share", "Non-Hispanic Black share", 4),
    ("nh_aian_share", "Non-Hispanic American Indian / Alaska Native share", 5),
    ("nh_asian_share", "Non-Hispanic Asian share", 6),
    ("nh_nhpi_share", "Non-Hispanic Native Hawaiian / Pacific Islander share", 7),
    ("nh_some_other_share", "Non-Hispanic some other race share", 8),
    ("nh_two_or_more_share", "Non-Hispanic two or more races share", 9),
):
    METRICS[metric] = (label, "percent", (f"B03002_{cell:03d}",), "B03002_001", (.2, .4, .6, .8))

BASES = sorted({base for _, _, numerator, denominator, _ in METRICS.values()
                for base in (*numerator, *((denominator,) if denominator else ()))})
NON_AGE_BASES = [base for base in BASES if not base.startswith("B01001_")]
# 12 complete quartets = 48 variables; the final list has four quartets.
PARTS = {"age": list(cells("B01001", range(1, 50)))}
PARTS.update({f"values_{i // 12}": NON_AGE_BASES[i:i + 12] for i in range(0, len(NON_AGE_BASES), 12)})


def variables(bases):
    return [base + suffix for base in bases for suffix in ("E", "M", "EA", "MA")]
