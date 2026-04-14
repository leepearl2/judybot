import streamlit as st
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import os, base64

from db import init_db, upsert_hospital, get_all_hospitals, update_hospital, delete_hospital, log_send, get_send_log
from mailer import send_newsletter

# ── 초기화 ────────────────────────────────────────────────────────────────────
init_db()
st.set_page_config(page_title="임상팀 뉴스레터 생성기", page_icon="💊", layout="wide")

# ── 사이드바 ──────────────────────────────────────────────────────────────────
st.sidebar.title("💊 임상팀 뉴스레터")
menu = st.sidebar.radio("메뉴", ["📨 뉴스레터 생성/발송", "🏥 병원 DB 관리", "📋 발송 이력"])

st.sidebar.divider()
st.sidebar.subheader("⚙️ 메일 서버 설정")
# SMTP 서버/포트는 시스템 고정값 (사내 릴레이)
smtp_host = "spam.ekdp.com"
smtp_port = 25
smtp_user = st.sidebar.text_input("발신 이메일 (SMTP_USER)", value="", key="smtp_user")
smtp_pass = st.sidebar.text_input("앱 비밀번호 (SMTP_PASS)", value="", type="password", key="smtp_pass")
st.sidebar.caption(f"📡 메일 서버: `{smtp_host}:{smtp_port}` (자동)")
st.sidebar.markdown("**브랜드 로고 (선택)**")
logo_file = st.sidebar.file_uploader("로고 PNG 업로드", type=["png"], key="logo_png")
if logo_file:
    logo_bytes = logo_file.getvalue()
    st.session_state["logo_url"] = "data:image/png;base64," + base64.b64encode(logo_bytes).decode()

if smtp_host:
    st.sidebar.success("✅ 메일 설정 완료")
else:
    st.sidebar.warning("발신 이메일을 입력해주세요")

# ── 공통 유틸 ─────────────────────────────────────────────────────────────────
SEASON_GREETINGS = {
    1:  "새해 첫 달, 매서운 한파 속에서도 희망찬 기운이 넘치는 1월입니다. 추운 날씨에 건강 각별히 유의하시고, 새해에도 교수님과 가정에 건강과 행복이 가득하시기를 진심으로 기원드립니다.",
    2:  "아직 겨울의 끝자락이 남아 있는 2월입니다. 입춘은 지났지만 여전히 차가운 날씨가 이어지고 있는 만큼 건강에 유의하시길 바라며, 이른 봄빛처럼 교수님의 나날이 따뜻하고 평온하시기를 기원드립니다.",
    3:  "봄의 문턱에 들어선 3월입니다. 낮에는 제법 따뜻한 햇살이 느껴지지만 아침저녁으로 일교차가 큰 환절기인 만큼 건강에 각별히 유의하시길 바라며, 새 계절의 설렘과 함께 교수님의 나날이 활기차고 행복하시기를 기원드립니다.",
    4:  "봄꽃이 만발한 4월입니다. 따사로운 봄볕과 함께 나들이하기 좋은 계절이 찾아왔습니다. 화창한 봄날처럼 교수님의 나날도 밝고 건강하시기를 바랍니다.",
    5:  "신록이 눈부신 5월입니다. 가정의 달을 맞아 교수님과 소중한 가족분들께서 건강하고 행복한 시간 보내시길 바라며, 따뜻한 계절의 기운이 언제나 함께하시기를 기원드립니다.",
    6:  "초여름의 싱그러운 기운이 물씬 풍기는 6월입니다. 낮 기온이 높아지는 시기인 만큼 수분 섭취와 건강 관리에 유의하시고, 활기찬 여름을 맞이하시길 바랍니다.",
    7:  "무더위가 본격적으로 시작되는 7월입니다. 연일 이어지는 더위 속에서도 건강 잘 챙기시고, 휴가 기간에는 충분한 휴식으로 재충전하시기 바랍니다.",
    8:  "일 년 중 가장 무더운 8월입니다. 강한 햇볕과 열대야로 체력이 소모되기 쉬운 시기인 만큼 건강에 각별히 유의하시고, 편안한 여름 휴가도 즐기시기 바랍니다.",
    9:  "선선한 바람이 불어오는 9월입니다. 한낮의 더위가 한풀 꺾이고 가을의 정취가 느껴지는 계절입니다. 풍요로운 가을과 함께 교수님의 나날도 여유롭고 건강하시기를 바랍니다.",
    10: "단풍이 곱게 물드는 10월입니다. 아름다운 가을 풍경만큼이나 교수님의 나날도 풍요롭고 따뜻하시기를 바라며, 일교차가 커지는 시기인 만큼 건강 유의하시기 바랍니다.",
    11: "겨울이 성큼 다가온 11월입니다. 날씨가 부쩍 쌀쌀해진 만큼 따뜻하게 건강 챙기시고, 한 해를 아름답게 마무리하시기를 기원드립니다.",
    12: "한 해를 마무리하는 12월입니다. 날씨가 매섭게 추워지는 이 시기, 교수님의 건강이 무엇보다 소중합니다. 올 한 해 아낌없는 협조에 깊이 감사드리며, 따뜻하고 건강한 새해를 맞이하시기를 진심으로 기원드립니다.",
}

