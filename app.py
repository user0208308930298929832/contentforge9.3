import json
from datetime import datetime, date, timedelta
from statistics import mean

import streamlit as st
from openai import OpenAI

# ---------- CONFIG BÁSICA ----------
st.set_page_config(
    page_title="ContentForge v9.3",
    page_icon="🍏",
    layout="wide",
)

# ---------- CLIENTE OPENAI ----------
# Usa a OPENAI_API_KEY definida nas variáveis de ambiente / st.secrets
client = OpenAI()


# ---------- STATE INIT ----------
def init_state():
    if "plan" not in st.session_state:
        st.session_state.plan = "Starter"

    if "gens_used_date" not in st.session_state:
        st.session_state.gens_used_date = date.today().isoformat()

    if "gens_used_today" not in st.session_state:
        st.session_state.gens_used_today = 0

    if "tasks" not in st.session_state:
        st.session_state.tasks = []

    if "next_task_id" not in st.session_state:
        st.session_state.next_task_id = 1

    if "planner_anchor" not in st.session_state:
        st.session_state.planner_anchor = date.today()

    if "selected_task_id" not in st.session_state:
        st.session_state.selected_task_id = None

    if "active_page" not in st.session_state:
        st.session_state.active_page = "gerar"


init_state()


# ---------- HELPERS GERAIS ----------
def reset_daily_generations_if_needed():
    today_str = date.today().isoformat()
    if st.session_state.gens_used_date != today_str:
        st.session_state.gens_used_date = today_str
        st.session_state.gens_used_today = 0


def get_daily_limit(plan: str) -> int:
    return 5 if plan == "Starter" else 9999


def add_emoji_to_title(title: str, tema: str) -> str:
    """Garante 1 emoji no início do título, em sintonia com o tema."""
    # Se já tiver emoji nos primeiros caracteres, não mexe
    if any(ch in title[:4] for ch in "✨💫🔥🍂🌟💄💅💎💸🎁🏷️"):
        return title

    lower = (title + " " + tema).lower()
    if any(x in lower for x in ["desconto", "%", "promo", "oferta"]):
        emoji = "💸"
    elif any(x in lower for x in ["outono", "outono", "fall"]):
        emoji = "🍂"
    elif any(x in lower for x in ["luxo", "premium", "exclusivo"]):
        emoji = "💎"
    elif any(x in lower for x in ["novo", "lançamento", "lancamento"]):
        emoji = "✨"
    else:
        emoji = "🌟"

    return f"{emoji} {title.strip()}"


def simple_analysis(caption: str, platform: str) -> dict:
    """Cria uma análise simples mas consistente da legenda."""
    length = len(caption)

    # Clareza
    if length < 200:
        clareza = 8.0
    elif length < 400:
        clareza = 7.5
    else:
        clareza = 7.0

    # Emojis e engajamento
    emoji_count = sum(ch in caption for ch in "✨💫🔥🍂🌟💄💅💎💸🎁🏷️😍❤️💖💥😮😁🤩🎉🎊")
    engaj = 6.0 + min(emoji_count * 0.3, 3.0)

    # Conversão
    conv = 6.5
    gatilhos = ["10%", "desconto", "% off", "link na bio", "visita o site", "shop"]
    if any(g.lower() in caption.lower() for g in gatilhos):
        conv += 1.5
    if "até domingo" in caption.lower():
        conv += 0.5

    # Ajuste por plataforma
    if platform.lower() == "tiktok":
        engaj += 0.4
    else:
        conv += 0.3

    clareza = round(min(clareza, 10), 1)
    engaj = round(min(engaj, 10), 1)
    conv = round(min(conv, 10), 1)
    score = round(mean([clareza, engaj, conv]), 1)

    return {
        "clareza": clareza,
        "engaj": engaj,
        "conv": conv,
        "score": score,
    }


def format_time_str(time_str: str) -> str:
    """HH:MM -> HH:MM (garante formato correcto)."""
    try:
        return datetime.strptime(time_str, "%H:%M").strftime("%H:%M")
    except Exception:
        return "18:00"


def parse_time_to_minutes(time_str: str) -> int:
    try:
        t = datetime.strptime(time_str, "%H:%M")
        return t.hour * 60 + t.minute
    except Exception:
        return 18 * 60


