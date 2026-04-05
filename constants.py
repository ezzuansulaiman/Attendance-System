"""constants.py — Shared configuration for the attendance system."""

REGIONS = {
    "sepang": "Sepang",
    "sabak": "Sabak Bernam",
}

STATUS_CODES = {"P", "OD", "RD", "PH", "AL", "MC", "EML"}

STATUS_LABELS = {
    "P":   "Hadir",
    "OD":  "Hari Rehat",
    "RD":  "Hari Berehat",
    "PH":  "Cuti Umum",
    "AL":  "Cuti Tahunan",
    "MC":  "Cuti Sakit",
    "EML": "Cuti Kecemasan",
}

# Hex fill colours for Excel cells and HTML badges
STATUS_COLORS = {
    "P":   "#d1fae5",  # green
    "OD":  "#e5e7eb",  # grey
    "RD":  "#dbeafe",  # blue
    "PH":  "#fef9c3",  # yellow
    "AL":  "#fed7aa",  # orange
    "MC":  "#fecaca",  # red-pink
    "EML": "#e9d5ff",  # purple
}

# Contrasting text colours for each status badge
STATUS_TEXT_COLORS = {
    "P":   "#065f46",
    "OD":  "#374151",
    "RD":  "#1e40af",
    "PH":  "#854d0e",
    "AL":  "#9a3412",
    "MC":  "#991b1b",
    "EML": "#6b21a8",
}

LEAVE_TYPES = ["AL", "MC", "EML"]

# Default entitlement days per leave type per year
LEAVE_DEFAULTS = {
    "AL":  8,
    "MC":  14,
    "EML": 3,
}

DESIGNATIONS = [
    "Supervisor",
    "Cleaner",
    "Tukang Kebun",
    "Pest Control Technician",
    "Pengawal Keselamatan",
    "Pemandu",
    "Pembantu Am",
    "Juruteknik",
]

# Malay day-of-week abbreviations (Monday=0)
DAY_ABBR_MS = ["Isn", "Sel", "Rab", "Kha", "Jum", "Sab", "Ahd"]
