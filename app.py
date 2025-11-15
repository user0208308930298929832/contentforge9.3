import json
import random
from datetime import date, datetime, timedelta
from statistics import mean

import streamlit as st
from openai import OpenAI

# =====================================================
# STREAMLIT CONFIG
# =====================================================
st.set_page_config(
    page_title="ContentForge v9.5",
    page_icon="🍏",
    layout="wide",
)

# =====================================================
# OPENAI CLIENT
# =====================================================
client = OpenAI()

# =====================================================
# INIT STATE
# =====================================================
def init_state():
    if "plan" not in st.session_state:
        st.session_state.plan = "Pro"

    today_str = date.today().isoformat()
    if "gens_date" not in st.session_state:
        st.session_state.gens_date = today_str
        st.session_state.gens_used_today = 0
    else:
        if st.session_state.gens_date != today_str:
            st.session_state.gens_date = today_str
            st.session_state.gens_used_today = 0

    if "last_variations" not in st.session_state:
        st.session_state.last_variations = None

    if "planner" not in st.session_state:
        st.session_state.planner = []

    if "next_task_id" not in st.session_state:
        st.session_state.next_task_id = 1

    if "selected_task_id" not in st.session_state:
        st.session_state.selected_task_id = None


# =====================================================
# PLAN LIMITS
# =====================================================
def limits_for_plan(plan: str) -> int:
    if plan == "Starter":
        return 5
    if plan == "Pro":
        return 50
    return 5


# =====================================================
# EMOJIS MAIS INTELIGENTES (NOVO SISTEMA)
# =====================================================
EMOJIS_POR_NICHO = {
    "moda feminina": ["👗", "👜", "👠", "✨", "💃"],
    "moda": ["👗", "👜", "👠", "✨", "💃"],
    "fitness": ["💪", "🏋️‍♀️", "🔥", "🏃‍♀️"],
    "ginásio": ["💪", "🏋️‍♂️"],
    "restauração": ["🍽️", "🍝", "🥂"],
    "comida": ["🍔", "🌮", "🍕"],
    "beleza": ["💄", "🌸", "✨"],
    "skincare": ["🧴", "💋"],
    "tecnologia": ["💻", "📱", "🤖", "⚡"],
}
EMOJIS_GENERICOS = ["✨", "⭐️", "🔥", "🌟", "🚀", "💫"]


def escolher_emoji_titulo(niche: str, plataforma: str) -> str:
    niche = (niche or "").lower()
    base = EMOJIS_POR_NICHO.get(niche, EMOJIS_GENERICOS)
    random.seed(f"{niche}-{plataforma}-{random.randint(1,99999)}")
    return random.choice(base)


def add_emoji_to_title(title: str, niche: str, plataforma: str) -> str:
    title = (title or "").strip()
    if not title:
        return title
    if ord(title[0]) > 1000:
        return title
    emoji = escolher_emoji_titulo(niche, plataforma)
    return f"{emoji} {title}"


# =====================================================
# ANALISE AUTOMÁTICA (FAKE MAS ESTÁVEL)
# =====================================================
def fake_analysis(caption: str, hashtags: list[str]):
    words = len((caption or "").split())
    base = 7.0 + min(2.0, max(0, (words - 40) / 40))
    extra_hash = min(0.6, len(hashtags) * 0.03)

    seed = abs(hash(caption)) % 100000
    random.seed(seed)
    jitter = random.uniform(-0.3, 0.3)

    score_final = max(6.0, min(9.5, base + extra_hash + jitter))
    eng = max(6.0, min(9.5, base + random.uniform(-0.3, 0.3)))
    conv = max(6.0, min(9.5, base + random.uniform(-0.3, 0.3)))

    return {
        "score": round(score_final, 1),
        "engaj": round(eng, 1),
        "conv": round(conv, 1),
    }


# =====================================================
# CHAMADA OPENAI
# =====================================================
def call_openai_variations(platform, brand, niche, tone, mode, message, extra):
    user_prompt = f"""
Marca: {brand}
Nicho: {niche}
Plataforma: {platform}
Tom: {tone}
Modo: {mode}

O que comunicar:
\"\"\"{message}\"\"\"

Info extra:
\"\"\"{extra}\"\"\"

Gera 3 variações completas:
- título sem emoji
- legenda 70-160 palavras
- hashtags 8-15 sem acentos

Responde em JSON:
{{"variacoes":[...]}}
"""

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system",
                 "content": "És copywriter PT-PT especialista em viralidade. Responde só JSON."},
                {"role": "user", "content": user_prompt}
            ],
        )

        data = json.loads(completion.choices[0].message.content)
        out = []

        for v in data.get("variacoes", [])[:3]:
            out.append({
                "titulo": v["titulo"].strip(),
                "legenda": v["legenda"].strip(),
                "hashtags": v["hashtags"],
                "plataforma": platform,
            })

        return out, None

    except Exception as e:
        return None, f"Erro API: {e}"


