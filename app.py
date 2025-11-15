import json
import random
from datetime import date, datetime, timedelta
from statistics import mean
import streamlit as st
from openai import OpenAI

# ============================
# CONFIG
# ============================
st.set_page_config(page_title="ContentForge v9.5", page_icon="🍏", layout="wide")
client = OpenAI()

# ============================
# SESSION STATE INIT
# ============================
def init_state():
    today = date.today().isoformat()

    st.session_state.setdefault("plan", "Pro")

    if st.session_state.get("gens_date") != today:
        st.session_state["gens_date"] = today
        st.session_state["gens_used_today"] = 0
    st.session_state.setdefault("gens_used_today", 0)

    st.session_state.setdefault("last_variations", None)
    st.session_state.setdefault("planner", [])
    st.session_state.setdefault("next_task_id", 1)
    st.session_state.setdefault("selected_task_id", None)

init_state()

# ============================
# PLAN LIMITS
# ============================
def limits_for_plan(plan):
    return 5 if plan == "Starter" else 50

# ============================
# EMOJIS
# ============================
def emoji_for_niche(niche):
    niche = niche.lower()
    if "moda" in niche: return random.choice(["👗","👠","👜","✨"])
    if "fitness" in niche: return random.choice(["💪","🏋️‍♂️","🔥"])
    if "restaurante" in niche: return random.choice(["🍽️","🍝","🍔"])
    if "beleza" in niche: return random.choice(["💄","💋","🌸"])
    return random.choice(["✨","🌟","🔥"])

def add_emoji_to_title(title, niche):
    if not title: return title
    if title[0] in "👗💄💪✨🔥🌟👜🍽️": return title
    return f"{emoji_for_niche(niche)} {title}"

# ============================
# ANALYSIS FAKE
# ============================
def fake_analysis(caption, hashtags):
    words = len(caption.split())
    base = 7 + min(2, max(0, (words - 40) / 40))
    score = round(max(6, min(9.4, base + random.uniform(-0.3, 0.3))), 1)
    eng = round(max(6, min(9.4, base - 0.2 + random.uniform(-0.3, 0.3))), 1)
    conv = round(max(6, min(9.4, base + 0.1 + random.uniform(-0.3, 0.3))), 1)
    return {"score": score, "engaj": eng, "conv": conv}

# ============================
# OPENAI GENERATION
# ============================
def call_openai_variations(platform, brand, niche, tone, mode, message, extra):
    prompt = f"""
Marca: {brand}
Nicho: {niche}
Plataforma: {platform}
Tom: {tone}
Modo: {mode}

Mensagem: \"{message}\"
Extra: \"{extra}\"

Gera 3 variações em JSON:
{{
 "variacoes":[
   {{"titulo":"...", "legenda":"...", "hashtags":["#..."]}},
   {{"titulo":"...", "legenda":"...", "hashtags":["#..."]}},
   {{"titulo":"...", "legenda":"...", "hashtags":["#..."]}}
 ]
}}
"""

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type":"json_object"},
            messages=[{"role":"user","content":prompt}]
        )
        data = json.loads(r.choices[0].message.content)
        return data["variacoes"], None
    except Exception as e:
        return None, str(e)

# ============================
# PLANNER
# ============================
def add_task(variation, day, time_obj, niche):
    task_id = st.session_state.next_task_id
    st.session_state.next_task_id += 1

    analysis = fake_analysis(variation["legenda"], variation["hashtags"])

    st.session_state.planner.append({
        "id": task_id,
        "titulo": add_emoji_to_title(variation["titulo"], niche),
        "legenda": variation["legenda"],
        "hashtags": variation["hashtags"],
        "plataforma": variation["plataforma"],
        "dia": day.isoformat(),
        "hora": time_obj.strftime("%H:%M"),
        "score": analysis["score"],
        "status": "planned",
    })

# ============================
# SIDEBAR
# ============================
def sidebar():
    st.sidebar.title("Plano & Perfil")

    st.session_state.plan = st.sidebar.selectbox("Plano", ["Starter", "Pro"], index=1)
    limit = limits_for_plan(st.session_state.plan)
    st.sidebar.write(f"**Gerações hoje:** {st.session_state.gens_used_today}/{limit}")

    st.sidebar.markdown("---")
    brand = st.sidebar.text_input("Marca", "Loukisses")
    niche = st.sidebar.text_input("Nicho", "Moda feminina")
    tone = st.sidebar.selectbox("Tom", ["profissional","premium","emocional","descontraído"])
    mode = st.sidebar.selectbox("Modo", ["Venda","Storytelling","Educacional"])

    return {
        "brand": brand,
        "niche": niche,
        "tone": tone,
        "mode": mode,
        "limit": limit
    }

