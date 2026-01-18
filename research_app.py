import streamlit as st
import requests
import datetime
import random
import time
import json
import os
import math

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

# --- 2. 데이터 관리 함수 (저장/로드) ---

def load_user_data(user_id):
    file_path = os.path.join(DATA_DIR, f"{user_id}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 데이터 구조 호환성을 위해 없는 키는 기본값으로 처리
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

def evaluate_paper(paper_data):
    current_year = get_current_year()
    year = paper_data.get('year', current_year - 5)
    age = current_year - year
    title_lower = paper_data['title'].lower()
    citation_count = paper_data.get('citations', 0)
    
    evidence_keywords = [
        'in vivo', 'in vitro', 'randomized', 'efficacy', 'mechanism', 'signaling', 
        'experiment', 'analysis', 'clinical', 'activity', 'synthesis', 'design', 
        'evaluation', 'characterization', 'properties', 'performance', 'application'
    ]
    has_evidence = any(k in title_lower for k in evidence_keywords)
    
    top_journals = ['nature', 'science', 'cell', 'lancet', 'nejm', 'jama', 'ieee', 'pnas', 'advanced materials', 'cancer discovery', 'chem', 'acs', 'angewandte']
    journal_lower = paper_data.get('journal', "").lower()
    is_top_tier = any(j in journal_lower for j in top_journals)

    author_count = paper_data.get('author_count', 1)
    is_big_team = author_count >= 5
    is_solo = author_count == 1

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

    # 점수 산정 로직
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
    total_estimated_value = potential + display_score
    ai_score = min(100, int((total_estimated_value / 400) * 100))

    reason_str = ", ".join(reasons) if reasons else "특이 사항 없음"

    return {
        "display_score": display_score,
        "potential": potential,
        "potential_type": potential_type,
        "ai_score": ai_score,
        "reason": reason_str,
        "has_evidence": has_evidence,
        "is_top_tier": is_top_tier,
        "is_big_team": is_big_team,
        "integrity_status": integrity_status,
        "risk_reason": risk_reason
    }

def search_crossref_api(query):
    # 따옴표 검색 감지
    is_exact_mode = query.startswith('"') and query.endswith('"')
    clean_query = query.strip('"') if is_exact_mode else query
    
    try:
        # 대량 수집 (rows=1000)
        url = f"https://api.crossref.org/works?query={clean_query}&rows=1000&sort=relevance"
        response = requests.get(url, timeout=20)
        data = response.json()
    except Exception as e:
        st.error(f"API 연결 중 오류가 발생했습니다: {e}")
        return [], False

    if not data.get('message') or not data['message'].get('items'):
        return [], False

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
    
    if not is_exact_mode:
        valid_papers.sort(key=lambda x: x['ai_score'], reverse=True)
            
    # 전체 리스트 반환 (페이지네이션은 UI에서 처리)
    return valid_papers, is_exact_mode

# --- 3. Streamlit UI ---

st.set_page_config(page_title="Research Simulator", page_icon="🎓", layout="wide")

# 세션 상태 초기화
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None
if 'score' not in st.session_state:
    st.session_state['score'] = 0
if 'inventory' not in st.session_state:
    st.session_state['inventory'] = []
if 'trash' not in st.session_state:
    st.session_state['trash'] = []
if 'mission_id' not in st.session_state:
    st.session_state['mission_id'] = 1
if 'search_results' not in st.session_state:
    st.session_state['search_results'] = []
# 페이지네이션 상태
if 'search_page' not in st.session_state:
    st.session_state['search_page'] = 1

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
        if st.session_state.get("user_id"):
            save_user_data(st.session_state.user_id)

# 모바일 대응: 로그인 전 화면
if not st.session_state.get("user_id"):
    st.title("🎓 AI 기반 논문 추천 시스템")
    st.caption("캡스톤 디자인 _ AI:D")
    st.markdown("---")
    st.markdown("### 👋 환영합니다!")
    st.info("연구자 ID를 입력하여 검색을 시작하세요.")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        user_input = st.text_input("연구자 이름 (ID)", placeholder="예: Dr.Kim")
    with col2:
        st.write("")
        st.write("")
        login_btn = st.button("로그인 / 시작", type="primary", use_container_width=True)
    
    if login_btn:
        if user_input:
            st.session_state.user_id = user_input
            saved_data = load_user_data(user_input)
            st.session_state.score = saved_data["score"]
            st.session_state.inventory = saved_data["inventory"]
            st.session_state.mission_id = saved_data["mission_id"]
            st.session_state.trash = saved_data["trash"]
            st.success(f"{user_input}님으로 로그인되었습니다.")
            st.rerun()
        else:
            st.warning("이름을 입력해주세요.")
    st.stop() 

# --- 로그인 후 사이드바 ---
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

tab_search, tab_inventory, tab_trash = st.tabs(["🔍 논문 검색", "📚 내 서재", "🗑️ 휴지통"])

with tab_search:
    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input("키워드 입력", placeholder='예: "Immunotherapy" (따옴표는 정확도순)')
    with col2:
        st.write("")
        st.write("")
        search_btn = st.button("검색", type="primary", use_container_width=True)

    if search_btn and query:
        with st.spinner("논문 데이터 대량 분석 중... (최대 1000건)"):
            results, is_exact = search_crossref_api(query)
            st.session_state.search_results = results
            st.session_state.is_exact_search = is_exact
            st.session_state.search_page = 1 # 검색 시 페이지 초기화
            if not results:
                st.error("검색 결과가 없습니다.")

    if st.session_state.search_results:
        # 페이지네이션 로직 적용
        items_per_page = 50
        total_items = len(st.session_state.search_results)
        total_pages = max(1, math.ceil(total_items / items_per_page))
        current_page = st.session_state.search_page

        start_idx = (current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        # 현재 페이지 데이터 슬라이싱
        page_items = st.session_state.search_results[start_idx:end_idx]

        count = total_items
        sort_mode = "정확도(Relevance) 순" if st.session_state.is_exact_search else "AI 추천(Potential) 순"
        st.caption(f"검색 결과 총 {count}건 ({sort_mode}) | 현재 페이지: {current_page}/{total_pages}")
        
        for i, paper in enumerate(page_items):
            # 고유 키 생성 (페이지 인덱스 반영)
            unique_key_idx = start_idx + i
            
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
                        st.button("보유중", key=f"owned_{unique_key_idx}", disabled=True, use_container_width=True)
                    else:
                        if st.button("수집하기", key=f"collect_{unique_key_idx}", type="secondary", use_container_width=True):
                            st.session_state.inventory.append(paper)
                            st.session_state.score += paper['display_score']
                            check_mission(paper, "collect")
                            save_user_data(st.session_state.user_id) 
                            st.rerun()
        
        # 페이지네이션 컨트롤러 (중앙 정렬 + 좁은 간격)
        st.divider()
        
        # 전체를 감싸는 컬럼을 사용하여 화면 중앙에 배치
        _, nav_col, _ = st.columns([1, 5, 1])
        
        with nav_col:
            # 페이지 번호 계산
            if total_pages <= 5:
                display_pages = range(1, total_pages + 1)
            else:
                if current_page <= 3:
                    display_pages = range(1, 6)
                elif current_page >= total_pages - 2:
                    display_pages = range(total_pages - 4, total_pages + 1)
                else:
                    display_pages = range(current_page - 2, current_page + 3)

            # 버튼들을 한 줄에 좁은 간격(small)으로 배치
            pg_cols = st.columns([1, 1, 1, 1, 1, 1, 1, 0.5, 2.5], gap="small")
            
            # Prev Button
            with pg_cols[0]:
                if st.button("◀", key="nav_prev", disabled=current_page==1, use_container_width=True):
                    st.session_state.search_page -= 1
                    st.rerun()
            
            # Page Number Buttons
            for idx, p_num in enumerate(display_pages):
                if idx < 5:
                    with pg_cols[idx + 1]:
                        b_type = "primary" if p_num == current_page else "secondary"
                        if st.button(f"{p_num}", key=f"nav_p_{p_num}", type=b_type, use_container_width=True):
                            st.session_state.search_page = p_num
                            st.rerun()
            
            # Next Button
            with pg_cols[6]:
                if st.button("▶", key="nav_next", disabled=current_page==total_pages, use_container_width=True):
                    st.session_state.search_page += 1
                    st.rerun()
                    
            # Direct Input
            with pg_cols[8]:
                 new_page = st.number_input("이동", min_value=1, max_value=total_pages, value=current_page, label_visibility="collapsed", key="nav_input")
                 if new_page != current_page:
                    st.session_state.search_page = new_page
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
                                save_user_data(st.session_state.user_id) 
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
                                save_user_data(st.session_state.user_id) 
                                st.rerun()
                    else:
                        st.success(f"획득: {paper.get('final_score', 0)}점")

                with c_btn2:
                    if st.button("삭제", key=f"del_{i}", use_container_width=True):
                        # 삭제 로직: 점수 차감 후 휴지통 이동
                        deduction = paper.get('final_score', paper['display_score'])
                        st.session_state.score = max(0, st.session_state.score - deduction)
                        
                        removed_paper = st.session_state.inventory.pop(i)
                        st.session_state.trash.append(removed_paper) # 휴지통으로 이동
                        
                        st.toast(f"논문이 휴지통으로 이동되었습니다. {deduction}점 차감됨", icon="🗑️")
                        save_user_data(st.session_state.user_id) 
                        st.rerun()
                
                st.markdown(f"[📄 원문 보기]({paper['url']})")
                
                if paper['is_reviewed']:
                    st.info(f"분석 결과: {paper['reason']}")

with tab_trash:
    if not st.session_state.trash:
        st.info("휴지통이 비어있습니다.")
    
    if st.session_state.trash:
        if st.button("휴지통 비우기 (전체 삭제)", type="primary"):
            st.session_state.trash = []
            save_user_data(st.session_state.user_id)
            st.toast("휴지통을 비웠습니다.", icon="🧹")
            st.rerun()

    cols = st.columns(2)
    for i, paper in enumerate(st.session_state.trash):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"**{paper['title']}**")
                st.caption(f"삭제됨 | {paper['journal']}")
                
                col_res, col_del = st.columns(2)
                
                with col_res:
                    if st.button("복구", key=f"restore_{i}", use_container_width=True):
                        restored_paper = st.session_state.trash.pop(i)
                        st.session_state.inventory.append(restored_paper)
                        
                        # 복구 시 점수 다시 부여 (실수 방지 차원)
                        restore_score = restored_paper.get('final_score', restored_paper['display_score'])
                        st.session_state.score += restore_score
                        
                        st.toast(f"논문이 복구되었습니다. (+{restore_score}점)", icon="♻️")
                        save_user_data(st.session_state.user_id)
                        st.rerun()
                
                with col_del:
                    if st.button("영구 삭제", key=f"perm_del_{i}", use_container_width=True):
                        st.session_state.trash.pop(i)
                        st.toast("논문이 영구 삭제되었습니다.", icon="🔥")
                        save_user_data(st.session_state.user_id)
                        st.rerun()
