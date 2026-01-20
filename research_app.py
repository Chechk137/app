import streamlit as st
import requests
import datetime
import random
import time
import json
import os
import math
from collections import Counter

# --- 1. Settings & Constants (설정 및 상수) ---

MISSIONS = [
    {"id": 1, "text": "Collect 1 paper from Top Tier Journals (Top Tier 저널 논문 1편 수집)", "type": "journal", "target": "top_tier", "count": 1, "reward": 150},
    {"id": 2, "text": "Collect papers with 5+ authors (5인 이상 협업 연구 수집)", "type": "team", "target": 5, "count": 1, "reward": 100},
    {"id": 3, "text": "Avoid Trap Papers (함정 논문 피하기 - 검증 실패 0회)", "type": "avoid_trap", "target": "trap", "count": 0, "reward": 0},
    {"id": 4, "text": "Reach 1500 Research Points (연구 점수 1500점 달성)", "type": "score", "target": 1500, "count": 1500, "reward": 500},
]

DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# JCR Data for Prestige Check
JCR_IMPACT_FACTORS = {
    # Top Tier & General
    "nature": {2023: 50.5, 2022: 64.8},
    "science": {2023: 44.7, 2022: 56.9},
    "cell": {2023: 45.5, 2022: 64.5},
    "pnas": {2023: 9.6, 2022: 11.1},
    "nature communications": {2023: 14.7, 2022: 16.6},
    "scientific reports": {2023: 3.8, 2022: 4.6},
    "plos one": {2023: 2.9, 2022: 3.7},
    
    # Medicine
    "lancet": {2023: 98.4, 2022: 168.9},
    "new england journal of medicine": {2023: 96.2, 2022: 158.5},
    "nejm": {2023: 96.2, 2022: 158.5}, # Abbreviation
    "jama": {2023: 63.1, 2022: 120.7},
    "bmj": {2023: 93.6},
    "nature medicine": {2023: 58.7, 2022: 82.9},
    "cancer discovery": {2023: 29.7, 2022: 38.3},
    "clinical cancer research": {2023: 11.5},
    
    # Material / Chem / Eng
    "advanced materials": {2023: 27.4, 2022: 29.4},
    "chem": {2023: 19.1, 2022: 24.3},
    "angewandte": {2023: 16.1},
    "jacs": {2023: 14.4},
    "journal of the american chemical society": {2023: 14.4},
    "ieee": {2023: 10.0} # Generic estimate
}

# --- 2. Data Management (데이터 관리) ---

def load_user_data(user_id):
    file_path = os.path.join(DATA_DIR, f"{user_id}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "score": data.get("score", 0),
                    "inventory": data.get("inventory", []),
                    "mission_id": data.get("mission_id", 1),
                    "trash": data.get("trash", [])
                }
        except Exception as e:
            st.error(f"Error loading data (데이터 로드 오류): {e}")
    return {"score": 0, "inventory": [], "mission_id": 1, "trash": []}

def save_user_data(user_id):
    file_path = os.path.join(DATA_DIR, f"{user_id}.json")
    data = {
        "score": st.session_state.score,
        "inventory": st.session_state.inventory,
        "mission_id": st.session_state.mission_id,
        "trash": st.session_state.trash
    }
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Error saving data (데이터 저장 오류): {e}")

# --- 3. Core Logic (핵심 로직) ---

def get_current_year():
    return datetime.datetime.now().year

def get_pubmed_count(query):
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "rettype": "count"
        }
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        count = int(data["esearchresult"]["count"])
        return count
    except Exception:
        return None

def get_impact_factor(journal_name, year):
    if not journal_name: return None
    j_lower = journal_name.lower().strip()
    sorted_keys = sorted(JCR_IMPACT_FACTORS.keys(), key=len, reverse=True)
    
    for key in sorted_keys:
        if key in j_lower:
            if year in JCR_IMPACT_FACTORS[key]:
                return JCR_IMPACT_FACTORS[key][year]
            return max(JCR_IMPACT_FACTORS[key].values())
    return None

