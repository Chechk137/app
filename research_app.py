import streamlit as st
import requests
import datetime
import random
import time

# --- 1. 설정 및 상수 ---

MISSIONS = [
    {"id": 1, "text": "Top Tier 저널(Nature, Science 등) 논문 1편 수집", "type": "journal", "target": "top_tier", "count": 1, "reward": 150},
    {"id": 2, "text": "5인 이상 협업 연구(Team Science) 수집", "type": "team", "target": 5, "count": 1, "reward": 100},
    {"id": 3, "text": "함정 논문(참고문헌 부족 등) 피하기", "type": "avoid_trap", "target": "trap", "count": 0, "reward": 0},
    {"id": 4, "text": "연구 점수 1500점 달성하기", "type": "score", "target": 1500, "count": 1500, "reward": 500},
]

# --- 2. 핵심 로직 함수 ---

def get_current_year():
    return datetime.datetime.now().year

def evaluate_paper(paper_data):
    """
    논문의 잠재적 가치를 평가하는 핵심 알고리즘
    """
    current_year = get_current_year()
    year = paper_data.get('year', current_year - 5)
    age = current_year - year
    title_lower = paper_data['title'].lower()
    citation_count = paper_data.get('citations', 0)
    
    # 1. 키워드 (Evidence)
    evidence_keywords = [
        'in vivo', 'in vitro', 'randomized', 'efficacy', 'mechanism', 'signaling', 
        'experiment', 'analysis', 'clinical', 'activity', 'synthesis', 'design', 
        'evaluation', 'characterization', 'properties', 'performance', 'application'
    ]
    has_evidence = any(k in title_lower for k in evidence_keywords)
    
    # 2. 저널 권위 (Journal Prestige)
    top_journals = ['nature', 'science', 'cell', 'lancet', 'nejm', 'jama', 'ieee', 'pnas', 'advanced materials', 'cancer discovery', 'chem', 'acs', 'angewandte']
    journal_lower = paper_data.get('journal', "").lower()
    is_top_tier = any(j in journal_lower for j in top_journals)

    # 3. 연구팀 규모 (Team Size)
    author_count = paper_data.get('author_count', 1)
    is_big_team = author_count >= 5
    is_solo = author_count == 1

    # 4. 참고문헌 수 (Reference Depth)
    ref_count = paper_data.get('ref_count') 
    
    integrity_status = "valid" 
    risk_reason = ""

    if ref_count is None:
        if citation_count < 5 and not is_top_tier:
            integrity_status = "uncertain"
            risk_reason = "메타데이터 누락 (참고문헌 정보 없음)"
    elif ref_count < 5:
        if citation_count < 5 and not is_top_tier:
            integrity_status = "suspected"
            risk_reason = "참고문헌 수 부족 (데이터 빈약 의심)"

    potential = 0
    potential_type = "normal"
    reasons = []

    # --- 점수 산정 로직 ---
    if integrity_status == "suspected":
        potential = 0
        potential_type = "bad"
        reasons.append("데이터 신뢰도 낮음")
    elif age > 10 and citation_count < 5:
        potential = 0
        potential_type = "bad"
        reasons.append("오래되고 인용 없는 도태된 연구")
    elif citation_count < 50 and age <= 3:
        bonus = 0
        if has_evidence:
            bonus += 100
            reasons.append("실험적 근거(Evidence)")
        if is_top_tier:
            bonus += 150
            reasons.append("Top Tier 저널")
        if is_big_team:
            bonus += 50
            reasons.append("대규모 연구팀")
        
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
    else:
        potential = 20
        if is_top_tier:
            potential += 50
            reasons.append("권위 있는 저널")
        if has_evidence:
            potential += 30
        potential_type = "good"
        reasons.append("이미 검증된 안전한 연구")

    if is_solo and not has_evidence and not is_top_tier:
        potential = max(0, potential - 20)
        reasons.append("단독 연구(데이터 부족 위험)")

    display_score = int(10 + (citation_count ** 0.5) * 2)
    
    # [수정] AI 분석 점수(AI Score) 계산 추가
    total_estimated_value = potential + display_score
    ai_score = min(100, int((total_estimated_value / 400) * 100))

    reason_str = ", ".join(reasons) if reasons else "특이 사항 없음"

    return {
        "display_score": display_score,
        "potential": potential,
        "potential_type": potential_type,
        "ai_score": ai_score, # [Fix] AI Score 추가
        "reason": reason_str,
        "has_evidence": has_evidence,
        "is_top_tier": is_top_tier,
        "is_big_team": is_big_team,
        "integrity_status": integrity_status,
        "risk_reason": risk_reason
    }

