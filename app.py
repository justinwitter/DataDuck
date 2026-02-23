import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, date
import gspread
from google.oauth2.service_account import Credentials
from collections import Counter
import json
import seaborn as sns
import time

# Load team/player config
with open("config.json") as _f:
    _config = json.load(_f)
TEAM_NAMES = list(_config["teams"].keys())
DEFAULT_TEAM = _config.get("default_team", TEAM_NAMES[0])
TEAM_PLAYERS = {team: data["players"] for team, data in _config["teams"].items()}

# Set page config
st.set_page_config(
    page_title="DataDuck",
    page_icon="🦆",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Set matplotlib style
plt.style.use('seaborn-v0_8')
sns.set_palette("viridis")

# Google Sheets configuration
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Initialize team selection in session state
if 'selected_team' not in st.session_state:
    st.session_state.selected_team = DEFAULT_TEAM

# Initialize API call tracking for rate limiting
if 'api_call_times' not in st.session_state:
    st.session_state.api_call_times = []

# Rate limiting configuration - Conservative limits to avoid hitting Google API limits
MAX_API_CALLS_PER_MINUTE = 15  # Google Sheets allows 100/minute, but we'll be conservative
MAX_API_CALLS_PER_HOUR = 200   # Google Sheets allows 1000/hour, but we'll be conservative

def check_api_rate_limit():
    """Check if we're within safe API rate limits - returns status but doesn't block"""
    current_time = time.time()
    
    # Remove calls older than 1 minute and 1 hour
    st.session_state.api_call_times = [
        call_time for call_time in st.session_state.api_call_times 
        if current_time - call_time < 3600  # Keep last hour of calls
    ]
    
    # Count recent calls
    calls_last_minute = len([
        call_time for call_time in st.session_state.api_call_times 
        if current_time - call_time < 60
    ])
    
    calls_last_hour = len(st.session_state.api_call_times)
    
    # Check if we're approaching limits
    minute_warning = calls_last_minute >= MAX_API_CALLS_PER_MINUTE * 0.8  # 80% of limit
    hour_warning = calls_last_hour >= MAX_API_CALLS_PER_HOUR * 0.8       # 80% of limit
    
    minute_exceeded = calls_last_minute >= MAX_API_CALLS_PER_MINUTE
    hour_exceeded = calls_last_hour >= MAX_API_CALLS_PER_HOUR
    
    return {
        'calls_last_minute': calls_last_minute,
        'calls_last_hour': calls_last_hour,
        'minute_warning': minute_warning,
        'hour_warning': hour_warning,
        'minute_exceeded': minute_exceeded,
        'hour_exceeded': hour_exceeded,
        'can_make_call': not (minute_exceeded or hour_exceeded)
    }

def record_api_call():
    """Record that an API call was made"""
    st.session_state.api_call_times.append(time.time())

def clear_cache_for_team(team_name):
    """Clear cached data for specific team"""
    cache_key = f"cached_data_{team_name}"
    cache_time_key = f"cache_time_{team_name}"
    
    # Clear session state cache
    if cache_key in st.session_state:
        del st.session_state[cache_key]
    if cache_time_key in st.session_state:
        del st.session_state[cache_time_key]

@st.cache_resource
def init_google_sheets():
    """Initialize Google Sheets connection"""
    try:
        # Get credentials from Streamlit secrets
        creds_dict = st.secrets["google_sheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        # Open the spreadsheet (you'll need to create this and share it with your service account)
        sheet_url = st.secrets["sheet_url"]  # Store your Google Sheet URL in secrets
        spreadsheet = client.open_by_url(sheet_url)
        
        return spreadsheet, client
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {str(e)}")
        st.error("Please check your Google Sheets credentials in Streamlit secrets.")
        return None, None

def get_or_create_worksheet(team_name):
    """Get or create worksheet for the selected team"""
    spreadsheet, client = init_google_sheets()
    if spreadsheet is None:
        return None
    
    try:
        # Try to get the worksheet by team name
        try:
            worksheet = spreadsheet.worksheet(team_name)
        except gspread.WorksheetNotFound:
            # Create the worksheet if it doesn't exist
            worksheet = spreadsheet.add_worksheet(title=team_name, rows="100", cols="20")
        
        # Initialize headers if sheet is empty
        try:
            headers = worksheet.row_values(1)
            if not headers or headers != ['winner', 'date']:
                worksheet.clear()
                worksheet.append_row(['winner', 'date'])
        except Exception:
            worksheet.append_row(['winner', 'date'])
        
        return worksheet
    except Exception as e:
        st.error(f"Failed to access worksheet for {team_name}: {str(e)}")
        return None

def load_data(team_name, force_refresh=False):
    """Load winner data from Google Sheets for selected team with smart caching and rate limiting"""
    
    # Create cache key
    cache_key = f"cached_data_{team_name}"
    cache_time_key = f"cache_time_{team_name}"
    
    # Check if we have cached data and not forcing refresh
    if not force_refresh and cache_key in st.session_state and cache_time_key in st.session_state:
        cache_age = time.time() - st.session_state[cache_time_key]
        if cache_age < 60:  # Use cache if less than 60 seconds old
            return st.session_state[cache_key]
    
    # Check API rate limits
    rate_status = check_api_rate_limit()
    
    # If we've exceeded limits, use cached data if available
    if not rate_status['can_make_call']:
        if cache_key in st.session_state:
            if rate_status['minute_exceeded']:
                st.warning("⚠️ API rate limit reached (too many requests per minute). Using cached data.")
            elif rate_status['hour_exceeded']:
                st.warning("⚠️ API rate limit reached (too many requests per hour). Using cached data.")
            return st.session_state[cache_key]
        else:
            st.error("❌ API rate limit reached and no cached data available. Please wait before trying again.")
            return []
    
    # Show warning if approaching limits
    if rate_status['minute_warning'] or rate_status['hour_warning']:
        st.warning(f"⚠️ Approaching API limits: {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} per minute, {rate_status['calls_last_hour']}/{MAX_API_CALLS_PER_HOUR} per hour")
    
    worksheet = get_or_create_worksheet(team_name)
    if worksheet is None:
        return []
    
    try:
        # Record the API call
        record_api_call()
        
        # Get all records (skip header row)
        records = worksheet.get_all_records()
        
        # Cache the data in session state with timestamp
        st.session_state[cache_key] = records
        st.session_state[cache_time_key] = time.time()
        
        return records
    except Exception as e:
        # If API call fails but we have cached data, use it
        if cache_key in st.session_state:
            st.warning(f"API call failed, using cached data: {str(e)}")
            return st.session_state[cache_key]
        else:
            st.error(f"Error loading data from Google Sheets for {team_name}: {str(e)}")
            return []

def delete_winner_from_sheets(winner_name, race_date_str):
    """Delete a specific winner entry from Google Sheets by matching winner + date"""
    worksheet = get_or_create_worksheet(st.session_state.selected_team)
    if worksheet is None:
        return False

    try:
        record_api_call()
        all_values = worksheet.get_all_values()  # includes header row

        for i, row in enumerate(all_values):
            if i == 0:
                continue  # skip header
            if row[0] == winner_name and row[1] == race_date_str:
                worksheet.delete_rows(i + 1)  # gspread rows are 1-indexed
                clear_cache_for_team(st.session_state.selected_team)
                return True

        st.error("Entry not found in sheet.")
        return False
    except Exception as e:
        st.error(f"Error deleting from Google Sheets: {str(e)}")
        return False


def save_winner_to_sheets(winner_name, race_date):
    """Add a new winner directly to Google Sheets for selected team"""
    # Check API rate limits but allow the save (this is important functionality)
    rate_status = check_api_rate_limit()
    
    if not rate_status['can_make_call']:
        if rate_status['minute_exceeded']:
            st.error("❌ Cannot save winner: Too many API requests per minute. Please wait a moment and try again.")
            return False
        elif rate_status['hour_exceeded']:
            st.error("❌ Cannot save winner: Too many API requests per hour. Please try again later.")
            return False
    
    worksheet = get_or_create_worksheet(st.session_state.selected_team)
    if worksheet is None:
        return False
    
    try:
        # Record the API call
        record_api_call()
        
        new_row = [
            winner_name,
            race_date.isoformat()
        ]
        worksheet.append_row(new_row)
        
        # Clear cached data to force refresh on next load
        clear_cache_for_team(st.session_state.selected_team)
        
        return True
    except Exception as e:
        st.error(f"Error saving to Google Sheets for {st.session_state.selected_team}: {str(e)}")
        return False

def calculate_statistics(start_date=None, end_date=None):
    """Calculate comprehensive statistics from the winner data
    
    Args:
        start_date: Optional start date filter (inclusive)
        end_date: Optional end date filter (inclusive)
    """
    data = load_data(st.session_state.selected_team)
    
    if not data:
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame(data)
    
    # Clean the data
    df['winner'] = df['winner'].astype(str).str.strip()
    df['date'] = pd.to_datetime(df['date'])
    
    # Remove empty or invalid rows
    df = df[
        df['winner'].notna() & 
        (df['winner'] != '') & 
        (df['winner'] != 'nan') &
        (df['winner'] != 'None')
    ]
    
    if len(df) == 0:
        return None
    
    # Apply date filters
    if start_date is not None:
        df = df[df['date'] >= pd.to_datetime(start_date)]
    
    if end_date is not None:
        df = df[df['date'] <= pd.to_datetime(end_date)]
    
    if len(df) == 0:
        return None
    
    # Sort by date
    df = df.sort_values('date')
    
    # Calculate basic stats
    total_races = len(df)
    unique_winners = df['winner'].nunique()
    
    # Win counts
    win_counts = df['winner'].value_counts()
    
    # Current champion (most recent winner)
    most_recent_race = df.loc[df['date'].idxmax()]
    current_champion = most_recent_race['winner']
    
    # Get current champion's total wins
    champion_total_wins = win_counts.get(current_champion, 0)
    
    # Recent winners (last 10)
    df_desc = df.sort_values('date', ascending=False)
    recent_winners = df_desc.head(10)[['winner', 'date']].copy()
    
    # Calculate cumulative wins over time for each player
    cumulative_data = []
    win_tracking = {}  # Track cumulative wins for each player
    
    for idx, row in df.iterrows():
        winner = row['winner']
        date = row['date']
        
        # Increment win count for this player
        if winner not in win_tracking:
            win_tracking[winner] = 0
        win_tracking[winner] += 1
        
        # Add to cumulative data
        cumulative_data.append({
            'date': date,
            'winner': winner,
            'cumulative_wins': win_tracking[winner]
        })
    
    cumulative_df = pd.DataFrame(cumulative_data)
    
    return {
        'total_races': total_races,
        'unique_winners': unique_winners,
        'win_counts': win_counts,
        'current_champion': current_champion,
        'champion_total_wins': champion_total_wins,
        'recent_winners': recent_winners,
        'cumulative_df': cumulative_df,
        'all_data': df
    }

# Check for pending refresh (auto-refresh logic) - REMOVED this section as it was causing issues

# Show setup instructions if Google Sheets is not configured
if 'google_sheets' not in st.secrets or 'sheet_url' not in st.secrets:
    st.error("🔧 Google Sheets Setup Required")
    st.markdown("""
    To use this app with Google Sheets, you need to:
    
    1. Create a Google Sheet for storing duck race data
    2. Set up a Google Service Account with Sheets API access
    3. Configure Streamlit Secrets with your credentials
    
    ### Step-by-step setup:
    
    #### 1. Create Google Service Account:
    - Go to [Google Cloud Console](https://console.cloud.google.com/)
    - Create a new project or select existing one
    - Enable Google Sheets API and Google Drive API
    - Create a Service Account and download the JSON key file
    
    #### 2. Create Google Sheet:
    - Create a new Google Sheet
    - Share it with your service account email (found in the JSON file)
    - Give it edit permissions
    - Copy the sheet URL
    
    #### 3. Configure Streamlit Secrets:
    Add to your `.streamlit/secrets.toml` file:
    ```toml
    sheet_url = "your_google_sheet_url_here"
    
    [google_sheets]
    type = "service_account"
    project_id = "your_project_id"
    private_key_id = "your_private_key_id"
    private_key = "-----BEGIN PRIVATE KEY-----\\nYOUR_PRIVATE_KEY\\n-----END PRIVATE KEY-----\\n"
    client_email = "your_service_account_email"
    client_id = "your_client_id"
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url = "your_cert_url"
    ```
    """)
    st.stop()

# Main app
st.title("🦆 DataDuck 🦆")
st.caption("Duck Race Tracker")

# Team Selection and connection status inline
col1, col2 = st.columns([3, 1])
with col1:
    # Test connection
    worksheet = get_or_create_worksheet(st.session_state.selected_team)
    if worksheet:
        st.success(f"✅ Connected to {st.session_state.selected_team} team database successfully!")
    else:
        st.error("❌ Failed to connect to Google Sheets. Check your configuration.")
        st.stop()

with col2:
    team_option = st.selectbox(
        "Team:",
        TEAM_NAMES,
        index=TEAM_NAMES.index(st.session_state.selected_team),
        key="team_selector"
    )
    if team_option != st.session_state.selected_team:
        st.session_state.selected_team = team_option
        clear_cache_for_team(team_option)  # Clear cache for new team
        st.rerun()

# Create tabs
tab1, tab2, tab3 = st.tabs(["🏁 Duck Race", "📝 Add Winner", "🏆 Wall of Champions"])

with tab1:
    st.header("🏁 Duck Race Game")
    
    # Center the content with some nice spacing
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Create centered columns for the game section
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
        <div style="text-align: center; padding: 2rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; color: white; margin: 1rem 0;">
            <h2 style="color: white; margin-bottom: 1rem;">🦆 Ready to Race? 🏁</h2>
            <p style="font-size: 1.1rem; margin-bottom: 1.5rem;">Click the button below to start the duck race in a new tab!</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Big prominent button to open the game
        st.link_button("🦆 **PLAY DUCK RACE**", "https://www.online-stopwatch.com/duck-race/", use_container_width=True, help="Opens the duck race game in a new tab")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Initialize player names in session state with team-specific keys
    team_key = f'player_names_{st.session_state.selected_team.replace(" ", "_")}'
    reset_key = f'reset_counter_{st.session_state.selected_team.replace(" ", "_")}'
    prev_text_key = f'prev_text_{st.session_state.selected_team.replace(" ", "_")}'
    
    # Set default players based on team (edit config.json to change these)
    default_players = TEAM_PLAYERS.get(st.session_state.selected_team, [])
    
    if team_key not in st.session_state:
        st.session_state[team_key] = default_players
    
    # Initialize reset counter for forcing text area refresh
    if reset_key not in st.session_state:
        st.session_state[reset_key] = 0
    
    # Initialize previous text state to detect changes
    if prev_text_key not in st.session_state:
        st.session_state[prev_text_key] = "\n".join(st.session_state[team_key])
    
    col1, col2 = st.columns([2, 1])
    
    with col2:
        st.subheader("🎮 Quick Actions:")
        
        # Reset to default button
        if st.button("🔄 Reset to Default", help=f"Reset to the original players for {st.session_state.selected_team}"):
            st.session_state[team_key] = default_players
            st.session_state[prev_text_key] = "\n".join(st.session_state[team_key])
            st.session_state[reset_key] += 1  # Increment to force text area refresh
            st.rerun()
        
        # Add new player
        new_player = st.text_input("Add New Player:", placeholder="Enter name")
        if st.button("➕ Add Player") and new_player.strip():
            if new_player.strip() not in st.session_state[team_key]:
                st.session_state[team_key].append(new_player.strip())
                st.session_state[prev_text_key] = "\n".join(st.session_state[team_key])
                st.rerun()
            else:
                st.warning("Player already in list!")
        
        # Show count (this will now update properly)
        st.metric("Total Players", len(st.session_state[team_key]))
    
    with col1:
        st.subheader("📝 Edit Player List:")
        
        # Text area for editing names with dynamic key to force refresh on reset
        names_text = st.text_area(
            "Player Names (one per line):",
            value="\n".join(st.session_state[team_key]),
            height=300,
            help="Add or remove names. Each name should be on a separate line.",
            key=f"player_names_text_{st.session_state.selected_team.replace(' ', '_')}_{st.session_state[reset_key]}"
        )
        
        # Check if text has changed and update session state
        if names_text != st.session_state[prev_text_key]:
            new_names = [name.strip() for name in names_text.split('\n') if name.strip()]
            st.session_state[team_key] = new_names
            st.session_state[prev_text_key] = names_text
            st.rerun()  # Force rerun to update the metric

with tab2:
    st.header("📝 Add New Winner")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Create dropdown with player names from session state
        current_team_players = st.session_state.get(team_key, [])
        if current_team_players:
            winner_name = st.selectbox(
                "Select Winner",
                options=current_team_players,
                help=f"Choose the winner from your team player list"
            )
        else:
            st.warning("No players in the list! Please add players in the Duck Race tab first.")
            winner_name = None
        
        race_date = st.date_input("Race Date", value=date.today())
    
    with col2:
        # Show current player count for context
        st.info(f"📊 {len(current_team_players)} players available to select from.\n\nAdd or edit players in the Duck Race tab if needed.")
    
    if 'adding_winner' not in st.session_state:
        st.session_state.adding_winner = False

    if st.button("🏆 Add Winner", type="primary", disabled=st.session_state.adding_winner):
        if winner_name:
            st.session_state.adding_winner = True
            with st.spinner("Saving to team sheet..."):
                success = save_winner_to_sheets(winner_name, race_date)
            st.session_state.adding_winner = False
            if success:
                st.success(f"🎉 {winner_name} added as champion for {race_date}!")
                st.balloons()
                st.info("📊 Click the 'Wall of Champions' tab and use the refresh button to see updated statistics!")
            else:
                st.error("Failed to add winner. Please check your Google Sheets connection.")
        else:
            st.error("Please select a winner from the dropdown.")
    
    # Show ALL entries instead of just recent ones
    st.subheader("📊 All Race Results")
    
    # Add refresh button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("🔄 Refresh Data"):
            # Force fresh data load
            data_fresh = load_data(st.session_state.selected_team, force_refresh=True)
            st.rerun()
    
    with col2:
        # Show API usage status
        rate_status = check_api_rate_limit()
        if rate_status['minute_warning'] or rate_status['hour_warning']:
            st.warning(f"⚠️ API Usage: {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} per min")
        else:
            st.info(f"✅ API Usage: {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} per min")
    
    with st.spinner("Loading all race results..."):
        data = load_data(st.session_state.selected_team, force_refresh=False)
        if data:
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            
            # Clean the data
            df['winner'] = df['winner'].astype(str).str.strip()
            df = df[
                df['winner'].notna() & 
                (df['winner'] != '') & 
                (df['winner'] != 'nan') &
                (df['winner'] != 'None')
            ]
            
            if len(df) > 0:
                # Sort by date descending to show most recent first
                df_display = df.sort_values('date', ascending=False).copy()
                df_display['date'] = df_display['date'].dt.strftime('%Y-%m-%d')
                df_display = df_display.rename(columns={'winner': 'Champion', 'date': 'Date'})
                df_display.index = range(1, len(df_display) + 1)  # Add row numbers starting from 1
                
                # Display with pagination for better performance
                st.markdown(f"**Total Records: {len(df_display)}**")
                
                # Add search functionality
                search_term = st.text_input("🔍 Search by champion name:", placeholder="Enter name to filter...")
                if search_term:
                    df_filtered = df_display[df_display['Champion'].str.contains(search_term, case=False, na=False)]
                    st.markdown(f"**Filtered Results: {len(df_filtered)}**")
                    st.dataframe(df_filtered, use_container_width=True)
                else:
                    # Show all data with pagination
                    st.dataframe(df_display, use_container_width=True, height=400)
                
                # Additional statistics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Races", len(df))
                with col2:
                    st.metric("Unique Champions", df['winner'].nunique())
                with col3:
                    most_wins = df['winner'].value_counts().iloc[0] if len(df) > 0 else 0
                    st.metric("Most Wins by One Player", most_wins)

                st.divider()
                st.subheader("🗑️ Delete an Entry")

                # Build options from the sorted display (most recent first)
                delete_options = [
                    f"{row['Champion']} — {row['Date']}"
                    for _, row in df_display.iterrows()
                ]
                selected_entry = st.selectbox("Select entry to delete:", delete_options, key="delete_selectbox")

                if 'deleting_winner' not in st.session_state:
                    st.session_state.deleting_winner = False

                if st.button("🗑️ Delete Selected Entry", type="secondary", disabled=st.session_state.deleting_winner):
                    winner_to_delete, date_to_delete = selected_entry.split(" — ")
                    st.session_state.deleting_winner = True
                    with st.spinner("Deleting entry..."):
                        success = delete_winner_from_sheets(winner_to_delete, date_to_delete)
                    st.session_state.deleting_winner = False
                    if success:
                        st.success(f"Deleted: {selected_entry}")
                        st.rerun()
                    else:
                        st.error("Failed to delete entry.")
            else:
                st.info("No valid race data found.")
        else:
            st.info("No winners recorded yet! Add some winners to see the complete race history.")

with tab3:
    st.header("🏆 Champions Wall & Statistics")
    
    # Date filter section
    st.subheader("📅 Date Filter")
    
    # Default start date: January 22, 2026
    default_start_date = date(2026, 1, 22)
    
    col_date1, col_date2, col_date3 = st.columns([2, 2, 1])
    
    with col_date1:
        filter_start_date = st.date_input(
            "Start Date (inclusive)",
            value=default_start_date,
            help="Only show races on or after this date"
        )
    
    with col_date2:
        filter_end_date = st.date_input(
            "End Date (inclusive)",
            value=None,
            help="Only show races on or before this date (leave empty for no end filter)"
        )
    
    with col_date3:
        st.write("")  # Spacer
        st.write("")  # Spacer
        if st.button("🔄 Reset Filter"):
            st.session_state['reset_date_filter'] = True
            st.rerun()
    
    # Check if we need to reset (this will be handled by the rerun with default values)
    if st.session_state.get('reset_date_filter', False):
        st.session_state['reset_date_filter'] = False
        filter_start_date = default_start_date
        filter_end_date = None
    
    # Display active filter info
    if filter_start_date or filter_end_date:
        filter_info = "🔍 **Active Filter:** "
        if filter_start_date:
            filter_info += f"From {filter_start_date.strftime('%Y-%m-%d')}"
        if filter_end_date:
            filter_info += f" to {filter_end_date.strftime('%Y-%m-%d')}"
        st.info(filter_info)
    
    st.divider()
    
    # Add refresh button for statistics
    col_refresh, col_status = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh Stats"):
            # Force refresh by clearing cache and reloading
            clear_cache_for_team(st.session_state.selected_team)
            st.rerun()
    
    with col_status:
        # Show API usage status
        rate_status = check_api_rate_limit()
        if not rate_status['can_make_call']:
            st.error(f"❌ API limit reached: {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} per min, {rate_status['calls_last_hour']}/{MAX_API_CALLS_PER_HOUR} per hour")
        elif rate_status['minute_warning'] or rate_status['hour_warning']:
            st.warning(f"⚠️ API Usage: {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} per min, {rate_status['calls_last_hour']}/{MAX_API_CALLS_PER_HOUR} per hour")
        else:
            st.success(f"✅ API Usage: {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} per min, {rate_status['calls_last_hour']}/{MAX_API_CALLS_PER_HOUR} per hour")
    
    with st.spinner("Loading statistics from team sheet..."):
        # Pass the date filters to calculate_statistics
        stats = calculate_statistics(
            start_date=filter_start_date,
            end_date=filter_end_date
        )
    
    if stats is None:
        st.info("No race data available for the selected date range. Adjust the date filter or add some winners to see amazing stats!")
    else:
        # Top metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Races", stats['total_races'])
        
        with col2:
            st.metric("Unique Champions", stats['unique_winners'])
        
        with col3:
            st.metric("Current Champion", stats['current_champion'])
        
        with col4:
            st.metric("Champion's Total Wins", stats['champion_total_wins'])
        
        st.divider()
        
        # Main charts
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🥇 Top Champions")
            
            # Get top 10 for display
            top_winners = stats['win_counts'].head(10)
            
            if len(top_winners) > 0:
                # Create horizontal bar chart
                fig, ax = plt.subplots(figsize=(10, 6))
                
                # Create the bar chart
                bars = ax.barh(range(len(top_winners)), top_winners.values, color=sns.color_palette("viridis", len(top_winners)))
                
                # Customize the chart
                ax.set_yticks(range(len(top_winners)))
                ax.set_yticklabels(top_winners.index)
                ax.set_xlabel('Number of Wins')
                ax.set_title('Top Champions by Wins', fontsize=14, fontweight='bold')
                
                # Add value labels on bars
                for i, (bar, value) in enumerate(zip(bars, top_winners.values)):
                    ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2, 
                           str(value), va='center', fontweight='bold')
                
                # Invert y-axis to show highest at top
                ax.invert_yaxis()
                ax.grid(axis='x', alpha=0.3)
                
                plt.tight_layout()
                st.pyplot(fig)
                plt.close()
        
        with col2:
            st.subheader("📈 Cumulative Wins Over Time")
            
            if len(stats['cumulative_df']) > 0:
                fig, ax = plt.subplots(figsize=(10, 6))
                
                # Get top players to avoid cluttering
                top_players = stats['win_counts'].head(8).index.tolist()
                
                # Create a line for each top player
                colors = sns.color_palette("tab10", len(top_players))
                
                for i, player in enumerate(top_players):
                    player_data = stats['cumulative_df'][stats['cumulative_df']['winner'] == player]
                    
                    if len(player_data) > 0:
                        # Sort by date to ensure proper line plotting
                        player_data = player_data.sort_values('date')
                        
                        ax.plot(
                            player_data['date'], 
                            player_data['cumulative_wins'], 
                            marker='o', 
                            label=player,
                            linewidth=2,
                            markersize=6,
                            color=colors[i]
                        )
                
                ax.set_xlabel('Date')
                ax.set_ylabel('Cumulative Wins')
                ax.set_title('Cumulative Wins Over Time (Top Players)', fontsize=14, fontweight='bold')
                ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
                ax.grid(True, alpha=0.3)
                
                # Format dates on x-axis
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                plt.xticks(rotation=45)
                
                plt.tight_layout()
                st.pyplot(fig)
                plt.close()
        
        st.divider()
        
        # Additional insights
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏆 Win Distribution")
            
            # Pie chart for win distribution
            if len(stats['win_counts']) > 0:
                # Show top 8 + others for cleaner pie chart
                top_8 = stats['win_counts'].head(8)
                others_count = stats['win_counts'].iloc[8:].sum() if len(stats['win_counts']) > 8 else 0
                
                # Create data for pie chart
                pie_names = top_8.index.tolist()
                pie_values = top_8.values.tolist()
                
                if others_count > 0:
                    pie_names.append('Others')
                    pie_values.append(others_count)
                
                fig, ax = plt.subplots(figsize=(8, 8))
                
                # Create pie chart
                wedges, texts, autotexts = ax.pie(
                    pie_values, 
                    labels=pie_names, 
                    autopct='%1.1f%%',
                    startangle=90,
                    colors=sns.color_palette("Set3", len(pie_values))
                )
                
                # Enhance text appearance
                for autotext in autotexts:
                    autotext.set_color('white')
                    autotext.set_fontweight('bold')
                
                ax.set_title('Champion Win Distribution', fontsize=14, fontweight='bold')
                
                plt.tight_layout()
                st.pyplot(fig)
                plt.close()
        
        with col2:
            st.subheader("🕐 Recent Champions")
            
            # Recent winners table
            recent_display = stats['recent_winners'].copy()
            recent_display['date'] = recent_display['date'].dt.strftime('%Y-%m-%d')
            recent_display = recent_display.rename(columns={'winner': 'Champion', 'date': 'Date'})
            
            st.dataframe(
                recent_display,
                use_container_width=True,
                hide_index=True
            )
        
        st.divider()
        
        # Current Tiers (formerly Hall of Fame)
        st.subheader("🎖️ Current Tiers")
        
        # Create 5 columns for the tiers
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.markdown("### 💎 Diamond Tier")
            st.caption("8+ Wins")
            diamond_champions = stats['win_counts'][stats['win_counts'] >= 8]
            
            if len(diamond_champions) > 0:
                for champion, wins in diamond_champions.items():
                    st.markdown(f"💎 **{champion}** - {wins} wins")
            else:
                st.markdown("*No diamond tier champions yet*")
        
        with col2:
            st.markdown("### 💠 Platinum Tier")
            st.caption("6-7 Wins")
            platinum_champions = stats['win_counts'][
                (stats['win_counts'] >= 6) & (stats['win_counts'] < 8)
            ]
            
            if len(platinum_champions) > 0:
                for champion, wins in platinum_champions.items():
                    st.markdown(f"💠 **{champion}** - {wins} wins")
            else:
                st.markdown("*No platinum tier champions yet*")
        
        with col3:
            st.markdown("### 🥇 Gold Tier")
            st.caption("4-5 Wins")
            gold_champions = stats['win_counts'][
                (stats['win_counts'] >= 4) & (stats['win_counts'] < 6)
            ]
            
            if len(gold_champions) > 0:
                for champion, wins in gold_champions.items():
                    st.markdown(f"🥇 **{champion}** - {wins} wins")
            else:
                st.markdown("*No gold tier champions yet*")
        
        with col4:
            st.markdown("### 🥈 Silver Tier")
            st.caption("2-3 Wins")
            silver_champions = stats['win_counts'][
                (stats['win_counts'] >= 2) & (stats['win_counts'] < 4)
            ]
            
            if len(silver_champions) > 0:
                for champion, wins in silver_champions.items():
                    st.markdown(f"🥈 **{champion}** - {wins} wins")
            else:
                st.markdown("*No silver tier champions yet*")
        
        with col5:
            st.markdown("### 🥉 Bronze Tier")
            st.caption("1 Win")
            bronze_champions = stats['win_counts'][stats['win_counts'] == 1]
            
            if len(bronze_champions) > 0:
                for champion, wins in bronze_champions.items():
                    st.markdown(f"🥉 **{champion}** - {wins} wins")
            else:
                st.markdown("*No bronze tier champions yet*")
        
        
        # Hall of Fame - Yearly Tier Winners
        st.divider()
        st.subheader("🏛️ Hall of Fame - Yearly Tier Winners")
        st.caption("Celebrating our annual champions in each tier")
        
        # Team-specific Hall of Fame data
        if st.session_state.selected_team == "Clean Room":
            hall_of_fame_data = {
                2025: {
                    "Diamond": {"name": "-", "wins": "-"},
                    "Platinum": {"name": "Jacqueline", "wins": "7"},
                    "Gold": {"name": "Justin", "wins": "4"},
                    "Silver": {"name": "Sam", "wins": "3"},
                    "Bronze": {"name": "-", "wins": "-"},
                },
            }
        else:  # Collab Cloud
            hall_of_fame_data = {
                2025: {
                    "Diamond": {"name": "-", "wins": "-"},
                    "Platinum": {"name": "-", "wins": "-"},
                    "Gold": {"name": "Derek", "wins": "4"},
                    "Silver": {"name": "Ryan", "wins": "3"},
                    "Bronze": {"name": "Harishwar", "wins": "1"},
                }
            }
        
        # Display Hall of Fame by year
        for year in sorted(hall_of_fame_data.keys(), reverse=True):
            year_data = hall_of_fame_data[year]
            
            with st.expander(f"🏆 {year} Champions", expanded=(year == 2025)):
                hof_col1, hof_col2, hof_col3, hof_col4, hof_col5 = st.columns(5)
                
                with hof_col1:
                    st.markdown("#### 💎 Diamond")
                    st.markdown(f"**{year_data['Diamond']['name']}**")
                    if year_data['Diamond']['wins'] != "-":
                        st.caption(f"{year_data['Diamond']['wins']} wins")
                
                with hof_col2:
                    st.markdown("#### 💠 Platinum")
                    st.markdown(f"**{year_data['Platinum']['name']}**")
                    if year_data['Platinum']['wins'] != "-":
                        st.caption(f"{year_data['Platinum']['wins']} wins")
                
                with hof_col3:
                    st.markdown("#### 🥇 Gold")
                    st.markdown(f"**{year_data['Gold']['name']}**")
                    if year_data['Gold']['wins'] != "-":
                        st.caption(f"{year_data['Gold']['wins']} wins")
                
                with hof_col4:
                    st.markdown("#### 🥈 Silver")
                    st.markdown(f"**{year_data['Silver']['name']}**")
                    if year_data['Silver']['wins'] != "-":
                        st.caption(f"{year_data['Silver']['wins']} wins")
                
                with hof_col5:
                    st.markdown("#### 🥉 Bronze")
                    st.markdown(f"**{year_data['Bronze']['name']}**")
                    if year_data['Bronze']['wins'] != "-":
                        st.caption(f"{year_data['Bronze']['wins']} wins")

# Sidebar with app info
with st.sidebar:
    st.header("About Duck Race Tracker")
    st.markdown(f"""
    This app helps you track weekly duck race winners with Google Sheets integration!
    
    **Current Team:** **{st.session_state.selected_team}**
    
    **Features:**
    - 🏢 Team selection (Clean Room/Collab Cloud)
    - 🏁 Access to the duck race game
    - 📝 Easy winner entry
    - 📊 Comprehensive statistics
    - 📅 Date filtering for statistics
    - 🏆 Hall of Fame system with 5 tiers:
      - 💎 Diamond (8+ wins)
      - 💠 Platinum (6-7 wins)
      - 🥇 Gold (4-5 wins)
      - 🥈 Silver (2-3 wins)
      - 🥉 Bronze (1 win)
    - 📈 Visual charts and graphs
    - 📊 Statistical significance analysis
    - ☁️ Cloud storage with Google Sheets
    - 🔄 Smart refresh with API protection
    
    **How to use:**
    1. Select your team at the top
    2. Play the duck race game in the first tab
    3. Record the winner in the second tab
    4. View stats in the third tab (use refresh button after adding winners)
    
    **Data Storage:**
    All data is stored in separate Google Sheets tabs for each team:
    - ✅ Persistent across sessions
    - ✅ Team-specific data tracking
    - ✅ Accessible from anywhere
    - ✅ Easy to backup and share
    - ✅ Editable directly in Google Sheets if needed
    """)
    
    st.divider()
    
    st.divider()
    
    # API Rate Limiting Status
    st.subheader("🚦 API Protection Status")
    rate_status = check_api_rate_limit()
    
    col1, col2 = st.columns(2)
    with col1:
        if rate_status['calls_last_minute'] == 0:
            st.success("✅ No recent API calls")
        elif rate_status['minute_warning']:
            st.warning(f"⚠️ {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} calls/min")
        elif rate_status['minute_exceeded']:
            st.error(f"❌ {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} calls/min (LIMIT REACHED)")
        else:
            st.info(f"📊 {rate_status['calls_last_minute']}/{MAX_API_CALLS_PER_MINUTE} calls/min")
    
    with col2:
        if rate_status['calls_last_hour'] == 0:
            st.success("✅ No API calls this hour")
        elif rate_status['hour_warning']:
            st.warning(f"⚠️ {rate_status['calls_last_hour']}/{MAX_API_CALLS_PER_HOUR} calls/hour")
        elif rate_status['hour_exceeded']:
            st.error(f"❌ {rate_status['calls_last_hour']}/{MAX_API_CALLS_PER_HOUR} calls/hour (LIMIT REACHED)")
        else:
            st.info(f"📊 {rate_status['calls_last_hour']}/{MAX_API_CALLS_PER_HOUR} calls/hour")
    
    if rate_status['can_make_call']:
        st.caption("✅ Safe to make API requests")
    else:
        st.caption("⏳ Using cached data to protect against API limits")
    
    st.divider()
    
    # Google Sheets info
    st.subheader("📊 Google Sheets Integration")
    if worksheet:
        st.success(f"✅ Connected to {st.session_state.selected_team} sheet")
        
        # Manual refresh button
        if st.button("🔄 Force Refresh Data"):
            clear_cache_for_team(st.session_state.selected_team)
            st.rerun()
    else:
        st.error("❌ Not connected to Google Sheets")
    
    st.divider()
    
    # Quick stats in sidebar
    stats = calculate_statistics()
    if stats:
        st.subheader("📈 Quick Stats")
        st.metric("Total Races", stats['total_races'])
        st.metric("Champions", stats['unique_winners'])
        if stats['current_champion']:
            st.success(f"🏆 Current Champion: {stats['current_champion']}")
    
    # Team switching shortcut
    st.divider()
    st.subheader("🔄 Quick Team Switch")
    other_team = "Collab Cloud" if st.session_state.selected_team == "Clean Room" else "Clean Room"
    if st.button(f"Switch to {other_team}", use_container_width=True):
        st.session_state.selected_team = other_team
        clear_cache_for_team(other_team)
        st.rerun()
