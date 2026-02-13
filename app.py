import streamlit as st
from pyvis.network import Network
import requests
import json
import streamlit.components.v1 as components
import re
import html

# 1. Page configuration
st.set_page_config(page_title="Literary Nexus", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Source+Sans+3:wght@300;400;600&display=swap');
html, body, [class*="css"] {
    font-family: 'Source Sans 3', sans-serif;
}
.block-container {
    padding-top: 2rem;
    padding-bottom: 0rem;
}
</style>
""", unsafe_allow_html=True)

# 2. Title and description
st.title("🌌 NextChapter")

# [IMPORTANT] Create a placeholder variable first!
desc_placeholder = st.empty()

# Fill the placeholder with introductory text
desc_placeholder.markdown(
    """
    Enter three books and NextChapter will analyze their **writing style, philosophy, and atmosphere** to create your personalized reading map.<br><br>
    👈 Enter 3 books in the left sidebar and click the button to begin.
    """,
    unsafe_allow_html=True
)

# 3. Retrieve API key (security hardened)
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
    if not API_KEY or API_KEY == "":
        raise ValueError("API key is empty")
except Exception as e:
    st.error("⚠️ Please check your API key configuration.")
    st.info("""
    **How to set up your API key:**
    1. Streamlit Cloud: Go to Settings → Secrets and add:
       ```
       GOOGLE_API_KEY = "your-api-key-here"
       ```
    2. Local run: Create a `.streamlit/secrets.toml` file with the same content.

    ⚠️ **Important**: Never hard-code your API key directly in the source code!
    """)
    st.stop()

# 4. Sidebar input fields
with st.sidebar:
    st.header("📚 Book Titles")
    book1 = st.text_input("First Book", placeholder="e.g., The Stranger")
    book2 = st.text_input("Second Book", placeholder="e.g., The Unbearable Lightness of Being")
    book3 = st.text_input("Third Book", placeholder="e.g., 1984")
    analyze_btn = st.button("Generate Network")

# 5. Plain-text tooltip generator (no HTML)
def create_tooltip_text(node_data):
    """Create tooltip using plain text only — no HTML."""
    book_title = node_data.get('title') or node_data.get('id') or "Untitled"
    author = node_data.get('author', 'Unknown Author')
    reason = node_data.get('reason', 'No recommendation reason provided.')
    summary = node_data.get('summary', 'No summary available.')
    group = node_data.get('group', 'Recommended')

    if group == 'Seed':
        badge = "🔴 Your Input Book"
    elif group == 'Level2':
        badge = "🟡 Deep Recommendation"
    else:
        badge = "🔵 Recommended Book"

    # Pure text tooltip
    tooltip = f"{badge}\n\n📚 {book_title}\n✍️ {author}\n\n💡 Why this book:\n{reason}\n\n📖 Summary:\n{summary}"

    return tooltip

# 6. JSON extraction helper
def extract_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    return None

# 7. Graph generation logic (refined prompt)
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_recommendations(books):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

    prompt = f"""
    [Role]
    You are a 'Literary Curator' who analyzes texts by their 'Style', 'Philosophy', and 'Mood' to draw a precise reading map.

    [Input Books (Seeds)]
    The user has provided these 3 books as seeds: {books}

    [⚠️ Core Constraints (Strict Rules)]
    1. **Real Books Only**: Only recommend books that genuinely exist and are verifiable (e.g., searchable on Amazon or Goodreads). Never invent or hallucinate titles.
    2. **Accuracy Over Quantity**: Do NOT force 3–4 recommendations per Seed. Only recommend books you are 100% certain exist. If only 1 book qualifies, recommend 1.
    3. **Correct Attribution**: Match author names to book titles accurately.

    [Reasoning Process]
    1. **Extract DNA**: Identify core attribute keywords — shared or unique — across the 3 seed books.
    2. **Target Search**: Select recommended books that powerfully embody those keywords.
    3. **Build the Network**:
        - Connect each recommended book to its parent Seed book.
        - Also connect recommended books to each other if they share strong commonalities.

    [Data Rules]
    1. **Groups**:
        - Seed: The 3 user-provided books
        - Recommended: Primary recommendations (1–4 per Seed, real books only)
        - Level2: Derived recommendations (0–3 total, real books only)
    2. **Edges**:
        - Every recommended book must be connected to its source Seed book.
        - Edge label: A specific shared keyword linking the two books.
    3. **Text Content**:
        - **summary**: Core plot in 2–3 sentences.
        - **reason**: Explain specifically why this book connects to the input books (e.g., "Like [Seed Book], this novel explores [keyword] through a strikingly similar lens.").

    [JSON Format — Output this format ONLY]
    {{
      "nodes": [
        {{"id": "The Stranger", "title": "The Stranger", "author": "Albert Camus", "group": "Seed",
          "summary": "...", "reason": "..."}},
        {{"id": "Nausea", "title": "Nausea", "author": "Jean-Paul Sartre", "group": "Recommended",
          "summary": "...", "reason": "..."}}
      ],
      "edges": [
        {{"source": "The Stranger", "target": "Nausea", "label": "Existential Absurdity"}}
      ]
    }}

    Important: Output only valid JSON. Do not include markdown code fences or any explanatory text.
    """
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # Retry logic
    max_retries = 3
    retry_delays = [2, 5, 10]

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=60)

            if response.status_code == 429:
                st.error("⏳ API rate limit exceeded (429 error). Please wait and try again.")
                return None

            if response.status_code == 503 and attempt < max_retries - 1:
                import time
                time.sleep(retry_delays[attempt])
                continue

            response.raise_for_status()
            result = response.json()

            if 'candidates' in result and result['candidates']:
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
                cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
                data = extract_json(cleaned_text)
                return data
            else:
                return None

        except Exception as e:
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delays[attempt])
            else:
                st.error(f"❌ Communication error: {e}")
                return None

    return None

# 8. Pyvis visualization + custom tooltips
def visualize_network(data):
    net = Network(height="750px", width="100%", bgcolor="#ffffff", font_color="#000000")

    if isinstance(data, list):
        data = {'nodes': data, 'edges': []}
    if not isinstance(data, dict) or 'nodes' not in data:
        return None

    # Physics engine options
    options = """
    {
      "nodes": {
        "font": {
          "size": 16,
          "face": "Source Sans 3",
          "color": "#000000",
          "strokeWidth": 3,
          "strokeColor": "#ffffff",
          "bold": true
        },
        "borderWidth": 2,
        "borderWidthSelected": 4,
        "shadow": {
          "enabled": true,
          "size": 10
        }
      },
      "edges": {
        "color": { "color": "#666666", "inherit": false },
        "width": 2,
        "smooth": {
          "type": "continuous",
          "roundness": 0.5
        },
        "font": {
          "size": 12,
          "face": "Source Sans 3",
          "align": "middle",
          "background": "#ffffff",
          "strokeWidth": 0,
          "bold": true
        },
        "arrows": {
          "to": {
            "enabled": false
          }
        }
      },
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -200,
          "centralGravity": 0.01,
          "springLength": 350,
          "springConstant": 0.02,
          "damping": 0.7,
          "avoidOverlap": 1
        },
        "stabilization": {
          "enabled": true,
          "iterations": 200
        }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 50,
        "hideEdgesOnDrag": false,
        "hideEdgesOnZoom": false
      }
    }
    """
    net.set_options(options)

    # Add nodes
    for node in data.get('nodes', []):
        node_id = node.get('id')
        node_label = node.get('title') or str(node_id)

        if not node_id:
            node_id = node_label
            node['id'] = node_id

        group = node.get('group', 'Recommended')

        if group == 'Seed':
            color = "#FF6B6B"
            size = 50
        elif group == 'Level2':
            color = "#FFD93D"
            size = 25
        else:
            color = "#4ECDC4"
            size = 35

        tooltip_text = create_tooltip_text(node)

        net.add_node(
            node_id,
            label=node_label,
            title=tooltip_text,  # Plain text only
            color=color,
            size=size
        )

    # Add edges
    for edge in data.get('edges', []):
        source = edge.get('source')
        target = edge.get('target')
        label = edge.get('label', 'Related')

        if source and target:
            net.add_edge(source, target, label=label, title=label)

    # Generate HTML and inject custom CSS
    try:
        path = "tmp_network.html"
        net.save_graph(path)
        with open(path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Custom tooltip styles
        custom_style = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Source+Sans+3:wght@400;500;600;700&display=swap');

        div.vis-tooltip {
            font-family: 'Source Sans 3', sans-serif !important;
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%) !important;
            color: #000000 !important;
            border: 2px solid #e0e0e0 !important;
            border-radius: 16px !important;
            padding: 20px !important;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15) !important;
            max-width: 380px !important;
            font-size: 14px !important;
            line-height: 1.7 !important;
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            z-index: 999999 !important;
            pointer-events: none !important;
        }

        canvas {
            outline: none !important;
        }
        </style>
        """

        final_html = html_content.replace('</head>', f'{custom_style}</head>')
        return final_html

    except Exception as e:
        st.error(f"Error generating HTML: {e}")
        return None

# 9. Main execution
if analyze_btn and book1 and book2 and book3:
    # Clear the description placeholder
    desc_placeholder.empty()

    # Show loading message
    msg_placeholder = st.empty()
    msg_placeholder.markdown(
        """
        <div style="text-align: left; margin-bottom: 15px;">
            <strong><br>NextChapter is mapping the universe of your books... 🚀</strong><br><br>
            Building your recommendation network — this may take a moment. Please hang tight!
        </div>
        """,
        unsafe_allow_html=True
    )

    # Run AI analysis with spinner
    with st.spinner("AI analysis in progress..."):
        data = get_recommendations([book1, book2, book3])

    # Clear loading message once done
    msg_placeholder.empty()

    # Display results
    if data:
        if not data.get('edges'):
            st.error("❌ The AI could not generate connections (edges). Please try again.")
        else:
            final_html = visualize_network(data)
            if final_html:
                components.html(final_html, height=770)
                st.success("✅ Analysis complete! Hover over the nodes to explore 📚")
            else:
                st.error("Failed to generate visualization.")
    else:
        st.error("No response from AI. Please wait a moment and try again.")
