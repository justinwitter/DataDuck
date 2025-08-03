import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import gspread
from google.oauth2.service_account import Credentials
from collections import Counter
import json

# Set page config
st.set_page_config(
    page_title="🦆 Duck Race Champion Tracker",
    page_icon="🏆",
    layout="wide"
)

# Google Sheets configuration
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

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
        worksheet = spreadsheet.sheet1  # Use the first worksheet
        
        # Initialize headers if sheet is empty
        try:
            headers = worksheet.row_values(1)
            if not headers or headers != ['winner', 'date', 'week', 'year', 'notes']:
                worksheet.clear()
                worksheet.append_row(['winner', 'date', 'week', 'year', 'notes'])
        except Exception:
            worksheet.append_row(['winner', 'date', 'week', 'year', 'notes'])
        
        return worksheet
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {str(e)}")
        st.error("Please check your Google Sheets credentials in Streamlit secrets.")
        return None

def load_data():
    """Load winner data from Google Sheets"""
    worksheet = init_google_sheets()
    if worksheet is None:
        return []
    
    try:
        # Get all records (skip header row)
        records = worksheet.get_all_records()
        return records
    except Exception as e:
        st.error(f"Error loading data from Google Sheets: {str(e)}")
        return []

def save_winner_to_sheets(winner_name, race_date, notes=""):
    """Add a new winner directly to Google Sheets"""
    worksheet = init_google_sheets()
    if worksheet is None:
        return False
    
    try:
        new_row = [
            winner_name,
            race_date.isoformat(),
            race_date.isocalendar()[1],  # week number
            race_date.year,
            notes
        ]
        worksheet.append_row(new_row)
        return True
    except Exception as e:
        st.error(f"Error saving to Google Sheets: {str(e)}")
        return False

def get_stats():
    """Calculate various statistics from the winner data"""
    data = load_data()
    if not data:
        return None
    
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    
    stats = {
        'total_races': len(data),
        'unique_winners': len(df['winner'].unique()),
        'most_wins': df['winner'].value_counts().head(5),
        'recent_winners': df.nlargest(10, 'date')[['winner', 'date']],
        'wins_by_month': df.groupby(df['date'].dt.to_period('M')).size(),
        'current_champion': df.loc[df['date'].idxmax(), 'winner'] if len(df) > 0 else None,
        'champion_streak': None
    }
    
    # Calculate current champion streak
    if len(df) > 0:
        df_sorted = df.sort_values('date', ascending=False)
        current_champ = df_sorted.iloc[0]['winner']
        streak = 1
        for i in range(1, len(df_sorted)):
            if df_sorted.iloc[i]['winner'] == current_champ:
                streak += 1
            else:
                break
        stats['champion_streak'] = streak
    
    return stats

