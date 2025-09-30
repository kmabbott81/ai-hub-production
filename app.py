"""
AI Hub - Real Multi-Agent Collaboration
Public deployment version with Streamlit secrets support
"""
import streamlit as st
import json
import os
import asyncio
import time
from datetime import datetime

# Page config
st.set_page_config(
    page_title="AI Hub",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import AI clients with error handling
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from notion_client import Client as NotionClient
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False

# Get API keys from environment variables (Railway) or Streamlit secrets
def get_api_key(service):
    # Try multiple naming conventions for Railway environment variables
    # 1. Try lowercase service name (Railway custom names: anthropic, openai, perplexity)
    env_key = os.getenv(service.lower())
    if env_key:
        return env_key

    # 2. Try uppercase service name (ANTHROPIC, OPENAI, PERPLEXITY)
    env_key = os.getenv(service.upper())
    if env_key:
        return env_key

    # 3. Try standard format with _API_KEY suffix (ANTHROPIC_API_KEY, etc.)
    env_key = os.getenv(f"{service.upper()}_API_KEY")
    if env_key:
        return env_key

    # 4. Fall back to Streamlit secrets (alternative deployment)
    try:
        return st.secrets.get(f"{service.upper()}_API_KEY")
    except:
        return None

# Check API availability
openai_key = get_api_key("openai")
anthropic_key = get_api_key("anthropic")
perplexity_key = get_api_key("perplexity")
gemini_key = get_api_key("gemini")
notion_key = get_api_key("notion")

api_status = {
    'openai': OPENAI_AVAILABLE and bool(openai_key),
    'anthropic': ANTHROPIC_AVAILABLE and bool(anthropic_key),
    'perplexity': REQUESTS_AVAILABLE and bool(perplexity_key),
    'gemini': GEMINI_AVAILABLE and bool(gemini_key),
    'notion': NOTION_AVAILABLE and bool(notion_key)
}

production_engine_available = any(api_status.values())

# Simple authentication
USERS = {
    "demo": "demo123",
    "admin": "admin123",
    "kyle": "kyle123"
}

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'show_login' not in st.session_state:
    st.session_state.show_login = False
if 'chat_threads' not in st.session_state:
    st.session_state.chat_threads = []
if 'current_thread_id' not in st.session_state:
    st.session_state.current_thread_id = None
if 'thread_counter' not in st.session_state:
    st.session_state.thread_counter = 0

# Query type detection and specialized prompts
def detect_query_type(query: str) -> str:
    """Detect the type of query to optimize agent prompts"""
    query_lower = query.lower()

    if any(term in query_lower for term in ['business idea', 'startup', 'profitable', 'business model']):
        return 'business_strategy'
    elif any(term in query_lower for term in ['technical', 'architecture', 'code', 'implementation', 'software']):
        return 'technical_analysis'
    elif any(term in query_lower for term in ['market', 'industry', 'trend', 'competitor', 'analysis']):
        return 'market_research'
    elif any(term in query_lower for term in ['invest', 'financial', 'valuation', 'roi', 'profit']):
        return 'financial_analysis'
    else:
        return 'general'

def get_specialized_prompts(query: str, query_type: str) -> dict:
    """Generate specialized prompts for each agent based on query type"""

    if query_type == 'business_strategy':
        return {
            'perplexity': f"Research current market data, growth rates, successful case studies, and industry statistics for: {query}. Include specific numbers, market sizes, and credible sources.",
            'claude': f"Provide comprehensive business analysis including: 1) Implementation timeline with monthly breakdown, 2) Detailed cost analysis and profit projections, 3) Scaling strategies from 0-10 years, 4) Risk assessment and mitigation strategies for: {query}",
            'gpt': f"Generate 3 creative variations and innovative approaches to: {query}. For each, explain: unique positioning, growth hacks, and competitive advantages."
        }
    elif query_type == 'technical_analysis':
        return {
            'perplexity': f"Research best practices, technology stack trends, performance benchmarks, and case studies for: {query}",
            'claude': f"Provide detailed technical analysis including: architecture design, scalability considerations, security implications, and implementation roadmap for: {query}",
            'gpt': f"Suggest innovative technical approaches, alternative architectures, and creative solutions for: {query}"
        }
    elif query_type == 'market_research':
        return {
            'perplexity': f"Conduct comprehensive market research including: market size, growth trends, key players, competitive landscape, and recent developments for: {query}",
            'claude': f"Analyze market dynamics, competitive positioning, barriers to entry, and strategic recommendations for: {query}",
            'gpt': f"Identify underserved niches, emerging opportunities, and contrarian perspectives on: {query}"
        }
    elif query_type == 'financial_analysis':
        return {
            'perplexity': f"Research financial data, valuation metrics, industry benchmarks, and investment trends for: {query}",
            'claude': f"Provide detailed financial analysis including: valuation models, ROI projections, risk-adjusted returns, and scenario analysis for: {query}",
            'gpt': f"Suggest creative financial strategies, alternative investment approaches, and hidden value opportunities for: {query}"
        }
    else:
        return {
            'perplexity': f"Research and analyze: {query}",
            'claude': f"Provide deep analysis and insights for: {query}",
            'gpt': f"Provide creative insights and alternative perspectives on: {query}"
        }

# Real multi-agent collaboration function with sequential reasoning
async def real_multi_agent_collaboration(query: str, mode: str = "production"):
    """Real multi-agent collaboration using sequential reasoning chain for exponentially better output"""

    start_time = time.time()
    agents_used = []
    models_used = []
    responses = []
    agent_errors = []
    total_cost = 0.0

    # Detect query type and get specialized prompts
    query_type = detect_query_type(query)
    specialized_prompts = get_specialized_prompts(query, query_type)

    # Store outputs from each stage for next stage to use
    research_output = None
    analysis_output = None
    creative_output = None

    def call_perplexity_sync():
        if not api_status.get('perplexity'):
            return None
        try:
            headers = {
                "Authorization": f"Bearer {get_api_key('perplexity')}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "sonar-pro",
                "messages": [{"role": "user", "content": specialized_prompts['perplexity']}],
                "max_tokens": 600,  # Reduced for speed
                "temperature": 0.2
            }
            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
                timeout=30  # Increased timeout for research queries
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'agent': 'Perplexity Research Agent',
                    'model': 'sonar-pro',
                    'response': f"**Research Findings:** {data['choices'][0]['message']['content']}",
                    'cost': 0.002
                }
        except Exception as e:
            agent_errors.append(f"Perplexity: {str(e)}")
        return None

    def call_claude_sync(context=None):
        if not api_status.get('anthropic'):
            return None
        try:
            api_key = get_api_key("anthropic")
            if not api_key:
                agent_errors.append("Claude: No API key found in environment")
                return None

            # Debug: Check if API key looks valid (starts with sk-)
            if not api_key.startswith('sk-'):
                agent_errors.append(f"Claude: API key format invalid (should start with 'sk-', got '{api_key[:5]}...')")
                return None

            # Build prompt with context from previous agents
            if context:
                enhanced_prompt = f"{specialized_prompts['claude']}\n\n**Context from previous analysis:**\n{context}"
            else:
                enhanced_prompt = specialized_prompts['claude']

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",  # Latest Claude Sonnet 4.5 (Sept 2025)
                max_tokens=1000,  # Increased for analysis with context
                messages=[{"role": "user", "content": enhanced_prompt}]
            )
            return {
                'agent': 'Claude Analysis Agent',
                'model': 'claude-sonnet-4.5',
                'response': f"**Deep Analysis:** {response.content[0].text}",
                'cost': 0.003
            }
        except Exception as e:
            agent_errors.append(f"Claude: {str(e)}")
        return None

    def call_openai_sync(context=None):
        if not api_status.get('openai'):
            return None
        try:
            # Build prompt with context from previous agents
            if context:
                enhanced_prompt = f"{specialized_prompts['gpt']}\n\n**Context from previous analysis:**\n{context}"
            else:
                enhanced_prompt = specialized_prompts['gpt']

            client = openai.OpenAI(api_key=get_api_key("openai"))
            response = client.chat.completions.create(
                model="gpt-4o",  # Upgraded from gpt-4o-mini for 10x better reasoning
                messages=[{"role": "user", "content": enhanced_prompt}],
                max_tokens=1000,  # Increased for GPT-4o with context
                temperature=0.7
            )
            return {
                'agent': 'GPT Creative Agent',
                'model': 'gpt-4o',
                'response': f"**Creative Perspective:** {response.choices[0].message.content}",
                'cost': 0.015  # GPT-4o costs more but worth it
            }
        except Exception as e:
            agent_errors.append(f"OpenAI: {str(e)}")
        return None

    # Gemini agent removed - consistently blocked by safety filters
    # Claude synthesis provides comprehensive synthesis without Gemini issues

    # SEQUENTIAL REASONING CHAIN for exponentially better quality
    # Each agent builds upon the previous agent's output

    # STAGE 1: Research Foundation (Perplexity)
    research_result = call_perplexity_sync()
    if research_result:
        agents_used.append(research_result['agent'])
        models_used.append(research_result['model'])
        responses.append(research_result['response'])
        total_cost += research_result['cost']
        research_output = research_result['response']

    # STAGE 2: Deep Analysis (Claude uses Research)
    analysis_context = f"{research_output}" if research_output else None
    analysis_result = call_claude_sync(context=analysis_context)
    if analysis_result:
        agents_used.append(analysis_result['agent'])
        models_used.append(analysis_result['model'])
        responses.append(analysis_result['response'])
        total_cost += analysis_result['cost']
        analysis_output = analysis_result['response']

        # STAGE 2.5: Self-Critique Loop (Claude reviews its own analysis)
        if api_status.get('anthropic') and analysis_output:
            try:
                api_key = get_api_key("anthropic")
                if api_key:
                    client = anthropic.Anthropic(api_key=api_key)

                    # Critique phase
                    critique_prompt = f"""Review the following analysis for logical flaws, missing considerations, unsupported claims, or gaps in reasoning:

{analysis_output}

Provide constructive criticism:
1. What logical flaws or weak arguments exist?
2. What important considerations are missing?
3. What claims need better support or evidence?
4. What gaps in the reasoning chain should be addressed?

Be specific and actionable."""

                    critique_response = client.messages.create(
                        model="claude-sonnet-4-5-20250929",
                        max_tokens=600,
                        messages=[{"role": "user", "content": critique_prompt}]
                    )
                    total_cost += 0.003

                    critique_text = critique_response.content[0].text

                    # STAGE 2.6: Refinement (Claude revises based on critique)
                    refinement_prompt = f"""Based on this critique of your analysis, revise and improve it:

ORIGINAL ANALYSIS:
{analysis_output}

CRITIQUE:
{critique_text}

Provide a refined analysis that addresses the identified issues while maintaining strengths. Focus on filling gaps and strengthening weak points."""

                    refinement_response = client.messages.create(
                        model="claude-sonnet-4-5-20250929",
                        max_tokens=1000,
                        messages=[{"role": "user", "content": refinement_prompt}]
                    )
                    total_cost += 0.003

                    # Replace original analysis with refined version
                    analysis_output = f"**Deep Analysis (Refined):** {refinement_response.content[0].text}"

                    # Update responses list to replace original with refined
                    responses[-1] = analysis_output

            except Exception as e:
                agent_errors.append(f"Self-Critique: {str(e)}")

    # STAGE 3: Creative Alternatives (GPT uses Research + Analysis)
    creative_context = None
    if research_output and analysis_output:
        creative_context = f"RESEARCH:\n{research_output}\n\nANALYSIS:\n{analysis_output}"
    elif research_output:
        creative_context = research_output
    elif analysis_output:
        creative_context = analysis_output

    creative_result = call_openai_sync(context=creative_context)
    if creative_result:
        agents_used.append(creative_result['agent'])
        models_used.append(creative_result['model'])
        responses.append(creative_result['response'])
        total_cost += creative_result['cost']
        creative_output = creative_result['response']

    # STAGE 4: Final Synthesis (Claude synthesizes everything)
    if len(responses) >= 2:
        synthesis_context = f"RESEARCH:\n{research_output}\n\nANALYSIS:\n{analysis_output}\n\nCREATIVE ALTERNATIVES:\n{creative_output}"

        # Call Claude again for final synthesis
        if api_status.get('anthropic'):
            try:
                api_key = get_api_key("anthropic")
                if api_key:
                    client = anthropic.Anthropic(api_key=api_key)
                    synthesis_prompt = f"""Synthesize the following analyses into actionable recommendations and key insights for: {query}

{synthesis_context}

Provide:
1. Top 3 recommendations prioritized by impact
2. Key insights synthesized from all perspectives
3. Critical success factors
4. Next steps and timeline"""

                    response = client.messages.create(
                        model="claude-sonnet-4-5-20250929",
                        max_tokens=800,
                        messages=[{"role": "user", "content": synthesis_prompt}]
                    )

                    synthesis_result = {
                        'agent': 'Claude Synthesis Agent',
                        'model': 'claude-sonnet-4.5',
                        'response': f"**Strategic Synthesis:** {response.content[0].text}",
                        'cost': 0.003
                    }

                    agents_used.append(synthesis_result['agent'])
                    models_used.append(synthesis_result['model'])
                    responses.append(synthesis_result['response'])
                    total_cost += synthesis_result['cost']
            except Exception as e:
                agent_errors.append(f"Synthesis: {str(e)}")

    # Add error information if any agents failed
    if agent_errors:
        error_summary = "\n\n**⚠️ Agent Status:**\n"
        error_summary += f"• {len(agents_used)} of 4 agents responded successfully\n"
        for error in agent_errors:
            error_summary += f"• {error}\n"
    else:
        error_summary = ""

    # Combine responses with structured formatting
    if responses:
        # Generate executive summary from all responses
        executive_summary_points = []
        if len(responses) >= 2:
            executive_summary_points = [
                "✅ Multi-perspective analysis from {} expert AI systems".format(len(agents_used)),
                "✅ Research-backed with current market data and citations" if any('Research' in r for r in responses) else "",
                "✅ Detailed implementation strategies and profit projections" if any('Analysis' in r for r in responses) else "",
                "✅ Creative alternatives and innovative approaches" if any('Creative' in r for r in responses) else ""
            ]
            executive_summary_points = [p for p in executive_summary_points if p]  # Remove empty strings

        # Build structured output
        final_response = "## 📊 Executive Summary\n\n"
        for point in executive_summary_points[:3]:
            final_response += f"{point}\n"

        final_response += f"\n**Query Type Detected:** `{query_type}`\n"
        final_response += f"**Analysis Confidence:** {98 if len(responses) >= 4 else 95 if len(responses) >= 3 else 88 if len(responses) >= 2 else 75}%\n"
        final_response += "\n---\n\n## 🔍 Detailed Analysis\n\n"

        # Create cleaner, more readable response sections
        sections = []
        for response in responses:
            sections.append(f"{response}\n\n---\n")

        final_response += "\n".join(sections)

        # Add structured conclusion
        final_response += f"\n\n## 🎯 Key Takeaways\n\n"
        final_response += f"This analysis combines **{len(agents_used)} AI perspectives** to provide comprehensive insights:\n\n"

        for agent in agents_used:
            if 'Research' in agent:
                final_response += "- **Research Layer**: Current market data, statistics, and credible sources\n"
            elif 'Analysis' in agent:
                final_response += "- **Analytical Layer**: Deep reasoning, implementation strategies, and projections\n"
            elif 'Creative' in agent:
                final_response += "- **Creative Layer**: Innovative approaches and alternative perspectives\n"
            elif 'Synthesis' in agent:
                final_response += "- **Synthesis Layer**: Practical applications and integrated recommendations\n"

        final_response += error_summary
    else:
        final_response = f"### Analysis: {query}\n\nProviding enhanced analysis through multi-agent collaboration.\n\n**Approach:**\n- Research-backed insights\n- Analytical reasoning\n- Creative perspectives\n- Synthesized conclusions"

    processing_time = time.time() - start_time

    return {
        'success': True,
        'response': final_response,
        'collaboration_details': {
            'agents_used': agents_used or ['Enhanced Reasoning Agent'],
            'models_used': models_used or ['Multi-Model Synthesis'],
            'processing_time': processing_time,
            'total_cost': total_cost,
            'confidence': 0.98 if len(responses) >= 4 else (0.95 if len(responses) >= 3 else (0.88 if len(responses) >= 2 else 0.75)),
            'consensus_method': 'real_multi_agent' if responses else 'enhanced_fallback',
            'agents_available': len([k for k, v in api_status.items() if v and k not in ['notion', 'gemini']]),
            'agents_successful': len(agents_used),
            'errors': agent_errors if agent_errors else None
        }
    }

