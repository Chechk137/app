import streamlit as st
import requests
import datetime
import random
import time
import json
import os
import math
import re
import pandas as pd
import altair as alt
from collections import Counter

# ==============================================================================
# [SECTION 1] 설정 및 상수 정의
# : 앱 전반에서 사용되는 고정값과 환경 설정을 관리합니다.
# ==============================================================================

# 논문 평가 및 시각적 강조(하이라이팅)에 사용되는 핵심 키워드 리스트
EVIDENCE_KEYWORDS = [
    'in vivo', 'in vitro', 'randomized', 'efficacy', 'mechanism', 'signaling', 
    'experiment', 'analysis', 'clinical', 'activity', 'synthesis', 'design', 
    'evaluation', 'characterization', 'properties', 'performance', 'application'
]

# 데이터 저장 경로 설정
DATA_DIR = "user_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)


# ==============================================================================
# [SECTION 2] 데이터 관리 (Persistence Layer)
# : 사용자 데이터를 JSON 파일로 로드하고 저장하는 함수들입니다.
# ==============================================================================

def load_user_data(user_id):
    """사용자 ID에 해당하는 JSON 파일을 읽어옵니다. 없으면 기본값을 반환합니다."""
    file_path = os.path.join(DATA_DIR, f"{user_id}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "score": data.get("score", 0),
                    "inventory": data.get("inventory", []),
                    "trash": data.get("trash", [])
                }
        except Exception as e:
            st.error(f"데이터 로드 오류: {e}")
    return {"score": 0, "inventory": [], "trash": []}

def save_user_data(user_id):
    """현재 세션 상태(점수, 인벤토리 등)를 JSON 파일로 저장합니다."""
    file_path = os.path.join(DATA_DIR, f"{user_id}.json")
    data = {
        "score": st.session_state.score,
        "inventory": st.session_state.inventory,
        "trash": st.session_state.trash
    }
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"데이터 저장 오류: {e}")


# ==============================================================================
# [SECTION 3] 유틸리티 및 텍스트 처리 함수
# : 날짜 계산, 번역, 텍스트 하이라이팅 등 보조 기능을 담당합니다.
# ==============================================================================

def get_current_year():
    return datetime.datetime.now().year

@st.cache_data
def get_translated_title(text):
    """구글 번역 API(비공식)를 사용하여 영문 제목을 한글로 변환합니다."""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": text
        }
        response = requests.get(url, params=params, timeout=2)
        if response.status_code == 200:
            return response.json()[0][0][0]
    except Exception:
        pass
    return "번역 실패 (연결 확인 필요)"

def highlight_text(text):
    """제목 내의 EVIDENCE_KEYWORDS를 찾아 HTML 형광펜 스타일을 적용합니다."""
    pattern = re.compile('|'.join(map(re.escape, EVIDENCE_KEYWORDS)), re.IGNORECASE)
    def replace(match):
        return f"<span style='background-color: #d1fae5; color: #065f46; padding: 0 4px; border-radius: 4px; font-weight: bold;'>{match.group(0)}</span>"
    return pattern.sub(replace, text)


# ==============================================================================
# [SECTION 4] 핵심 평가 알고리즘 (Scoring Logic)
# : 논문의 가치를 계산하는 가장 중요한 로직입니다.
# : [Update] PubMed 주제 과열도(Multiplier)를 인자(topic_multiplier)로 받도록 수정되었습니다.
# ==============================================================================

def evaluate_paper(paper_data, topic_multiplier=1.0):
    """
    논문 메타데이터와 주제 과열도를 기반으로 Impact(인기도)와 Potential(내실)을 계산합니다.
    
    topic_multiplier: PubMed 문헌 수에 따른 과열 가중치 (기본 1.0 ~ 최대 2.0)
    """
    current_year = get_current_year()
    year = paper_data.get('year', current_year - 5)
    age = current_year - year
    title_lower = paper_data['title'].lower()
    citation_count = paper_data.get('citations', 0)
    
    # 지표 1: 증거 키워드 포함 여부
    has_evidence = any(k in title_lower for k in EVIDENCE_KEYWORDS)
    
    # 지표 2: 대규모 연구팀 여부 (5인 이상)
    author_count = paper_data.get('author_count', 1)
    is_big_team = author_count >= 5

    # 지표 3: 데이터 신뢰도 (참고문헌 수 기반)
    ref_count = paper_data.get('ref_count') 
    integrity_status = "valid"
    risk_reason = ""

    if ref_count is None:
        if citation_count < 5:
            integrity_status = "uncertain"
            risk_reason = "메타데이터 누락"
    elif ref_count < 5:
        if citation_count < 5:
            integrity_status = "suspected"
            risk_reason = "참고문헌 부족"

    score_breakdown = {
        "Base": 30, "Evidence": 0, "Team": 0, "Volume Penalty": 0, "Integrity Penalty": 0
    }

    # 1. Impact (Raw Score): 인기도 기반 점수
    raw_score = min(99, int(5 + (math.log(citation_count + 1) * 15)))

    # 2. Potential (Debiased Score): 내실 기반 점수
    debiased_base = 30
    if has_evidence: 
        debiased_base += 30 
        score_breakdown["Evidence"] = 30
    if is_big_team: 
        debiased_base += 10
        score_breakdown["Team"] = 10
    
    # [Logic Update] 문헌량 편향 제거 (Volume Discount)
    # PubMed 주제 과열도(Multiplier)를 곱하여, 과열된 주제일수록 인용수 감점을 크게 적용
    base_volume_discount = min(25, int(math.log(citation_count + 1) * 4))
    
    # 최신 연구 보정 (오래될수록 페널티 그대로, 최신일수록 페널티 완화)
    if age <= 2: base_volume_discount = int(base_volume_discount * 0.1)
    elif age <= 5: base_volume_discount = int(base_volume_discount * 0.5)

    # 최종 감점 = 인용 기반 감점 * 주제 과열도
    final_volume_penalty = int(base_volume_discount * topic_multiplier)

    score_breakdown["Volume Penalty"] = -final_volume_penalty
    debiased_score = debiased_base - final_volume_penalty
    
    # 신뢰도 패널티 적용
    if integrity_status != "valid":
        penalty = debiased_score - 5
        debiased_score = 5
        score_breakdown["Integrity Penalty"] = -penalty
        risk_reason = risk_reason or "데이터 신뢰도 낮음"
    elif age > 10 and citation_count < 5:
        penalty = debiased_score - 5
        debiased_score = 5
        score_breakdown["Integrity Penalty"] = -penalty
        risk_reason = "도태된 연구"

    debiased_score = max(5, min(95, debiased_score))

    # 3. Bias Penalty: 인기도와 내실의 괴리
    bias_penalty = raw_score - debiased_score
    
    # 논문 유형 분류
    potential_type = "normal"
    if debiased_score > 70 and bias_penalty < 0:
        potential_type = "amazing" 
    elif bias_penalty > 30:
        potential_type = "bubble" 
    elif integrity_status != "valid":
        potential_type = "bad"

    return {
        "raw_score": raw_score, # Impact
        "debiased_score": debiased_score, # Potential
        "bias_penalty": bias_penalty,
        "potential_type": potential_type,
        "risk_reason": risk_reason,
        "has_evidence": has_evidence,
        "is_big_team": is_big_team,
        "integrity_status": integrity_status,
        "score_breakdown": score_breakdown,
        "age": age,
        "citation_count": citation_count
    }