# Show setup instructions if Google Sheets is not configured
if 'google_sheets' not in st.secrets or 'sheet_url' not in st.secrets:
    st.error("🔧 **Google Sheets Setup Required**")
    st.markdown("""
    To use this app with Google Sheets, you need to:
    
    1. **Create a Google Sheet** for storing duck race data
    2. **Set up a Google Service Account** with Sheets API access
    3. **Configure Streamlit Secrets** with your credentials
    
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
st.title("🦆 Duck Race Champion Tracker 🏆")
st.caption("📊 Data stored in Google Sheets - accessible from anywhere!")

# Test connection
worksheet = init_google_sheets()
if worksheet:
    st.success("✅ Connected to Google Sheets successfully!")
else:
    st.error("❌ Failed to connect to Google Sheets. Check your configuration.")
    st.stop()

# Create tabs
tab1, tab2, tab3 = st.tabs(["🏁 Duck Race", "📝 Add Winner", "📊 Champions Wall"])

with tab1:
    st.header("🏁 Duck Race Game")
    
    # Create columns for better layout
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.warning("⚠️ **Embedding Issue Detected:** The duck race website blocks embedding in iframes for security reasons.")
        st.info("🎮 **How to Play:** Click the button below to open the duck race in a new tab, then come back here to record the winner!")
    
    with col2:
        # Big prominent button to open the game
        if st.button("🦆 **PLAY DUCK RACE**", type="primary", use_container_width=True):
            st.markdown("""
            <script>
            window.open('https://www.online-stopwatch.com/duck-race/', '_blank');
            </script>
            """, unsafe_allow_html=True)
    
    # Alternative: Show the link prominently
    st.markdown("---")
    st.markdown("""
    ### 🎯 Quick Access Links:
    - **[🦆 Play Duck Race (Main Game)](https://www.online-stopwatch.com/duck-race/)**
    - **[⏱️ Online Stopwatch (Alternative)](https://www.online-stopwatch.com/)**
    """)
    
    # Try embedding with different approach (sometimes works)
    st.markdown("---")
    st.subheader("🔄 Alternative Embedding Attempt")
    st.markdown("*If the game loads below, you can play directly here:*")
    
    # Try a different embedding approach
    components.html("""
        <div style="width: 100%; height: 600px; border: 2px dashed #ccc; border-radius: 10px; position: relative;">
            <iframe src="https://www.online-stopwatch.com/duck-race/" 
                    width="100%" 
                    height="100%" 
                    frameborder="0"
                    sandbox="allow-scripts allow-same-origin allow-forms"
                    loading="lazy"
                    style="border-radius: 8px;">
            </iframe>
            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; color: #666;">
                <p>🚫 Game cannot be embedded due to website restrictions</p>
                <p><strong><a href="https://www.online-stopwatch.com/duck-race/" target="_blank" style="color: #ff6b6b;">Click here to play in new tab</a></strong></p>
            </div>
        </div>
        """, height=620)
    
    st.markdown("---")
    st.success("**🏆 After playing the race, return here and go to the 'Add Winner' tab to record the champion!**")

with tab2:
    st.header("📝 Add New Winner")
    
    col1, col2 = st.columns(2)
    
    with col1:
        winner_name = st.text_input("Winner Name", placeholder="Enter the champion's name")
        race_date = st.date_input("Race Date", value=date.today())
    
    with col2:
        notes = st.text_area("Notes (optional)", placeholder="Any additional notes about this race...")
    
    if st.button("🏆 Add Winner", type="primary"):
        if winner_name.strip():
            with st.spinner("Saving to Google Sheets..."):
                if save_winner_to_sheets(winner_name.strip(), race_date, notes):
                    st.success(f"🎉 {winner_name} added as champion for {race_date}!")
                    st.balloons()
                    # Clear the cache to refresh data
                    st.cache_data.clear()
                else:
                    st.error("Failed to add winner. Please check your Google Sheets connection.")
        else:
            st.error("Please enter a winner name.")
    
    # Show recent entries
    st.subheader("🕐 Recent Winners")
    with st.spinner("Loading recent winners..."):
        data = load_data()
        if data:
            recent_df = pd.DataFrame(data).tail(5)
            recent_df['date'] = pd.to_datetime(recent_df['date']).dt.strftime('%Y-%m-%d')
            st.dataframe(recent_df[['winner', 'date', 'notes']], use_container_width=True)
        else:
            st.info("No winners recorded yet!")

with tab3:
    st.header("🏆 Champions Wall & Statistics")
    
    with st.spinner("Loading statistics from Google Sheets..."):
        stats = get_stats()
    
    if stats is None:
        st.info("No race data available yet. Add some winners to see amazing stats!")
    else:
        # Top stats row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Races", stats['total_races'])
        
        with col2:
            st.metric("Unique Champions", stats['unique_winners'])
        
        with col3:
            st.metric("Current Champion", stats['current_champion'] or "None")
        
        with col4:
            st.metric("Champion Streak", f"{stats['champion_streak']} race(s)" if stats['champion_streak'] else "0")
        
        st.divider()
        
        # Charts section
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🥇 Top Champions")
            if len(stats['most_wins']) > 0:
                fig_bar = px.bar(
                    x=stats['most_wins'].values,
                    y=stats['most_wins'].index,
                    orientation='h',
                    title="Wins by Champion",
                    color=stats['most_wins'].values,
                    color_continuous_scale="Viridis"
                )
                fig_bar.update_layout(yaxis_title="Champion", xaxis_title="Number of Wins")
                st.plotly_chart(fig_bar, use_container_width=True)
        
        with col2:
            st.subheader("📅 Races Over Time")
            if len(stats['wins_by_month']) > 0:
                fig_line = px.line(
                    x=stats['wins_by_month'].index.astype(str),
                    y=stats['wins_by_month'].values,
                    title="Races per Month"
                )
                fig_line.update_layout(xaxis_title="Month", yaxis_title="Number of Races")
                st.plotly_chart(fig_line, use_container_width=True)
        
        st.divider()
        
        # Recent activity
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🕐 Recent Champions")
            recent_df = stats['recent_winners'].copy()
            recent_df['date'] = recent_df['date'].dt.strftime('%Y-%m-%d')
            st.dataframe(recent_df, use_container_width=True, hide_index=True)
        
        with col2:
            st.subheader("🎯 Champion Distribution")
            win_counts = stats['most_wins']
            if len(win_counts) > 0:
                fig_pie = px.pie(
                    values=win_counts.values,
                    names=win_counts.index,
                    title="Win Distribution"
                )
                st.plotly_chart(fig_pie, use_container_width=True)
        
        # Hall of Fame section
        st.divider()
        st.subheader("🏛️ Hall of Fame")
        
        # Create hall of fame with different tiers
        if len(stats['most_wins']) > 0:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("### 🥇 Gold Tier (5+ wins)")
                gold_champions = stats['most_wins'][stats['most_wins'] >= 5]
                if len(gold_champions) > 0:
                    for champ, wins in gold_champions.items():
                        st.markdown(f"**{champ}** - {wins} wins")
                else:
                    st.markdown("*No gold tier champions yet*")
            
            with col2:
                st.markdown("### 🥈 Silver Tier (3-4 wins)")
                silver_champions = stats['most_wins'][(stats['most_wins'] >= 3) & (stats['most_wins'] < 5)]
                if len(silver_champions) > 0:
                    for champ, wins in silver_champions.items():
                        st.markdown(f"**{champ}** - {wins} wins")
                else:
                    st.markdown("*No silver tier champions yet*")
            
            with col3:
                st.markdown("### 🥉 Bronze Tier (2 wins)")
                bronze_champions = stats['most_wins'][stats['most_wins'] == 2]
                if len(bronze_champions) > 0:
                    for champ, wins in bronze_champions.items():
                        st.markdown(f"**{champ}** - {wins} wins")
                else:
                    st.markdown("*No bronze tier champions yet*")

# Sidebar with app info
with st.sidebar:
    st.header("About Duck Race Tracker")
    st.markdown("""
    This app helps you track weekly duck race winners with **Google Sheets integration**!
    
    **Features:**
    - 🏁 Access to the duck race game
    - 📝 Easy winner entry
    - 📊 Comprehensive statistics
    - 🏆 Hall of Fame system
    - 📈 Visual charts and graphs
    - ☁️ **Cloud storage with Google Sheets**
    
    **How to use:**
    1. Play the duck race game in the first tab
    2. Record the winner in the second tab
    3. View awesome stats in the third tab
    
    **Data Storage:**
    All data is stored in Google Sheets, making it:
    - ✅ Persistent across sessions
    - ✅ Accessible from anywhere
    - ✅ Easy to backup and share
    - ✅ Editable directly in Google Sheets if needed
    """)
    
    st.divider()
    
    # Google Sheets info
    st.subheader("📊 Google Sheets Integration")
    if worksheet:
        st.success("✅ Connected to Google Sheets")
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
    else:
        st.error("❌ Not connected to Google Sheets")
    
    st.divider()
    
    # Quick stats in sidebar
    stats = get_stats()
    if stats:
        st.metric("Total Races", stats['total_races'])
        st.metric("Champions", stats['unique_winners'])
        if stats['current_champion']:
            st.success(f"Current Champion: {stats['current_champion']}")
