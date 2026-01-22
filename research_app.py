if chart_data:
            df_chart = pd.DataFrame(chart_data)
            
            # Type Color Mapping
            # Domain: ["amazing", "bubble", "bad", "normal", "uncertain", "suspected", "verified_user"]
            domain = ["amazing", "bubble", "bad", "normal", "uncertain", "suspected", "verified_user"]
            range_ = ["#10b981", "#ef4444", "#6b7280", "#3b82f6", "#f59e0b", "#f59e0b", "#8b5cf6"]
            
            # Base chart with fixed domain [0, 100] for quadrants
            base = alt.Chart(df_chart).encode(
                x=alt.X('Impact', title='Impact (인기도/영향력)', scale=alt.Scale(domain=[0, 100])),
                y=alt.Y('Potential', title='Potential (잠재력/내실)', scale=alt.Scale(domain=[0, 100]))
            )

            # 1. Scatter Points
            scatter = base.mark_circle(size=60).encode(
                color=alt.Color('Type', scale=alt.Scale(domain=domain, range=range_), legend=None),
                tooltip=['Title', 'Impact', 'Potential', 'Type']
            )

            # 2. Quadrant Lines (Threshold: 50)
            h_rule = alt.Chart(pd.DataFrame({'y': [50]})).mark_rule(strokeDash=[5, 5], color='gray', opacity=0.5).encode(y='y')
            v_rule = alt.Chart(pd.DataFrame({'x': [50]})).mark_rule(strokeDash=[5, 5], color='gray', opacity=0.5).encode(x='x')

            # 3. Area Labels
            text_df = pd.DataFrame({
                'x': [25, 85], 
                'y': [90, 10], 
                'label': ['💎 Hidden Gem (원석)', '🫧 Bubble (거품)']
            })
            text_layer = alt.Chart(text_df).mark_text(
                align='center', baseline='middle', fontSize=13, fontWeight='bold', color='gray', opacity=0.8
            ).encode(x='x', y='y', text='label')
            
            # Combine Layers
            final_chart = (scatter + h_rule + v_rule + text_layer).interactive()
            
            st.altair_chart(final_chart, use_container_width=True)
            st.info("💡 **좌측 상단(High Potential, Low Impact)** 영역에 위치한 논문이 바로 숨겨진 원석(Hidden Gem)입니다!")