def evaluate_paper(paper_data):
    current_year = get_current_year()
    year = paper_data.get('year', current_year - 5)
    age = current_year - year
    title_lower = paper_data['title'].lower()
    citation_count = paper_data.get('citations', 0)
    journal_name = paper_data.get('journal', "")
    
    evidence_keywords = [
        'in vivo', 'in vitro', 'randomized', 'efficacy', 'mechanism', 'signaling', 
        'experiment', 'analysis', 'clinical', 'activity', 'synthesis', 'design', 
        'evaluation', 'characterization', 'properties', 'performance', 'application'
    ]
    has_evidence = any(k in title_lower for k in evidence_keywords)
    
    impact_factor = get_impact_factor(journal_name, year)
    if impact_factor:
        is_top_tier = impact_factor > 10.0
    else:
        top_journals_fallback = ['nature', 'science', 'cell', 'new england journal of medicine', 'lancet', 'jama', 'pnas', 'ieee']
        j_lower = journal_name.lower()
        is_top_tier = any(tj in j_lower for tj in top_journals_fallback)
        impact_factor = 0

    author_count = paper_data.get('author_count', 1)
    is_big_team = author_count >= 5

    ref_count = paper_data.get('ref_count') 
    integrity_status = "valid"
    risk_reason = ""

    if ref_count is None:
        if citation_count < 5 and not is_top_tier:
            integrity_status = "uncertain"
            risk_reason = "Missing Metadata (메타데이터 누락)"
    elif ref_count < 5:
        if citation_count < 5 and not is_top_tier:
            integrity_status = "suspected"
            risk_reason = "Insufficient References (참고문헌 부족)"

    # Score Calculation
    score_breakdown = {
        "Base": 30,
        "Evidence": 0,
        "Prestige": 0,
        "Team": 0,
        "Volume Penalty": 0,
        "Integrity Penalty": 0
    }

    # 1. Raw Score
    raw_score = min(99, int(5 + (math.log(citation_count + 1) * 12)))
    if is_top_tier: raw_score = min(99, raw_score + 15)

    # 2. Debiased Score
    debiased_base = 30
    if has_evidence: 
        debiased_base += 25 
        score_breakdown["Evidence"] = 25
    if is_big_team: 
        debiased_base += 10
        score_breakdown["Team"] = 10
    
    if impact_factor:
        prestige_score = min(30, int(impact_factor * 0.8))
        debiased_base += prestige_score
        score_breakdown["Prestige"] = prestige_score
    elif is_top_tier:
        debiased_base += 15
        score_breakdown["Prestige"] = 15

    volume_discount = min(25, int(math.log(citation_count + 1) * 4))
    if age <= 2: volume_discount = int(volume_discount * 0.1)
    elif age <= 5: volume_discount = int(volume_discount * 0.5)

    score_breakdown["Volume Penalty"] = -volume_discount
    debiased_score = debiased_base - volume_discount
    
    if integrity_status != "valid":
        penalty = debiased_score - 5
        debiased_score = 5
        score_breakdown["Integrity Penalty"] = -penalty
        risk_reason = risk_reason or "Low Data Reliability (데이터 신뢰도 낮음)"
    elif age > 10 and citation_count < 5:
        penalty = debiased_score - 5
        debiased_score = 5
        score_breakdown["Integrity Penalty"] = -penalty
        risk_reason = "Obsolete Research (도태된 연구)"

    debiased_score = max(5, min(95, debiased_score))

    # 3. Bias Penalty & Type
    bias_penalty = raw_score - debiased_score
    
    potential_type = "normal"
    if debiased_score > 70 and bias_penalty < 0:
        potential_type = "amazing" 
    elif bias_penalty > 30:
        potential_type = "bubble" 
    elif integrity_status != "valid":
        potential_type = "bad"

    ai_score = debiased_score

    return {
        "raw_score": raw_score,
        "debiased_score": debiased_score,
        "bias_penalty": bias_penalty,
        "ai_score": ai_score,
        "potential_type": potential_type,
        "risk_reason": risk_reason,
        "has_evidence": has_evidence,
        "is_top_tier": is_top_tier,
        "impact_factor": impact_factor,
        "is_big_team": is_big_team,
        "integrity_status": integrity_status,
        "score_breakdown": score_breakdown,
        "age": age,
        "citation_count": citation_count
    }