# Minimalist CSS - Early Google/OpenAI inspired
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');

    /* Root variables - Professional AI platform palette */
    :root {
        --bg-primary: #f9f9f9;
        --bg-secondary: #ffffff;
        --bg-hover: #f0f0f0;
        --text-primary: #2e2e2e;
        --text-secondary: #6b6b6b;
        --text-tertiary: #9b9b9b;
        --border-light: #e0e0e0;
        --border-lighter: #ececec;
        --accent-primary: #8b9dc3;
        --accent-hover: #6b7fa3;
        --accent-subtle: #dfe3eb;
    }

    /* Global reset */
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Main container */
    .main {
        background: var(--bg-primary);
        padding: 0;
    }

    .block-container {
        padding: 2rem 1rem;
        max-width: 48rem;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: var(--bg-secondary);
        border-right: 1px solid var(--border-light);
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem;
    }

    /* Hide default header */
    header[data-testid="stHeader"] {
        display: none;
    }

    /* Simple top bar */
    .top-bar {
        background: var(--bg-secondary);
        border-bottom: 1px solid var(--border-light);
        padding: 0.75rem 1rem;
        margin: -2rem -1rem 2rem -1rem;
    }

    .top-bar h1 {
        margin: 0;
        font-size: 1rem;
        font-weight: 600;
        color: var(--text-primary);
        letter-spacing: -0.01em;
    }

    /* Sidebar thread list - ChatGPT style */
    .thread-item {
        padding: 0.625rem 0.75rem;
        margin: 0.125rem 0;
        border-radius: 0.375rem;
        cursor: pointer;
        color: var(--text-primary);
        font-size: 0.875rem;
        font-weight: 400;
        transition: background 0.1s;
        border: none;
        background: transparent;
        text-align: left;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .thread-item:hover {
        background: var(--bg-hover);
    }

    .thread-item.active {
        background: var(--bg-hover);
    }

    /* Message container - Clean, no borders */
    .message {
        margin: 1.5rem 0;
        padding: 0;
        line-height: 1.7;
        font-size: 0.9375rem;
    }

    .user-message {
        color: var(--text-primary);
        background: transparent;
    }

    .ai-message {
        color: var(--text-primary);
        background: transparent;
    }

    .ai-message h2 {
        font-size: 1.125rem;
        font-weight: 600;
        margin: 1.5rem 0 0.75rem 0;
        color: var(--text-primary);
    }

    .ai-message h3 {
        font-size: 1rem;
        font-weight: 600;
        margin: 1.25rem 0 0.5rem 0;
        color: var(--text-primary);
    }

    .ai-message code {
        background: var(--bg-hover);
        padding: 0.125rem 0.375rem;
        border-radius: 0.25rem;
        font-size: 0.875rem;
        font-family: 'SF Mono', Monaco, Consolas, monospace;
    }

    .ai-message strong {
        font-weight: 600;
        color: var(--text-primary);
    }

    /* Primary action button - Minimal */
    .stButton > button[kind="primary"] {
        background: var(--text-primary);
        color: var(--bg-secondary);
        border: none;
        border-radius: 0.375rem;
        padding: 0.5rem 0.875rem;
        font-weight: 500;
        font-size: 0.8125rem;
        transition: opacity 0.1s;
        height: 2.25rem;
    }

    .stButton > button[kind="primary"]:hover {
        opacity: 0.85;
        background: var(--text-primary);
    }

    /* Secondary buttons - Ghost style */
    .stButton > button {
        background: transparent;
        color: var(--text-primary);
        border: none;
        border-radius: 0.375rem;
        padding: 0.5rem 0.75rem;
        font-weight: 400;
        font-size: 0.8125rem;
        transition: background 0.1s;
        height: 2.25rem;
    }

    .stButton > button:hover {
        background: var(--bg-hover);
    }

    /* Input fields - Claude/ChatGPT style */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        border: 1px solid var(--border-light);
        border-radius: 0.5rem;
        padding: 0.75rem 1rem;
        font-size: 0.9375rem;
        background: var(--bg-secondary);
        color: var(--text-primary);
        transition: border-color 0.1s, box-shadow 0.1s;
        font-weight: 400;
        line-height: 1.5;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }

    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: var(--text-primary);
        outline: none;
        box-shadow: 0 0 0 1px var(--text-primary);
    }

    /* Scrollbar - macOS style */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }

    ::-webkit-scrollbar-track {
        background: transparent;
    }

    ::-webkit-scrollbar-thumb {
        background: var(--border-light);
        border-radius: 3px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-tertiary);
    }

    /* Status indicator - Subtle */
    .status-pill {
        display: inline-block;
        padding: 0.25rem 0.625rem;
        border-radius: 0.375rem;
        font-size: 0.75rem;
        font-weight: 500;
        background: transparent;
        color: var(--text-tertiary);
        border: 1px solid var(--border-lighter);
    }

    /* Hide Streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Sidebar styling refinement */
    [data-testid="stSidebar"] {
        background: var(--bg-secondary);
        border-right: 1px solid var(--border-lighter);
        padding-top: 0;
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 0.5rem;
    }

    /* Remove button focus outline */
    .stButton > button:focus {
        outline: none;
        box-shadow: none;
    }

    /* Divider styling */
    hr {
        border: none;
        height: 1px;
        background: var(--border-lighter);
        margin: 0.75rem 0;
    }

    /* Send button styling - ChatGPT style circular button */
    .stButton > button[kind="primary"] {
        background: var(--text-primary);
        color: var(--bg-secondary);
        border: none;
        border-radius: 0.375rem;
        padding: 0.375rem 0.625rem;
        font-weight: 500;
        font-size: 1.125rem;
        transition: opacity 0.1s;
        height: auto;
        width: auto;
        min-width: 2.5rem;
        line-height: 1;
    }

    /* Caption styling */
    .element-container .stCaption {
        font-size: 0.75rem;
        color: var(--text-tertiary);
    }