def minutes_to_time_str(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


# ---------- GERAÇÃO COM OPENAI ----------
def generate_variations(
    marca: str,
    nicho: str,
    tom: str,
    modo_copy: str,
    plataforma: str,
    objetivo: str,
    extra: str,
):
    prompt_system = (
        "És um copywriter de social media de alto nível. "
        "Responde SEMPRE em JSON válido, no seguinte formato:\n\n"
        "{\n"
        '  "variations": [\n'
        "    {\n"
        '      "title": "string",\n'
        '      "caption": "string",\n'
        '      "hashtags": ["#tag1", "#tag2", "..."]\n'
        "    }, ...\n"
        "  ]\n"
        "}\n\n"
        "Titulos curtos. Legendas em PT-PT, com emojis naturais. "
        "Hashtags em minúsculas, sem acentos."
    )

    user_prompt = f"""
Marca: {marca}
Nicho: {nicho}
Tom de voz: {tom}
Modo de copy: {modo_copy}
Plataforma: {plataforma}

O que quero comunicar hoje:
{objetivo}

Informação extra:
{extra}

Gera exatamente 3 variações diferentes, todas focadas em venda suave,
com CTA claro para visitar site/perfil/comprar.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.9,
            max_tokens=900,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = response.choices[0].message.content
        data = json.loads(content)

        variations = data.get("variations", [])
        cleaned = []
        for var in variations[:3]:
            title = var.get("title", "").strip()
            caption = var.get("caption", "").strip()
            hashtags = var.get("hashtags", [])
            if isinstance(hashtags, str):
                hashtags = hashtags.split()

            cleaned.append(
                {
                    "title": title,
                    "caption": caption,
                    "hashtags": hashtags,
                }
            )
        return cleaned

    except Exception as e:
        st.error("❌ Não consegui interpretar a resposta da API. Tenta novamente.")
        st.write(e)
        return []


# ---------- SIDEBAR ----------
def sidebar():
    st.sidebar.markdown("## Plano e perfil")

    plan = st.sidebar.selectbox("Plano", ["Starter", "Pro"], key="plan")

    reset_daily_generations_if_needed()
    limit = get_daily_limit(plan)
    st.sidebar.markdown(
        f"**Gerações usadas hoje:** {st.session_state.gens_used_today}/{limit}"
    )

    st.sidebar.markdown("---")

    marca = st.sidebar.text_input("Marca", value="Loukisses")
    nicho = st.sidebar.text_input("Nicho/tema", value="Moda feminina")
    tom = st.sidebar.selectbox("Tom de voz", ["premium", "emocional", "profissional"])
    modo_copy = st.sidebar.selectbox(
        "Modo de copy", ["Venda", "Storytelling", "Educacional"]
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Métricas da conta (simuladas)**")

    seguidores = st.sidebar.number_input("Seguidores", min_value=0, value=1200, step=50)
    engaj_percent = st.sidebar.number_input(
        "Engaj. %", min_value=0.0, value=3.4, step=0.1
    )
    alcance_medio = st.sidebar.number_input(
        "Alcance médio", min_value=0, value=1400, step=50
    )

    return {
        "plan": plan,
        "marca": marca,
        "nicho": nicho,
        "tom": tom,
        "modo_copy": modo_copy,
        "seguidores": seguidores,
        "engaj_percent": engaj_percent,
        "alcance_medio": alcance_medio,
    }


# ---------- NAV ----------
def nav():
    page = st.radio(
        "",
        ["⚡ Gerar", "📅 Planner", "📊 Performance"],
        horizontal=True,
        index=["gerar", "planner", "performance"].index(st.session_state.active_page),
        label_visibility="collapsed",
    )
    mapping = {"⚡ Gerar": "gerar", "📅 Planner": "planner", "📊 Performance": "performance"}
    st.session_state.active_page = mapping[page]


# ---------- PÁGINA GERAR ----------
def page_gerar(ctx):
    st.markdown("### ⚡ Geração inteligente de conteúdo")

    plataforma = st.selectbox("Plataforma", ["Instagram", "Tiktok"])
    objetivo = st.text_input("O que queres comunicar hoje?")
    extra = st.text_area("Informação extra (opcional)")

    plan = ctx["plan"]
    limit = get_daily_limit(plan)
    btn_disabled = st.session_state.gens_used_today >= limit

    if btn_disabled:
        st.warning("Limite diário de gerações atingido para este plano.")
    gerar = st.button("⚡ Gerar agora", disabled=btn_disabled)

    results = []

    if gerar:
        with st.spinner("A pensar na melhor legenda para ti..."):
            variations = generate_variations(
                ctx["marca"],
                ctx["nicho"],
                ctx["tom"],
                ctx["modo_copy"],
                plataforma,
                objetivo,
                extra,
            )

        if variations:
            st.session_state.gens_used_today += 1

            # Análise + emojis
            for var in variations:
                title_raw = var["title"] or "Legenda"
                title = add_emoji_to_title(title_raw, ctx["nicho"])
                caption = var["caption"]
                hashtags = var["hashtags"]

                analysis = simple_analysis(caption, plataforma)
                results.append(
                    {
                        "title": title,
                        "caption": caption,
                        "hashtags": hashtags,
                        "analysis": analysis,
                    }
                )

    if results:
        st.success("✅ Conteúdo gerado com sucesso!")

        # Escolher recomendação Pro
        best_idx = max(range(len(results)), key=lambda i: results[i]["analysis"]["score"])

        cols = st.columns(3)
        for i, (col, res) in enumerate(zip(cols, results)):
            with col:
                is_best = i == best_idx and ctx["plan"] == "Pro"

                if is_best:
                    st.markdown("🟡 **Nossa recomendação**")

                st.markdown(f"**{res['title']}**")
                st.write(res["caption"])

                if res["hashtags"]:
                    st.markdown("**Hashtags sugeridas:**")
                    st.write(" ".join(res["hashtags"]))

                a = res["analysis"]
                if ctx["plan"] == "Pro":
                    st.markdown(
                        f"**Análise automática (Pro):** 🧠 Score {a['score']}/10 · 💬 Engaj. {a['engaj']}/10 · 💰 Conv. {a['conv']}/10"
                    )
                else:
                    st.markdown(
                        "**Análise automática (Pro):** 🔒 Pré-visualização — disponível no plano Pro."
                    )

                st.markdown("---")
                # Inputs para planner
                dia = st.date_input(
                    "Dia",
                    value=date.today(),
                    key=f"dia_{i}",
                )
                hora = st.time_input(
                    "Hora",
                    value=datetime.strptime("18:00", "%H:%M").time(),
                    key=f"hora_{i}",
                )

                if st.button("➕ Adicionar ao planner", key=f"add_planner_{i}"):
                    task = {
                        "id": st.session_state.next_task_id,
                        "date": dia,
                        "time": hora.strftime("%H:%M"),
                        "platform": plataforma,
                        "title": res["title"],
                        "caption": res["caption"],
                        "hashtags": res["hashtags"],
                        "score": res["analysis"]["score"],
                        "status": "planned",
                        "created_at": datetime.now(),
                    }
                    st.session_state.next_task_id += 1
                    st.session_state.tasks.append(task)
                    st.success("Post adicionado ao planner!")

    elif gerar and not results:
        st.info("Tenta gerar novamente. Pode ter havido um erro de resposta da API.")


# ---------- PÁGINA PLANNER ----------
def get_week_range(anchor: date):
    # devolve segunda a domingo da semana da âncora
    weekday = anchor.weekday()  # 0 = Monday
    monday = anchor - timedelta(days=weekday)
    days = [monday + timedelta(days=i) for i in range(7)]
    return days


def page_planner(ctx):
    st.markdown("### 📅 Planner semanal")

    col_prev, col_anchor, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("« Semana anterior"):
            st.session_state.planner_anchor -= timedelta(days=7)
    with col_anchor:
        st.date_input(
            "Semana de referência",
            value=st.session_state.planner_anchor,
            key="planner_anchor_input",
        )
        # Se o user mexer manualmente, actualizar
        anchor_input = st.session_state.planner_anchor_input
        if anchor_input != st.session_state.planner_anchor:
            st.session_state.planner_anchor = anchor_input
    with col_next:
        if st.button("Semana seguinte »"):
            st.session_state.planner_anchor += timedelta(days=7)

    days = get_week_range(st.session_state.planner_anchor)
    st.markdown(
        f"Semana de {days[0].strftime('%d/%m')} a {days[-1].strftime('%d/%m')}"
    )

    # Grid semanal
    cols = st.columns(7)
    for day, col in zip(days, cols):
        with col:
            st.markdown(f"**{day.strftime('%a')}**")
            st.caption(day.strftime("%d/%m"))

            # tarefas desse dia
            day_tasks = [
                t for t in st.session_state.tasks if t["date"] == day
            ]
            day_tasks.sort(key=lambda t: t["time"])

            if not day_tasks:
                st.caption("Sem tarefas.")
            else:
                for task in day_tasks:
                    is_done = task["status"] == "done"
                    bg_color = "#10451D" if is_done else "#111827"
                    text_color = "#F9FAFB"

                    st.markdown(
                        f"""
<div style="background:{bg_color}; color:{text_color}; padding:8px 10px; border-radius:12px; margin-bottom:8px; font-size:0.85rem;">
  <div style="font-size:0.75rem; opacity:0.8;">{task['time']} · {task['platform'].capitalize()}</div>
  <div style="font-weight:600; margin:4px 0;">{task['title']}</div>
  <div style="font-size:0.75rem; opacity:0.8;">Score: {task['score']}/10</div>
  <div style="font-size:0.75rem; margin-top:4px;">Estado: {"✅ Concluído" if is_done else "⏳ Pendente"}</div>
</div>
""",
                        unsafe_allow_html=True,
                    )

                    btn_cols = st.columns(2)
                    with btn_cols[0]:
                        if st.button(
                            "👁 Ver detalhes",
                            key=f"detail_{task['id']}",
                        ):
                            st.session_state.selected_task_id = task["id"]
                    with btn_cols[1]:
                        if st.button(
                            "✅ Concluir",
                            key=f"done_{task['id']}",
                            disabled=is_done,
                        ):
                            task["status"] = "done"
                            st.session_state.selected_task_id = task["id"]

    # Detalhes da tarefa seleccionada
    if st.session_state.selected_task_id is not None:
        st.markdown("---")
        task = next(
            (t for t in st.session_state.tasks if t["id"] == st.session_state.selected_task_id),
            None,
        )
        if task:
            st.markdown("### 🔍 Detalhes da tarefa selecionada")
            st.markdown(f"**{task['title']}**")
            st.caption(
                f"{task['date'].strftime('%d/%m/%Y')} · {task['time']} · {task['platform'].capitalize()}"
            )
            st.write(task["caption"])

            if task["hashtags"]:
                st.markdown("**Hashtags:**")
                st.write(" ".join(task["hashtags"]))

            st.markdown("#### Estado atual:")
            if task["status"] == "done":
                st.success("Concluído ✅")
            else:
                st.info("Pendente ⏳")

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button(
                    "✅ Marcar como concluído",
                    key=f"detail_done_{task['id']}",
                    disabled=task["status"] == "done",
                ):
                    task["status"] = "done"
            with c2:
                if st.button("🗑 Remover do planner", key=f"remove_{task['id']}"):
                    st.session_state.tasks = [
                        t for t in st.session_state.tasks if t["id"] != task["id"]
                    ]
                    st.session_state.selected_task_id = None
            with c3:
                if st.button("❌ Fechar detalhes", key=f"close_detail_{task['id']}"):
                    st.session_state.selected_task_id = None


# ---------- PÁGINA PERFORMANCE ----------
def page_performance(ctx):
    st.markdown("### 📊 Performance (v9.3)")

    if ctx["plan"] != "Pro":
        st.warning(
            "🔒 Disponível no plano Pro. Desbloqueia métricas e previsões avançadas."
        )
        return

    completed = [t for t in st.session_state.tasks if t["status"] == "done"]

    posts_concluidos = len(completed)
    if completed:
        score_medio = round(mean(t["score"] for t in completed), 2)
        # Hora recomendada: média das horas concluídas
        minutos = [parse_time_to_minutes(t["time"]) for t in completed]
        media_min = int(mean(minutos))
        hora_rec = minutes_to_time_str(media_min)
    else:
        score_medio = 0.0
        hora_rec = "--:--"

    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("Posts concluídos", posts_concluidos)
    with k2:
        st.metric("Score médio da IA", score_medio)
    with k3:
        st.metric("Hora recomendada", hora_rec)

    st.caption("🧠 Precisão da IA aumenta com o nº de postagens concluídas.")

    st.markdown("---")
    st.markdown("#### Últimos posts concluídos")

    if not completed:
        st.write("Ainda não tens posts concluídos no planner.")
        return

    # ordenar do mais recente para o mais antigo
    completed_sorted = sorted(
        completed, key=lambda t: t["date"].isoformat() + t["time"], reverse=True
    )

    for t in completed_sorted:
        st.markdown(
            f"- **{t['date'].strftime('%d/%m %H:%M')} · {t['platform'].capitalize()}** — "
            f"{t['title']}  · Score: {t['score']}/10 · Estado: ✅ Concluído"
        )


# ---------- MAIN ----------
def main():
    ctx = sidebar()

    st.markdown(
        f"## ContentForge v9.3 🍏\n"
        "Gera conteúdo inteligente, organiza num planner semanal e, no plano Pro, acompanha a força de cada publicação."
    )

    nav()

    if st.session_state.active_page == "gerar":
        page_gerar(ctx)
    elif st.session_state.active_page == "planner":
        page_planner(ctx)
    elif st.session_state.active_page == "performance":
        page_performance(ctx)


if __name__ == "__main__":
    main()