# ==============================================================================
# [SECTION 5] 외부 API 통신
# : Crossref 및 PubMed API와 통신하여 데이터를 가져옵니다.
# ==============================================================================

def get_pubmed_count(query):
    """PubMed에서 해당 키워드의 전체 문헌 수를 조회합니다."""
    try:
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {"db": "pubmed", "term": query, "retmode": "json", "rettype": "count"}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        return int(data["esearchresult"]["count"])
    except Exception:
        return None

def search_crossref_api(query):
    """Crossref API를 통해 논문 메타데이터를 검색하고 평가합니다."""
    is_exact_mode = query.startswith('"') and query.endswith('"')
    clean_query = query.strip('"') if is_exact_mode else query
    
    try:
        # [Modified] 제목 우선 검색 (query.title)
        url = f"https://api.crossref.org/works?query.title={clean_query}&rows=1000&sort=relevance"
        response = requests.get(url, timeout=20)
        data = response.json()
    except Exception as e:
        st.error(f"API 연결 오류: {e}")
        return [], {}, False

    if not data or not isinstance(data, dict): return [], {}, False
    items = data.get('message', {}).get('items', [])
    if not items: return [], {}, False

    valid_papers = []
    current_year = get_current_year()
    pubmed_count = get_pubmed_count(clean_query)
    
    # [New] 주제 과열도(Multiplier) 산정
    # 문헌량이 많을수록 거품일 확률이 높다고 가정하여 페널티를 강화함
    topic_multiplier = 1.0
    if pubmed_count:
        if pubmed_count > 10000: topic_multiplier = 2.0  # 매우 과열됨 -> 감점 2배
        elif pubmed_count > 5000: topic_multiplier = 1.5 # 과열됨 -> 감점 1.5배
        elif pubmed_count > 1000: topic_multiplier = 1.2 # 보통 -> 감점 1.2배
        # 그 외(1000 이하)는 1.0배 (기본)

    citations_list = []
    years_list = []

    # [New] 검색어 단어 경계 패턴 (엄격한 필터링용)
    word_pattern = re.compile(r'\b' + re.escape(clean_query) + r'\b', re.IGNORECASE)

    for idx, item in enumerate(items):
        if not item.get('DOI') or not item.get('title'): continue
        
        raw_title = item['title'][0]
        title_str = raw_title.lower()

        # [Check] 제목 내 단어 단위 포함 여부 확인
        if not word_pattern.search(raw_title):
            continue

        invalid_titles = ["announcement", "editorial", "issue info", "correction", "erratum", "author index", "front matter", "back matter"]
        if any(inv in title_str for inv in invalid_titles): continue
        
        cit = item.get('is-referenced-by-count', 0)
        citations_list.append(cit)
        
        # 연도 추출
        y = None
        if item.get('published') and item['published'].get('date-parts'): y = item['published']['date-parts'][0][0]
        elif item.get('created') and item['created'].get('date-parts'): y = item['created']['date-parts'][0][0]
        if y: years_list.append(y)

        # 저자 정보 정제
        if not item.get('author'): continue
        valid_authors = []
        for a in item['author']:
            given = a.get('given', '').strip()
            family = a.get('family', '').strip()
            full = f"{given} {family}".strip()
            if full and "anonymous" not in full.lower():
                valid_authors.append(full)
        if not valid_authors: continue

        pub_year = y if y else current_year - 5
        
        paper_data_for_eval = {
            'title': item['title'][0], 'year': pub_year, 'citations': cit, 
            'journal': item.get('container-title', ["Unknown"])[0], 
            'author_count': len(valid_authors), 
            'ref_count': item.get('reference-count')
        }
        
        # [Modified] topic_multiplier를 평가 함수에 전달
        eval_result = evaluate_paper(paper_data_for_eval, topic_multiplier)

        # 결과 객체 생성
        paper_obj = {
            'id': item['DOI'],
            'title': item['title'][0],
            'authors': valid_authors[:3], 
            'author_full_count': len(valid_authors),
            'journal': item.get('container-title', ["Unknown"])[0],
            'year': pub_year,
            'citations': cit,
            'ref_count': item.get('reference-count') if item.get('reference-count') else 0,
            'url': f"https://doi.org/{item['DOI']}",
            **eval_result,
            'is_reviewed': False,
            'original_rank': idx
        }
        valid_papers.append(paper_obj)
    
    # 통계 정보 생성
    avg_citations = int(sum(citations_list) / len(citations_list)) if citations_list else 0
    period_str = "Unknown"
    if years_list:
        min_y, max_y = min(years_list), max(years_list)
        period_str = f"{min_y}~{max_y}"

    bias_summary = {
        "pubmed_count": pubmed_count if pubmed_count is not None else "집계 불가",
        "avg_citations": avg_citations,
        "period": period_str,
        "is_high_exposure": (pubmed_count > 5000 if pubmed_count else False) or avg_citations > 100,
        "multiplier": topic_multiplier # UI 표시용
    }

    # 기본 정렬: Potential(내실) 순
    if not is_exact_mode:
        valid_papers.sort(key=lambda x: x['debiased_score'], reverse=True)
            
    return valid_papers, bias_summary, is_exact_mode


