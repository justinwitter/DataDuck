import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import json
import os
from collections import Counter

# Set page config
st.set_page_config(
    page_title="🦆 Duck Race Champion Tracker",
    page_icon="🏆",
    layout="wide"
)

# File to store winner data
DATA_FILE = "duck_race_winners.json"

def load_data():
    """Load winner data from JSON file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []

def save_data(data):
    """Save winner data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def add_winner(winner_name, race_date, notes=""):
    """Add a new winner to the data"""
    data = load_data()
    new_entry = {
        "winner": winner_name,
        "date": race_date.isoformat(),
        "week": race_date.isocalendar()[1],
        "year": race_date.year,
        "notes": notes
    }
    data.append(new_entry)
    save_data(data)
    return True

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

# Main app
st.title("🦆 Duck Race Champion Tracker 🏆")

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
    st.header("Add New Winner")
    
    col1, col2 = st.columns(2)
    
    with col1:
        winner_name = st.text_input("Winner Name", placeholder="Enter the champion's name")
        race_date = st.date_input("Race Date", value=date.today())
    
    with col2:
        notes = st.text_area("Notes (optional)", placeholder="Any additional notes about this race...")
    
    if st.button("🏆 Add Winner", type="primary"):
        if winner_name:
            if add_winner(winner_name, race_date, notes):
                st.success(f"🎉 {winner_name} added as champion for {race_date}!")
                st.balloons()
            else:
                st.error("Failed to add winner. Please try again.")
        else:
            st.error("Please enter a winner name.")
    
    # Show recent entries
    st.subheader("Recent Winners")
    data = load_data()
    if data:
        recent_df = pd.DataFrame(data).tail(5)
        recent_df['date'] = pd.to_datetime(recent_df['date']).dt.strftime('%Y-%m-%d')
        st.dataframe(recent_df[['winner', 'date', 'notes']], use_container_width=True)
    else:
        st.info("No winners recorded yet!")

with tab3:
    st.header("🏆 Champions Wall & Statistics")
    
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
    This app helps you track weekly duck race winners and shows amazing statistics!
    
    **Features:**
    - 🏁 Access to the duck race game
    - 📝 Easy winner entry
    - 📊 Comprehensive statistics
    - 🏆 Hall of Fame system
    - 📈 Visual charts and graphs
    
    **How to use:**
    1. Play the duck race game in the first tab
    2. Record the winner in the second tab
    3. View awesome stats in the third tab
    """)
    
    st.divider()
    
    # Quick stats in sidebar
    stats = get_stats()
    if stats:
        st.metric("Total Races", stats['total_races'])
        st.metric("Champions", stats['unique_winners'])
        if stats['current_champion']:
            st.success(f"Current Champion: {stats['current_champion']}")