def search_crossref_api(query):
    try:
        url = f"https://api.crossref.org/works?query={query}&rows=40&sort=relevance"
        response = requests.get(url, timeout=5)
        data = response.json()
    except Exception as e:
        st.error("API 연결 중 오류가 발생했습니다.")
        return []

    if not data.get('message') or not data['message'].get('items'):
        return []

    items = data['message']['items']
    valid_papers = []
    current_year = get_current_year()

    for item in items:
        if not item.get('DOI'): continue
        if not item.get('title'): continue
        if not item.get('author'): continue
        
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

        authors_raw = item['author']
        valid_authors = []
        for a in authors_raw:
            given = a.get('given', '').strip()
            family = a.get('family', '').strip()
            full_name = f"{given} {family}".strip()
            if full_name and "&na;" not in full_name.lower() and "anonymous" not in full_name.lower():
                valid_authors.append(full_name)
        
        if not valid_authors: continue

        citations = item.get('is-referenced-by-count', 0)
        journal = item.get('container-title', ["Unknown Journal"])[0]
        ref_count = item.get('reference-count')
        
        pub_year = current_year - 5
        if item.get('published') and item['published'].get('date-parts'):
             pub_year = item['published']['date-parts'][0][0]
        elif item.get('created') and item['created'].get('date-parts'):
             pub_year = item['created']['date-parts'][0][0]

        paper_data_for_eval = {
            'title': title, 'year': pub_year, 'citations': citations, 
            'journal': journal, 'author_count': len(valid_authors), 'ref_count': ref_count
        }
        eval_result = evaluate_paper(paper_data_for_eval)

        paper_obj = {
            'id': item['DOI'],
            'title': title,
            'authors': valid_authors[:3], 
            'author_full_count': len(valid_authors),
            'journal': journal,
            'year': pub_year,
            'citations': citations,
            'ref_count': ref_count if ref_count is not None else 0,
            'url': f"https://doi.org/{item['DOI']}",
            **eval_result,
            'is_reviewed': False
        }
        valid_papers.append(paper_obj)
    
    # [Fix] AI Score 기준으로 정렬
    valid_papers.sort(key=lambda x: x['ai_score'], reverse=True)
            
    return valid_papers[:12]

# --- 3. Streamlit UI ---

st.set_page_config(page_title="Research Simulator", page_icon="🎓", layout="wide")

if 'score' not in st.session_state:
    st.session_state.score = 0
if 'inventory' not in st.session_state:
    st.session_state.inventory = []
if 'mission_id' not in st.session_state:
    st.session_state.mission_id = 1
if 'search_results' not in st.session_state:
    st.session_state.search_results = []

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

with st.sidebar:
    st.title("🎓 연구 시뮬레이터")
    st.caption("Evidence-Based Analysis")
    
    current_level, progress, next_score = get_level_info(st.session_state.score)
    
    st.divider()
    
    st.metric("연구 레벨", f"Lv. {current_level}")
    st.write(f"현재 점수: {st.session_state.score} / {next_score}")
    st.progress(progress)
    
    st.divider()
    
    st.metric("보유 논문", f"{len(st.session_state.inventory)}편")
    
    current_mission = next((m for m in MISSIONS if m['id'] == st.session_state.mission_id), None)
    if current_mission:
        st.info(f"🎯 미션: {current_mission['text']}")
    else:
        st.success("🏆 모든 미션 완료!")

    st.divider()
    st.markdown("#### 📊 평가 가이드")
    st.markdown("""
    1. **증거 적합성 (Evidence)**
       : in vivo, efficacy 등 실험 키워드 포함
    2. **저널 권위 (Prestige)**
       : Nature, Science 등 Top Tier 저널
    3. **연구 규모 (Collaboration)**
       : 저자 5인 이상 참여
    4. **데이터 신뢰도 (Reliability)**
       : 참고문헌 수 10개 이상 (함정 주의)
    5. **시의성/인용 (Opportunity)**
       : 최신+저인용은 기회, 과거+무인용은 함정
    """)

