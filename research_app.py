import streamlit as st
import requests
import datetime
import random
import time
import json
import os
import math
from collections import Counter

# --- 1. 설정 및 상수 ---

MISSIONS = [
    {"id": 1, "text": "Top Tier 저널(Nature, Science 등) 논문 1편 수집", "type": "journal", "target": "top_tier", "count": 1, "reward": 150},
    {"id": 2, "text": "5인 이상 협업 연구(Team Science) 수집", "type": "team", "target": 5, "count": 1, "reward": 100},
    {"id": 3, "text": "함정 논문(참고문헌 부족 등) 피하기", "type": "avoid_trap", "target": "trap", "count": 0, "reward": 0},
    {"id": 4, "text": "연구 점수 1500점 달성하기", "type": "score", "target": 1500, "count": 1500, "reward": 500},
]

DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# [수정] 정확한 매칭을 위해 저널명을 구체적으로 명시
JCR_IMPACT_FACTORS = {
    "nature": {2023: 50.5, 2022: 64.8, 2021: 69.5},
    "science": {2023: 44.7, 2022: 56.9, 2021: 63.7},
    "cell": {2023: 45.5, 2022: 64.5, 2021: 66.8},
    "the lancet": {2023: 98.4, 2022: 168.9},
    "new england journal of medicine": {2023: 96.2, 2022: 158.5},
    "jama": {2023: 63.1, 2022: 120.7},
    "nature medicine": {2023: 58.7, 2022: 82.9},
    "cancer discovery": {2023: 29.7, 2022: 38.3},
    "advanced materials": {2023: 27.4, 2022: 29.4},
    "chem": {2023: 19.1, 2022: 24.3},
    "angewandte chemie international edition": {2023: 16.1},
    "journal of the american chemical society": {2023: 14.4},
    "proceedings of the national academy of sciences": {2023: 9.6},
    "ieee transactions on pattern analysis and machine intelligence": {2023: 23.6}
}

# --- 2. 데이터 관리 함수 (저장/로드) ---

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
            st.error(f"데이터 로드 중 오류 발생: {e}")
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
        st.error(f"데이터 저장 중 오류 발생: {e}")