def make_greeting(professor, hospital, month, pm_name):
    base = SEASON_GREETINGS.get(month, "")
    return (
        f"락손필름코팅정 시판 후 사용성적조사를 담당하고 있는 광동제약㈜ PM {pm_name}입니다.\n\n"
        f"{base} 아울러, 바쁘신 와중에도 사용성적조사에 아낌없는 성원을 보내주셔서 진심으로 감사드립니다.\n\n"
        f"진행 중인 시판 후 사용성적조사의 News letter를 송부드립니다."
    )



def get_season_image_url(month:int)->str:
    monthly = {
        1: "https://images.unsplash.com/photo-1483664852095-d6cc6870702d?auto=format&fit=crop&w=1200&q=80",
        2: "https://images.unsplash.com/photo-1510798831971-661eb04b3739?auto=format&fit=crop&w=1200&q=80",
        3: "https://images.unsplash.com/photo-1455656678494-4d1b5f3e7ad1?auto=format&fit=crop&w=1200&q=80",
        4: "https://images.unsplash.com/photo-1490750967868-88aa4486c946?auto=format&fit=crop&w=1200&q=80",
        5: "https://images.unsplash.com/photo-1462275646964-a0e3386b89fa?auto=format&fit=crop&w=1200&q=80",
        6: "https://images.unsplash.com/photo-1473116763249-2faaef81ccda?auto=format&fit=crop&w=1200&q=80",
        7: "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1200&q=80",
        8: "https://images.unsplash.com/photo-1500375592092-40eb2168fd21?auto=format&fit=crop&w=1200&q=80",
        9: "https://images.unsplash.com/photo-1502082553048-f009c37129b9?auto=format&fit=crop&w=1200&q=80",
        10:"https://images.unsplash.com/photo-1477414348463-c0eb7f1359b6?auto=format&fit=crop&w=1200&q=80",
        11:"https://images.unsplash.com/photo-1418985991508-e47386d96a71?auto=format&fit=crop&w=1200&q=80",
        12:"https://images.unsplash.com/photo-1512389098783-66b81f86e199?auto=format&fit=crop&w=1200&q=80",
    }
    return monthly.get(month, monthly[5])

def file_to_data_uri(file_path:str,mime:str='image/png')->str:
    with open(file_path,'rb') as f:
        return f"data:{mime};base64,"+base64.b64encode(f.read()).decode()

def render_html(data):
    import mjml as _mjml
    template_dir = os.path.dirname(os.path.abspath(__file__))
    env = Environment(loader=FileSystemLoader(template_dir))
    # MJML 템플릿에 Jinja2 변수 주입
    mjml_tmpl = env.get_template("template.mjml")
    rendered_mjml = mjml_tmpl.render(**data)
    # MJML → 이메일 호환 HTML 컴파일
    result = _mjml.mjml_to_html(rendered_mjml)
    if result.errors:
        raise RuntimeError(f"MJML 컴파일 오류: {result.errors}")
    return result.html

def download_link(html_content, filename="newsletter.html"):
    b64 = base64.b64encode(html_content.encode("utf-8")).decode()
    return (
        f'<a href="data:text/html;base64,{b64}" download="{filename}">'
        f'<button style="background:#0055a4;color:white;border:none;padding:10px 22px;'
        f'border-radius:8px;font-size:14px;cursor:pointer;">📥 HTML 다운로드</button></a>'
    )

DEFAULT_CONTACTS = [
    {"role": "CRM",          "name": "이성희", "tel": "02-6006-7262", "email": "happyday@ekdp.com"},
    {"role": "PM",           "name": "오다혜", "tel": "02-6006-7252", "email": "dhoh@ekdp.com"},
    {"role": "CRA",          "name": "신혜지", "tel": "02-6006-7263", "email": "hjshin@ekdp.com"},
    {"role": "안전성 보고(PV)", "name": "-",    "tel": "02-6006-7244", "email": "kdpv@ekdp.com"},
]