# =====================================================
# PLANNER: ADICIONAR TAREFA
# =====================================================
def add_task_to_planner(variation, day, time_obj, niche):
    task_id = st.session_state.next_task_id
    st.session_state.next_task_id += 1

    titulo = add_emoji_to_title(variation["titulo"], niche, variation["plataforma"])
    legenda = variation["legenda"]
    hashtags = variation["hashtags"]
    platform = variation["plataforma"]

    analysis = fake_analysis(legenda, hashtags)
    score = analysis["score"]

    st.session_state.planner.append({
        "id": task_id,
        "titulo": titulo,
        "legenda": legenda,
        "hashtags": hashtags,
        "plataforma": platform,
        "dia": day.isoformat(),
        "hora": time_obj.strftime("%H:%M"),
        "score": score,
        "status": "planned",
    })
    return score


# =====================================================
# SIDEBAR
# =====================================================
def sidebar():
    st.sidebar.title("Plano & Perfil")

    plan = st.sidebar.selectbox(
        "Plano", ["Starter", "Pro"],
        index=1 if st.session_state.plan == "Pro" else 0,
    )
    st.session_state.plan = plan

    limit = limits_for_plan(plan)
    st.sidebar.markdown(f"**Gerações hoje:** {st.session_state.gens_used_today}/{limit}")

    st.sidebar.markdown("---")

    brand = st.sidebar.text_input("Marca", "Loukisses")
    niche = st.sidebar.text_input("Nicho/tema", "Moda feminina")
    tone = st.sidebar.selectbox("Tom", ["profissional", "premium", "emocional"])
    mode = st.sidebar.selectbox("Modo", ["Venda", "Storytelling", "Educacional"])

    st.sidebar.markdown("---")

    return {"plan": plan, "limit": limit, "brand": brand, "niche": niche,
            "tone": tone, "mode": mode}


# =====================================================
# PAGE: GERAR
# =====================================================
def page_generate(ctx):
    st.subheader("⚡ Geração inteligente de conteúdo")

    platform = st.selectbox("Plataforma", ["Instagram", "TikTok"])
    message = st.text_input("O que queres comunicar hoje?")
    extra = st.text_area("Informação extra (opcional)")

    disabled = st.session_state.gens_used_today >= ctx["limit"]

    if st.button("🚀 Gerar agora", disabled=disabled, use_container_width=True):
        with st.spinner("A pensar na melhor legenda…"):
            variations, err = call_openai_variations(
                platform, ctx["brand"], ctx["niche"], ctx["tone"],
                ctx["mode"], message, extra
            )

        if err:
            st.error(err)
        else:
            st.session_state.last_variations = variations
            st.session_state.gens_used_today += 1
            st.experimental_rerun()

    variations = st.session_state.last_variations
    if not variations:
        st.info("Gera conteúdo para ver sugestões aqui.")
        return

    analyses = [fake_analysis(v["legenda"], v["hashtags"]) for v in variations]
    best_idx = max(range(len(variations)), key=lambda i: analyses[i]["score"])

    cols = st.columns(3)

    for idx, (col, var, ana) in enumerate(zip(cols, variations, analyses)):
        with col:

            if ctx["plan"] == "Pro" and idx == best_idx:
                st.markdown("""
<div style="background:#facc15;color:#111;padding:4px 10px;
border-radius:999px;font-size:0.7rem;font-weight:700;
text-transform:uppercase;display:inline-block;margin-bottom:6px;">
NOSSA RECOMENDAÇÃO ⭐
</div>
""", unsafe_allow_html=True)

            title = add_emoji_to_title(var["titulo"], ctx["niche"], platform)
            st.markdown(f"### {title}")

            st.write(var["legenda"])

            st.markdown("**Hashtags:**")
            st.write(" ".join(var["hashtags"]))

            if ctx["plan"] == "Pro":
                st.markdown(
                    f"🧠 Score {ana['score']} · 💬 Engaj {ana['engaj']} · 💰 Conv {ana['conv']}"
                )
            else:
                st.markdown("🔒 Análise disponível apenas no Pro.")

            st.markdown("---")

            day = st.date_input("Dia", value=date.today(), key=f"day_{idx}")
            hour = st.time_input("Hora", value=datetime.strptime("18:00","%H:%M"), key=f"hr_{idx}")

            if st.button("➕ Adicionar ao planner", key=f"add_{idx}"):
                add_task_to_planner(var, day, hour, ctx["niche"])
                st.success("Adicionado ao planner!")
                st.experimental_rerun()