# ============================
# PAGE: GENERATE
# ============================
def page_generate(ctx):
    st.subheader("⚡ Geração de conteúdo")

    platform = st.selectbox("Plataforma", ["Instagram","TikTok"])
    message = st.text_input("Mensagem", "Lançamento da nova coleção")
    extra = st.text_area("Extra (opcional)", "")

    disabled = st.session_state.gens_used_today >= ctx["limit"]
    if disabled:
        st.warning("Limite diário atingido")

    if st.button("🚀 Gerar agora", disabled=disabled):
        with st.spinner("A gerar…"):
            v, err = call_openai_variations(platform, ctx["brand"], ctx["niche"], ctx["tone"], ctx["mode"], message, extra)
        if err:
            st.error(err)
        else:
            st.session_state.last_variations = v
            st.session_state.gens_used_today += 1
            st.success("Conteúdo gerado!")

    if not st.session_state.last_variations:
        st.info("Gera conteúdo para ver aqui.")
        return

    variations = st.session_state.last_variations
    analyses = [fake_analysis(v["legenda"], v["hashtags"]) for v in variations]
    best = max(range(3), key=lambda i: analyses[i]["score"])

    cols = st.columns(3)
    for i,(col,var,ana) in enumerate(zip(cols, variations, analyses)):
        with col:
            if i == best:
                st.success("⭐ Nossa recomendação")

            st.write("### " + add_emoji_to_title(var["titulo"], ctx["niche"]))
            st.write(var["legenda"])
            st.caption(" ".join(var["hashtags"]))

            st.write(f"Score: {ana['score']}/10 · Engaj: {ana['engaj']}/10 · Conv: {ana['conv']}/10")

            day = st.date_input("Dia", value=date.today(), key=f"d{i}")
            hour = st.time_input("Hora", value=datetime.strptime("18:00","%H:%M").time(), key=f"h{i}")

            if st.button("Adicionar ao planner", key=f"p{i}"):
                add_task(var, day, hour, ctx["niche"])
                st.success("Adicionado ao planner!")

# ============================
# PAGE: PLANNER
# ============================
def page_planner(ctx):
    st.subheader("📅 Planner")

    anchor = st.date_input("Semana", value=date.today())
    monday = anchor - timedelta(days=anchor.weekday())
    days = [monday + timedelta(days=i) for i in range(7)]
    names = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]

    cols = st.columns(7)
    for col, name, d in zip(cols, names, days):
        with col:
            st.write(f"**{name}**\n{d.strftime('%d/%m')}")
            tasks = [t for t in st.session_state.planner if t["dia"] == d.isoformat()]
            if not tasks:
                st.caption("Sem tarefas.")
            else:
                for t in tasks:
                    st.write(f"**{t['hora']} · {t['plataforma']}**")
                    st.write(t["titulo"])
                    st.write(f"Score {t['score']}")

                    if st.button("Ver detalhes", key=f"det{t['id']}"):
                        st.session_state.selected_task_id = t["id"]

    if st.session_state.selected_task_id:
        st.markdown("---")
        task = next(t for t in st.session_state.planner if t["id"] == st.session_state.selected_task_id)
        st.write("### Detalhes")
        st.write(f"**{task['titulo']}**")
        st.caption(f"{task['dia']} · {task['hora']} · {task['plataforma']}")
        st.write(task["legenda"])
        st.write(" ".join(task["hashtags"]))

        if task["status"] != "done":
            if st.button("✔ Marcar concluído"):
                task["status"] = "done"
        if st.button("🗑 Remover"):
            st.session_state.planner = [t for t in st.session_state.planner if t["id"] != task["id"]]
            st.session_state.selected_task_id = None
        if st.button("Fechar"):
            st.session_state.selected_task_id = None

# ============================
# PAGE: PERFORMANCE
# ============================
def page_performance(ctx):
    st.subheader("📊 Performance")

    if st.session_state.plan != "Pro":
        st.warning("Disponível apenas no plano Pro.")
        return

    done = [t for t in st.session_state.planner if t["status"] == "done"]
    if not done:
        st.info("Nenhum post concluído ainda.")
        return

    avg_score = mean([t["score"] for t in done])
    times = [(int(t["hora"][:2])*60 + int(t["hora"][3:])) for t in done]
    avg_min = int(mean(times))
    hr, mn = avg_min//60, avg_min%60
    rec = f"{hr:02d}:{mn:02d}"

    c1,c2,c3 = st.columns(3)
    c1.metric("Concluídos", len(done))
    c2.metric("Score médio", f"{avg_score:.2f}")
    c3.metric("Hora recomendada", rec)

    st.write("### Últimos concluídos")
    for t in sorted(done, key=lambda x: (x["dia"],x["hora"]), reverse=True):
        st.write(f"- {t['dia']} {t['hora']} — {t['titulo']} · Score {t['score']}")

# ============================
# MAIN
# ============================
def main():
    ctx = sidebar()
    st.title("ContentForge v9.5 🍏")

    tab1,tab2,tab3 = st.tabs(["Gerar","Planner","Performance"])

    with tab1: page_generate(ctx)
    with tab2: page_planner(ctx)
    with tab3: page_performance(ctx)

main()
