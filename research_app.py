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
    {"id": 1, "text": "Collect a Recent Paper (2024년 최신 논문 1편 수집)", "type": "year", "target": 2024, "count": 1, "reward": 150},
    {"id": 2, "text": "Collect papers with 5+ authors (5인 이상 협업 연구 수집)", "type": "team", "target": 5, "count": 1, "reward": 100},
    {"id": 3, "text": "Avoid Trap Papers (함정 논문 피하기 - 검증 실패 0회)", "type": "avoid_trap", "target": "trap", "count": 0, "reward": 0},
    {"id": 4, "text": "Reach 1500 Research Points (연구 점수 1500점 달성)", "type": "score", "target": 1500, "count": 1500, "reward": 500},
]

DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

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

def evaluate_paper(paper_data):
    current_year = get_current_year()
    year = paper_data.get('year', current_year - 5)
    age = current_year - year
    title_lower = paper_data['title'].lower()
    citation_count = paper_data.get('citations', 0)
    
    # 1. Keywords (Evidence)
    evidence_keywords = [
        'in vivo', 'in vitro', 'randomized', 'efficacy', 'mechanism', 'signaling', 
        'experiment', 'analysis', 'clinical', 'activity', 'synthesis', 'design', 
        'evaluation', 'characterization', 'properties', 'performance', 'application'
    ]
    has_evidence = any(k in title_lower for k in evidence_keywords)
    
    # [Removed] Prestige Index Logic (임팩트 팩터/저널 권위 평가 삭제)

    # 2. Team Size (연구 규모)
    author_count = paper_data.get('author_count', 1)
    is_big_team = author_count >= 5

    # 3. Reliability (데이터 신뢰도)
    ref_count = paper_data.get('ref_count') 
    integrity_status = "valid"
    risk_reason = ""

    # [Modified] 저널 권위가 아닌 인용 수로만 예외 처리 (인용 10회 미만이면 의심)
    if ref_count is None:
        if citation_count < 10: 
            integrity_status = "uncertain"
            risk_reason = "Missing Metadata (메타데이터 누락)"
    elif ref_count < 5:
        if citation_count < 10:
            integrity_status = "suspected"
            risk_reason = "Insufficient References (참고문헌 부족)"

    # Score Calculation
    score_breakdown = {
        "Base": 40,
        "Evidence": 0,
        # "Prestige": 0,  <- Deleted
        "Team": 0,
        "Volume Penalty": 0,
        "Integrity Penalty": 0
    }

    # 1. Raw Score (인기도 중심)
    # Prestige 점수 제거로 인한 기본 점수 조정 없음 (순수 인용 기반)
    raw_score = min(99, int(10 + (math.log(citation_count + 1) * 15)))

    # 2. Debiased Score (내실 중심)
    debiased_base = 40
    if has_evidence: 
        debiased_base += 30 
        score_breakdown["Evidence"] = 30
    if is_big_team: 
        debiased_base += 10
        score_breakdown["Team"] = 10
    
    # [Removed] Prestige Score Addition

    volume_discount = min(25, int(math.log(citation_count + 1) * 4))
    if age <= 2: volume_discount = int(volume_discount * 0.1)
    elif age <= 5: volume_discount = int(volume_discount * 0.5)

    score_breakdown["Volume Penalty"] = -volume_discount
    debiased_score = debiased_base - volume_discount
    
    if integrity_status != "valid":
        penalty = debiased_score - 10
        debiased_score = 10
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
    if debiased_score > 60 and bias_penalty < 0: # 기준 조정 (Prestige 점수가 빠졌으므로 70->60)
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
if 'analysis_weights' not in st.session_state: st.session_state['analysis_weights'] = {"evidence": 1.0, "recency": 1.0, "team": 1.0, "scarcity": 1.0}
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
    
    if m_type == "year" and action == "collect" and paper['year'] == 2024:
        completed = True
    elif m_type == "team" and action == "collect" and paper['is_big_team']:
        completed = True
    elif m_type == "score" and st.session_state.score >= current_m['target']:
        completed = True
    
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
    st.title("🎓 Research Simulator (연구 시뮬레이터)")
    st.caption("Outlier Hunter Edition")
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
    
    st.markdown("#### 🔍 Evaluation Metrics (평가 지표 가이드)")
    st.markdown("""
    **1. Raw Score (인기도)**
    : Conventional search score based on citations. (기존 검색 엔진 점수. 인용수에 비례.)
    
    **2. Debiased Score (내실)**
    : Value without volume bias. Focuses on evidence/scarcity. (문헌량 거품을 뺀 진짜 가치. 증거와 희소성 중심.)
    
    **3. Bias Penalty (편향)**
    : Difference between Raw & Debiased. (인기도와 내실의 차이. 양수면 과열, 음수면 저평가.)
    """)
    st.markdown("#### 🔍 Raw Score Indicators (Raw score 지표)")
    st.markdown("""
    1. **Evidence Index (증거 적합성 지표)**
       : Title contains experimental keywords (in vivo, clinical, etc.). (제목에 실험적 검증을 암시하는 구체적인 단어 포함)
    2. **Collaboration Index (연구 규모 지표)**
       : Large team (5+ authors). (참여 저자 수 다수(5인 이상)가 참여한 연구 우대)
    3. **Reliability Index (데이터 신뢰도 지표)**
       : Filters out low ref count papers. (참고 문헌 수를 확인하여 연구의 깊이를 1차적으로 거릅니다.)
    4. **Opportunity Index (시의성 대비 인용 지표)**
       : Identifies hidden gems by analyzing recency vs citations. (발행 시점과 인용 수의 상관관계를 분석하여 숨겨진 가치를 찾습니다.)
    """)
    st.markdown("#### 📊 Search Method (검색 방법)")
    st.markdown("""
    1. **General Search (일반 검색)**
       : Recommended by AI Recommendation Score. (AI 추천 지수가 높은 순으로 추천)
    2. **"Keyword" ("키워드")**
       : Exact match sort using quotes. (따옴표 검색을 통해 정확도 순으로 검색)
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
                    if paper['has_evidence']: tags.append("🔬 Evidence")
                    if paper['is_big_team']: tags.append("👥 Big Team")
                    if paper['integrity_status'] != "valid": tags.append("⚠️ Low Data (데이터 부족)")
                    if paper['potential_type'] == "amazing": tags.append("💎 Hidden Gem")
                    st.write(" ".join([f"`{t}`" for t in tags]))
                    auth_display = ", ".join(paper['authors'])
                    if paper['author_full_count'] > 3: auth_display += f" et al. (+{paper['author_full_count'] - 3})"
                    st.caption(f"{paper['year']} | {paper['journal']} | Citations: {paper['citations']} (인용 {paper['citations']}회) | Authors: {auth_display}")
                    
                    links_col1, links_col2 = st.columns(2)
                    with links_col1:
                        st.markdown(f"[📄 View Original (원문 보기)]({paper['url']})")

                with c2:
                    col_raw, col_deb = st.columns(2)
                    with col_raw: st.metric("Raw Score", f"{paper['raw_score']}", help="Popularity Score (검색 엔진이 선호하는 인기도 점수)")
                    with col_deb: st.metric("Debiased", f"{paper['debiased_score']}", delta=f"{-paper['bias_penalty']}", help="Intirnsic Value (문헌량 거품을 뺀 진짜 내실 점수)")
                    if paper['bias_penalty'] > 20: st.caption("⚠ High exposure (거품 주의)")
                    
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