# =====================================================
# PAGE: PLANNER
# =====================================================
def page_planner(ctx):
    st.subheader("📅 Planner semanal")

    anchor = st.date_input("Semana de referência", value=date.today())
    monday = anchor - timedelta(days=anchor.weekday())
    week_days = [monday + timedelta(days=i) for i in range(7)]
    names = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]

    st.markdown(f"Semana de {week_days[0].strftime('%d/%m')} a {week_days[-1].strftime('%d/%m')}")

    cols = st.columns(7)
    for col, name, d in zip(cols, names, week_days):
        with col:
            st.markdown(f"**{name}**")
            st.caption(d.strftime("%d/%m"))

            tasks = [t for t in st.session_state.planner if t["dia"] == d.isoformat()]

            for t in tasks:
                bg = "#1f2937" if t["status"]=="planned" else "#14532d"

                st.markdown(f"""
<div style="border-radius:14px;padding:10px;margin-top:8px;color:#e5e7eb;background:{bg};">
  <div style="opacity:0.7;font-size:0.75rem;">{t["hora"]} · {t["plataforma"]}</div>
  <div style="font-weight:600;margin-top:4px;">{t["titulo"]}</div>
  <div style="font-size:0.75rem;margin-top:4px;">Score: {t["score"]}/10 {"✅" if t["status"]=="done" else ""}</div>
</div>
""", unsafe_allow_html=True)

                if st.button("👁 Ver detalhes", key=f"detail_{t['id']}"):
                    st.session_state.selected_task_id = t["id"]
                    st.experimental_rerun()

    # Modal (detalhes)
    if st.session_state.selected_task_id:
        t = next((x for x in st.session_state.planner if x["id"]==st.session_state.selected_task_id), None)

        if t:
            st.markdown("---")
            st.markdown("### 🔎 Detalhes da tarefa")

            st.markdown(f"**{t['titulo']}**")
            st.caption(f"{t['dia']} · {t['hora']} · {t['plataforma']} · Score {t['score']}")

            st.write(t["legenda"])

            st.markdown("**Hashtags:**")
            st.write(" ".join(t["hashtags"]))

            c1, c2, c3 = st.columns(3)

            with c1:
                if t["status"]!="done":
                    if st.button("✅ Marcar como concluído", key=f"done_modal_{t['id']}"):
                        t["status"] = "done"
                        st.experimental_rerun()

            with c2:
                if st.button("🗑 Remover", key=f"rm_{t['id']}"):
                    st.session_state.planner = [x for x in st.session_state.planner if x["id"]!=t["id"]]
                    st.session_state.selected_task_id = None
                    st.experimental_rerun()

            with c3:
                if st.button("Fechar", key=f"close_{t['id']}"):
                    st.session_state.selected_task_id = None
                    st.experimental_rerun()


# =====================================================
# PAGE: PERFORMANCE
# =====================================================
def page_performance(ctx):
    st.subheader("📊 Performance")

    if ctx["plan"]!="Pro":
        st.warning("🔒 Disponível apenas no Pro.")
        return

    completed = [t for t in st.session_state.planner if t["status"]=="done"]

    if not completed:
        st.info("Nenhum post concluído ainda.")
        return

    avg_score = mean([t["score"] for t in completed])

    minutes = []
    for t in completed:
        h,m = map(int, t["hora"].split(":"))
        minutes.append(h*60+m)

    if minutes:
        avg_min = int(round(mean(minutes)/15)*15)
        hr = (avg_min//60)%24
        mn = avg_min%60
        recommended_hour = f"{hr:02d}:{mn:02d}"
    else:
        recommended_hour = "18:00"

    c1, c2, c3 = st.columns(3)

    with c1: st.metric("Posts concluídos", len(completed))
    with c2: st.metric("Score médio", f"{avg_score:.2f}")
    with c3: st.metric("Hora recomendada", recommended_hour)

    st.caption("🧠 Precisão da IA aumenta com o nº de postagens concluídas.")

    st.markdown("---")
    st.markdown("#### Últimos posts concluídos")

    for t in sorted(completed, key=lambda x:(x["dia"], x["hora"]), reverse=True)[:10]:
        st.markdown(
            f"- **{t['dia']} {t['hora']} · {t['plataforma']}** — {t['titulo']} · Score: {t['score']}/10"
        )


# =====================================================
# MAIN
# =====================================================
def main():
    init_state()
    ctx = sidebar()

    st.title("ContentForge v9.5 🍏")
    st.caption("Gera conteúdo inteligente, organiza o teu planner e acompanha performance (Pro).")

    tab1, tab2, tab3 = st.tabs(["⚡ Gerar", "📅 Planner", "📊 Performance"])

    with tab1: page_generate(ctx)
    with tab2: page_planner(ctx)
    with tab3: page_performance(ctx)


if __name__ == "__main__":
    main()
