import streamlit as st
import requests
import datetime
import random
import time

# --- 1. 설정 및 상수 (Configuration) ---

MISSIONS = [
    {"id": 1, "text": "Top Tier 저널(Nature, Science 등) 논문 1편 수집", "type": "journal", "target": "top_tier", "count": 1, "reward": 150},
    {"id": 2, "text": "5인 이상 협업 연구(Team Science) 수집", "type": "team", "target": 5, "count": 1, "reward": 100},
    {"id": 3, "text": "함정 논문(참고문헌 부족 등) 피하기 (심층 검증 시 실패 0회)", "type": "avoid_trap", "target": "trap", "count": 0, "reward": 0},
    {"id": 4, "text": "연구 점수 1500점 달성하기", "type": "score", "target": 1500, "count": 1500, "reward": 500},
]

# 가상 데이터 (API 실패 시 백업용)
MOCK_DATABASE = [
    {"doi": "10.1038/nature12345", "title": "In vivo efficacy of novel immunotherapy", "citations": 12, "year": 2024, "journal": "Nature Medicine", "authors": ["Park", "Kim", "Lee", "Choi", "Smith"], "ref_count": 45},
    {"doi": "10.1126/science.54321", "title": "Deep Learning for Protein Folding", "citations": 5000, "year": 2020, "journal": "Science", "authors": ["AlphaTeam", "BetaTeam"], "ref_count": 60},
]

# --- 2. 핵심 로직 함수 (Core Logic) ---

def get_current_year():
    return datetime.datetime.now().year

def evaluate_paper(paper_data):
    """
    논문의 잠재적 가치를 평가하는 핵심 알고리즘
    v2.5 update: 메타데이터 결손(None)과 데이터 부족(Low Ref)을 구분
    """
    current_year = get_current_year()
    year = paper_data.get('year', current_year - 5)
    age = current_year - year
    title_lower = paper_data['title'].lower()
    citation_count = paper_data.get('citations', 0)
    
    # 1. 키워드 (Evidence)
    evidence_keywords = ['in vivo', 'in vitro', 'randomized', 'efficacy', 'mechanism', 'signaling', 'experiment', 'analysis', 'clinical']
    has_evidence = any(k in title_lower for k in evidence_keywords)
    
    # 2. 저널 권위 (Journal Prestige)
    top_journals = ['nature', 'science', 'cell', 'lancet', 'nejm', 'jama', 'ieee', 'pnas', 'advanced materials', 'cancer discovery']
    journal_lower = paper_data.get('journal', "").lower()
    is_top_tier = any(j in journal_lower for j in top_journals)

    # 3. 연구팀 규모 (Team Size)
    author_count = paper_data.get('author_count', 1)
    is_big_team = author_count >= 5
    is_solo = author_count == 1

    # 4. 참고문헌 수 확인 (Data Integrity Check)
    # API에서 키 자체가 없는 경우(None)와 0인 경우를 구분해야 함
    ref_count = paper_data.get('ref_count') 
    
    # 무결성 상태 판단
    integrity_status = "valid" # valid, uncertain, suspected
    risk_reason = ""

    if ref_count is None:
        integrity_status = "uncertain"
        risk_reason = "메타데이터 누락 (참고문헌 정보 없음)"
    elif ref_count < 10:
        # 참고문헌이 있긴 한데 너무 적음 -> 함정 의심
        integrity_status = "suspected"
        risk_reason = "참고문헌 수 부족 (데이터 빈약 의심)"

    # --- 점수 산정 로직 (Calculated Potential) ---
    # 함정 여부와 관계없이, 이 논문이 '진짜'라면 가질 수 있는 잠재력을 먼저 계산
    potential = 0
    potential_type = "normal"
    reasons = []

    # B. 숨겨진 명작 (Hidden Gem) 판별
    if citation_count < 50 and age <= 3:
        bonus = 0
        if has_evidence:
            bonus += 100
            reasons.append("실험적 근거(Evidence) 확보")
        if is_top_tier:
            bonus += 150
            reasons.append("Top Tier 저널 게재")
        if is_big_team:
            bonus += 50
            reasons.append("대규모 연구팀 참여")
        
        if bonus >= 200:
            potential = 300 + bonus
            potential_type = "amazing"
            reasons.insert(0, "최신 명작 발견!")
        elif bonus > 0:
            potential = 50 + bonus
            potential_type = "good"
        else:
            potential = 30
            potential_type = "normal"
            reasons.append("평이한 최신 연구")
            
    # C. 안전 자산 (Safe Asset)
    else:
        potential = 20
        if is_top_tier:
            potential += 50
            reasons.append("권위 있는 저널")
        if has_evidence:
            potential += 20
        potential_type = "good"
        reasons.append("이미 검증된 안전한 연구")

    if is_solo and not has_evidence and not is_top_tier:
        potential = max(0, potential - 20)
        reasons.append("단독 연구(데이터 부족 위험)")

    display_score = int(10 + (citation_count ** 0.5) * 2)
    reason_str = " / ".join(reasons) if reasons else "특이 사항 없음"

    return {
        "display_score": display_score,
        "potential": potential,       # 알고리즘이 판단한 잠재 점수
        "potential_type": potential_type,
        "reason": reason_str,
        "has_evidence": has_evidence,
        "is_top_tier": is_top_tier,
        "is_big_team": is_big_team,
        "integrity_status": integrity_status, # 데이터 신뢰성 상태
        "risk_reason": risk_reason    # 신뢰성 문제 사유
    }