# ==============================================================================
# [SECTION 6] 내보내기 유틸리티 (Export)
# : BibTeX 및 CSV 변환 함수입니다.
# ==============================================================================

def convert_to_bibtex(inventory_list):
    bibtex_entries = []
    for paper in inventory_list:
        first_author = paper['authors'][0].split()[-1] if paper['authors'] else "Unknown"
        safe_key = re.sub(r'\W+', '', f"{first_author}{paper['year']}")
        authors_formatted = " and ".join(paper['authors'])
        
        entry = f"""@article{{{safe_key},
  title = {{{paper['title']}}},
  author = {{{authors_formatted}}},
  journal = {{{paper['journal']}}},
  year = {{{paper['year']}}},
  doi = {{{paper['id']}}}
}}"""
        bibtex_entries.append(entry)
    return "\n\n".join(bibtex_entries)

def convert_to_csv(inventory_list):
    lines = ["DOI,Title,Authors,Journal,Year,Citations,MyScore"]
    for paper in inventory_list:
        safe_title = paper['title'].replace('"', '""')
        safe_authors = "; ".join(paper['authors']).replace('"', '""')
        safe_journal = paper['journal'].replace('"', '""')
        score = paper.get('final_score', paper.get('debiased_score', 0))
        line = f"\"{paper['id']}\",\"{safe_title}\",\"{safe_authors}\",\"{safe_journal}\",{paper['year']},{paper['citations']},{score}"
        lines.append(line)
    return "\n".join(lines)


# ==============================================================================
# [SECTION 7] Streamlit UI 구성 - 메인 및 사이드바
# ==============================================================================

st.set_page_config(page_title="Research Simulator", page_icon="🎓", layout="wide")

# 세션 상태 초기화
if 'user_id' not in st.session_state: st.session_state['user_id'] = None
if 'score' not in st.session_state: st.session_state['score'] = 0
if 'inventory' not in st.session_state: st.session_state['inventory'] = []
if 'trash' not in st.session_state: st.session_state['trash'] = []
if 'search_results' not in st.session_state: st.session_state['search_results'] = []
if 'bias_summary' not in st.session_state: st.session_state['bias_summary'] = {}
if 'search_page' not in st.session_state: st.session_state['search_page'] = 1
if 'analysis_page' not in st.session_state: st.session_state['analysis_page'] = 1
if 'is_exact_search' not in st.session_state: st.session_state['is_exact_search'] = False
if 'sort_option' not in st.session_state: st.session_state['sort_option'] = "Potential"
if 'analysis_weights' not in st.session_state: st.session_state['analysis_weights'] = {"evidence": 1.0, "recency": 1.0, "team": 1.0, "scarcity": 1.0}
if 'current_preset' not in st.session_state: st.session_state['current_preset'] = "⚖️ 밸런스"