# --- 3. 핵심 로직 함수 ---

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
    """
    [수정] 정확도 높은 매칭을 위해 로직 개선
    단순 포함이 아니라, 전체 이름이 일치하거나 확실한 경우에만 IF 반환
    """
    if not journal_name: return None
    
    j_lower = journal_name.lower().strip()
    
    # 1. 우선순위: 긴 이름부터 매칭 (Nature Medicine이 Nature보다 먼저 걸리게)
    sorted_keys = sorted(JCR_IMPACT_FACTORS.keys(), key=len, reverse=True)
    
    for key in sorted_keys:
        # 정확히 일치하거나, ': ' 등으로 부제가 붙은 경우만 인정
        # 예: "Nature" == "Nature" (O), "Nature Communications" != "Nature" (X)
        if j_lower == key or j_lower.startswith(f"{key}:") or j_lower == f"the {key}":
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
    
    # [수정] Top Tier 판단도 정확한 IF 함수에 의존
    impact_factor = get_impact_factor(journal_name, year)
    
    # IF가 10 이상이면 확실한 Top Tier, 아니면 키워드로 보완하되 엄격하게
    if impact_factor:
        is_top_tier = impact_factor > 15.0 # 기준 상향 (10 -> 15)
    else:
        # IF 데이터가 없을 때 보조 수단 (매우 유명한 것만)
        top_journals_fallback = ['nature', 'science', 'cell', 'new england journal of medicine', 'lancet', 'jama']
        j_lower = journal_name.lower()
        is_top_tier = any(tj == j_lower for tj in top_journals_fallback)
        impact_factor = 0

    author_count = paper_data.get('author_count', 1)
    is_big_team = author_count >= 5

    ref_count = paper_data.get('ref_count') 
    integrity_status = "valid" 
    risk_reason = ""

    if ref_count is None:
        if citation_count < 5 and not is_top_tier:
            integrity_status = "uncertain"
            risk_reason = "메타데이터 누락"
    elif ref_count < 5:
        if citation_count < 5 and not is_top_tier:
            integrity_status = "suspected"
            risk_reason = "참고문헌 데이터 부족"

    # --- 점수 산정 로직 (밸런스 조정) ---
    
    score_breakdown = {
        "Base": 30, # 기본 점수 하향 (40 -> 30)
        "Evidence": 0,
        "Prestige": 0,
        "Team": 0,
        "Volume Penalty": 0,
        "Integrity Penalty": 0
    }

    # 1. Raw Score (인기도)
    # 로그 스케일 적용은 유지하되 계수 조정
    raw_score = min(99, int(5 + (math.log(citation_count + 1) * 12))) # 10+15*log -> 5+12*log
    if is_top_tier: raw_score = min(99, raw_score + 15)

    # 2. Debiased Score (내실)
    debiased_base = 30
    if has_evidence: 
        debiased_base += 25 # 30 -> 25
        score_breakdown["Evidence"] = 25
    if is_big_team: 
        debiased_base += 10
        score_breakdown["Team"] = 10
    
    # Prestige 점수 (IF 기반)
    if impact_factor:
        prestige_score = min(30, int(impact_factor * 0.8)) # IF 반영 비율 조정
        debiased_base += prestige_score
        score_breakdown["Prestige"] = prestige_score
    elif is_top_tier:
        debiased_base += 15
        score_breakdown["Prestige"] = 15

    # 문헌량 편향 제거
    volume_discount = min(25, int(math.log(citation_count + 1) * 4))
    
    if age <= 2: volume_discount = int(volume_discount * 0.1) # 최신 논문은 페널티 거의 없음
    elif age <= 5: volume_discount = int(volume_discount * 0.5)

    score_breakdown["Volume Penalty"] = -volume_discount
    debiased_score = debiased_base - volume_discount
    
    if integrity_status != "valid":
        penalty = debiased_score - 5
        debiased_score = 5
        score_breakdown["Integrity Penalty"] = -penalty
        risk_reason = risk_reason or "데이터 신뢰도 낮음"
    elif age > 10 and citation_count < 5:
        penalty = debiased_score - 5
        debiased_score = 5
        score_breakdown["Integrity Penalty"] = -penalty
        risk_reason = "도태된 연구 (Old & Low Cited)"

    debiased_score = max(5, min(95, debiased_score)) # 최대 95점으로 제한 (99점 방지)

    # 3. Bias Penalty & Type
    bias_penalty = raw_score - debiased_score
    
    potential_type = "normal"
    if debiased_score > 70 and bias_penalty < 0: # 기준 완화 (75 -> 70)
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
        "score_breakdown": score_breakdown
    }

def search_crossref_api(query):
    is_exact_mode = query.startswith('"') and query.endswith('"')
    clean_query = query.strip('"') if is_exact_mode else query
    
    try:
        url = f"https://api.crossref.org/works?query={clean_query}&rows=1000&sort=relevance"
        response = requests.get(url, timeout=20)
        data = response.json()
    except Exception as e:
        st.error(f"API 연결 중 오류가 발생했습니다: {e}")
        return [], {}, False

    if not data or not isinstance(data, dict): return [], {}, False
    message = data.get('message')
    if not message or not isinstance(message, dict): return [], {}, False
    items = message.get('items')
    if not items: return [], {}, False

    valid_papers = []
    current_year = get_current_year()

    # --- PubMed 실제 데이터 조회 ---
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
        "pubmed_count": pubmed_count if pubmed_count is not None else "집계 불가",
        "avg_citations": avg_citations,
        "period": period_str,
        "is_high_exposure": (pubmed_count > 5000 if pubmed_count else False) or avg_citations > 100
    }

    if not is_exact_mode:
        valid_papers.sort(key=lambda x: x['debiased_score'], reverse=True)
            
    return valid_papers, bias_summary, is_exact_mode

# --- 3. Streamlit UI ---