def search_crossref_api(query):
    """
    Crossref API를 통해 실제 논문 데이터를 검색하고 필터링함
    """
    try:
        url = f"https://api.crossref.org/works?query={query}&rows=40&sort=relevance"
        response = requests.get(url, timeout=5)
        data = response.json()
    except Exception as e:
        return []

    if not data.get('message') or not data['message'].get('items'):
        return []

    items = data['message']['items']
    valid_papers = []
    current_year = get_current_year()

    for item in items:
        # 1. 필수 데이터 필터링
        if not item.get('DOI'): continue
        if not item.get('title'): continue
        if not item.get('author'): continue
        
        # 2. 제목 노이즈 필터링
        title = item['title'][0]
        title_lower = title.lower()
        if len(title) < 5: continue
        
        invalid_titles = [
            "announcement", "editorial", "issue info", "table of contents", 
            "front matter", "back matter", "author index", "subject index", 
            "correction", "erratum", "publisher's note", "conference info",
            "trial number", "trial registration", "clinicaltrials.gov", "identifier",
            "&na;", "unknown", "calendar", "masthead", "abstracts", "session",
            "meeting", "symposium", "workshop", "chinese journal", "test", 
            "protocol", "data descriptor", "dataset"
        ]
        
        if any(inv in title_lower for inv in invalid_titles): continue
        if "&na;" in title_lower: continue

        # 3. 저자 유효성 검사
        authors_raw = item['author']
        valid_authors = []
        for a in authors_raw:
            given = a.get('given', '').strip()
            family = a.get('family', '').strip()
            full_name = f"{given} {family}".strip()
            if full_name and "&na;" not in full_name.lower() and "anonymous" not in full_name.lower():
                valid_authors.append(full_name)
        
        if not valid_authors: continue

        # 메타데이터 추출
        citations = item.get('is-referenced-by-count', 0)
        journal = item.get('container-title', ["Unknown Journal"])[0]
        
        # [수정] reference-count 키가 아예 없으면 None 반환
        ref_count = item.get('reference-count') 
        
        pub_year = current_year - 5
        if item.get('published') and item['published'].get('date-parts'):
             pub_year = item['published']['date-parts'][0][0]
        elif item.get('created') and item['created'].get('date-parts'):
             pub_year = item['created']['date-parts'][0][0]

        # 평가 실행
        paper_data_for_eval = {
            'title': title, 'year': pub_year, 'citations': citations, 
            'journal': journal, 'author_count': len(valid_authors), 'ref_count': ref_count
        }
        eval_result = evaluate_paper(paper_data_for_eval)

        # 결과 객체 생성
        paper_obj = {
            'id': item['DOI'],
            'title': title,
            'authors': valid_authors[:3], # 3명까지만 표시
            'author_count': len(valid_authors),
            'journal': journal,
            'year': pub_year,
            'citations': citations,
            'ref_count': ref_count if ref_count is not None else 0, # 표시는 0으로 하되 내부 로직은 None 인지함
            'url': f"https://doi.org/{item['DOI']}",
            **eval_result,
            'is_reviewed': False
        }
        valid_papers.append(paper_obj)
    
    # 평가 점수(잠재력 + 기본 점수)가 높은 순서대로 정렬하여 상위 추천
    valid_papers.sort(key=lambda x: x['potential'] + x['display_score'], reverse=True)
            
    return valid_papers[:10] # 상위 10개 반환

