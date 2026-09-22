# ------------------------------------------------------------
# Staff Training Tracker (Practice Index export)
# Run locally with:  streamlit run app.py
# ------------------------------------------------------------

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Staff Training Tracker", page_icon="📋", layout="wide")

# Colours for each status (standard Excel-style red/amber/green)
STATUS_COLOURS = {
    "Completed": "#c6efce",    # green
    "Due soon": "#ffeb9c",     # amber
    "Overdue": "#ffc7ce",      # red
    "Not due yet": "#e7e6e6",  # grey
}

# The columns we need from the Practice Index export
REQUIRED_COLUMNS = ["First name", "Last name", "Learner Email", "Course", "Due", "Completed Date"]
DATE_COLUMNS = ["Enrolled", "Start Date", "Due", "Completed Date"]


# ------------------------------------------------------------
# 1. Helper functions
# ------------------------------------------------------------

def load_file(uploaded_file):
    """Read the uploaded CSV or Excel file and line the columns up correctly.

    Practice Index exports can have an extra ID number at the start of each
    data row that the header row doesn't have. That pushes every column one
    place out of line. So instead of trusting pandas to match headers to
    data, we read everything as plain rows and line them up ourselves using
    the email column as an anchor.
    """

    # Read every row as raw data (no header). names=range(60) lets rows
    # have different lengths without pandas throwing an error.
    if uploaded_file.name.lower().endswith(".csv"):
        raw = pd.read_csv(uploaded_file, header=None, names=range(60), dtype=str, engine="python")
    else:
        raw = pd.read_excel(uploaded_file, header=None, dtype=str)

    # Find the header row: the first row that contains "Learner Email"
    is_header = raw.apply(lambda r: r.astype(str).str.strip().eq("Learner Email").any(), axis=1)
    header_row = is_header.idxmax()

    # The column names, in order, ignoring any blank header cells
    names = [str(v).strip() for v in raw.loc[header_row] if pd.notna(v) and str(v).strip() != ""]

    # Everything below the header is data
    data = raw.loc[header_row + 1:]

    # Find which raw column actually holds the email addresses (contains "@")
    email_col = next(c for c in data.columns if data[c].astype(str).str.contains("@").any())

    # Work out where the data really starts, so the header lines up with it.
    # e.g. if the emails are in raw column 3 but "Learner Email" is the 3rd
    # name (position 2), the data starts one column in (the extra ID column).
    start = list(data.columns).index(email_col) - names.index("Learner Email")
    data = data.iloc[:, start:start + len(names)]
    data.columns = names

    # Drop completely empty rows and give rows clean numbers (0, 1, 2...)
    return data.dropna(how="all").reset_index(drop=True)


def is_yes(value):
    """True if a cell says Yes/Completed (ignores case and spaces)."""
    return str(value).strip().lower() in ["yes", "completed"]


def get_status(row, today, due_soon_days):
    """Work out the status of one course for one person."""

    # A course counts as done if ANY of these say so
    completed = (
        pd.notna(row.get("Completed Date"))
        or is_yes(row.get("Outcome"))
        or is_yes(row.get("Completed Elsewhere"))
        or is_yes(row.get("Marked as completed"))
    )
    if completed:
        return "Completed"

    due = row.get("Due")
    if pd.isna(due):
        return "Not due yet"          # no due date set
    if due < today:
        return "Overdue"              # due date has passed
    if due <= today + pd.Timedelta(days=due_soon_days):
        return "Due soon"             # due within the next X days
    return "Not due yet"


def colour_cell(value):
    """Background colour for a cell in the grid, based on its status."""
    colour = STATUS_COLOURS.get(value)
    if colour:
        return f"background-color: {colour}; color: black"
    return ""  # blank cell = person isn't enrolled on that course


def colour_percent(value):
    """Colour the % complete column: red under 50%, amber 50-89%, green 90%+."""
    if value >= 90:
        colour = STATUS_COLOURS["Completed"]
    elif value >= 50:
        colour = STATUS_COLOURS["Due soon"]
    else:
        colour = STATUS_COLOURS["Overdue"]
    return f"background-color: {colour}; color: black"


def format_dates(df):
    """Show dates as dd/mm/yyyy in tables (blank if missing)."""
    df = df.copy()
    for col in DATE_COLUMNS:
        if col in df.columns:
            df[col] = df[col].dt.strftime("%d/%m/%Y").fillna("")
    return df.reset_index(drop=True)  # unique row numbers so colouring works


# ------------------------------------------------------------
# 2. Page header and file upload
# ------------------------------------------------------------

st.title("📋 Staff Training Tracker")
st.write("Upload the course export from Practice Index to see who has completed, is due, or is overdue.")

uploaded_file = st.file_uploader("Upload the Practice Index export", type=["csv", "xlsx", "xls"])

if uploaded_file is None:
    st.info("Upload a file to get started. The file is only used while this page is open and isn't saved.")
    st.stop()

df = load_file(uploaded_file)

# Check the file has the columns we need
missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
if missing:
    st.error(f"This file is missing these columns: {', '.join(missing)}. Check it's the course export from Practice Index.")
    st.stop()


# ------------------------------------------------------------
# 3. Clean the data
# ------------------------------------------------------------

# Convert date text (UK format, some with times) into real dates
for col in DATE_COLUMNS:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], dayfirst=True, format="mixed", errors="coerce")

# One "Person" column made from first name + surname
df["Person"] = df["First name"].str.strip() + " " + df["Last name"].str.strip()

# If someone has the same course more than once (e.g. old versions),
# keep only their most recent enrolment
if "Enrolled" in df.columns:
    df = df.sort_values("Enrolled")