st.set_page_config(page_title="Research Simulator", page_icon="🎓", layout="wide")

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
        st.toast(f"🎉 미션 완료! 보상 +{current_m['reward']}점", icon="🎁")
        if st.session_state.get("user_id"): save_user_data(st.session_state.user_id)

# 로그인 화면
if not st.session_state.get("user_id"):
    st.title("🎓 AI 기반 논문 추천 시스템")
    st.caption("캡스톤 디자인 _ AI:D")
    st.markdown("---")
    st.info("연구자 ID를 입력하여 검색을 시작하세요.")
    col1, col2 = st.columns([3, 1])
    with col1: user_input = st.text_input("연구자 이름 (ID)", placeholder="예: Dr.Kim")
    with col2:
        st.write(""); st.write("")
        if st.button("로그인 / 시작", type="primary", use_container_width=True):
            if user_input:
                st.session_state.user_id = user_input
                saved_data = load_user_data(user_input)
                st.session_state.score = saved_data["score"]
                st.session_state.inventory = saved_data["inventory"]
                st.session_state.mission_id = saved_data["mission_id"]
                st.session_state.trash = saved_data["trash"]
                st.rerun()
            else: st.warning("이름을 입력해주세요.")
    st.stop() 

# 사이드바
with st.sidebar:
    st.title("🎓 AI 기반 논문 추천 시스템")
    st.caption("캡스톤 디자인_AI:D")
    st.info(f"👤 {st.session_state.user_id} 연구원")
    if st.button("로그아웃 (저장됨)", use_container_width=True):
        save_user_data(st.session_state.user_id)
        st.session_state.user_id = None
        st.rerun()
    st.divider()
    current_level, progress, next_score = get_level_info(st.session_state.score)
    st.metric("연구 레벨", f"Lv. {current_level}")
    st.write(f"현재 점수: {st.session_state.score} / {next_score}")
    st.progress(progress)
    st.metric("보유 논문", f"{len(st.session_state.inventory)}편")
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
    st.markdown("#### 🔍 Raw score 지표")
    st.markdown("""
    1. 증거 적합성 지표 (Evidence Index)
       : 제목에 실험적 검증(in vivo, clinical 등)을 암시하는 구체적인 단어 포함
    2. 저널 권위 지표 (Prestige Index)
       : Nature, Science 등 학계에서 인정받는 최상위 저널
    3. 연구 규모 지표 (Collaboration Index)
       : 참여 저자 수 다수(5인 이상)가 참여한 연구 우대
    4. 데이터 신뢰도 지표 (Reliability Index)
       : 참고 문헌 수를 확인하여 연구의 깊이를 1차적으로 거릅니다. 참고 문헌이 너무 적으면 정식 논문이 아닌 초록이나 단순 투고일 가능성이 높아 배제합니다.
    5. 시의성 대비 인용 지표 (Opportunity Index)
       : 발행 시점과 인용 수의 상관관계를 분석하여 숨겨진 가치를 찾습니다. 최신이면서 인용이 적은 연구는 기회(Opportunity)로, 오래되었는데 인용이 없는 연구는 함정(Trap)으로 분류합니다.
    """)
    st.markdown("#### 📊 검색 방법")
    st.markdown("""
    1. 일반 검색
       : AI 추천 지수가 높은 순으로 추천
    2. "키워드"
       : 따옴표 검색을 통해 정확도 순으로 검색
    """)

tab_search, tab_analysis, tab_inventory, tab_trash = st.tabs(["🔍 논문 검색", "📊 지표 분석", "📚 내 서재", "🗑️ 휴지통"])