tab_search, tab_inventory = st.tabs(["🔍 논문 검색", "📚 내 서재"])

with tab_search:
    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input("키워드 입력", placeholder="Immunotherapy, Quantum Computing...")
    with col2:
        st.write("")
        st.write("")
        search_btn = st.button("검색", type="primary", use_container_width=True)

    if search_btn and query:
        with st.spinner("논문 데이터 분석 중..."):
            results = search_crossref_api(query)
            st.session_state.search_results = results
            if not results:
                st.error("검색 결과가 없습니다.")

    if st.session_state.search_results:
        st.caption(f"AI 추천 순으로 정렬된 결과 {len(st.session_state.search_results)}건")
        
        for i, paper in enumerate(st.session_state.search_results):
            with st.container(border=True):
                c1, c2 = st.columns([5, 1.5])
                
                with c1:
                    st.progress(paper['ai_score'] / 100, text=f"AI 추천 지수: {paper['ai_score']}점")
                    
                    st.markdown(f"### {paper['title']}")
                    
                    tags = []
                    if paper['is_top_tier']: tags.append("👑 Top Tier")
                    if paper['has_evidence']: tags.append("🔬 Evidence")
                    if paper['is_big_team']: tags.append("👥 Big Team")
                    if paper['integrity_status'] != "valid": tags.append("⚠️ 검증 필요")
                    
                    st.write(" ".join([f"`{t}`" for t in tags]))
                    
                    auth_display = ", ".join(paper['authors'])
                    if paper['author_full_count'] > 3:
                        auth_display += f" 외 {paper['author_full_count'] - 3}명"
                    
                    st.caption(f"{paper['year']} | {paper['journal']} | 인용 {paper['citations']}회 | 저자: {auth_display}")
                    st.markdown(f"[📄 원문 보기]({paper['url']})")

                with c2:
                    st.metric("기본 보상", f"+{paper['display_score']}")
                    
                    is_owned = any(p['id'] == paper['id'] for p in st.session_state.inventory)
                    if is_owned:
                        st.button("보유중", key=f"owned_{i}", disabled=True, use_container_width=True)
                    else:
                        if st.button("수집하기", key=f"collect_{i}", type="secondary", use_container_width=True):
                            st.session_state.inventory.append(paper)
                            st.session_state.score += paper['display_score']
                            check_mission(paper, "collect")
                            st.rerun()

with tab_inventory:
    if not st.session_state.inventory:
        st.info("수집된 논문이 없습니다.")
    
    cols = st.columns(2)
    for i, paper in enumerate(st.session_state.inventory):
        with cols[i % 2]:
            with st.container(border=True):
                status_emoji = "❓"
                status_text = "미검증"
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
                                bonus = paper['potential']
                                st.session_state.score += bonus
                                st.session_state.inventory[i]['final_score'] = paper['display_score'] + bonus
                                
                                if paper['potential_type'] == 'amazing':
                                    st.toast("대박! 숨겨진 명작을 찾았습니다!", icon="🎉")
                                else:
                                    st.toast("검증이 완료되었습니다.", icon="✅")
                                st.rerun()
                        else:
                            st.warning(paper['risk_reason'])
                            if st.button("강제 승인", key=f"force_{i}", use_container_width=True):
                                st.session_state.inventory[i]['is_reviewed'] = True
                                bonus = paper['potential']
                                st.session_state.score += bonus
                                st.session_state.inventory[i]['final_score'] = paper['display_score'] + bonus
                                st.session_state.inventory[i]['potential_type'] = "verified_user"
                                st.session_state.inventory[i]['reason'] = "사용자 직접 확인으로 검증됨"
                                st.rerun()
                    else:
                        st.success(f"획득: {paper.get('final_score', 0)}점")

                with c_btn2:
                    if st.button("삭제", key=f"del_{i}", use_container_width=True):
                        deduction = paper.get('final_score', paper['display_score'])
                        st.session_state.score = max(0, st.session_state.score - deduction)
                        st.session_state.inventory.pop(i)
                        st.toast(f"논문 삭제. {deduction}점 차감됨", icon="🗑️")
                        st.rerun()
                
                st.markdown(f"[📄 원문 보기]({paper['url']})")
                
                if paper['is_reviewed']:
                    st.info(f"분석 결과: {paper['reason']}")