def get_level_info(score):
    level_threshold = 500
    level = (score // level_threshold) + 1
    progress = (score % level_threshold) / level_threshold
    next_milestone = (level) * level_threshold
    return level, progress, next_milestone

# ------------------------------------------------------------------------------
# [UI Part 1] 로그인 화면
# ------------------------------------------------------------------------------
if not st.session_state.get("user_id"):
    st.title("🎓 AI 기반 논문 추천 시스템")
    st.caption("캡스톤 디자인 _ AI:D")
    st.markdown("---")
    st.markdown("### 👋 환영합니다!")
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
                st.session_state.trash = saved_data["trash"]
                st.rerun()
            else: st.warning("이름을 입력해주세요.")
    st.stop() 

# ------------------------------------------------------------------------------
# [UI Part 2] 사이드바 (정보 및 가이드)
# ------------------------------------------------------------------------------
with st.sidebar:
    st.title("🎓 AI 기반 논문 추천 시스템")
    st.caption("캡스톤 디자인 _ AI:D")
    st.info(f"👤 {st.session_state.user_id} 연구원")
    if st.button("로그아웃 (저장됨)", use_container_width=True):
        save_user_data(st.session_state.user_id)
        st.session_state.user_id = None
        st.rerun()
    st.divider()
    
    # 레벨 정보
    current_level, progress, next_score = get_level_info(st.session_state.score)
    st.metric("연구 레벨", f"Lv. {current_level}")
    st.write(f"현재 점수: {st.session_state.score} / {next_score}")
    st.progress(progress)
    st.metric("보유 논문", f"{len(st.session_state.inventory)}편")
    st.divider()
    
    # 가이드
    st.markdown("#### 🔍 평가 지표 가이드")
    st.markdown("""
    **1. Impact (영향력)**
    : 기존의 인기도 점수(Raw Score). 인용수와 저널 인지도 등 학계에서의 현재 위상을 반영합니다.
    
    **2. Potential (잠재력)**
    : 인용 거품을 제거한 내실 점수(Debiased Score). 증거 기반의 희소성과 미래 가치를 평가합니다.
    
    **3. Bias Penalty (편향)**
    : Impact와 Potential의 괴리. 양수면 과열(Bubble), 음수면 저평가(Hidden Gem)된 연구입니다.
    """)

    st.markdown("#### 📊 점수 상세 지표")
    st.markdown("""
    **1. Evidence (증거)**
    - **방식**: 제목 내 실험 키워드(in vivo, clinical 등) 포함 여부
    - **점수**: 포함 시 30점 (미포함 0점)
    - **의미**: 실질적 실험 데이터가 있는 논문 우대

    **2. Recency (최신성)**
    - **방식**: (5 - 경과년수) * 10 (최대 50점)
    - **점수**: 최신순 50점 ~ 5년 이상 0점
    - **의미**: 최신 연구일수록 고득점

    **3. Scarcity (희소성)**
    - **방식**: 50 - 인용 횟수 (최소 0점)
    - **점수**: 인용 0회 시 50점 ~ 50회 이상 0점
    - **의미**: 인용이 적은 숨겨진 논문(Hidden Gem) 발굴

    **4. Team (규모)**
    - **방식**: 저자 5명 이상 여부
    - **점수**: 5명 이상 시 10점 (미만 0점)
    - **의미**: 대규모 협업 연구 반영
    """)

    st.markdown("#### 📊 검색 방법")
    st.markdown("""
    1. 일반 검색
        : AI 추천 지수(Potential)가 높은 순으로 추천
    2. "키워드"
        : 따옴표 검색 시 정확도 순으로 결과 노출
    """)
    
    st.divider()
    # 옵션 설정
    show_translation = st.checkbox("한글 번역 항상 보기 (모바일용)", value=False)
    show_highlight = st.checkbox("키워드 하이라이팅 (Visual Evidence)", value=True, help="점수에 긍정적 영향을 준 핵심 단어를 강조합니다.")


# ==============================================================================
# [SECTION 8] 메인 기능 탭 구성
# ==============================================================================
tab_search, tab_analysis, tab_inventory, tab_trash = st.tabs(["🔍 논문 검색", "📊 지표 분석", "📚 내 서재", "🗑️ 휴지통"])

# ------------------------------------------------------------------------------
# [Tab 1] 논문 검색
# ------------------------------------------------------------------------------
with tab_search:
    col1, col2 = st.columns([4, 1])
    with col1: query = st.text_input("키워드 입력", placeholder='예: "Immunotherapy" (따옴표는 정확도순)')
    with col2:
        st.write(""); st.write("")
        search_btn = st.button("검색", type="primary", use_container_width=True)

    if search_btn and query:
        with st.spinner("문헌량 편향 분석 및 데이터 처리 중..."):
            results, summary, is_exact = search_crossref_api(query)
            st.session_state.search_results = results
            st.session_state.bias_summary = summary
            st.session_state.is_exact_search = is_exact
            st.session_state.search_page = 1 
            st.session_state.sort_option = "정확도" if is_exact else "Potential"
            if not results: st.error("검색 결과가 없습니다.")

    if st.session_state.search_results:
        summary = st.session_state.bias_summary
        
        # 1. 편향 요약
        with st.expander("🔍 편향 요약", expanded=True):
            bc1, bc2, bc3 = st.columns(3)
            pub_cnt = summary['pubmed_count']
            pub_cnt_str = f"{pub_cnt:,}편" if isinstance(pub_cnt, int) else str(pub_cnt)
            with bc1: st.metric("PubMed 논문 수", pub_cnt_str, help="해당 키워드의 전체 문헌 수 (시장 규모)")
            with bc2: st.metric("평균 인용수 (Top 200)", f"{summary['avg_citations']:,}회")
            
            # Multiplier 표시
            mult = summary.get('multiplier', 1.0)
            mult_color = "normal"
            if mult >= 2.0: mult_color = "off" # 빨강 느낌
            elif mult >= 1.5: mult_color = "off"
            
            with bc3: 
                st.metric("과열도 가중치", f"x{mult}", help="문헌량이 많을수록 인용수 거품을 제거하기 위해 페널티가 강화됩니다.")

            if summary['is_high_exposure']:
                st.warning(f"⚠ **High Exposure Topic**: 연구가 매우 활발하여(x{mult}), 상위 노출 논문의 Impact(영향력)가 과대평가되었을 가능성이 큽니다. Potential(잠재력) 지표를 참고하세요.")
            else:
                st.success("✅ **Niche Topic**: 비교적 연구가 덜 된 분야입니다. 숨겨진 명작이 많을 수 있습니다.")
        st.divider()

        # 2. 거품 vs 원석 산점도
        with st.expander("📈 거품 vs 원석 분포도", expanded=True):
            chart_data = []
            for p in st.session_state.search_results:
                chart_data.append({
                    "Title": p['title'],
                    "Impact": p['raw_score'],
                    "Potential": p['debiased_score'],
                    "Type": p['potential_type']
                })
            
            if chart_data:
                df_chart = pd.DataFrame(chart_data)
                domain = ["amazing", "bubble", "bad", "normal", "uncertain", "suspected", "verified_user"]
                range_ = ["#10b981", "#ef4444", "#6b7280", "#3b82f6", "#f59e0b", "#f59e0b", "#8b5cf6"]
                
                base = alt.Chart(df_chart).encode(
                    x=alt.X('Impact', title='Impact (인기도/영향력)', scale=alt.Scale(domain=[0, 100])),
                    y=alt.Y('Potential', title='Potential (잠재력/내실)', scale=alt.Scale(domain=[0, 100]))
                )
                scatter = base.mark_circle(size=60).encode(
                    color=alt.Color('Type', scale=alt.Scale(domain=domain, range=range_), legend=None),
                    tooltip=['Title', 'Impact', 'Potential', 'Type']
                )
                # 4분면 기준선
                h_rule = alt.Chart(pd.DataFrame({'y': [50]})).mark_rule(strokeDash=[5, 5], color='gray', opacity=0.5).encode(y='y')
                v_rule = alt.Chart(pd.DataFrame({'x': [50]})).mark_rule(strokeDash=[5, 5], color='gray', opacity=0.5).encode(x='x')
                # 텍스트 라벨
                text_df = pd.DataFrame({
                    'x': [25, 85], 'y': [90, 10], 
                    'label': ['💎 Hidden Gem (원석)', '🫧 Bubble (거품)']
                })
                text_layer = alt.Chart(text_df).mark_text(
                    align='center', baseline='middle', fontSize=13, fontWeight='bold', color='gray', opacity=0.8
                ).encode(x='x', y='y', text='label')
                
                final_chart = (scatter + h_rule + v_rule + text_layer).interactive()
                st.altair_chart(final_chart, use_container_width=True)
                st.info("💡 **좌측 상단(High Potential, Low Impact)** 영역에 위치한 논문이 바로 숨겨진 원석(Hidden Gem)입니다!")

        # 3. 정렬 및 목록 표시
        st.markdown("""<div style="font-size: 1rem; font-weight: 600; margin-bottom: 1rem;">🔃 정렬 기준 선택</div>""", unsafe_allow_html=True)
        sort_col, _ = st.columns([2, 1])
        with sort_col:
            sort_opt = st.radio(
                "정렬 기준", 
                ["Potential (잠재력)", "Impact (영향력)", "최신", "정확도"], 
                horizontal=True, 
                label_visibility="collapsed", 
                key="sort_selector"
            )
        
        if "Potential" in sort_opt:
            st.session_state.search_results.sort(key=lambda x: x['debiased_score'], reverse=True)
        elif "Impact" in sort_opt:
            st.session_state.search_results.sort(key=lambda x: x['raw_score'], reverse=True)
        elif sort_opt == "최신":
            st.session_state.search_results.sort(key=lambda x: x['year'], reverse=True)
        elif sort_opt == "정확도":
            st.session_state.search_results.sort(key=lambda x: x['original_rank'])

        # 페이지네이션
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
                    translated_title = get_translated_title(paper['title'])
                    display_title = highlight_text(paper['title']) if show_highlight else paper['title']
                    st.markdown(
                        f"""<div title="[번역] {translated_title}" style="font-size:1.1rem; font-weight:bold; margin-bottom:5px;">{start_idx + i + 1}. {display_title}</div>""", 
                        unsafe_allow_html=True
                    )
                    if show_translation:
                        st.caption(f"🇰🇷 {translated_title}")
                    
                    tags = []
                    if paper['has_evidence']: tags.append("🔬 Evidence")
                    if paper['is_big_team']: tags.append("👥 Big Team")
                    if paper['integrity_status'] != "valid": tags.append("⚠️ 데이터 부족")
                    if paper['potential_type'] == "amazing": tags.append("💎 Hidden Gem")
                    st.write(" ".join([f"`{t}`" for t in tags]))
                    
                    auth_display = ", ".join(paper['authors'])
                    if paper['author_full_count'] > 3: auth_display += f" 외 {paper['author_full_count'] - 3}명"
                    st.caption(f"{paper['year']} | {paper['journal']} | 인용 {paper['citations']}회 | 저자: {auth_display}")
                    st.markdown(f"[📄 원문 보기]({paper['url']})")

                with c2:
                    col_raw, col_deb = st.columns(2)
                    with col_raw: st.metric("Impact", f"{paper['raw_score']}", help="현재 학계에서의 영향력 및 인기도 (Raw Score)")
                    with col_deb: st.metric("Potential", f"{paper['debiased_score']}", delta=f"{-paper['bias_penalty']}", help="미래 가치 및 잠재력 (Debiased Score)")
                    if paper['bias_penalty'] > 20: st.caption("⚠ 과열됨")

                    is_owned = any(p['id'] == paper['id'] for p in st.session_state.inventory)
                    if is_owned:
                        st.button("보유중", key=f"owned_{unique_key_idx}", disabled=True, use_container_width=True)
                    else:
                        if st.button("수집", key=f"collect_{unique_key_idx}", type="secondary", use_container_width=True):
                            st.session_state.inventory.append(paper)
                            st.session_state.score += paper['debiased_score']
                            save_user_data(st.session_state.user_id) 
                            st.rerun()
        
        st.divider()
        # 페이지 이동 버튼
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
                 new_page = st.number_input("이동", min_value=1, max_value=total_pages, value=current_page, label_visibility="collapsed", key="nav_search_input")
                 if new_page != current_page:
                    st.session_state.search_page = new_page
                    st.rerun()

# ------------------------------------------------------------------------------
# [Tab 2] 지표 분석
# ------------------------------------------------------------------------------
with tab_analysis:
    if not st.session_state.search_results:
        st.info("먼저 '논문 검색' 탭에서 검색을 수행해주세요.")
    else:
        st.markdown("""<div style="font-size: 1.5rem; font-weight: 600; margin-bottom: 1rem;">🛠️ 맞춤형 지표 분석</div>""", unsafe_allow_html=True)
        st.markdown("각 지표의 가중치를 조절하여 나만의 기준(Custom Potential)으로 논문을 재평가하고 정렬합니다.")
        
        if 'analysis_weights' not in st.session_state:
            st.session_state.analysis_weights = {"evidence": 1.0, "recency": 1.0, "team": 1.0, "scarcity": 1.0}
            st.session_state.current_preset = "⚖️ 밸런스"
        
        if 'analysis_page' not in st.session_state:
            st.session_state.analysis_page = 1

        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        with col_p1:
            if st.button("⚖️ 밸런스", use_container_width=True, help="모든 지표를 골고루 반영합니다."):
                st.session_state.analysis_weights = {"evidence": 1.0, "recency": 1.0, "team": 1.0, "scarcity": 1.0}
                st.session_state.current_preset = "⚖️ 밸런스"
                st.rerun()
        with col_p2:
            if st.button("💎 숨겨진 원석", use_container_width=True, help="인용은 적지만 증거가 확실한 논문을 찾습니다."):
                st.session_state.analysis_weights = {"evidence": 2.0, "recency": 1.0, "team": 1.0, "scarcity": 3.0}
                st.session_state.current_preset = "💎 숨겨진 원석"
                st.rerun()
        with col_p3:
            if st.button("🚀 최신 트렌드", use_container_width=True, help="최신성과 실험적 근거를 최우선으로 봅니다."):
                st.session_state.analysis_weights = {"evidence": 2.0, "recency": 3.0, "team": 0.5, "scarcity": 1.0}
                st.session_state.current_preset = "🚀 최신 트렌드"
                st.rerun()
        with col_p4:
            if st.button("👑 대규모", use_container_width=True, help="대규모 연구팀을 선호합니다."):
                st.session_state.analysis_weights = {"evidence": 1.0, "recency": 0.5, "team": 3.0, "scarcity": 0.5}
                st.session_state.current_preset = "👑 대규모"
                st.rerun()

        st.info(f"현재 적용된 분석 모드: **{st.session_state.current_preset}**")

        st.markdown("""
        <small>💡 **가중치 설정 가이드**: 슬라이더의 숫자는 해당 지표의 중요도(배수)를 의미합니다.
        <br>• **1.0**: 기본 반영 | • **2.0**: 2배 더 중요하게 반영 | • **0.0**: 점수 산정에서 제외</small>
        """, unsafe_allow_html=True)

        w = st.session_state.analysis_weights
        
        with st.container(border=True):
            col_w1, col_w2 = st.columns(2)
            with col_w1: w["evidence"] = st.slider("증거", 0.0, 3.0, w["evidence"])
            with col_w2: w["recency"] = st.slider("최신성", 0.0, 3.0, w["recency"])
            col_w3, col_w4 = st.columns(2)
            with col_w3: w["team"] = st.slider("규모", 0.0, 3.0, w["team"])
            with col_w4: w["scarcity"] = st.slider("희소성", 0.0, 3.0, w["scarcity"])

        w_evidence = w["evidence"]
        w_recency = w["recency"]
        w_team = w["team"]
        w_scarcity = w["scarcity"]

        analyzed_papers = []
        for paper in st.session_state.search_results:
            details = paper.get('score_breakdown', {})
            ev_score = details.get('Evidence', 0)
            team_score = details.get('Team', 0)
            vol_penalty = details.get('Volume Penalty', 0)
            age_score = max(0, (5 - paper.get('age', 5)) * 10)
            scarcity_score = max(0, (50 - paper.get('citation_count', 0))) 
            if scarcity_score > 50: scarcity_score = 50
            
            custom_score = (
                (ev_score * w_evidence) +
                (team_score * w_team) +
                (age_score * w_recency) +
                (scarcity_score * w_scarcity) +
                vol_penalty
            )
            paper_copy = paper.copy()
            paper_copy['custom_score'] = int(custom_score)
            analyzed_papers.append(paper_copy)
            
        analyzed_papers.sort(key=lambda x: x['custom_score'], reverse=True)
        
        # 분석 탭 페이지네이션
        items_per_page = 50
        total_items_an = len(analyzed_papers)
        total_pages_an = max(1, math.ceil(total_items_an / items_per_page))
        current_page_an = st.session_state.analysis_page
        start_idx_an = (current_page_an - 1) * items_per_page
        end_idx_an = start_idx_an + items_per_page
        page_items_an = analyzed_papers[start_idx_an:end_idx_an]

        st.divider()
        st.caption(f"재평가 결과 ({total_items_an}건) | 페이지: {current_page_an}/{total_pages_an}")
        
        for i, paper in enumerate(page_items_an):
            unique_an_key = f"an_{start_idx_an + i}"
            with st.container(border=True):
                c1, c2 = st.columns([5, 2])
                with c1:
                    translated_title = get_translated_title(paper['title'])
                    display_title = highlight_text(paper['title']) if show_highlight else paper['title']
                    st.markdown(
                        f"""<div title="[번역] {translated_title}" style="font-size:1.1rem; font-weight:bold; margin-bottom:5px;">{display_title}</div>""", 
                        unsafe_allow_html=True
                    )
                    if show_translation:
                        st.caption(f"🇰🇷 {translated_title}")
                    
                    tags = []
                    if paper['has_evidence']: tags.append("🔬 Evidence")
                    if paper['is_big_team']: tags.append("👥 Big Team")
                    if paper['integrity_status'] != "valid": tags.append("⚠️ 데이터 부족")
                    if paper['potential_type'] == "amazing": tags.append("💎 Hidden Gem")
                    st.write(" ".join([f"`{t}`" for t in tags]))
                    
                    auth_display = ", ".join(paper['authors'])
                    if paper['author_full_count'] > 3: auth_display += f" 외 {paper['author_full_count'] - 3}명"
                    st.caption(f"{paper['year']} | {paper['journal']} | 인용 {paper['citations']}회 | 저자: {auth_display}")
                    st.markdown(f"[📄 원문 보기]({paper['url']})")

                    with st.expander("점수 상세 구성 보기"):
                        details = paper.get('score_breakdown', {})
                        chart_data = {
                            "Evidence (증거)": details.get('Evidence', 0) * w_evidence,
                            "Team (규모)": details.get('Team', 0) * w_team,
                            "Recency (최신성)": max(0, (5 - paper.get('age', 5)) * 10) * w_recency,
                            "Scarcity (희소성)": max(0, (50 - paper.get('citation_count', 0))) * w_scarcity,
                        }
                        st.bar_chart(chart_data, horizontal=True)
                with c2:
                    st.metric("사용자 점수", f"{paper['custom_score']}")
                    is_owned = any(p['id'] == paper['id'] for p in st.session_state.inventory)
                    if is_owned:
                        st.button("보유중", key=f"an_own_{unique_an_key}", disabled=True, use_container_width=True)
                    else:
                        if st.button("수집", key=f"an_col_{unique_an_key}", type="secondary", use_container_width=True):
                            st.session_state.inventory.append(paper)
                            st.session_state.score += paper['debiased_score']
                            save_user_data(st.session_state.user_id)
                            st.rerun()

        st.divider()
        _, nav_col_an, _ = st.columns([1, 5, 1])
        with nav_col_an:
            if total_pages_an <= 5: display_pages_an = range(1, total_pages_an + 1)
            else:
                if current_page_an <= 3: display_pages_an = range(1, 6)
                elif current_page_an >= total_pages_an - 2: display_pages_an = range(total_pages_an - 4, total_pages_an + 1)
                else: display_pages_an = range(current_page_an - 2, current_page_an + 3)

            pg_cols_an = st.columns([1, 1, 1, 1, 1, 1, 1, 0.5, 2.5], gap="small")
            
            with pg_cols_an[0]:
                if st.button("◀", key="nav_an_prev", disabled=current_page_an==1, use_container_width=True):
                    st.session_state.analysis_page -= 1
                    st.rerun()
            for idx, p_num in enumerate(display_pages_an):
                if idx < 5:
                    with pg_cols_an[idx + 1]:
                        b_type = "primary" if p_num == current_page_an else "secondary"
                        if st.button(f"{p_num}", key=f"nav_an_p_{p_num}", type=b_type, use_container_width=True):
                            st.session_state.analysis_page = p_num
                            st.rerun()
            with pg_cols_an[6]:
                if st.button("▶", key="nav_an_next", disabled=current_page_an==total_pages_an, use_container_width=True):
                    st.session_state.analysis_page += 1
                    st.rerun()
            with pg_cols_an[8]:
                 new_page_an = st.number_input("이동", min_value=1, max_value=total_pages_an, value=current_page_an, label_visibility="collapsed", key="nav_an_input")
                 if new_page_an != current_page_an:
                    st.session_state.analysis_page = new_page_an
                    st.rerun()

# ------------------------------------------------------------------------------
# [Tab 3] 내 서재 (Inventory)
# ------------------------------------------------------------------------------
with tab_inventory:
    inv_main, inv_info = st.columns([3, 1])
    
    with inv_info:
        with st.container(border=True):
            st.markdown("""<div style="font-size: 1.2rem; font-weight: 600; margin-bottom: 1rem;">💡 가치 산정 공식</div>""", unsafe_allow_html=True)
            st.markdown("""
            **1. 심층 검증 (성공)**
            > **Potential + 50% 보너스**

            <small>좋은 원석(Potential)을 발굴할수록, 연구자의 검증을 통해 그 가치가 1.5배로 증폭됩니다.</small>
            """, unsafe_allow_html=True)
            st.markdown("---")
            st.markdown("""
            **2. 강제 승인 (리스크)**
            > **Potential + 10점**

            <small>데이터가 부족한(Risk) 논문을 억지로 승인하면, 보너스가 대폭 축소됩니다.</small>
            """, unsafe_allow_html=True)

    with inv_main:
        if not st.session_state.inventory: 
            st.info("수집된 논문이 없습니다.")
        else:
            with st.expander("📂 서지 정보 내보내기 (BibTeX / CSV)"):
                e_col1, e_col2 = st.columns(2)
                with e_col1:
                    bib_data = convert_to_bibtex(st.session_state.inventory)
                    st.download_button("BibTeX 다운로드 (.bib)", bib_data, "my_research_inventory.bib", "text/plain", use_container_width=True)
                with e_col2:
                    csv_data = convert_to_csv(st.session_state.inventory)
                    st.download_button("CSV 다운로드 (.csv)", csv_data, "my_research_inventory.csv", "text/csv", use_container_width=True)
            
            with st.expander("📖 Overleaf로 BibTeX 쓰는 초간단 루트 (가이드 보기)"):
                st.markdown("🔗 [Overleaf 로그인 바로가기](https://www.overleaf.com/login)")
                st.markdown(r"""
                BibTeX에서 .bib 파일은 참고문헌이 “출력된 결과물”이 아니라, 논문 정보가 정리되어 있는 데이터 파일에 해당한다. 그래서 .bib 파일을 그냥 열어서는 참고문헌 목록이 보이지 않고, 반드시 LaTeX 문서가 이 파일을 불러와 PDF로 출력해 주어야 한다. Overleaf를 사용하는 이유는 이 과정을 가장 간단하게 처리해 주기 때문이다.

                Overleaf에서는 먼저 새 프로젝트를 만들고, 기본으로 생성된 main.tex 파일과 함께 가지고 있는 .bib 파일을 같은 프로젝트 안에 업로드한다. 그다음 main.tex에서 본문을 작성하고, 문서의 끝부분, 즉 `\end{document}` 바로 위에 BibTeX 관련 코드를 추가한다. 이때 `\bibliography{references}`는 “references.bib라는 파일을 참고문헌 데이터로 사용하겠다”는 의미이고, 확장자 .bib는 쓰지 않는다. 만약 .bib 파일 안에 들어 있는 모든 논문을 한꺼번에 참고문헌으로 출력하고 싶다면 `\nocite{*}`를 함께 넣어 주면 된다.

                여기서 `\bibliographystyle{unsrt}`는 참고문헌의 출력 형식과 정렬 방식을 지정하는 역할을 한다. unsrt는 “정렬하지 않는다(unsorted)”는 뜻으로, 본문에서 인용된 순서 그대로 참고문헌을 나열하라는 의미다. 즉, 서론에서 처음 인용한 논문이 1번, 그다음에 인용한 논문이 2번이 되는 방식이다. 이 방식은 자연과학, 의생명 분야 논문이나 캡스톤 보고서에서 가장 흔히 쓰이며, 독자가 본문 흐름을 따라가면서 참고문헌을 확인하기 쉽다는 장점이 있다.

                이렇게 .bib 파일을 업로드하고, 문서 맨 아래에 `\bibliographystyle{unsrt}`와 `\bibliography{bib 파일 이름}`를 추가한 뒤 Recompile 버튼을 누르면, Overleaf가 LaTeX와 BibTeX를 자동으로 실행해 주고 PDF에 참고문헌 목록을 만들어 준다. 사용자는 컴파일 순서를 신경 쓸 필요가 없고, 파일 이름만 정확히 맞추면 된다.

                정리하면, Overleaf에서 BibTeX를 쓰는 핵심은 “.bib 파일은 데이터, .tex 파일은 이를 출력하는 도구”라는 점을 이해하고, 문서 끝에 참고문헌 스타일과 데이터 파일을 지정해 주는 것이다. `\bibliographystyle{unsrt}`는 그중에서도 “참고문헌을 어떤 규칙으로 보여줄지”를 정하는 중요한 한 줄이라고 보면 된다.
                """)
                st.code(r"""
\documentclass{article}
\usepackage{graphicx} % Required for inserting images
\title{Title}
\author{Name}
\date{Month Year}
\begin{document}
\maketitle
\section{Introduction}

#아래 3줄 복사 붙여넣기
======================
\nocite{*}
\bibliographystyle{unsrt}
\bibliography{bib파일 이름}
======================

\end{document}
""", language="latex")

            st.divider()
            col_sort, _ = st.columns([2, 5])
            with col_sort:
                inv_sort_opt = st.selectbox("정렬 방식", ["저장한 순서", "가치 높은 순서"])
            
            inv_list = st.session_state.inventory
            if inv_sort_opt == "가치 높은 순서":
                display_items = sorted(inv_list, key=lambda x: x.get('final_score', x.get('debiased_score', 0)), reverse=True)
            else:
                display_items = inv_list

            for i, paper in enumerate(display_items):
                p_id = paper['id']
                with st.container(border=True):
                    c1, c2 = st.columns([5, 2])
                    
                    # Left Column: Paper Info & Chart (Same as Search Tab)
                    with c1:
                        # Title
                        translated_title = get_translated_title(paper['title'])
                        display_title = highlight_text(paper['title']) if show_highlight else paper['title']
                        st.markdown(
                            f"""<div title="[번역] {translated_title}" style="font-size:1.2rem; font-weight:bold; margin-bottom:5px;">{display_title}</div>""", 
                            unsafe_allow_html=True
                        )
                        if show_translation:
                            st.caption(f"🇰🇷 {translated_title}")
                        
                        # Tags
                        tags = []
                        if paper['has_evidence']: tags.append("🔬 Evidence")
                        if paper['is_big_team']: tags.append("👥 Big Team")
                        if paper['integrity_status'] != "valid": tags.append("⚠️ 데이터 부족")
                        if paper['potential_type'] == "amazing": tags.append("💎 Hidden Gem")
                        st.write(" ".join([f"`{t}`" for t in tags]))
                        
                        # Meta Info
                        auth_display = ", ".join(paper['authors'])
                        if paper['author_full_count'] > 3: auth_display += f" 외 {paper['author_full_count'] - 3}명"
                        st.caption(f"{paper['year']} | {paper['journal']} | 인용 {paper['citations']}회 | 저자: {auth_display}")
                        st.markdown(f"[📄 원문 보기]({paper['url']})")

                        # Chart
                        with st.expander("점수 상세 구성 보기"):
                            details = paper.get('score_breakdown', {})
                            w_evidence = st.session_state.analysis_weights["evidence"]
                            w_team = st.session_state.analysis_weights["team"]
                            w_recency = st.session_state.analysis_weights["recency"]
                            w_scarcity = st.session_state.analysis_weights["scarcity"]
                            
                            chart_data = {
                                "Evidence (증거)": details.get('Evidence', 0) * w_evidence,
                                "Team (규모)": details.get('Team', 0) * w_team,
                                "Recency (최신성)": max(0, (5 - paper.get('age', 5)) * 10) * w_recency,
                                "Scarcity (희소성)": max(0, (50 - paper.get('citation_count', 0))) * w_scarcity,
                            }
                            st.bar_chart(chart_data, horizontal=True)

                    # Right Column: Metrics & Actions (Inventory Specific)
                    with c2:
                        # Base Metrics
                        col_raw, col_deb = st.columns(2)
                        # [Fixed] Safe access to dictionary keys
                        raw_s = paper.get('raw_score', 0)
                        deb_s = paper.get('debiased_score', 0)
                        bias_p = paper.get('bias_penalty', 0)
                        
                        with col_raw: st.metric("Impact", f"{raw_s}", help="현재 학계에서의 영향력")
                        with col_deb: st.metric("Potential", f"{deb_s}", delta=f"{-bias_p}", help="미래 가치")
                        if bias_p > 20: st.caption("⚠ 과열됨")
                        
                        st.divider()
                        
                        # Validation Status & Value
                        if paper['is_reviewed']:
                            status_emoji = "✅"
                            if paper['potential_type'] == "amazing": status_emoji = "✨ 대성공"
                            elif paper['potential_type'] == "bad": status_emoji = "💀 실패"
                            elif paper['potential_type'] == "verified_user": status_emoji = "🛡️ 사용자 승인"
                            
                            st.success(f"{status_emoji} (최종: {paper.get('final_score', 0)}점)")
                        else:
                            # Action Buttons for Unreviewed
                            if paper['integrity_status'] == "valid":
                                if st.button("🔬 심층 검증", key=f"rev_{p_id}", type="primary", use_container_width=True):
                                    paper['is_reviewed'] = True
                                    bonus = int(deb_s * 0.5)
                                    st.session_state.score += bonus
                                    paper['final_score'] = deb_s + bonus
                                    if paper['potential_type'] == 'amazing': st.toast(f"대박! 숨겨진 명작을 찾았습니다! (+{bonus})", icon="🎉")
                                    else: st.toast(f"검증이 완료되었습니다. (+{bonus})", icon="✅")
                                    save_user_data(st.session_state.user_id) 
                                    st.rerun()
                            else:
                                st.warning(paper['risk_reason'])
                                if st.button("강제 승인", key=f"force_{p_id}", use_container_width=True):
                                    paper['is_reviewed'] = True
                                    bonus = 10 
                                    st.session_state.score += bonus
                                    paper['final_score'] = deb_s + bonus
                                    paper['potential_type'] = "verified_user"
                                    paper['reason'] = "사용자 직접 확인으로 검증됨"
                                    save_user_data(st.session_state.user_id) 
                                    st.rerun()
                        
                        # Delete Button
                        if st.button("삭제", key=f"del_{p_id}", use_container_width=True):
                            deduction = paper.get('final_score', deb_s)
                            st.session_state.score = max(0, st.session_state.score - deduction)
                            st.session_state.inventory = [p for p in st.session_state.inventory if p['id'] != p_id]
                            st.session_state.trash.append(paper)
                            st.toast(f"논문 삭제. {deduction}점 차감됨", icon="🗑️")
                            save_user_data(st.session_state.user_id) 
                            st.rerun()

# ------------------------------------------------------------------------------
# [Tab 4] 휴지통 (Trash)
# ------------------------------------------------------------------------------
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
                translated_title = get_translated_title(paper['title'])
                display_title = highlight_text(paper['title']) if show_highlight else paper['title']
                st.markdown(
                    f"""<div title="[번역] {translated_title}" style="font-size:1rem; font-weight:bold; color:gray; margin-bottom:5px;">{display_title}</div>""", 
                    unsafe_allow_html=True
                )
                if show_translation: st.caption(f"🇰🇷 {translated_title}")
                st.caption(f"삭제됨 | {paper['journal']}")
                
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("복구", key=f"rest_{i}", use_container_width=True):
                        restored = st.session_state.trash.pop(i)
                        st.session_state.inventory.append(restored)
                        r_score = restored.get('final_score', restored.get('debiased_score', 0))
                        st.session_state.score += r_score
                        st.toast(f"복구 완료 (+{r_score}점)", icon="♻️")
                        save_user_data(st.session_state.user_id)
                        st.rerun()
                with c2:
                    if st.button("영구 삭제", key=f"pdel_{i}", use_container_width=True):
                        st.session_state.trash.pop(i)
                        st.toast("영구 삭제됨", icon="🔥")
                        save_user_data(st.session_state.user_id)
                        st.rerun()