def search_crossref_api(query):
    is_exact_mode = query.startswith('"') and query.endswith('"')
    clean_query = query.strip('"') if is_exact_mode else query
    
    try:
        url = f"https://api.crossref.org/works?query={clean_query}&rows=1000&sort=relevance"
        response = requests.get(url, timeout=20)
        data = response.json()
    except Exception as e:
        st.error(f"API Connection Error (API 연결 오류): {e}")
        return [], {}, False

    if not data or not isinstance(data, dict): return [], {}, False
    message = data.get('message')
    if not message or not isinstance(message, dict): return [], {}, False
    items = message.get('items')
    if not items: return [], {}, False

    valid_papers = []
    current_year = get_current_year()

    pubmed_count = get_pubmed_count(clean_query)
    
    citations_list = []
    years_list = []

    for idx, item in enumerate(items):
        if not item.get('DOI'): continue
        if not item.get('title'): continue
        
        title_str = item['title'][0].lower()
        invalid_titles = ["announcement", "editorial", "issue info", "table of contents", "front matter", "back matter", "author index", "subject index", "correction", "erratum", "publisher's note", "conference info", "trial number", "trial registration", "clinicaltrials.gov", "identifier", "&na;", "unknown", "calendar", "masthead", "abstracts", "session", "meeting", "symposium", "workshop", "chinese journal", "test", "protocol", "data descriptor", "dataset"]
        if any(inv in title_str for inv in invalid_titles): continue
        
        cit = item.get('is-referenced-by-count', 0)
        citations_list.append(cit)
        
        y = None
        if item.get('published') and item['published'].get('date-parts'): y = item['published']['date-parts'][0][0]
        elif item.get('created') and item['created'].get('date-parts'): y = item['created']['date-parts'][0][0]
        if y: years_list.append(y)

        if not item.get('author'): continue
        authors_raw = item['author']
        valid_authors = []
        for a in authors_raw:
            given = a.get('given', '').strip()
            family = a.get('family', '').strip()
            full = f"{given} {family}".strip()
            if full and "&na;" not in full.lower() and "anonymous" not in full.lower():
                valid_authors.append(full)
        if not valid_authors: continue

        journal = item.get('container-title', ["Unknown Journal"])[0]
        ref_count = item.get('reference-count')
        pub_year = y if y else current_year - 5
        
        paper_data_for_eval = {
            'title': item['title'][0], 'year': pub_year, 'citations': cit, 
            'journal': journal, 'author_count': len(valid_authors), 'ref_count': ref_count
        }
        eval_result = evaluate_paper(paper_data_for_eval)

        paper_obj = {
            'id': item['DOI'],
            'title': item['title'][0],
            'authors': valid_authors[:3], 
            'author_full_count': len(valid_authors),
            'journal': journal,
            'year': pub_year,
            'citations': cit,
            'ref_count': ref_count if ref_count is not None else 0,
            'url': f"https://doi.org/{item['DOI']}",
            **eval_result,
            'is_reviewed': False,
            'original_rank': idx
        }
        valid_papers.append(paper_obj)
    
    avg_citations = int(sum(citations_list) / len(citations_list)) if citations_list else 0
    if years_list:
        year_counts = Counter(years_list)
        most_common_year = year_counts.most_common(1)[0][0]
        min_y, max_y = min(years_list), max(years_list)
        if max_y - min_y > 10: period_str = f"{most_common_year-2}~{most_common_year+2}"
        else: period_str = f"{min_y}~{max_y}"
    else:
        period_str = "Unknown"

    bias_summary = {
        "pubmed_count": pubmed_count if pubmed_count is not None else "N/A (집계 불가)",
        "avg_citations": avg_citations,
        "period": period_str,
        "is_high_exposure": (pubmed_count > 5000 if pubmed_count else False) or avg_citations > 100
    }

    if not is_exact_mode:
        valid_papers.sort(key=lambda x: x['debiased_score'], reverse=True)
            
    return valid_papers, bias_summary, is_exact_mode

# --- 3. Streamlit UI ---

st.set_page_config(page_title="Research Simulator (연구 시뮬레이터)", page_icon="🎓", layout="wide")

if 'user_id' not in st.session_state: st.session_state['user_id'] = None
if 'score' not in st.session_state: st.session_state['score'] = 0
if 'inventory' not in st.session_state: st.session_state['inventory'] = []
if 'trash' not in st.session_state: st.session_state['trash'] = []
if 'mission_id' not in st.session_state: st.session_state['mission_id'] = 1
if 'search_results' not in st.session_state: st.session_state['search_results'] = []
if 'bias_summary' not in st.session_state: st.session_state['bias_summary'] = {}
if 'search_page' not in st.session_state: st.session_state['search_page'] = 1
if 'is_exact_search' not in st.session_state: st.session_state['is_exact_search'] = False
if 'sort_option' not in st.session_state: st.session_state['sort_option'] = "내실 (Debiased)"
if 'analysis_weights' not in st.session_state: st.session_state['analysis_weights'] = {"evidence": 1.0, "prestige": 1.0, "recency": 1.0, "team": 1.0, "scarcity": 1.0}
if 'current_preset' not in st.session_state: st.session_state['current_preset'] = "⚖️ 밸런스"