df = df.drop_duplicates(subset=["Person", "Course"], keep="last")


# ------------------------------------------------------------
# 4. Sidebar filters
# ------------------------------------------------------------

# Mandatory filter sits at the top of the main page (not the sidebar)
if "Mandatory" in df.columns:
    mandatory_only = st.checkbox("Show mandatory courses only")
    if mandatory_only:
        df = df[df["Mandatory"].apply(is_yes)]

st.sidebar.header("Filters")

due_soon_days = st.sidebar.slider("Count as 'due soon' if due within (days)", 7, 90, 30)

all_courses = sorted(df["Course"].dropna().unique())
chosen_courses = st.sidebar.multiselect("Courses", all_courses, default=all_courses)

# Apply the course filter
df = df[df["Course"].isin(chosen_courses)]

if df.empty:
    st.warning("No courses match these filters. Try selecting more courses in the sidebar.")
    st.stop()

# Work out each row's status
today = pd.Timestamp.today().normalize()
df["Status"] = df.apply(get_status, axis=1, today=today, due_soon_days=due_soon_days)


# ------------------------------------------------------------
# 5. Headline numbers
# ------------------------------------------------------------

total = len(df)
completed = (df["Status"] == "Completed").sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Staff", df["Person"].nunique())
col2.metric("Courses completed", f"{completed / total:.0%}")
col3.metric("Overdue", (df["Status"] == "Overdue").sum())
col4.metric(f"Due in next {due_soon_days} days", (df["Status"] == "Due soon").sum())


# ------------------------------------------------------------
# 6. Person x course grid (click a row to see that person's details)
# ------------------------------------------------------------

st.subheader("Everyone at a glance")
st.caption(
    "🟩 Completed   🟨 Due soon   🟥 Overdue   ⬜ Not due yet   Blank = not enrolled.  "
    "Lowest completion is at the top. Click a row to see that person's details."
)

# Turn the list into a grid: one row per person, one column per course
grid = df.pivot(index="Person", columns="Course", values="Status").fillna("")
course_columns = list(grid.columns)  # remember which columns are courses

# For each person: how many courses completed, out of how many enrolled on
done_count = (df["Status"] == "Completed").groupby(df["Person"]).sum()
total_count = df.groupby("Person").size()
completed_pct = (done_count / total_count * 100).round(0).astype(int)

# "Completed" column shown as text, e.g. "4/6"
completed_label = done_count.astype(str) + "/" + total_count.astype(str)

# Add both as the first two columns. "% complete" stays a real number,
# so clicking its header sorts it properly (5, 33, 100 - not "100", "33", "5")
grid.insert(0, "% complete", completed_pct)
grid.insert(1, "Completed", completed_label)

# Order rows so the lowest % is at the top
grid = grid.sort_values("% complete")

styled_grid = (
    grid.style
    .map(colour_cell, subset=course_columns)          # RAG colours on the course cells
    .map(colour_percent, subset=["% complete"])       # RAG colours on the % column
    .format({"% complete": "{}%"})                    # show 67 as 67%
)

# on_select lets us know which row was clicked
event = st.dataframe(
    styled_grid,
    on_select="rerun",
    selection_mode="single-row",
    height=min(600, 38 + 35 * len(grid)),
)


# ------------------------------------------------------------
# 7. Details for the selected person
# ------------------------------------------------------------

selected_rows = event.selection.rows

if selected_rows:
    person = grid.index[selected_rows[0]]
    person_df = df[df["Person"] == person]

    st.subheader(f"👤 {person}")
    st.write(person_df["Learner Email"].iloc[0])

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Completed", (person_df["Status"] == "Completed").sum())
    p2.metric("Overdue", (person_df["Status"] == "Overdue").sum())
    p3.metric("Due soon", (person_df["Status"] == "Due soon").sum())
    p4.metric("Not due yet", (person_df["Status"] == "Not due yet").sum())

    # Their courses, most urgent first
    order = {"Overdue": 0, "Due soon": 1, "Not due yet": 2, "Completed": 3}
    person_df = person_df.sort_values("Status", key=lambda s: s.map(order))

    detail_cols = [c for c in ["Course", "Status", "Due", "Completed Date", "Mandatory"] if c in person_df.columns]
    detail = format_dates(person_df[detail_cols])

    st.dataframe(
        detail.style.map(colour_cell, subset=["Status"]),
        hide_index=True,
    )
else:
    st.info("Click a row in the grid above to see that person's details.")


# ------------------------------------------------------------
# 8. Chase list: overdue and due soon, ready to download
# ------------------------------------------------------------

st.subheader("Chase list")

chase = df[df["Status"].isin(["Overdue", "Due soon"])]

# Optional staff filter for the chase list only (leave empty = everyone)
chase_people = sorted(chase["Person"].unique())
chosen_people = st.multiselect(
    "Filter by staff (leave empty to show everyone)",
    chase_people,
    placeholder="All staff",
)
if chosen_people:
    chase = chase[chase["Person"].isin(chosen_people)]

chase = chase.sort_values(["Status", "Due"], ascending=[False, True])  # Overdue first
chase = format_dates(chase[["Person", "Learner Email", "Course", "Status", "Due"]])

if chase.empty:
    st.success("Nobody here is overdue or due soon. 🎉")
else:
    st.dataframe(chase.style.map(colour_cell, subset=["Status"]), hide_index=True)
    st.download_button(
        "Download chase list (CSV)",
        data=chase.to_csv(index=False),
        file_name=f"training_chase_list_{today:%Y-%m-%d}.csv",
        mime="text/csv",
    )