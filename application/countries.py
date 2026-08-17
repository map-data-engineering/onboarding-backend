"""
Country lists for the two dropdowns on the details step.

Free-text country fields were the single largest source of dirty data in the
export: "Tanzania", "tanzania" and "United Republic of Tanzania" arrived as three
distinct values, and the panel's Tanzania-based diversity floor matches on an
exact string, so a third of the applicants it should have counted were invisible
to it.

The list is the 195 UN member states (193 members plus the two permanent
observers, Palestine and the Holy See, which people do apply from). Tanzania and
its neighbours are pinned in a group at the top: most applicants come from that
group, and a nine-entry shortlist saves them scrolling past 190 options on a
phone.
"""

TANZANIA = "Tanzania"

# Pinned at the top of both dropdowns, in the order shown.
REGIONAL = [
    TANZANIA,
    "Kenya",
    "Uganda",
    "Rwanda",
    "Burundi",
    "Democratic Republic of the Congo",
    "Zambia",
    "Malawi",
    "Mozambique",
]

# The remaining states, alphabetically. Tanzania's neighbours are omitted here
# because they appear in REGIONAL -- a name in both groups would let the same
# country be submitted under two identical-looking options.
OTHERS = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola",
    "Antigua and Barbuda", "Argentina", "Armenia", "Australia", "Austria",
    "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus",
    "Belgium", "Belize", "Benin", "Bhutan", "Bolivia",
    "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
    "Burkina Faso", "Cabo Verde", "Cambodia", "Cameroon", "Canada",
    "Central African Republic", "Chad", "Chile", "China", "Colombia",
    "Comoros", "Congo", "Costa Rica", "Côte d'Ivoire", "Croatia", "Cuba",
    "Cyprus", "Czechia", "Denmark", "Djibouti", "Dominica",
    "Dominican Republic", "Ecuador", "Egypt", "El Salvador",
    "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia",
    "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany",
    "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau",
    "Guyana", "Haiti", "Holy See", "Honduras", "Hungary", "Iceland", "India",
    "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica",
    "Japan", "Jordan", "Kazakhstan", "Kiribati", "Kuwait", "Kyrgyzstan",
    "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya",
    "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malaysia",
    "Maldives", "Mali", "Malta", "Marshall Islands", "Mauritania",
    "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia",
    "Montenegro", "Morocco", "Myanmar", "Namibia", "Nauru", "Nepal",
    "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria",
    "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau",
    "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru",
    "Philippines", "Poland", "Portugal", "Qatar", "Romania", "Russia",
    "Saint Kitts and Nevis", "Saint Lucia",
    "Saint Vincent and the Grenadines", "Samoa", "San Marino",
    "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia",
    "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia",
    "Solomon Islands", "Somalia", "South Africa", "South Korea",
    "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden",
    "Switzerland", "Syria", "Tajikistan", "Thailand", "Timor-Leste", "Togo",
    "Tonga", "Trinidad and Tobago", "Tunisia", "Türkiye", "Turkmenistan",
    "Tuvalu", "Ukraine", "United Arab Emirates", "United Kingdom",
    "United States of America", "Uruguay", "Uzbekistan", "Vanuatu",
    "Venezuela", "Vietnam", "Yemen", "Zimbabwe",
]

# What the client renders: [{"label": ..., "countries": [...]}, ...]. Sent to the
# browser by /api/config/ so the two dropdowns and this module can never drift.
COUNTRY_GROUPS = [
    {"label": "Tanzania and neighbours", "countries": REGIONAL},
    {"label": "All countries", "countries": OTHERS},
]

ALL_COUNTRIES = REGIONAL + OTHERS

# Historic records may hold a free-text spelling from before the dropdowns
# existed, so the panel's Tanzania test stays a substring match (see
# shortlist.is_tanzania_based) rather than `== TANZANIA`.
assert len(set(ALL_COUNTRIES)) == len(ALL_COUNTRIES), "duplicate country name"