# ══════════════════════════════════════════════════════════════════════════════
# 메뉴 1: 뉴스레터 생성/발송
# ══════════════════════════════════════════════════════════════════════════════
if menu == "📨 뉴스레터 생성/발송":
    st.title("📨 뉴스레터 생성 및 발송")

    hospitals = get_all_hospitals()
    hosp_labels = ["-- 직접 입력 --"] + [f"{h['hospital_name']} / {h['professor']}" for h in hospitals]

    col_left, col_right = st.columns([1, 1.6])

    with col_left:
        st.subheader("📝 정보 입력")

        # ── 병원 선택 ──
        with st.expander("🏥 수신 기관 선택", expanded=True):
            selected = st.selectbox("DB에서 불러오기", hosp_labels)
            if selected != "-- 직접 입력 --":
                idx = hosp_labels.index(selected) - 1
                h = hospitals[idx]
                default_hospital = h["hospital_name"]
                default_professor = h["professor"]
                default_email = h["email"]
                default_contracted = h["site_contracted"]
                default_enrolled = h["site_enrolled"]
                default_ecrf = h["site_ecrf"]
                default_delta = h["site_delta"]
            else:
                default_hospital = ""
                default_professor = ""
                default_email = ""
                default_contracted = 0
                default_enrolled = 0
                default_ecrf = 0
                default_delta = 0

            hospital = st.text_input("병원명", value=default_hospital)
            professor = st.text_input("교수명 (직함 포함)", value=default_professor)
            to_email = st.text_input("수신 이메일", value=default_email)

        # ── 과제 정보 ──
        with st.expander("📌 과제 기본 정보", expanded=False):
            study_id = st.text_input("과제 ID", value="KD-RXN-401")
            base_date = st.text_input("기준일", value="2026년 2월 27일")

        # ── 전체 현황 ──
        with st.expander("📊 전체 현황", expanded=True):
            c1, c2 = st.columns(2)
            total_pssv     = c1.number_input("PSSV 완료 기관", value=22, min_value=0)
            total_siv      = c2.number_input("SIV 완료 기관",  value=18, min_value=0)
            c3, c4 = st.columns(2)
            total_enrolled = c3.number_input("총 등록 대상자", value=38, min_value=0)
            target_total   = c4.number_input("목표 례수",       value=600, min_value=1)

        # ── 본원 현황 ──
        with st.expander("🏢 본원 현황 (기관 DB 기준)", expanded=True):
            c5, c6, c7 = st.columns(3)
            site_contracted = c5.number_input("계약례",        value=default_contracted, min_value=0)
            site_enrolled   = c6.number_input("등록례",        value=default_enrolled,   min_value=0)
            site_ecrf       = c7.number_input("E-CRF 작성례", value=default_ecrf,        min_value=0)
            site_delta_num  = st.number_input("전월 대비 변동 (음수 가능)", value=default_delta)
            site_delta = f"{abs(site_delta_num)}례{'↑' if site_delta_num > 0 else '↓' if site_delta_num < 0 else ' 동일'}"

        # ── 일정/링크 ──
        with st.expander("📅 일정 및 링크", expanded=False):
            enrollment_deadline = st.text_input("대상자 등록 마감", value="2028년 4월")
            ecrf_url = st.text_input("E-CRF URL", value="https://www.cubecdms.com/kd_rxn_401")
            st.markdown("**📸 조사 일정 이미지 (선택)**")
            schedule_img_file = st.file_uploader("이미지 업로드 (jpg/png/gif)", type=["jpg","jpeg","png","gif"], key="sched_img")
            if schedule_img_file:
                img_bytes = schedule_img_file.getvalue()
                mime = schedule_img_file.type or "image/png"
                ext = mime.split("/")[-1].replace("jpeg", "jpg")
                img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"_tmp_schedule.{ext}")
                with open(img_path, "wb") as f:
                    f.write(img_bytes)
                st.session_state["schedule_image_path"] = img_path
                st.session_state["schedule_image_mime"] = mime
                st.success(f"✅ 이미지 업로드됨: {schedule_img_file.name}")

            # 저장된 이미지 읽기
            img_path = st.session_state.get("schedule_image_path", "")
            if img_path and os.path.exists(img_path):
                mime = st.session_state.get("schedule_image_mime", "image/png")
                with open(img_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                schedule_image = f"data:{mime};base64,{img_b64}"
                st.markdown(f'<img src="{schedule_image}" style="max-width:100%;border-radius:6px;"/>', unsafe_allow_html=True)
            else:
                schedule_image = get_season_image_url(datetime.now().month)

        # ── 발신자 ──
        with st.expander("👤 발신 담당자", expanded=False):
            sender_name = st.text_input("PM 이름", value="오다혜")

        # ── Contact ──
        with st.expander("📞 Contact 정보", expanded=False):
            contacts = []
            for i, c in enumerate(DEFAULT_CONTACTS):
                cc1, cc2, cc3 = st.columns(3)
                name  = cc1.text_input(f"{c['role']} 이름", value=c["name"],  key=f"cn{i}")
                tel_d = cc2.text_input("전화",               value=c["tel"],   key=f"ct{i}")
                email = cc3.text_input("이메일",             value=c["email"], key=f"ce{i}")
                contacts.append({
                    "role": c["role"], "name": name,
                    "tel": tel_d.replace("-", ""), "tel_display": tel_d, "email": email,
                })

        gen_col, send_col = st.columns(2)
        generate_btn = gen_col.button("🚀 뉴스레터 생성", type="primary", use_container_width=True)
        send_btn     = send_col.button("📧 이메일 발송",  use_container_width=True)

    # ── 우측 미리보기 ──
    with col_right:
        st.subheader("👁️ 미리보기")

        if generate_btn or send_btn:
            month = datetime.now().month
            enrollment_pct = round((total_enrolled / target_total) * 100, 1)
            enrollment_pct_int = min(int(enrollment_pct), 100)

            data = {
                "study_id": study_id, "base_date": base_date,
                "hospital": hospital, "professor": professor,
                "total_pssv": total_pssv, "total_siv": total_siv,
                "total_enrolled": total_enrolled, "target_total": target_total,
                "enrollment_pct": enrollment_pct,
                "enrollment_pct_int": enrollment_pct_int,
                "site_contracted": site_contracted, "site_enrolled": site_enrolled,
                "site_ecrf": site_ecrf, "site_delta": site_delta,
                "enrollment_deadline": enrollment_deadline, "ecrf_url": ecrf_url,
                "sender_name": sender_name, "sender_pm": sender_name,
                "contacts": contacts,
                "greeting_body": make_greeting(professor, hospital, month, sender_name),
                "schedule_image": schedule_image,
                "has_enrollment": site_enrolled > 0,
                "logo_url": st.session_state.get("logo_url", ""),
            }

            html_output = render_html(data)
            st.session_state["last_html"] = html_output
            st.session_state["last_data"] = data

            if send_btn:
                if not to_email:
                    st.error("수신 이메일을 입력해주세요.")
                elif not smtp_user or not smtp_pass:
                    st.error("❌ 사이드바에서 메일 서버 설정을 먼저 입력해주세요.")
                else:
                    subject = f"[{study_id}] 락손필름코팅정 사용성적조사 News Letter"
                    img_path = st.session_state.get("schedule_image_path", "")
                    result = send_newsletter(
                        to_email, professor, subject, html_output,
                        smtp_host=smtp_host, smtp_port=int(smtp_port),
                        smtp_user=smtp_user, smtp_pass=smtp_pass,
                        template_data=data,
                        image_path=img_path,
                    )
                    if result["ok"]:
                        log_send(hospital, professor, to_email, "sent")
                        st.success(f"✅ 발송 완료! → {to_email}")
                    else:
                        log_send(hospital, professor, to_email, f"error: {result['error']}")
                        st.error(f"❌ 발송 실패: {result['error']}")

            st.success("✅ 생성 완료!")
            st.markdown(download_link(html_output, f"newsletter_{hospital}.html"), unsafe_allow_html=True)
            st.divider()
            st.components.v1.html(html_output, height=900, scrolling=True)
        else:
            st.info("왼쪽에서 정보를 입력하고 **뉴스레터 생성** 버튼을 눌러주세요.")

# ══════════════════════════════════════════════════════════════════════════════
# 메뉴 2: 병원 DB 관리
# ══════════════════════════════════════════════════════════════════════════════
elif menu == "🏥 병원 DB 관리":
    st.title("🏥 병원 DB 관리")

    tab1, tab2 = st.tabs(["📤 엑셀 업로드", "📋 DB 목록"])

    with tab1:
        st.subheader("엑셀 파일로 병원 정보 일괄 등록")
        st.caption("엑셀 컬럼: `병원명` | `교수명` | `이메일` | `계약례` | `등록례` | `ECRF작성례` | `전월대비변동`")

        # 샘플 엑셀 다운로드
        sample_df = pd.DataFrame([
            {"병원명": "중앙대학교광명병원", "교수명": "김응수 교수", "이메일": "test@hospital.com",
             "계약례": 30, "등록례": 16, "ECRF작성례": 16, "전월대비변동": 1},
            {"병원명": "서울아산병원", "교수명": "홍길동 교수", "이메일": "hong@asan.or.kr",
             "계약례": 20, "등록례": 8,  "ECRF작성례": 8,  "전월대비변동": 2},
        ])
        csv = sample_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥 샘플 엑셀 다운로드 (CSV)", data=csv.encode("utf-8-sig"),
                           file_name="sample_hospitals.csv", mime="text/csv")

        uploaded = st.file_uploader("엑셀 또는 CSV 파일 업로드", type=["xlsx", "csv"])
        if uploaded:
            try:
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)

                st.dataframe(df, use_container_width=True)

                if st.button("💾 DB에 저장", type="primary"):
                    count = 0
                    for _, row in df.iterrows():
                        upsert_hospital(
                            hospital_name=str(row.get("병원명", "")),
                            professor=str(row.get("교수명", "")),
                            email=str(row.get("이메일", "")),
                            site_contracted=int(row.get("계약례", 0)),
                            site_enrolled=int(row.get("등록례", 0)),
                            site_ecrf=int(row.get("ECRF작성례", 0)),
                            site_delta=int(row.get("전월대비변동", 0)),
                        )
                        count += 1
                    st.success(f"✅ {count}건 저장 완료!")
                    st.rerun()
            except Exception as e:
                st.error(f"파일 파싱 오류: {e}")

    with tab2:
        st.subheader("등록된 병원 목록")
        hospitals = get_all_hospitals()
        if not hospitals:
            st.info("등록된 병원이 없습니다. 엑셀 업로드로 추가해주세요.")
        else:
            st.caption(f"총 {len(hospitals)}개 기관 — 수정하려면 행을 선택하세요")

            # 선택용 목록 표시
            df_view = pd.DataFrame(hospitals)
            df_view = df_view.rename(columns={
                "id": "ID", "hospital_name": "병원명", "professor": "교수명",
                "email": "이메일", "site_contracted": "계약례",
                "site_enrolled": "등록례", "site_ecrf": "ECRF작성례", "site_delta": "전월대비변동"
            })
            st.dataframe(df_view.drop(columns=["ID"]), use_container_width=True, height=300)

            st.divider()

            # 수정할 행 선택
            hosp_options = [f"{h['hospital_name']} / {h['professor']}" for h in hospitals]
            selected_label = st.selectbox("✏️ 수정할 기관 선택", ["-- 선택 --"] + hosp_options)

            if selected_label != "-- 선택 --":
                idx = hosp_options.index(selected_label)
                h = hospitals[idx]

                with st.form("edit_form"):
                    st.markdown(f"**{h['hospital_name']} 수정**")
                    ec1, ec2 = st.columns(2)
                    e_hospital = ec1.text_input("병원명", value=h["hospital_name"])
                    e_professor = ec2.text_input("교수명", value=h["professor"])
                    e_email = st.text_input("이메일", value=h["email"])
                    c1, c2, c3, c4 = st.columns(4)
                    e_contracted = c1.number_input("계약례", value=h["site_contracted"], min_value=0)
                    e_enrolled   = c2.number_input("등록례", value=h["site_enrolled"],   min_value=0)
                    e_ecrf       = c3.number_input("ECRF작성례", value=h["site_ecrf"],    min_value=0)
                    e_delta      = c4.number_input("전월대비변동", value=h["site_delta"])

                    save_btn, del_btn = st.columns(2)
                    submitted = save_btn.form_submit_button("💾 저장", type="primary", use_container_width=True)
                    delete_clicked = del_btn.form_submit_button("🗑️ 삭제", use_container_width=True)

                if submitted:
                    update_hospital(h["id"], e_hospital, e_professor, e_email,
                                    int(e_contracted), int(e_enrolled), int(e_ecrf), int(e_delta))
                    st.success(f"✅ '{e_hospital}' 수정 완료!")
                    st.rerun()

                if delete_clicked:
                    delete_hospital(h["id"])
                    st.warning(f"🗑️ '{h['hospital_name']}' 삭제 완료!")
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# 메뉴 3: 발송 이력
# ══════════════════════════════════════════════════════════════════════════════
elif menu == "📋 발송 이력":
    st.title("📋 발송 이력")
    logs = get_send_log()
    if logs:
        df_log = pd.DataFrame(logs)
        df_log.columns = ["병원명", "교수명", "이메일", "발송일시", "상태"]
        st.dataframe(df_log, use_container_width=True, height=500)
        st.caption(f"최근 {len(logs)}건")
    else:
        st.info("발송 이력이 없습니다.")