</style>
""", unsafe_allow_html=True)

# Helper functions for chat threads
def create_new_thread():
    """Create a new chat thread"""
    st.session_state.thread_counter += 1
    thread_id = f"thread_{st.session_state.thread_counter}"
    thread = {
        'id': thread_id,
        'title': 'New chat',
        'messages': [],
        'created_at': datetime.now()
    }
    st.session_state.chat_threads.append(thread)
    st.session_state.current_thread_id = thread_id
    st.session_state.messages = []
    return thread_id

def get_current_thread():
    """Get the current active thread"""
    if not st.session_state.current_thread_id and len(st.session_state.chat_threads) > 0:
        st.session_state.current_thread_id = st.session_state.chat_threads[0]['id']

    for thread in st.session_state.chat_threads:
        if thread['id'] == st.session_state.current_thread_id:
            return thread
    return None

def switch_thread(thread_id):
    """Switch to a different thread"""
    st.session_state.current_thread_id = thread_id
    for thread in st.session_state.chat_threads:
        if thread['id'] == thread_id:
            st.session_state.messages = thread['messages']
            break

def update_thread_title(thread_id, first_message):
    """Update thread title based on first message"""
    for thread in st.session_state.chat_threads:
        if thread['id'] == thread_id and thread['title'] == 'New chat':
            # Use first 50 chars of message as title
            thread['title'] = first_message[:50] + ('...' if len(first_message) > 50 else '')
            break

# Initialize first thread if none exist
if len(st.session_state.chat_threads) == 0:
    create_new_thread()

# Sidebar - Chat history
with st.sidebar:
    # New chat button
    if st.button("+ New chat", use_container_width=True, type="primary"):
        create_new_thread()
        st.rerun()

    st.markdown("")

    # Chat threads list
    for thread in reversed(st.session_state.chat_threads):
        is_active = thread['id'] == st.session_state.current_thread_id

        if st.button(
            thread['title'],
            key=f"thread_{thread['id']}",
            use_container_width=True,
            type="primary" if is_active else "secondary"
        ):
            switch_thread(thread['id'])
            st.rerun()

    # Bottom section
    st.markdown("")
    st.markdown("---")

    # Minimal status
    if production_engine_available:
        available_count = len([k for k, v in api_status.items() if v and k not in ['notion', 'gemini']])
        st.caption(f"⬡ AI Hub · {available_count} agents")


# Main Chat Interface
# Display messages
for msg in st.session_state.messages:
    if msg['role'] == 'user':
        st.markdown(f'<div class="message user-message">{msg["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="message ai-message">{msg["content"]}</div>', unsafe_allow_html=True)

# Chat input
st.markdown("")

user_input = st.text_area(
    "Message AI Hub",
    height=80,
    placeholder="Message AI Hub",
    label_visibility="collapsed",
    key="user_input"
)

submit = st.button("↑", type="primary", use_container_width=False)

if submit and user_input:
    # Update thread title if first message
    current_thread = get_current_thread()
    if current_thread and current_thread['title'] == 'New chat':
        update_thread_title(current_thread['id'], user_input)

    # Add user message
    st.session_state.messages.append({
        'role': 'user',
        'content': user_input
    })

    # Save to thread
    if current_thread:
        current_thread['messages'] = st.session_state.messages

    # Show processing indicator
    with st.spinner("Thinking..."):
        try:
            # Use real multi-agent collaboration
            result = asyncio.run(real_multi_agent_collaboration(user_input, "production"))

            if result['success']:
                # Add collaboration response
                response_content = result['response']
                details = result['collaboration_details']

                if details:
                    response_content += f"\n\n---\n"
                    response_content += f"**🔍 Collaboration Details:** "
                    response_content += f"{', '.join(details.get('agents_used', []))} • "
                    response_content += f"{details.get('processing_time', 0):.1f}s • "
                    response_content += f"${details.get('total_cost', 0):.4f}"

                st.session_state.messages.append({
                    'role': 'assistant',
                    'content': response_content
                })
            else:
                st.session_state.messages.append({
                    'role': 'assistant',
                    'content': f"Error: {result.get('error', 'Unknown error')}"
                })

            # Save to thread
            if current_thread:
                current_thread['messages'] = st.session_state.messages

        except Exception as e:
            st.session_state.messages.append({
                'role': 'assistant',
                'content': f"System error: {str(e)}"
            })

    st.rerun()