with tab_search:
    col1, col2 = st.columns([4, 1])
    with col1: query = st.text_input("키워드 입력", placeholder='예: "Immunotherapy" (따옴표는 정확도순)')
    with col2:
        st.write(""); st.write("")
        search_btn = st.button("검색", type="primary", use_container_width=True)

    if search_btn and query:
        with st.spinner("PubMed 데이터베이스 및 문헌량 편향 분석 중..."):
            results, summary, is_exact = search_crossref_api(query)
            st.session_state.search_results = results
            st.session_state.bias_summary = summary
            st.session_state.is_exact_search = is_exact
            st.session_state.search_page = 1 
            # 검색 시 정렬 초기값 설정
            st.session_state.sort_option = "정확도 (Relevance)" if is_exact else "내실 (Debiased)"
            if not results: st.error("검색 결과가 없습니다.")

    if st.session_state.search_results:
        summary = st.session_state.bias_summary
        with st.container(border=True):
            st.markdown("### 🔍 Search Bias Summary")
            bc1, bc2, bc3 = st.columns(3)
            pub_cnt = summary['pubmed_count']
            pub_cnt_str = f"{pub_cnt:,}편" if isinstance(pub_cnt, int) else str(pub_cnt)
            with bc1: st.metric("PubMed 논문 수 (실제)", pub_cnt_str)
            with bc2: st.metric("평균 인용수 (Top 200)", f"{summary['avg_citations']:,}회")
            with bc3: st.metric("연구 집중 시기", summary['period'])
            if summary['is_high_exposure']:
                st.warning("⚠ **High Exposure Topic**: 이 주제는 연구가 매우 활발하여, 상위 노출 논문이 과대평가(Bias)되었을 가능성이 큽니다. Debiased Score를 참고하여 내실 있는 연구를 선별하세요.")
            else:
                st.success("✅ **Niche Topic**: 비교적 연구가 덜 된 분야입니다. 숨겨진 명작이 많을 수 있습니다.")
        st.divider()

        st.markdown("##### 🔃 정렬 기준 선택")
        sort_col, _ = st.columns([2, 1])
        with sort_col:
            sort_opt = st.radio(
                "정렬 기준", 
                ["내실 (Debiased)", "인기 (Raw)", "최신 (Year)", "정확도 (Relevance)"], 
                horizontal=True, 
                label_visibility="collapsed", 
                key="sort_selector"
            )
        
        if sort_opt == "내실 (Debiased)":
            st.session_state.search_results.sort(key=lambda x: x['debiased_score'], reverse=True)
        elif sort_opt == "인기 (Raw)":
            st.session_state.search_results.sort(key=lambda x: x['raw_score'], reverse=True)
        elif sort_opt == "최신 (Year)":
            st.session_state.search_results.sort(key=lambda x: x['year'], reverse=True)
        elif sort_opt == "정확도 (Relevance)":
            st.session_state.search_results.sort(key=lambda x: x['original_rank'])

        items_per_page = 50
        total_items = len(st.session_state.search_results)
        total_pages = max(1, math.ceil(total_items / items_per_page))
        current_page = st.session_state.search_page
        start_idx = (current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_items = st.session_state.search_results[start_idx:end_idx]

        st.caption(f"검색 결과 총 {total_items}건 | 정렬: {sort_opt} | 페이지: {current_page}/{total_pages}")
        
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
                    if paper['integrity_status'] != "valid": tags.append("⚠️ 데이터 부족")
                    if paper['potential_type'] == "amazing": tags.append("💎 Hidden Gem")
                    st.write(" ".join([f"`{t}`" for t in tags]))
                    auth_display = ", ".join(paper['authors'])
                    if paper['author_full_count'] > 3: auth_display += f" 외 {paper['author_full_count'] - 3}명"
                    st.caption(f"{paper['year']} | {paper['journal']} | 인용 {paper['citations']}회 | 저자: {auth_display}")
                    
                    google_search_url = f"https://www.google.com/search?q={paper['journal'].replace(' ', '+')}+impact+factor+{paper['year']}"
                    
                    links_col1, links_col2 = st.columns(2)
                    with links_col1:
                        st.markdown(f"[📄 원문 보기]({paper['url']})")
                    with links_col2:
                         st.markdown(f"[📊 IF 검색 (Google)]({google_search_url})")

                with c2:
                    col_raw, col_deb = st.columns(2)
                    with col_raw: st.metric("Raw Score", f"{paper['raw_score']}", help="검색 엔진이 선호하는 인기도 점수")
                    with col_deb: st.metric("Debiased", f"{paper['debiased_score']}", delta=f"{-paper['bias_penalty']}", help="문헌량 거품을 뺀 진짜 내실 점수")
                    if paper['bias_penalty'] > 20: st.caption("⚠ High exposure")
                    
                    if paper['impact_factor']:
                        st.caption(f"🏆 IF: {paper['impact_factor']}")

                    is_owned = any(p['id'] == paper['id'] for p in st.session_state.inventory)
                    if is_owned:
                        st.button("보유중", key=f"owned_{unique_key_idx}", disabled=True, use_container_width=True)
                    else:
                        if st.button("수집하기", key=f"collect_{unique_key_idx}", type="secondary", use_container_width=True):
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
                 new_page = st.number_input("이동", min_value=1, max_value=total_pages, value=current_page, label_visibility="collapsed", key="nav_input")
                 if new_page != current_page:
                    st.session_state.search_page = new_page
                    st.rerun()

# --- [New] 지표 분석 탭 ---
with tab_analysis:
    if not st.session_state.search_results:
        st.info("먼저 '논문 검색' 탭에서 검색을 수행해주세요.")
    else:
        st.markdown("### 🛠️ 맞춤형 지표 분석")
        st.markdown("각 지표의 가중치를 조절하여 나만의 기준(Custom Score)으로 논문을 재평가하고 정렬합니다.")
        with st.container(border=True):
            col_w1, col_w2, col_w3 = st.columns(3)
            with col_w1: w_evidence = st.slider("🔬 증거 (Evidence)", 0.0, 3.0, 1.0, help="실험적 근거 유무")
            with col_w2: w_prestige = st.slider("👑 권위 (Prestige)", 0.0, 3.0, 1.0, help="Top Tier 저널 여부")
            with col_w3: w_recency = st.slider("📅 최신성 (Recency)", 0.0, 3.0, 1.0, help="최신 논문 우대")
            col_w4, col_w5 = st.columns(2)
            with col_w4: w_team = st.slider("👥 규모 (Team)", 0.0, 3.0, 1.0, help="대규모 연구팀")
            with col_w5: w_scarcity = st.slider("💎 희소성 (Scarcity)", 0.0, 3.0, 1.0, help="인용이 적은 원석 발굴")

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
        st.caption(f"재평가된 상위 20개 결과")
        for i, paper in enumerate(analyzed_papers[:20]):
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{i+1}. {paper['title']}**")
                    st.caption(f"{paper['year']} | {paper['journal']} | Custom Score: {paper['custom_score']}")
                    with st.expander("점수 상세 구성 보기"):
                        details = paper.get('score_breakdown', {})
                        chart_data = {
                            "Base": details.get('Base', 40),
                            "Evidence": details.get('Evidence', 0) * w_evidence,
                            "Prestige": (20 if paper['is_top_tier'] else 0) * w_prestige,
                            "Team": details.get('Team', 0) * w_team,
                            "Recency": max(0, (5 - paper.get('age', 5)) * 10) * w_recency,
                            "Scarcity": max(0, (50 - paper.get('citation_count', 0))) * w_scarcity,
                        }
                        st.bar_chart(chart_data)
                with c2:
                    st.metric("Custom", f"{paper['custom_score']}")
                    is_owned = any(p['id'] == paper['id'] for p in st.session_state.inventory)
                    if is_owned:
                        st.button("보유중", key=f"an_owned_{i}", disabled=True, use_container_width=True)
                    else:
                        if st.button("수집", key=f"an_collect_{i}", type="secondary", use_container_width=True):
                            st.session_state.inventory.append(paper)
                            st.session_state.score += paper['debiased_score']
                            check_mission(paper, "collect")
                            save_user_data(st.session_state.user_id)
                            st.rerun()

with tab_inventory:
    if not st.session_state.inventory: st.info("수집된 논문이 없습니다.")
    cols = st.columns(2)
    for i, paper in enumerate(st.session_state.inventory):
        with cols[i % 2]:
            with st.container(border=True):
                status_emoji = "❓"; status_text = "미검증"
                if paper['is_reviewed']:
                    if paper['potential_type'] == "amazing": status_emoji, status_text = "✨", "대성공"
                    elif paper['potential_type'] == "bad": status_emoji, status_text = "💀", "실패"
                    elif paper['potential_type'] == "verified_user": status_emoji, status_text = "🛡️", "사용자 승인"
                    else: status_emoji, status_text = "✅", "검증됨"

                st.markdown(f"**{paper['title']}**")
                st.caption(f"{status_emoji} {status_text} | {paper['journal']}")
                
                c_btn1, c_btn2 = st.columns([2, 1])
                with c_btn1:
                    if not paper['is_reviewed']:
                        if paper['integrity_status'] == "valid":
                            if st.button("🔬 심층 검증", key=f"rev_{i}", type="primary", use_container_width=True):
                                st.session_state.inventory[i]['is_reviewed'] = True
                                bonus = int(paper['debiased_score'] * 0.5)
                                st.session_state.score += bonus
                                st.session_state.inventory[i]['final_score'] = paper['debiased_score'] + bonus
                                if paper['potential_type'] == 'amazing': st.toast(f"대박! 숨겨진 명작을 찾았습니다! (+{bonus})", icon="🎉")
                                else: st.toast(f"검증이 완료되었습니다. (+{bonus})", icon="✅")
                                save_user_data(st.session_state.user_id) 
                                st.rerun()
                        else:
                            st.warning(paper['risk_reason'])
                            if st.button("강제 승인", key=f"force_{i}", use_container_width=True):
                                st.session_state.inventory[i]['is_reviewed'] = True
                                bonus = 10 
                                st.session_state.score += bonus
                                st.session_state.inventory[i]['final_score'] = paper['debiased_score'] + bonus
                                st.session_state.inventory[i]['potential_type'] = "verified_user"
                                st.session_state.inventory[i]['reason'] = "사용자 직접 확인으로 검증됨"
                                save_user_data(st.session_state.user_id) 
                                st.rerun()
                    else:
                        st.success(f"가치: {paper.get('final_score', 0)}점")

                with c_btn2:
                    if st.button("삭제", key=f"del_{i}", use_container_width=True):
                        deduction = paper.get('final_score', paper['debiased_score'])
                        st.session_state.score = max(0, st.session_state.score - deduction)
                        removed = st.session_state.inventory.pop(i)
                        st.session_state.trash.append(removed)
                        st.toast(f"논문 삭제. {deduction}점 차감됨", icon="🗑️")
                        save_user_data(st.session_state.user_id) 
                        st.rerun()
                st.markdown(f"[📄 원문 보기]({paper['url']})")

with tab_trash:
    if not st.session_state.trash: st.info("휴지통이 비어있습니다.")
    if st.session_state.trash:
        if st.button("휴지통 비우기", type="primary"):
            st.session_state.trash = []
            save_user_data(st.session_state.user_id)
            st.toast("휴지통 비움", icon="🧹")
            st.rerun()
    cols = st.columns(2)
    for i, paper in enumerate(st.session_state.trash):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"**{paper['title']}**")
                st.caption(f"삭제됨 | {paper['journal']}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("복구", key=f"rest_{i}", use_container_width=True):
                        restored = st.session_state.trash.pop(i)
                        st.session_state.inventory.append(restored)
                        r_score = restored.get('final_score', restored['debiased_score'])
                        st.session_state.score += r_score
                        st.toast(f"복구 완료 (+{r_score})", icon="♻️")
                        save_user_data(st.session_state.user_id)
                        st.rerun()
                with c2:
                    if st.button("영구삭제", key=f"pdel_{i}", use_container_width=True):
                        st.session_state.trash.pop(i)
                        st.toast("영구 삭제됨", icon="🔥")
                        save_user_data(st.session_state.user_id)
                        st.rerun()
