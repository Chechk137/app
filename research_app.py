with tab_inventory:
    if not st.session_state.inventory: 
        st.info("수집된 논문이 없습니다.")
    else:
        # [New] 정렬 방식 선택
        col_sort, _ = st.columns([2, 5])
        with col_sort:
            inv_sort_opt = st.selectbox("정렬 방식", ["저장한 순서", "가치 높은 순서"])
        
        # 원본 데이터 참조
        inv_list = st.session_state.inventory
        
        # 정렬 로직 (원본 보존을 위해 리스트 복사본 사용이 아닌, 객체 참조 정렬)
        if inv_sort_opt == "가치 높은 순서":
            # final_score가 있으면 그것을, 없으면 debiased_score를 기준으로 정렬
            display_items = sorted(inv_list, key=lambda x: x.get('final_score', x.get('debiased_score', 0)), reverse=True)
        else:
            display_items = inv_list

        cols = st.columns(2)
        for i, paper in enumerate(display_items):
            # Key collision prevention using Paper ID
            p_id = paper['id']
            
            with cols[i % 2]:
                with st.container(border=True):
                    status_emoji = "❓"; status_text = "미검증"
                    if paper['is_reviewed']:
                        if paper['potential_type'] == "amazing": status_emoji, status_text = "✨", "대성공"
                        elif paper['potential_type'] == "bad": status_emoji, status_text = "💀", "실패"
                        elif paper['potential_type'] == "verified_user": status_emoji, status_text = "🛡️", "사용자 승인"
                        else: status_emoji, status_text = "✅", "검증됨"

                    # [Changed] Title Display
                    translated_title = get_translated_title(paper['title'])
                    st.markdown(
                        f"""<div title="[번역] {translated_title}" style="font-size:1rem; font-weight:bold; margin-bottom:5px;">{paper['title']}</div>""", 
                        unsafe_allow_html=True
                    )
                    if show_translation:
                        st.caption(f"🇰🇷 {translated_title}")
                    
                    st.caption(f"{status_emoji} {status_text} | {paper['journal']}")
                    
                    c_btn1, c_btn2 = st.columns([2, 1])
                    with c_btn1:
                        if not paper['is_reviewed']:
                            if paper['integrity_status'] == "valid":
                                if st.button("🔬 심층 검증", key=f"rev_{p_id}", type="primary", use_container_width=True):
                                    # 객체 직접 수정 (Reference Update)
                                    paper['is_reviewed'] = True
                                    bonus = int(paper['debiased_score'] * 0.5)
                                    st.session_state.score += bonus
                                    paper['final_score'] = paper['debiased_score'] + bonus
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
                                    paper['final_score'] = paper['debiased_score'] + bonus
                                    paper['potential_type'] = "verified_user"
                                    paper['reason'] = "사용자 직접 확인으로 검증됨"
                                    save_user_data(st.session_state.user_id) 
                                    st.rerun()
                        else:
                            st.success(f"가치: {paper.get('final_score', 0)}점")

                    with c_btn2:
                        if st.button("삭제", key=f"del_{p_id}", use_container_width=True):
                            deduction = paper.get('final_score', paper.get('debiased_score', 0))
                            st.session_state.score = max(0, st.session_state.score - deduction)
                            
                            # ID 기반 삭제 (정렬 상태와 무관하게 안전하게 삭제)
                            st.session_state.inventory = [p for p in st.session_state.inventory if p['id'] != p_id]
                            st.session_state.trash.append(paper)
                            
                            st.toast(f"논문 삭제. {deduction}점 차감됨", icon="🗑️")
                            save_user_data(st.session_state.user_id) 
                            st.rerun()
                    st.markdown(f"[📄 원문 보기]({paper['url']})")