def get_level_info(score):
    level_threshold = 500
    level = (score // level_threshold) + 1
    progress = (score % level_threshold) / level_threshold
    next_milestone = (level) * level_threshold
    return level, progress, next_milestone

def check_mission(paper, action):
    current_m = next((m for m in MISSIONS if m['id'] == st.session_state.mission_id), None)
    if not current_m: return
    completed = False
    m_type = current_m['type']
    if m_type == "journal" and action == "collect" and paper['is_top_tier']: completed = True
    elif m_type == "team" and action == "collect" and paper['is_big_team']: completed = True
    elif m_type == "score" and st.session_state.score >= current_m['target']: completed = True
    if completed:
        st.session_state.score += current_m['reward']
        st.session_state.mission_id += 1
        st.toast(f"🎉 Mission Complete! Reward +{current_m['reward']}pts (미션 완료! 보상 +{current_m['reward']}점)", icon="🎁")
        if st.session_state.get("user_id"): save_user_data(st.session_state.user_id)

# Login Screen
if not st.session_state.get("user_id"):
    st.title("🎓 AI-Based Research Simulator (AI 기반 논문 추천 시스템)")
    st.caption("Capstone Design _ AI:D (캡스톤 디자인 _ AI:D)")
    st.markdown("---")
    st.markdown("### 👋 Welcome! (환영합니다!)")
    st.info("Enter your Researcher ID to start. (연구자 ID를 입력하여 검색을 시작하세요.)")
    col1, col2 = st.columns([3, 1])
    with col1: user_input = st.text_input("Researcher ID (연구자 이름)", placeholder="e.g., Dr.Kim")
    with col2:
        st.write(""); st.write("")
        if st.button("Login / Start (로그인 / 시작)", type="primary", use_container_width=True):
            if user_input:
                st.session_state.user_id = user_input
                saved_data = load_user_data(user_input)
                st.session_state.score = saved_data["score"]
                st.session_state.inventory = saved_data["inventory"]
                st.session_state.mission_id = saved_data["mission_id"]
                st.session_state.trash = saved_data["trash"]
                st.rerun()
            else: st.warning("Please enter your name. (이름을 입력해주세요.)")
    st.stop() 

# Sidebar
with st.sidebar:
    st.title("🎓 AI 기반 논문 추천 시스템")
    st.caption("캡스톤 디자인 _ AI:D")
    st.info(f"👤 Researcher **{st.session_state.user_id}** (연구원)")
    if st.button("Logout (Saved) (로그아웃 - 저장됨)", use_container_width=True):
        save_user_data(st.session_state.user_id)
        st.session_state.user_id = None
        st.rerun()
    st.divider()
    current_level, progress, next_score = get_level_info(st.session_state.score)
    st.metric("Research Level (연구 레벨)", f"Lv. {current_level}")
    st.write(f"Current Score (현재 점수): {st.session_state.score} / {next_score}")
    st.progress(progress)
    st.metric("Collected Papers (보유 논문)", f"{len(st.session_state.inventory)}")
    st.divider()
    
    st.markdown("#### 🔍 평가 지표 가이드")
    st.markdown("""
    **1. Raw Score (인기도)**
    : 기존 검색 엔진 점수. 인용수와 저널 인지도에 비례.
    
    **2. Debiased Score (내실)**
    : 문헌량 거품을 뺀 진짜 가치. 증거와 희소성 중심.
    
    **3. Bias Penalty (편향)**
    : 인기도와 내실의 차이. 양수면 과열(Bubble), 음수면 저평가(Hidden Gem).
    """)
    st.markdown("#### 🔍 Raw Score Indicators (Raw score 지표)")
    st.markdown("""
    1. **Evidence Index (증거 적합성 지표)**
       : 제목에 실험적 검증(in vivo, clinical 등)을 암시하는 구체적인 단어 포함
    2. **Prestige Index (저널 권위 지표)**
       : Nature, Science 등 학계에서 인정받는 최상위 저널
    3. **Collaboration Index (연구 규모 지표)**
       : 참여 저자 수 다수(5인 이상)가 참여한 연구 우대
    4. **Reliability Index (데이터 신뢰도 지표)**
       : 참고 문헌 수를 확인하여 연구의 깊이를 1차적으로 거릅니다. 참고 문헌이 너무 적으면 정식 논문이 아닌 초록이나 단순 투고일 가능성이 높아 배제합니다.
    5. **Opportunity Index (시의성 대비 인용 지표)**
       : 발행 시점과 인용 수의 상관관계를 분석하여 숨겨진 가치를 찾습니다. 최신이면서 인용이 적은 연구는 기회(Opportunity)로, 오래되었는데 인용이 없는 연구는 함정(Trap)으로 분류합니다.
    """)
    st.markdown("#### 📊 Search Method (검색 방법)")
    st.markdown("""
    1. **General Search (일반 검색)**
       : AI 추천 지수가 높은 순으로 추천
    2. **"Keyword" ("키워드")**
       : 따옴표 검색을 통해 정확도 순으로 검색
    """)

tab_search, tab_analysis, tab_inventory, tab_trash = st.tabs(["🔍 Search (논문 검색)", "📊 Analysis (지표 분석)", "📚 Library (내 서재)", "🗑️ Trash (휴지통)"])

with tab_search:
    col1, col2 = st.columns([4, 1])
    with col1: query = st.text_input("Enter Keywords (키워드 입력)", placeholder='e.g., "Immunotherapy" (Quotes for Exact Match)')
    with col2:
        st.write(""); st.write("")
        search_btn = st.button("Search (검색)", type="primary", use_container_width=True)

    if search_btn and query:
        with st.spinner("Analyzing Literature Volume Bias... (문헌량 편향 분석 및 데이터 처리 중...)"):
            results, summary, is_exact = search_crossref_api(query)
            st.session_state.search_results = results
            st.session_state.bias_summary = summary
            st.session_state.is_exact_search = is_exact
            st.session_state.search_page = 1 
            st.session_state.sort_option = "Relevance (정확도)" if is_exact else "Debiased (내실)"
            if not results: st.error("No results found. (검색 결과가 없습니다.)")

    if st.session_state.search_results:
        summary = st.session_state.bias_summary
        with st.container(border=True):
            st.markdown("### 🔍 Search Bias Summary (편향 요약)")
            bc1, bc2, bc3 = st.columns(3)
            pub_cnt = summary['pubmed_count']
            pub_cnt_str = f"{pub_cnt:,}" if isinstance(pub_cnt, int) else str(pub_cnt)
            with bc1: st.metric("PubMed Count (Actual) (PubMed 논문 수 - 실제)", pub_cnt_str)
            with bc2: st.metric("Avg Citations (Top 200) (평균 인용수)", f"{summary['avg_citations']:,}")
            with bc3: st.metric("Peak Period (연구 집중 시기)", summary['period'])
            if summary['is_high_exposure']:
                st.warning("⚠ **High Exposure Topic**: This topic is highly active. Top results might be biased. (이 주제는 연구가 매우 활발하여, 상위 노출 논문이 과대평가(Bias)되었을 가능성이 큽니다.)")
            else:
                st.success("✅ **Niche Topic**: Less researched area. Potential hidden gems. (비교적 연구가 덜 된 분야입니다. 숨겨진 명작이 많을 수 있습니다.)")
        st.divider()

        st.markdown("##### 🔃 Sort By (정렬 기준 선택)")
        sort_col, _ = st.columns([2, 1])
        with sort_col:
            sort_opt = st.radio(
                "Sort Criteria (정렬 기준)", 
                ["Debiased (내실)", "Raw (인기)", "Recency (최신)", "Relevance (정확도)"], 
                horizontal=True, 
                label_visibility="collapsed", 
                key="sort_selector"
            )
        
        if sort_opt == "Debiased (내실)":
            st.session_state.search_results.sort(key=lambda x: x['debiased_score'], reverse=True)
        elif sort_opt == "Raw (인기)":
            st.session_state.search_results.sort(key=lambda x: x['raw_score'], reverse=True)
        elif sort_opt == "Recency (최신)":
            st.session_state.search_results.sort(key=lambda x: x['year'], reverse=True)
        elif sort_opt == "Relevance (정확도)":
            st.session_state.search_results.sort(key=lambda x: x['original_rank'])

        items_per_page = 50
        total_items = len(st.session_state.search_results)
        total_pages = max(1, math.ceil(total_items / items_per_page))
        current_page = st.session_state.search_page
        start_idx = (current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_items = st.session_state.search_results[start_idx:end_idx]

        st.caption(f"Total Results: {total_items} ({sort_opt}) | Page: {current_page}/{total_pages} (검색 결과 총 {total_items}건 | 페이지: {current_page}/{total_pages})")
        
        for i, paper in enumerate(page_items):
            unique_key_idx = start_idx + i
            with st.container(border=True):
                c1, c2 = st.columns([5, 2])
                with c1:
                    st.markdown(f"#### {paper['title']}")
                    tags = []
                    if paper['is_top_tier']: tags.append("👑 Top Tier")
                    if paper['has_evidence']: tags.append("🔬 Evidence")
                    if paper['is_big_team']: tags.append("👥 Big Team")
                    if paper['integrity_status'] != "valid": tags.append("⚠️ Low Data (데이터 부족)")
                    if paper['potential_type'] == "amazing": tags.append("💎 Hidden Gem")
                    st.write(" ".join([f"`{t}`" for t in tags]))
                    auth_display = ", ".join(paper['authors'])
                    if paper['author_full_count'] > 3: auth_display += f" et al. (+{paper['author_full_count'] - 3})"
                    st.caption(f"{paper['year']} | {paper['journal']} | Citations: {paper['citations']} (인용 {paper['citations']}회) | Authors: {auth_display}")
                    
                    google_search_url = f"https://www.google.com/search?q={paper['journal'].replace(' ', '+')}+impact+factor+{paper['year']}"
                    
                    links_col1, links_col2 = st.columns(2)
                    with links_col1:
                        st.markdown(f"[📄 View Original (원문 보기)]({paper['url']})")
                    with links_col2:
                         st.markdown(f"[📊 Check IF (IF 검색)]({google_search_url})")

                with c2:
                    col_raw, col_deb = st.columns(2)
                    with col_raw: st.metric("Raw Score", f"{paper['raw_score']}", help="Popularity Score (검색 엔진이 선호하는 인기도 점수)")
                    with col_deb: st.metric("Debiased", f"{paper['debiased_score']}", delta=f"{-paper['bias_penalty']}", help="Intirnsic Value (문헌량 거품을 뺀 진짜 내실 점수)")
                    if paper['bias_penalty'] > 20: st.caption("⚠ High exposure (거품 주의)")
                    
                    if paper['impact_factor']:
                        st.caption(f"🏆 IF: {paper['impact_factor']}")

                    is_owned = any(p['id'] == paper['id'] for p in st.session_state.inventory)
                    if is_owned:
                        st.button("Owned (보유중)", key=f"owned_{unique_key_idx}", disabled=True, use_container_width=True)
                    else:
                        if st.button("Collect (수집하기)", key=f"collect_{unique_key_idx}", type="secondary", use_container_width=True):
                            st.session_state.inventory.append(paper)
                            st.session_state.score += paper['debiased_score']
                            check_mission(paper, "collect")
                            save_user_data(st.session_state.user_id) 
                            st.rerun()
        
        st.divider()
        _, nav_col, _ = st.columns([1, 5, 1])
        with nav_col:
            if total_pages <= 5: display_pages = range(1, total_pages + 1)
            else:
                if current_page <= 3: display_pages = range(1, 6)
                elif current_page >= total_pages - 2: display_pages = range(total_pages - 4, total_pages + 1)
                else: display_pages = range(current_page - 2, current_page + 3)

            pg_cols = st.columns([1, 1, 1, 1, 1, 1, 1, 0.5, 2.5], gap="small")
            with pg_cols[0]:
                if st.button("◀", key="nav_prev", disabled=current_page==1, use_container_width=True):
                    st.session_state.search_page -= 1
                    st.rerun()
            
            for idx, p_num in enumerate(display_pages):
                if idx < 5:
                    with pg_cols[idx + 1]:
                        b_type = "primary" if p_num == current_page else "secondary"
                        if st.button(f"{p_num}", key=f"nav_p_{p_num}", type=b_type, use_container_width=True):
                            st.session_state.search_page = p_num
                            st.rerun()
            
            with pg_cols[6]:
                if st.button("▶", key="nav_next", disabled=current_page==total_pages, use_container_width=True):
                    st.session_state.search_page += 1
                    st.rerun()
            with pg_cols[8]:
                 new_page = st.number_input("Move (이동)", min_value=1, max_value=total_pages, value=current_page, label_visibility="collapsed", key="nav_input")
                 if new_page != current_page:
                    st.session_state.search_page = new_page
                    st.rerun()

# --- [New] Analysis Tab ---
with tab_analysis:
    if not st.session_state.search_results:
        st.info("Please search for papers first. (먼저 '논문 검색' 탭에서 검색을 수행해주세요.)")
    else:
        st.markdown("### 🛠️ Custom Metrics Analysis (맞춤형 지표 분석)")
        st.markdown("Adjust weights to re-evaluate papers based on your criteria. (각 지표의 가중치를 조절하여 나만의 기준(Custom Score)으로 논문을 재평가하고 정렬합니다.)")
        
        # [Fix] 세션 초기화 코드 (KeyError 방지)
        if 'analysis_weights' not in st.session_state:
            st.session_state.analysis_weights = {"evidence": 1.0, "prestige": 1.0, "recency": 1.0, "team": 1.0, "scarcity": 1.0}
            st.session_state.current_preset = "⚖️ Balance (밸런스)"
        
        # 안전 장치: 키가 하나라도 없으면 복구
        required_keys = ["evidence", "prestige", "recency", "team", "scarcity"]
        for k in required_keys:
            if k not in st.session_state.analysis_weights:
                st.session_state.analysis_weights[k] = 1.0

        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        
        with col_p1:
            if st.button("⚖️ 밸런스", use_container_width=True, help="모든 지표를 골고루 반영합니다."):
                st.session_state.analysis_weights = {"evidence": 1.0, "prestige": 1.0, "recency": 1.0, "team": 1.0, "scarcity": 1.0}
                st.session_state.current_preset = "⚖️ 밸런스"
                st.rerun()

        with col_p2:
            if st.button("💎 숨겨진 원석", use_container_width=True, help="인용은 적지만 증거가 확실한 논문을 찾습니다."):
                st.session_state.analysis_weights = {"evidence": 2.0, "prestige": 0.5, "recency": 1.0, "team": 1.0, "scarcity": 3.0}
                st.session_state.current_preset = "💎 숨겨진 원석"
                st.rerun()
                
        with col_p3:
            if st.button("🚀 최신 트렌드", use_container_width=True, help="최신성과 실험적 근거를 최우선으로 봅니다."):
                st.session_state.analysis_weights = {"evidence": 2.0, "prestige": 0.5, "recency": 3.0, "team": 0.5, "scarcity": 1.0}
                st.session_state.current_preset = "🚀 최신 트렌드"
                st.rerun()

        with col_p4:
            if st.button("👑 대규모", use_container_width=True, help="유명 저널과 대규모 연구팀을 선호합니다."):
                st.session_state.analysis_weights = {"evidence": 1.0, "prestige": 3.0, "recency": 0.5, "team": 2.0, "scarcity": 0.5}
                st.session_state.current_preset = "👑 대규모"
                st.rerun()

        st.info(f"Current Mode (현재 적용된 분석 모드): **{st.session_state.current_preset}**")

        w = st.session_state.analysis_weights
        
        with st.container(border=True):
            col_w1, col_w2, col_w3 = st.columns(3)
            with col_w1: w["evidence"] = st.slider("증거 (Evidence)", 0.0, 3.0, w["evidence"])
            with col_w2: w["prestige"] = st.slider("권위 (Prestige)", 0.0, 3.0, w["prestige"])
            with col_w3: w["recency"] = st.slider("최신성 (Recency)", 0.0, 3.0, w["recency"])
            col_w4, col_w5 = st.columns(2)
            with col_w4: w["team"] = st.slider("규모 (Team)", 0.0, 3.0, w["team"])
            with col_w5: w["scarcity"] = st.slider("희소성 (Scarcity)", 0.0, 3.0, w["scarcity"])

        w_evidence = w["evidence"]
        w_prestige = w["prestige"]
        w_recency = w["recency"]
        w_team = w["team"]
        w_scarcity = w["scarcity"]

        analyzed_papers = []
        for paper in st.session_state.search_results:
            details = paper.get('score_breakdown', {})
            base = details.get('Base', 40)
            ev_score = details.get('Evidence', 0)
            team_score = details.get('Team', 0)
            vol_penalty = details.get('Volume Penalty', 0)
            age_score = max(0, (5 - paper.get('age', 5)) * 10)
            scarcity_score = max(0, (50 - paper.get('citation_count', 0))) 
            if scarcity_score > 50: scarcity_score = 50
            
            custom_score = (
                base +
                (ev_score * w_evidence) +
                (20 * int(paper['is_top_tier']) * w_prestige) +
                (team_score * w_team) +
                (age_score * w_recency) +
                (scarcity_score * w_scarcity) +
                vol_penalty
            )
            paper_copy = paper.copy()
            paper_copy['custom_score'] = int(custom_score)
            analyzed_papers.append(paper_copy)
            
        analyzed_papers.sort(key=lambda x: x['custom_score'], reverse=True)
        st.divider()
        st.caption(f"Top 20 Re-evaluated Results (재평가된 상위 20개 결과)")
        for i, paper in enumerate(analyzed_papers[:20]):
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{i+1}. {paper['title']}**")
                    st.caption(f"{paper['year']} | {paper['journal']} | Custom Score: {paper['custom_score']}")
                    with st.expander("View Score Details (점수 상세 구성 보기)"):
                        details = paper.get('score_breakdown', {})
                        # [Modification] Chart Keys with English (Korean)
                        chart_data = {
                            "Base (기본)": details.get('Base', 40),
                            "Evidence (증거)": details.get('Evidence', 0) * w_evidence,
                            "Prestige (권위)": (20 if paper['is_top_tier'] else 0) * w_prestige,
                            "Team (규모)": details.get('Team', 0) * w_team,
                            "Recency (최신성)": max(0, (5 - paper.get('age', 5)) * 10) * w_recency,
                            "Scarcity (희소성)": max(0, (50 - paper.get('citation_count', 0))) * w_scarcity,
                        }
                        st.bar_chart(chart_data, horizontal=True)
                with c2:
                    st.metric("Custom", f"{paper['custom_score']}")
                    is_owned = any(p['id'] == paper['id'] for p in st.session_state.inventory)
                    if is_owned:
                        st.button("Owned (보유중)", key=f"an_owned_{i}", disabled=True, use_container_width=True)
                    else:
                        if st.button("Collect (수집)", key=f"an_collect_{i}", type="secondary", use_container_width=True):
                            st.session_state.inventory.append(paper)
                            st.session_state.score += paper['debiased_score']
                            check_mission(paper, "collect")
                            save_user_data(st.session_state.user_id)
                            st.rerun()

with tab_inventory:
    if not st.session_state.inventory: st.info("Library is empty. (수집된 논문이 없습니다.)")
    cols = st.columns(2)
    for i, paper in enumerate(st.session_state.inventory):
        with cols[i % 2]:
            with st.container(border=True):
                status_emoji = "❓"; status_text = "Unverified (미검증)"
                if paper['is_reviewed']:
                    if paper['potential_type'] == "amazing": status_emoji, status_text = "✨", "Jackpot (대성공)"
                    elif paper['potential_type'] == "bad": status_emoji, status_text = "💀", "Failed (실패)"
                    elif paper['potential_type'] == "verified_user": status_emoji, status_text = "🛡️", "User Verified (사용자 승인)"
                    else: status_emoji, status_text = "✅", "Verified (검증됨)"

                st.markdown(f"**{paper['title']}**")
                st.caption(f"{status_emoji} {status_text} | {paper['journal']}")
                
                c_btn1, c_btn2 = st.columns([2, 1])
                with c_btn1:
                    if not paper['is_reviewed']:
                        if paper['integrity_status'] == "valid":
                            if st.button("🔬 Deep Review (심층 검증)", key=f"rev_{i}", type="primary", use_container_width=True):
                                st.session_state.inventory[i]['is_reviewed'] = True
                                bonus = int(paper['debiased_score'] * 0.5)
                                st.session_state.score += bonus
                                st.session_state.inventory[i]['final_score'] = paper['debiased_score'] + bonus
                                if paper['potential_type'] == 'amazing': st.toast(f"Jackpot! Hidden Gem found! (+{bonus}) (대박! 숨겨진 명작을 찾았습니다!)", icon="🎉")
                                else: st.toast(f"Verification Complete (+{bonus}) (검증이 완료되었습니다.)", icon="✅")
                                save_user_data(st.session_state.user_id) 
                                st.rerun()
                        else:
                            st.warning(paper['risk_reason'])
                            if st.button("Force Approve (강제 승인)", key=f"force_{i}", use_container_width=True):
                                st.session_state.inventory[i]['is_reviewed'] = True
                                bonus = 10 
                                st.session_state.score += bonus
                                st.session_state.inventory[i]['final_score'] = paper['debiased_score'] + bonus
                                st.session_state.inventory[i]['potential_type'] = "verified_user"
                                st.session_state.inventory[i]['reason'] = "Verified by User (사용자 직접 확인으로 검증됨)"
                                save_user_data(st.session_state.user_id) 
                                st.rerun()
                    else:
                        st.success(f"Value: {paper.get('final_score', 0)} pts (획득 점수)")

                with c_btn2:
                    if st.button("Delete (삭제)", key=f"del_{i}", use_container_width=True):
                        deduction = paper.get('final_score', paper['debiased_score'])
                        st.session_state.score = max(0, st.session_state.score - deduction)
                        removed = st.session_state.inventory.pop(i)
                        st.session_state.trash.append(removed)
                        st.toast(f"Paper deleted. -{deduction} pts (논문 삭제. {deduction}점 차감됨)", icon="🗑️")
                        save_user_data(st.session_state.user_id) 
                        st.rerun()
                st.markdown(f"[📄 View Original (원문 보기)]({paper['url']})")

with tab_trash:
    if not st.session_state.trash: st.info("Trash is empty. (휴지통이 비어있습니다.)")
    if st.session_state.trash:
        if st.button("Empty Trash (휴지통 비우기)", type="primary"):
            st.session_state.trash = []
            save_user_data(st.session_state.user_id)
            st.toast("Trash emptied. (휴지통 비움)", icon="🧹")
            st.rerun()
    cols = st.columns(2)
    for i, paper in enumerate(st.session_state.trash):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"**{paper['title']}**")
                st.caption(f"Deleted (삭제됨) | {paper['journal']}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Restore (복구)", key=f"rest_{i}", use_container_width=True):
                        restored = st.session_state.trash.pop(i)
                        st.session_state.inventory.append(restored)
                        r_score = restored.get('final_score', restored['debiased_score'])
                        st.session_state.score += r_score
                        st.toast(f"Restored (+{r_score} pts) (복구 완료)", icon="♻️")
                        save_user_data(st.session_state.user_id)
                        st.rerun()
                with c2:
                    if st.button("Delete Forever (영구 삭제)", key=f"pdel_{i}", use_container_width=True):
                        st.session_state.trash.pop(i)
                        st.toast("Deleted Forever (영구 삭제됨)", icon="🔥")
                        save_user_data(st.session_state.user_id)
                        st.rerun()
