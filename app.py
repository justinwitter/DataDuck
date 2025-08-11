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

# Set page config
st.set_page_config(
    page_title="DataDuck",
    page_icon="🦆",
    layout="wide"
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
    st.session_state.selected_team = "Clean Room"  # Default team

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

def load_data():
    """Load winner data from Google Sheets for selected team"""
    worksheet = get_or_create_worksheet(st.session_state.selected_team)
    if worksheet is None:
        return []
    
    try:
        # Get all records (skip header row)
        records = worksheet.get_all_records()
        return records
    except Exception as e:
        st.error(f"Error loading data from Google Sheets for {st.session_state.selected_team}: {str(e)}")
        return []

def save_winner_to_sheets(winner_name, race_date):
    """Add a new winner directly to Google Sheets for selected team"""
    worksheet = get_or_create_worksheet(st.session_state.selected_team)
    if worksheet is None:
        return False
    
    try:
        new_row = [
            winner_name,
            race_date.isoformat()
        ]
        worksheet.append_row(new_row)
        return True
    except Exception as e:
        st.error(f"Error saving to Google Sheets for {st.session_state.selected_team}: {str(e)}")
        return False

def calculate_statistics():
    """Calculate comprehensive statistics from the winner data"""
    data = load_data()
    
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
        ["Clean Room", "Collab Cloud"],
        index=0 if st.session_state.selected_team == "Clean Room" else 1,
        key="team_selector"
    )
    if team_option != st.session_state.selected_team:
        st.session_state.selected_team = team_option
        st.cache_data.clear()  # Clear cache when switching teams
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
    
    # Set default players based on team
    if st.session_state.selected_team == "Clean Room":
        default_players = ["Nate", "Justin", "Bjorn", "Jacqueline", "Adi", "Brayden", "Sam", "Ryan", "Lavanya", "Vikram"]
    else:  # Collab Cloud
        default_players = ["Jeffrey", "Jacob", "Cate", "Ryan", "Bharathi", "Gerardo", "Jordan", "Mazie", "Derek"]
    
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
    
    if st.button("🏆 Add Winner", type="primary"):
        if winner_name:
            with st.spinner("Saving to team sheet..."):
                if save_winner_to_sheets(winner_name, race_date):
                    st.success(f"🎉 {winner_name} added as champion for {race_date}!")
                    st.balloons()
                    # Clear the cache to refresh data
                    st.cache_data.clear()
                else:
                    st.error("Failed to add winner. Please check your Google Sheets connection.")
        else:
            st.error("Please select a winner from the dropdown.")
    
    # Show recent entries
    st.subheader("🕐 Recent Winners")
    with st.spinner("Loading recent winners..."):
        data = load_data()
        if data:
            recent_df = pd.DataFrame(data)
            recent_df['date'] = pd.to_datetime(recent_df['date'])
            # Sort by date descending to show most recent first, then take last 5
            recent_df = recent_df.sort_values('date', ascending=False).head(5)
            recent_df['date'] = recent_df['date'].dt.strftime('%Y-%m-%d')
            st.dataframe(recent_df[['winner', 'date']], use_container_width=True)
        else:
            st.info("No winners recorded yet!")

with tab3:
    st.header("🏆 Champions Wall & Statistics")
    
    with st.spinner("Loading statistics from team sheet..."):
        stats = calculate_statistics()
    
    if stats is None:
        st.info("No race data available yet. Add some winners to see amazing stats!")
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
        
        # Hall of Fame
        st.subheader("🏛️ Hall of Fame")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### 🥇 Gold Tier")
            st.caption("5+ Wins")
            gold_champions = stats['win_counts'][stats['win_counts'] >= 5]
            
            if len(gold_champions) > 0:
                for champion, wins in gold_champions.items():
                    st.markdown(f"🏆 **{champion}** - {wins} wins")
            else:
                st.markdown("*No gold tier champions yet*")
        
        with col2:
            st.markdown("### 🥈 Silver Tier")
            st.caption("3-4 Wins")
            silver_champions = stats['win_counts'][
                (stats['win_counts'] >= 3) & (stats['win_counts'] < 5)
            ]
            
            if len(silver_champions) > 0:
                for champion, wins in silver_champions.items():
                    st.markdown(f"🥈 **{champion}** - {wins} wins")
            else:
                st.markdown("*No silver tier champions yet*")
        
        with col3:
            st.markdown("### 🥉 Bronze Tier")
            st.caption("2 Wins")
            bronze_champions = stats['win_counts'][stats['win_counts'] == 2]
            
            if len(bronze_champions) > 0:
                for champion, wins in bronze_champions.items():
                    st.markdown(f"🥉 **{champion}** - {wins} wins")
            else:
                st.markdown("*No bronze tier champions yet*")
        
        # Summary statistics
        st.divider()
        st.subheader("📊 Summary Statistics")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            avg_wins = stats['win_counts'].mean()
            st.metric("Average Wins per Player", f"{avg_wins:.1f}")
        
        with col2:
            max_wins = stats['win_counts'].max()
            st.metric("Most Wins by One Player", max_wins)
        
        with col3:
            one_time_winners = len(stats['win_counts'][stats['win_counts'] == 1])
            st.metric("One-Time Winners", one_time_winners)
        
        with col4:
            multi_winners = len(stats['win_counts'][stats['win_counts'] > 1])
            st.metric("Multi-Time Winners", multi_winners)

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
    - 🏆 Hall of Fame system
    - 📈 Visual charts and graphs
    - ☁️ Cloud storage with Google Sheets
    
    **How to use:**
    1. Select your team at the top
    2. Play the duck race game in the first tab
    3. Record the winner in the second tab
    4. View awesome stats in the third tab
    
    **Data Storage:**
    All data is stored in separate Google Sheets tabs for each team:
    - ✅ Persistent across sessions
    - ✅ Team-specific data tracking
    - ✅ Accessible from anywhere
    - ✅ Easy to backup and share
    - ✅ Editable directly in Google Sheets if needed
    """)
    
    st.divider()
    
    # Google Sheets info
    st.subheader("📊 Google Sheets Integration")
    if worksheet:
        st.success(f"✅ Connected to {st.session_state.selected_team} sheet")
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
    else:
        st.error("❌ Not connected to Google Sheets")
    
    st.divider()
    
    # Quick stats in sidebar
    stats = calculate_statistics()
    if stats:
        st.metric("Total Races", stats['total_races'])
        st.metric("Champions", stats['unique_winners'])
        if stats['current_champion']:
            st.success(f"Current Champion: {stats['current_champion']}")
    
    # Team switching shortcut
    st.divider()
    st.subheader("🔄 Quick Team Switch")
    other_team = "Collab Cloud" if st.session_state.selected_team == "Clean Room" else "Clean Room"
    if st.button(f"Switch to {other_team}", use_container_width=True):
        st.session_state.selected_team = other_team
        st.cache_data.clear()
        st.rerun()