# --- 3. Streamlit UI ---

# 페이지 설정
st.set_page_config(page_title="Research Simulator", page_icon="🎓", layout="wide")

# 세션 상태 초기화
if 'score' not in st.session_state:
    st.session_state.score = 0
if 'inventory' not in st.session_state:
    st.session_state.inventory = []
if 'mission_id' not in st.session_state:
    st.session_state.mission_id = 1
if 'search_results' not in st.session_state:
    st.session_state.search_results = []

# 점수 기반 레벨 및 게이지 계산 함수
def get_level_info(score):
    level_threshold = 500  # 레벨업 기준 점수
    level = (score // level_threshold) + 1
    progress = (score % level_threshold) / level_threshold
    next_milestone = (level) * level_threshold
    return level, progress, next_milestone

# 미션 체크 함수
def check_mission(paper, action):
    current_m = next((m for m in MISSIONS if m['id'] == st.session_state.mission_id), None)
    if not current_m: return

    completed = False
    m_type = current_m['type']
    
    if m_type == "journal" and action == "collect" and paper['is_top_tier']:
        completed = True
    elif m_type == "team" and action == "collect" and paper['is_big_team']:
        completed = True
    elif m_type == "score" and st.session_state.score >= current_m['target']:
        completed = True
    
    if completed:
        st.session_state.score += current_m['reward']
        st.session_state.mission_id += 1
        st.toast(f"🎉 미션 완료! 보상 +{current_m['reward']}점", icon="🎁")

# 사이드바 (정보 패널)
with st.sidebar:
    st.title("🎓 연구 시뮬레이터")
    st.caption("Outlier Hunter Edition")
    
    # 학위 대신 레벨 및 게이지 바 표시
    current_level, progress, next_score = get_level_info(st.session_state.score)
    
    st.divider()
    
    st.metric("현재 레벨", f"Lv. {current_level}")
    st.metric("연구 점수", f"{st.session_state.score} / {next_score}")
    
    st.write("다음 레벨까지:")
    st.progress(progress)
    
    st.metric("수집한 논문", f"{len(st.session_state.inventory)}편")
    
    st.divider()
    
    # 미션 표시
    current_mission = next((m for m in MISSIONS if m['id'] == st.session_state.mission_id), None)
    if current_mission:
        st.info(f"🎯 현재 미션\n\n{current_mission['text']}")
        st.caption(f"보상: {current_mission['reward']}점")
    else:
        st.success("🏆 모든 미션을 완료했습니다!")

    st.divider()
    st.markdown("""
    💡 평가 가이드
    - 증거 적합성 지표 (Evidence Index) : 제목에 실험적 검증(in vivo, clinical 등)을 암시하는 구체적인 단어 포함
    - 저널 권위 지표 (Prestige Index) : Nature, Science 등 학계에서 인정받는 최상위 저널
    - 연구 규모 지표 (Collaboration Index) : 참여 저자 수 다수(5인 이상)가 참여한 연구 우대
    - 데이터 신뢰도 지표 (Reliability Index) : 참고 문헌 수를 확인하여 연구의 깊이를 1차적으로 거릅니다. 참고 문헌이 너무 적으면 정식 논문이 아닌 초록이나 단순 투고일 가능성이 높아 배제합니다.
    - 시의성 대비 인용 지표 (Opportunity Index) : 발행 시점과 인용 수의 상관관계를 분석하여 숨겨진 가치를 찾습니다. 최신이면서 인용이 적은 연구는 기회(Opportunity)로, 오래되었는데 인용이 없는 연구는 함정(Trap)으로 분류합니다.
    """)

# 메인 화면 (탭 구성)
tab_search, tab_inventory = st.tabs(["🔍 논문 검색", "📚 내 서재"])

# --- 탭 1: 논문 검색 ---
with tab_search:
    st.header("학술 논문 검색")
    
    col_s1, col_s2 = st.columns([4, 1])
    with col_s1:
        query = st.text_input("연구 주제 키워드 (예: Immunotherapy, Quantum)", placeholder="관심 연구 분야를 입력하세요...")
    with col_s2:
        st.write("")
        st.write("") 
        search_btn = st.button("검색 시작", type="primary", use_container_width=True)

    if search_btn and query:
        with st.spinner("전 세계 학술 데이터베이스(Crossref) 탐색 중..."):
            results = search_crossref_api(query)
            st.session_state.search_results = results
            
            if not results:
                st.error("검색 결과가 없습니다. 다른 키워드로 시도해보세요.")

    if st.session_state.search_results:
        st.subheader(f"검색 결과 ({len(st.session_state.search_results)}건)")
        
        for i, paper in enumerate(st.session_state.search_results):
            with st.container(border=True):
                c1, c2 = st.columns([5, 1])
                
                with c1:
                    badges = []
                    if paper['is_top_tier']: badges.append("Top Tier")
                    if paper['has_evidence']: badges.append("Evidence")
                    if paper['is_big_team']: badges.append("Big Team")
                    
                    # 경고 뱃지 추가 (검색 단계에서 미리 경고)
                    if paper['integrity_status'] == "uncertain":
                        badges.append("⚠️ 정보 부족")
                    elif paper['integrity_status'] == "suspected":
                        badges.append("⚠️ 의심됨")
                    
                    badge_html = " ".join([f"<span style='background:#e0e7ff; color:#4338ca; padding:2px 6px; border-radius:4px; font-size:0.8em; font-weight:bold;'>{b}</span>" for b in badges])
                    
                    st.markdown(f"{paper['title']} {badge_html}", unsafe_allow_html=True)
                    st.caption(f"{paper['year']} | {paper['journal']} | 인용 {paper['citations']}회 | 저자: {', '.join(paper['authors'])} 등")
                    st.markdown(f"[원문 페이지 방문]({paper['url']})", unsafe_allow_html=True)

                with c2:
                    st.write(f"예상 +{paper['display_score']}")
                    is_owned = any(p['id'] == paper['id'] for p in st.session_state.inventory)
                    if is_owned:
                        st.button("보유중", key=f"btn_owned_{i}", disabled=True)
                    else:
                        if st.button("수집하기", key=f"btn_collect_{i}", type="secondary"):
                            st.session_state.inventory.append(paper)
                            st.session_state.score += paper['display_score']
                            check_mission(paper, "collect")
                            st.rerun()

# --- 탭 2: 내 서재 ---
with tab_inventory:
    st.header(f"내 서재 ({len(st.session_state.inventory)}편)")
    
    if not st.session_state.inventory:
        st.info("아직 수집된 논문이 없습니다. 검색 탭에서 논문을 찾아보세요.")
    
    cols = st.columns(2)
    
    for i, paper in enumerate(st.session_state.inventory):
        col_idx = i % 2
        with cols[col_idx]:
            with st.container(border=True):
                # 검증 상태 아이콘
                status_icon = "❓ 미검증"
                if paper['is_reviewed']:
                    if paper['potential_type'] == "amazing": status_icon = "✨ 대성공"
                    elif paper['potential_type'] == "bad": status_icon = "⚠️ 실패"
                    elif paper['potential_type'] == "verified_user": status_icon = "🕵️ 사용자 승인"
                    else: status_icon = "✅ 검증됨"

                st.markdown(f"#### {paper['title']}")
                st.caption(f"{status_icon} | {paper['journal']} ({paper['year']})")
                
                b_col1, b_col2 = st.columns([1, 1])

                with b_col2:
                    if st.button("🗑️ 삭제", key=f"del_{i}", use_container_width=True, type="secondary"):
                        deduction = paper.get('final_score', paper['display_score'])
                        st.session_state.score = max(0, st.session_state.score - deduction)
                        st.session_state.inventory.pop(i)
                        st.toast(f"논문이 삭제되었습니다. 점수가 차감됩니다 (-{deduction})", icon="🗑️")
                        st.rerun()

                with b_col1:
                    if not paper['is_reviewed']:
                        # [핵심 로직 변경] 무결성 상태에 따른 버튼 분기
                        if paper['integrity_status'] == "valid":
                            # 정상적인 경우 -> 알고리즘 검증
                            if st.button("🔬 심층 검증", key=f"review_{i}", use_container_width=True, type="primary"):
                                st.session_state.inventory[i]['is_reviewed'] = True
                                bonus = paper['potential']
                                st.session_state.score += bonus
                                st.session_state.inventory[i]['final_score'] = paper['display_score'] + bonus
                                
                                if paper['potential_type'] == 'amazing':
                                    st.toast(f"대박 발견! {paper['reason']} (+{bonus})", icon="🎉")
                                else:
                                    st.toast(f"검증 완료. {paper['reason']} (+{bonus})", icon="✅")
                                st.rerun()
                        else:
                            # 정보 부족/함정 의심 -> 경고 및 사용자 개입
                            st.warning(f"{paper['risk_reason']}")
                            if st.button("🔍 수동 검증 (강제 승인)", key=f"override_{i}", use_container_width=True):
                                st.session_state.inventory[i]['is_reviewed'] = True
                                # 강제 승인 시 원래 잠재력 점수 획득 (혹은 페널티 없는 점수)
                                bonus = paper['potential']
                                st.session_state.score += bonus
                                st.session_state.inventory[i]['final_score'] = paper['display_score'] + bonus
                                st.session_state.inventory[i]['potential_type'] = "verified_user"
                                st.session_state.inventory[i]['reason'] = "사용자 직접 확인으로 검증됨"
                                
                                st.toast(f"사용자 검증 완료! 점수 획득 (+{bonus})", icon="🛡️")
                                st.rerun()
                            
                            # 함정으로 인정하고 폐기하는 버튼 (선택 사항)
                            # if st.button("확인 (폐기)", ...) -> 삭제 로직과 유사
                    else:
                        st.button("완료됨", key=f"done_{i}", disabled=True, use_container_width=True)

                # 원문 바로가기 버튼
                st.link_button("📄 원문 보기", paper['url'], use_container_width=True)

                if paper['is_reviewed']:
                    if paper['potential_type'] == "amazing":
                        st.success(f"Hidden Gem!\n\n{paper['reason']}")
                        st.markdown(f"추가 점수: +{paper['potential']}")
                    elif paper['potential_type'] == "bad":
                        st.error(f"Trap!\n\n{paper['reason']}")
                        st.markdown("추가 점수: 0")
                    elif paper['potential_type'] == "verified_user":
                        st.info(f"User Verified\n\n{paper['reason']}")
                        st.markdown(f"추가 점수: +{paper['potential']}")
                    else:
                        st.info(f"Verified\n\n{paper['reason']}")
                        st.markdown(f"추가 점수: +{paper['potential']}")
                    
                    st.caption(f"최종 획득 점수: {paper.get('final_score', paper['display_score'])}")

